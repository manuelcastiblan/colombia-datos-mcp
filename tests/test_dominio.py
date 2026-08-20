"""Pruebas del adaptador y las herramientas, con la red simulada."""

import pytest

from colombia_datos_mcp.adapters import socrata
from colombia_datos_mcp.core.cache import Cache
from colombia_datos_mcp.core.errors import ErrorNoEncontrado, ErrorValidacion
from colombia_datos_mcp.domain import catalogo, geo, secop
from colombia_datos_mcp.registry import datasets as reg

from .fixtures import ADICIONES, CATALOGO, CENTROS_POBLADOS, CONTRATOS, MUNICIPIOS


class RedFalsa:
    """Sustituye a ClienteHTTP. Registra las llamadas para poder auditarlas."""

    def __init__(self, respuestas):
        self.respuestas = respuestas
        self.llamadas = []

    async def get_json(self, url, params=None, headers=None):
        self.llamadas.append((url, dict(params or {})))
        for patron, valor in self.respuestas.items():
            if patron in url:
                return valor(params or {}) if callable(valor) else valor
        raise AssertionError(f"URL no simulada: {url}")


@pytest.fixture(autouse=True)
def cache_limpia(monkeypatch, tmp_path):
    """Cada prueba arranca con caché vacía y aislada del disco real."""
    import colombia_datos_mcp.core.cache as mod
    fresca = Cache(dir_disco=tmp_path / "cache")
    monkeypatch.setattr(mod, "cache", fresca)
    monkeypatch.setattr(socrata, "cache", fresca)
    return fresca


def _instala(monkeypatch, respuestas):
    red = RedFalsa(respuestas)
    monkeypatch.setattr(socrata, "_http", red)
    return red


# Dominios categóricos tal como los devuelve la fuente: CON acentos. Es el
# hecho que rompía los filtros antes de resolver contra los valores canónicos.
DOMINIOS = {
    "departamento": ["Antioquia", "Atlántico", "Distrito Capital de Bogotá", "Chocó"],
    "modalidad_de_contratacion": ["Contratación directa", "Mínima cuantía"],
}


def _filas_de_contratos(params):
    seleccionar = params.get("$select", "")
    if seleccionar.startswith("distinct "):
        campo = seleccionar.split(" ", 1)[1].strip()
        return [{campo: v} for v in DOMINIOS.get(campo, [])]
    if "count(*)" in seleccionar and "nombre_entidad" not in seleccionar:
        return [{"total": "3"}]
    if "$group" in params or "nombre_entidad," in seleccionar:
        return [{"nombre_entidad": "INSTITUTO NACIONAL DE VIAS", "nit_entidad": "800215807",
                 "total": "3", "valor": "37500000", "contratos": "3"}]
    return CONTRATOS


# --------------------------------------------------------------- catálogo --
async def test_buscar_datasets_inyecta_search_context(monkeypatch):
    red = _instala(monkeypatch, {"api/catalog/v1": CATALOGO})
    salida = await catalogo.buscar_datasets(consulta="SECOP")
    _, params = red.llamadas[0]
    assert params["search_context"] == "www.datos.gov.co"  # sin esto, filtros dan 0
    assert params["only"] == "dataset"
    assert params["provenance"] == "official"
    assert "jbjy-vk9h" in salida["texto"]


async def test_buscar_datasets_traduce_la_sigla_a_atribucion_exacta(monkeypatch):
    red = _instala(monkeypatch, {"api/catalog/v1": CATALOGO})
    await catalogo.buscar_datasets(entidad="DANE")
    _, params = red.llamadas[0]
    assert params["attribution"].startswith("Departamento Administrativo Nacional")


async def test_describir_dataset_expone_nombre_legible(monkeypatch):
    _instala(monkeypatch, {"api/catalog/v1": CATALOGO})
    salida = await catalogo.describir_dataset("jbjy-vk9h")
    # El slug truncado sin su nombre legible es inutilizable para el modelo.
    assert "valor_pendiente_de" in salida["texto"]
    assert "Valor Pendiente de Amortizacion" in salida["texto"]


async def test_describir_dataset_inexistente(monkeypatch):
    _instala(monkeypatch, {"api/catalog/v1": {"resultSetSize": 0, "results": []}})
    with pytest.raises(ErrorNoEncontrado):
        await catalogo.describir_dataset("xxxx-yyyy")


async def test_allowlist_rechaza_columna_inventada(monkeypatch):
    _instala(monkeypatch, {"api/catalog/v1": CATALOGO})
    with pytest.raises(ErrorValidacion) as exc:
        await catalogo.consultar("jbjy-vk9h", donde="columna_que_no_existe = '1'")
    assert "columna_que_no_existe" in str(exc.value)
    assert "nombre_entidad" in exc.value.sugerencia  # lista los campos válidos


async def test_conteo_no_descarga_filas(monkeypatch):
    red = _instala(monkeypatch, {
        "api/catalog/v1": CATALOGO,
        "/resource/jbjy-vk9h.json": _filas_de_contratos,
    })
    salida = await catalogo.consultar("jbjy-vk9h", detalle="conteo")
    assert "3" in salida["texto"]
    consultas = [p for u, p in red.llamadas if "resource" in u]
    assert all("count(*)" in p.get("$select", "") for p in consultas)


# ------------------------------------------------------------------ SECOP --
async def test_filtro_categorico_resuelve_contra_el_valor_canonico(monkeypatch):
    red = _instala(monkeypatch, {"/resource/jbjy-vk9h.json": _filas_de_contratos})
    await secop.buscar_contratos(departamento="Antioquía")
    donde = [p["$where"] for _, p in red.llamadas if "$where" in p][0]
    # Se compara por igualdad contra el literal exacto, no con un `like` sobre
    # el término plegado: eso devolvía cero para todo valor con tilde.
    assert donde == "departamento in ('Antioquia')"


async def test_filtro_categorico_alcanza_los_valores_con_tilde(monkeypatch):
    red = _instala(monkeypatch, {"/resource/jbjy-vk9h.json": _filas_de_contratos})
    await secop.buscar_contratos(departamento="atlantico")
    donde = [p["$where"] for _, p in red.llamadas if "$where" in p][0]
    assert donde == "departamento in ('Atlántico')"


async def test_termino_categorico_inexistente_no_consulta_y_lo_dice(monkeypatch):
    red = _instala(monkeypatch, {"/resource/jbjy-vk9h.json": _filas_de_contratos})
    salida = await secop.buscar_contratos(departamento="Narnia")
    # Cero honesto: se dice que el término no existe en la fuente…
    assert "no corresponde a ningún valor" in salida["texto"]
    assert "no es un fallo de la fuente" in salida["texto"].lower()
    # …y no se gasta una consulta de datos que devolvería cero igual.
    assert not [p for _, p in red.llamadas if "$where" in p]


async def test_entidad_es_texto_libre_y_tolera_la_tilde(monkeypatch):
    red = _instala(monkeypatch, {"/resource/jbjy-vk9h.json": _filas_de_contratos})
    await secop.buscar_contratos(entidad="gobernacion")
    donde = [p["$where"] for _, p in red.llamadas if "$where" in p][0]
    # El dominio es abierto: no se puede enumerar, así que el plegado de los
    # acentos se hace en el servidor sobre la columna.
    assert "replace(" in donde and "'Ó', 'O'" in donde
    assert donde.endswith("like '%GOBERNACION%'")


async def test_buscar_contratos_escapa_comillas(monkeypatch):
    red = _instala(monkeypatch, {"/resource/jbjy-vk9h.json": _filas_de_contratos})
    await secop.buscar_contratos(entidad="O'Brien")
    donde = [p["$where"] for _, p in red.llamadas if "$where" in p][0]
    assert "O''BRIEN" in donde  # comilla simple escapada, no inyectable


async def test_buscar_contratos_limpia_el_nit(monkeypatch):
    red = _instala(monkeypatch, {"/resource/jbjy-vk9h.json": _filas_de_contratos})
    await secop.buscar_contratos(nit_entidad="800.215.807-1")
    donde = [p["$where"] for _, p in red.llamadas if "$where" in p][0]
    assert "nit_entidad = '8002158071'" in donde


async def test_resumen_formatea_moneda_y_recorta(monkeypatch):
    _instala(monkeypatch, {"/resource/jbjy-vk9h.json": _filas_de_contratos})
    salida = await secop.buscar_contratos(departamento="Antioquia")
    assert "$12.500.000" in salida["texto"]
    assert "2025-05-02" in salida["texto"]
    assert "unidad de análisis" in salida["texto"].lower()


async def test_detalle_contrato_compone_y_conserva_url_publica(monkeypatch):
    _instala(monkeypatch, {
        "/resource/jbjy-vk9h.json": lambda p: CONTRATOS,
        "/resource/cb9c-h8sn.json": lambda p: ADICIONES,
    })
    salida = await secop.detalle_contrato("CO1.PCCNTR.1234567")
    assert "Modificaciones registradas (1)" in salida["texto"]
    assert "community.secop.gov.co" in salida["texto"]   # verificación humana
    assert "Prórroga" in salida["texto"]


async def test_detalle_contrato_inexistente_no_finge(monkeypatch):
    _instala(monkeypatch, {
        "/resource/jbjy-vk9h.json": lambda p: [],
        "/resource/cb9c-h8sn.json": lambda p: [],
    })
    with pytest.raises(ErrorNoEncontrado):
        await secop.detalle_contrato("CO1.PCCNTR.0")


async def test_perfil_proveedor_sin_contratos_distingue_de_fallo(monkeypatch):
    _instala(monkeypatch, {"/resource/jbjy-vk9h.json": lambda p: [{"total": "0"}]
                           if "count(*)" in p.get("$select", "") else []})
    salida = await secop.perfil_proveedor("900999999")
    texto = " ".join(salida["estructurado"]["_meta"].get("advertencias", []))
    assert "no es un fallo de la fuente" in texto.lower()


async def test_perfil_proveedor_exige_digitos(monkeypatch):
    _instala(monkeypatch, {})
    with pytest.raises(ErrorValidacion):
        await secop.perfil_proveedor("no-es-un-nit")


async def test_agregar_rechaza_dimension_desconocida(monkeypatch):
    _instala(monkeypatch, {})
    with pytest.raises(ErrorValidacion):
        await secop.agregar(agrupar_por="color_favorito")


async def test_agregar_devuelve_grupos_no_filas(monkeypatch):
    _instala(monkeypatch, {"/resource/jbjy-vk9h.json": _filas_de_contratos})
    salida = await secop.agregar(agrupar_por="entidad", desde="2025-01-01")
    assert salida["estructurado"]["_meta"]["orden"] == "valor DESC"
    assert "deflactar" in " ".join(salida["estructurado"]["_meta"]["advertencias"])


# -------------------------------------------------------------------- geo --
async def test_divipola_normaliza_coordenadas_incluido_medellin(monkeypatch):
    _instala(monkeypatch, {"/resource/gdxc-w37w.json":
                           lambda p: [{"total": "2"}] if "count(*)" in p.get("$select", "")
                           else MUNICIPIOS})
    salida = await geo.divipola(consulta="Medellin")
    fila = salida["estructurado"]["datos"][0]
    assert fila["lon"] == pytest.approx(-75.581775)
    assert fila["cod_mpio"] == "05001"  # texto, con cero a la izquierda


async def test_divipola_centros_poblados(monkeypatch):
    _instala(monkeypatch, {"/resource/xaxy-8nri.json":
                           lambda p: [{"total": "3"}] if "count(*)" in p.get("$select", "")
                           else CENTROS_POBLADOS})
    salida = await geo.divipola(nivel="centro_poblado", consulta="santa elena")
    medellin = [f for f in salida["estructurado"]["datos"] if f["cod_cp"] == "05001000"][0]
    assert medellin["lon"] == pytest.approx(-75.581775)  # el registro envenenado, ya limpio


async def test_divipola_nivel_invalido(monkeypatch):
    _instala(monkeypatch, {})
    with pytest.raises(ErrorValidacion):
        await geo.divipola(nivel="galaxia")


# ------------------------------------------------------------------ caché --
async def test_cache_deduplica_peticiones_identicas(monkeypatch):
    red = _instala(monkeypatch, {"/resource/jbjy-vk9h.json": _filas_de_contratos})
    await socrata.consultar("jbjy-vk9h", donde="departamento = 'X'")
    await socrata.consultar("jbjy-vk9h", donde="departamento = 'X'")
    assert len(red.llamadas) == 1  # la segunda salió de caché


async def test_paginacion_fuerza_orden_estable(monkeypatch):
    red = _instala(monkeypatch, {"/resource/jbjy-vk9h.json": _filas_de_contratos})
    await socrata.consultar("jbjy-vk9h", offset=100)
    _, params = red.llamadas[0]
    assert params["$order"] == ":id"  # sin esto se pierden o duplican filas


# ------------------------------------------- regresiones de agregación ----
async def test_agregar_ordena_por_el_alias_real_de_la_metrica(monkeypatch):
    red = _instala(monkeypatch, {
        "api/catalog/v1": CATALOGO,
        "/resource/jbjy-vk9h.json": _filas_de_contratos,
    })
    await catalogo.agregar("jbjy-vk9h", "nombre_entidad",
                           metricas="sum(valor_del_contrato) as valor")
    orden = [p["$order"] for _, p in red.llamadas if "$order" in p][0]
    # Estaba cableado a "total DESC": con cualquier métrica que no se llamara
    # `total`, Socrata respondía 400 «No such column: total».
    assert orden == "valor DESC"


async def test_agregar_por_defecto_sigue_ordenando_por_total(monkeypatch):
    red = _instala(monkeypatch, {
        "api/catalog/v1": CATALOGO,
        "/resource/jbjy-vk9h.json": _filas_de_contratos,
    })
    await catalogo.agregar("jbjy-vk9h", "nombre_entidad")
    assert [p["$order"] for _, p in red.llamadas if "$order" in p][0] == "total DESC"


async def test_el_conteo_no_se_formatea_como_pesos(monkeypatch):
    _instala(monkeypatch, {
        "api/catalog/v1": CATALOGO,
        "/resource/jbjy-vk9h.json": _filas_de_contratos,
    })
    salida = await catalogo.agregar("jbjy-vk9h", "nombre_entidad")
    # `count(*) as total` es un conteo. Mostrarlo como "$3" convertía
    # "3 contratos" en "3 pesos".
    assert "| $3 |" not in salida["texto"]   # el conteo, como número
    assert "| 3 |" in salida["texto"]
    assert "$37.500.000" in salida["texto"]   # el importe, como moneda


async def test_allowlist_admite_palabras_reservadas_de_soql(monkeypatch):
    _instala(monkeypatch, {
        "api/catalog/v1": CATALOGO,
        "/resource/jbjy-vk9h.json": _filas_de_contratos,
    })
    # `distinct` no es una columna: rechazarlo era un [VALIDACION] falso.
    salida = await catalogo.consultar("jbjy-vk9h", seleccionar="distinct nombre_entidad")
    assert salida["texto"]


# ----------------------------------------------- validación de entradas ---
async def test_valor_min_acepta_separadores_colombianos(monkeypatch):
    red = _instala(monkeypatch, {"/resource/jbjy-vk9h.json": _filas_de_contratos})
    await secop.buscar_contratos(valor_min="1.000.000")
    donde = [p["$where"] for _, p in red.llamadas if "$where" in p][0]
    assert "valor_del_contrato >= 1000000.0" in donde


async def test_valor_min_no_numerico_da_error_tipado(monkeypatch):
    _instala(monkeypatch, {"/resource/jbjy-vk9h.json": _filas_de_contratos})
    # Antes escapaba un ValueError crudo, sin código ni sugerencia accionable.
    with pytest.raises(ErrorValidacion) as exc:
        await secop.buscar_contratos(valor_min="mucho dinero")
    assert exc.value.sugerencia


# ---------------------------------------------------------- paginación ---
async def test_la_primera_pagina_ya_lleva_orden_estable(monkeypatch):
    red = _instala(monkeypatch, {
        "api/catalog/v1": CATALOGO,
        "/resource/jbjy-vk9h.json": _filas_de_contratos,
    })
    await catalogo.consultar("jbjy-vk9h")
    datos = [p for u, p in red.llamadas if "resource" in u and "count(*)" not in p.get("$select", "")]
    # Sin orden en la página 1 y `:id` en la 2 se pierden y duplican filas al
    # paginar, que es justo lo que el orden forzado pretendía evitar.
    assert all(p.get("$order") for p in datos)


async def test_el_conteo_no_lleva_orden(monkeypatch):
    """`count(*)` colapsa filas: Socrata rechaza `$order=:id` sobre un agregado
    con «Column ':id' is not in group by». Forzar el orden estable sin excluir
    las agregadas tumbaba TODAS las herramientas, porque todas cuentan primero.
    """
    red = _instala(monkeypatch, {
        "api/catalog/v1": CATALOGO,
        "/resource/jbjy-vk9h.json": _filas_de_contratos,
    })
    await catalogo.consultar("jbjy-vk9h", detalle="conteo")
    agregadas = [p for _, p in red.llamadas if "count(*)" in p.get("$select", "")]
    assert agregadas and all("$order" not in p for p in agregadas)


async def test_distinct_tampoco_lleva_orden(monkeypatch):
    red = _instala(monkeypatch, {
        "api/catalog/v1": CATALOGO,
        "/resource/jbjy-vk9h.json": _filas_de_contratos,
    })
    await catalogo.consultar("jbjy-vk9h", seleccionar="distinct nombre_entidad")
    dist = [p for _, p in red.llamadas if p.get("$select", "").startswith("distinct")]
    assert dist and all("$order" not in p for p in dist)


async def test_un_alias_caduco_reintenta_con_lo_que_escribio_el_usuario(monkeypatch):
    """Un alias curado que ya no casa nada no debe convertirse en cero filas."""
    monkeypatch.setitem(reg.ALIAS_ENTIDADES, "INVIAS", "NOMBRE QUE YA NO EXISTE")

    def respuesta(params):
        donde = params.get("$where", "")
        if "NOMBRE QUE YA NO EXISTE" in donde:
            return []                      # el alias caducó
        return [{"nombre_entidad": "INVIAS", "nit_entidad": "800215807", "total": "42"}]

    _instala(monkeypatch, {"/resource/jbjy-vk9h.json": respuesta})
    salida = await secop.resolver_entidad("invias")
    assert "INVIAS" in salida["texto"]
    assert "caduco" in salida["texto"]


async def test_el_resumen_conserva_una_columna_ausente_en_la_primera_fila(monkeypatch):
    """Regresión: el contrato de mayor valor podía no traer `fecha_de_firma`
    —los borradores no la tienen— y eso borraba la fecha de todas las demás."""
    def respuesta(params):
        if "count(*)" in params.get("$select", ""):
            return [{"total": "2"}]
        return [
            {"id_contrato": "CO1.PCCNTR.1", "nombre_entidad": "ANLA",
             "valor_del_contrato": "93192634", "estado_contrato": "Borrador"},
            {"id_contrato": "CO1.PCCNTR.2", "nombre_entidad": "MINMINAS",
             "valor_del_contrato": "81650000", "estado_contrato": "Modificado",
             "fecha_de_firma": "2026-01-10T00:00:00.000"},
        ]

    _instala(monkeypatch, {"/resource/jbjy-vk9h.json": respuesta})
    salida = await secop.buscar_contratos(documento_proveedor="1000000001")
    assert "fecha de firma" in salida["texto"]
    assert "2026-01-10" in salida["texto"]
    # Y el orden curado se conserva: la fecha no se va al final de la tabla.
    cabecera = salida["texto"].splitlines()[0]
    assert cabecera.index("fecha de firma") < cabecera.index("estado contrato")


# ------------------------------- honestidad del conteo de grupos (0.7.0) ----
async def test_agregar_no_toma_las_filas_devueltas_por_el_total(monkeypatch):
    """Regresión: `total_coincidencias` era `len(filas)`, así que una tabla
    recortada a 5 juraba «5 de 5» habiendo 2.881 grupos. El sobre existe
    justo para no mentir en eso."""
    def respuesta(params):
        if "$query" in params:
            assert "|>" in params["$query"]  # contar grupos exige anidar
            return [{"grupos": "2881"}]
        return [{"nombre_entidad": f"ENTIDAD {i}", "contratos": "10"} for i in range(5)]

    _instala(monkeypatch, {"api/catalog/v1": CATALOGO,
                           "/resource/jbjy-vk9h.json": respuesta})
    salida = await catalogo.agregar("jbjy-vk9h", "nombre_entidad",
                                    metricas="count(*) as contratos", limite=5)
    meta = salida["estructurado"]["_meta"]
    assert meta["total_coincidencias"] == 2881
    assert "5 de 2881" in " ".join(meta["advertencias"])


async def test_agregar_no_pregunta_el_total_si_ya_vio_todos_los_grupos(monkeypatch):
    """Si la fuente devuelve menos de lo pedido, no hay más: el total es
    exacto y gratis. Cobrar una petición extra por saberlo sería tonto."""
    def respuesta(params):
        assert "$query" not in params, "no hacía falta contar los grupos"
        return [{"nombre_entidad": "A", "contratos": "10"}]

    _instala(monkeypatch, {"api/catalog/v1": CATALOGO,
                           "/resource/jbjy-vk9h.json": respuesta})
    salida = await catalogo.agregar("jbjy-vk9h", "nombre_entidad",
                                    metricas="count(*) as contratos", limite=20)
    assert salida["estructurado"]["_meta"]["total_coincidencias"] == 1


async def test_agregar_declara_el_total_desconocido_en_vez_de_inventarlo(monkeypatch):
    """Si la fuente no admite anidar, el total se declara desconocido. Un
    total ignorado se puede avisar; uno inventado contamina lo que toque."""
    def respuesta(params):
        if "$query" in params:
            raise ErrorValidacion("esta fuente no admite el operador anidado")
        return [{"nombre_entidad": f"E{i}", "contratos": "1"} for i in range(3)]

    _instala(monkeypatch, {"api/catalog/v1": CATALOGO,
                           "/resource/jbjy-vk9h.json": respuesta})
    salida = await catalogo.agregar("jbjy-vk9h", "nombre_entidad",
                                    metricas="count(*) as contratos", limite=3)
    meta = salida["estructurado"]["_meta"]
    assert meta.get("total_coincidencias") is None
    assert "desconocido" in " ".join(meta["advertencias"]).lower()


async def test_luego_encadena_una_segunda_agregacion(monkeypatch):
    """`count(*)` con `having` cuenta DENTRO de cada grupo. Para contar los
    grupos que el `having` deja hace falta una segunda etapa."""
    def respuesta(params):
        q = params.get("$query", "")
        assert "|> SELECT" in q and "HAVING" in q
        # El orden va sobre el alias de la 2.ª etapa, no sobre el de la 1.ª.
        assert "ORDER BY personas DESC" in q
        return [{"personas": "130720", "contratos": "293546"}]

    _instala(monkeypatch, {"api/catalog/v1": CATALOGO,
                           "/resource/jbjy-vk9h.json": respuesta})
    salida = await catalogo.agregar(
        "jbjy-vk9h", "nombre_entidad", metricas="count(*) as n",
        teniendo="count(*) > 1", luego="count(*) as personas, sum(n) as contratos")
    assert salida["estructurado"]["datos"][0]["personas"] == "130.720"


# ----------------------- el validador ya no rechaza SoQL válido (0.8.0) ----
def test_campos_citados_no_confunde_funciones_con_columnas():
    """Se contrastaba contra una lista cableada de ~60 funciones y se tomaba
    por columna todo lo que faltara. `caseless_eq` y `date_diff_d` son SoQL
    válido en datos.gov.co y ninguna de las dos estaba en la lista: el
    validador fallaba CERRADO sobre consultas correctas."""
    from colombia_datos_mcp.domain.catalogo import _campos_citados
    assert _campos_citados("date_diff_d(fecha_de_firma, fecha_fin_liquidacion)") == {
        "fecha_de_firma", "fecha_fin_liquidacion"}
    assert _campos_citados("caseless_eq(sector, 'MINAS')") == {"sector"}


def test_campos_citados_no_toma_los_alias_por_columnas():
    """`nombre_entidad as entidad` se rechazaba porque `entidad` no existe en
    el esquema. Claro que no: es el alias que se está declarando."""
    from colombia_datos_mcp.domain.catalogo import _campos_citados
    assert _campos_citados("nombre_entidad as entidad") == {"nombre_entidad"}
    assert _campos_citados("count(*) as total") == set()
    assert _campos_citados("sum(valor_del_contrato) as valor, departamento") == {
        "valor_del_contrato", "departamento"}


def test_campos_citados_ignora_literales_y_palabras_sueltas():
    from colombia_datos_mcp.domain.catalogo import _campos_citados
    assert _campos_citados("estado_contrato in ('Borrador', 'Cancelado')") == {
        "estado_contrato"}
    assert _campos_citados("valor_del_contrato DESC") == {"valor_del_contrato"}
    assert _campos_citados("fecha_de_firma is not null") == {"fecha_de_firma"}


async def test_resolver_entidad_no_oculta_coincidencias_en_silencio(monkeypatch):
    """Ocultar filas aquí es lo más caro del servidor: es la herramienta de
    desambiguación, y creer que se vieron todas hace elegir mal el NIT y
    contaminar cada consulta posterior. Medido en vivo: 10 mostradas, 11 reales."""
    def respuesta(params):
        if "$query" in params:
            return [{"grupos": "11"}]
        return [{"nombre_entidad": f"MUNICIPIO DE SANTA {i}",
                 "nit_entidad": f"8000{i}", "total": "10"} for i in range(10)]

    _instala(monkeypatch, {"api/catalog/v1": CATALOGO,
                           "/resource/jbjy-vk9h.json": respuesta})
    salida = await secop.resolver_entidad("MUNICIPIO DE SANTA")
    meta = salida["estructurado"]["_meta"]
    assert meta["total_coincidencias"] == 11
    assert "10 de 11" in " ".join(meta["advertencias"])


async def test_contar_grupos_no_tumba_una_respuesta_que_ya_tiene_datos(monkeypatch):
    """El conteo de grupos es un extra sobre una respuesta ya construida. Solo
    se capturaban errores de validación, así que un timeout suyo cambiaba «un
    total equivocado» por «ninguna respuesta», que es peor."""
    from colombia_datos_mcp.core.errors import ErrorTimeout

    def respuesta(params):
        if "$query" in params:
            raise ErrorTimeout("la fuente tardó demasiado")
        return [{"nombre_entidad": f"E{i}", "contratos": "1"} for i in range(3)]

    _instala(monkeypatch, {"api/catalog/v1": CATALOGO,
                           "/resource/jbjy-vk9h.json": respuesta})
    salida = await catalogo.agregar("jbjy-vk9h", "nombre_entidad",
                                    metricas="count(*) as contratos", limite=3)
    meta = salida["estructurado"]["_meta"]
    assert meta.get("total_coincidencias") is None
    assert len(salida["estructurado"]["datos"]) == 3      # los datos sobreviven
    assert "desconocido" in " ".join(meta["advertencias"]).lower()


# ------------------------- periodos sin cerrar (0.12.0) --------------------
def test_cerrado_usa_el_calendario_no_una_lista_de_dias_plausibles():
    """La versión anterior daba por cerrado cualquier mes acabado en 28-31.
    Abril no tiene 31 días, y febrero cierra el 28 o el 29 según el año."""
    from colombia_datos_mcp.domain import periodos
    assert periodos.cerrado("2026-04-30", "mes") is True      # abril cierra el 30
    assert periodos.cerrado("2026-04-29", "mes") is False
    assert periodos.cerrado("2024-02-29", "mes") is True      # bisiesto
    assert periodos.cerrado("2026-02-28", "mes") is True
    assert periodos.cerrado("2026-12-31", "anio") is True
    assert periodos.cerrado("2026-07-31", "anio") is False    # julio no cierra el año
    assert periodos.cerrado("2026-07-15", "dia") is True      # un día siempre cierra


def test_incompleto_solo_marca_el_periodo_donde_cortan_los_datos():
    from colombia_datos_mcp.domain import periodos
    assert periodos.incompleto("2026", "2026-07-31", "anio") is True
    assert periodos.incompleto("2025", "2026-07-31", "anio") is False   # ya cerró
    assert periodos.incompleto("2026", "2026-12-31", "anio") is False   # cerró entero
    assert periodos.incompleto("", "2026-07-31", "anio") is False
    assert periodos.incompleto("2026", None, "anio") is False


def test_comparables_quita_el_ultimo_solo_si_no_cerro():
    from colombia_datos_mcp.domain import periodos
    serie = [{"periodo": "2024"}, {"periodo": "2025"}, {"periodo": "2026"}]
    assert len(periodos.comparables(serie, "2026-07-31", "anio")) == 2
    assert len(periodos.comparables(serie, "2026-12-31", "anio")) == 3
    assert len(periodos.comparables(serie, None, "anio")) == 3
    assert periodos.comparables([], "2026-07-31", "anio") == []
