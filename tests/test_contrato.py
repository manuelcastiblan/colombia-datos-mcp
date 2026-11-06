"""Suite de contrato contra la API VIVA. No corre con `pytest` a secas.

    pytest -m contrato

Su fallo no es un bug del servidor: es la señal de que el Estado cambió el
esquema, la convención de acentos o los identificadores. Por eso vive separada
de las pruebas con fixtures y corre en CI a diario.

Cada aserción de aquí corresponde a una suposición sobre la que está construido
el código. Si una deja de cumplirse, hay que cambiar el código, no la prueba.
"""

import pytest

from colombia_datos_mcp.adapters import socrata
from colombia_datos_mcp.core import privacidad, texto
from colombia_datos_mcp.domain import geo, secop
from colombia_datos_mcp.registry import datasets as reg

pytestmark = pytest.mark.contrato


# ------------------------------------------------- la premisa de acentos --
async def test_divipola_conserva_los_acentos():
    """Sobre esto descansa `core.texto`: si la fuente dejara de acentuar, la
    resolución contra valores canónicos sobraría y habría que simplificarla."""
    nombres = await socrata.valores_distintos(reg.DIVIPOLA_MUNICIPIOS.id, "nom_mpio")
    acentuados = [n for n in nombres if texto.plegar(n) != n.upper()]
    assert len(nombres) > 1000
    assert len(acentuados) > 300, "DIVIPOLA ya no acentúa: revisar core.texto"


async def test_secop_conserva_los_acentos_en_columnas_categoricas():
    """El README afirmaba lo contrario. Es cierto solo en el texto libre."""
    deps = await socrata.valores_distintos(reg.SECOP["contratos"].id, "departamento")
    acentuados = [d for d in deps if texto.plegar(d) != d.upper()]
    assert len(acentuados) >= 8, f"SECOP dejó de acentuar `departamento`: {deps}"


async def test_el_filtro_plegado_seguiria_dando_cero():
    """Documenta el defecto original: sin resolución, esto devuelve 0."""
    r = await socrata.consultar(
        reg.SECOP["contratos"].id, seleccionar="count(*) as total",
        donde="upper(departamento) like '%ATLANTICO%'")
    assert r["filas"][0]["total"] == "0"


async def test_la_resolucion_si_encuentra_atlantico():
    salida = await secop.buscar_contratos(departamento="Atlantico", detalle="conteo")
    assert "0 " not in salida["texto"].split("**")[1]


# ----------------------------------------------------- trampas de origen --
async def test_soql_soporta_replace_anidado():
    """El plegado de acentos del texto libre depende de esto.

    Si SoQL dejara de aceptar `replace()`, `filtro_texto_libre` volvería a
    perder todas las filas con tilde y habría que rehacerlo.
    """
    campo = socrata.expr_sin_acentos("departamento")
    r = await socrata.consultar(reg.SECOP["contratos"].id,
                                seleccionar="count(*) as total",
                                donde=f"{campo} like '%ATLANTICO%'")
    assert int(r["filas"][0]["total"]) > 100_000


async def test_el_plegado_en_servidor_encuentra_mas_que_el_literal():
    """Cuantifica el defecto: plegar solo el término pierde las filas tildadas."""
    ds = reg.SECOP["contratos"].id
    literal = await socrata.consultar(
        ds, seleccionar="count(*) as total",
        donde="upper(nombre_entidad) like '%GOBERNACION%'")
    plegado = await socrata.consultar(
        ds, seleccionar="count(*) as total",
        donde=f"{socrata.expr_sin_acentos('nombre_entidad')} like '%GOBERNACION%'")
    assert int(plegado["filas"][0]["total"]) > int(literal["filas"][0]["total"])


async def test_medellin_sigue_trayendo_separador_de_miles():
    """El registro envenenado de `xaxy-8nri` que rompe `float()`."""
    r = await socrata.consultar(reg.DIVIPOLA_CENTROS.id,
                                donde="codigo_centro_poblado = '05001000'", limite=1)
    assert r["filas"], "cambió el código del centro poblado de Medellín"
    cruda = r["filas"][0]["longitud"]
    assert cruda.count(",") >= 1
    from colombia_datos_mcp.core.coords import normaliza_coord
    assert -76 < normaliza_coord(cruda, "lon") < -75


async def test_las_adiciones_conservan_sus_campos():
    esq = await socrata.esquema(reg.SECOP["adiciones"].id)
    campos = {c["campo"] for c in esq["columnas"]}
    assert {"id_contrato", "fecharegistro", "tipo"} <= campos


async def test_los_datasets_del_registro_siguen_existiendo():
    """Los IDs de Socrata rotan: `6d52-qyqg` ya devuelve 403."""
    faltantes = []
    for clave, ds in reg.SECOP.items():
        if not await socrata.esquema(ds.id):
            faltantes.append(f"{clave}={ds.id}")
    assert not faltantes, f"datasets desaparecidos: {faltantes}"


# --------------------------------------------------- contrato del cliente --
async def test_el_conteo_no_admite_orden():
    """Socrata rechaza `$order` sobre un agregado; el adaptador debe omitirlo."""
    assert socrata.es_agregada("count(*) as total")
    assert socrata.es_agregada("distinct departamento")
    assert not socrata.es_agregada("nombre_entidad, valor_del_contrato")
    total = await socrata.contar(reg.DIVIPOLA_MUNICIPIOS.id)
    assert total > 1000


async def test_divipola_encuentra_los_nombres_con_tilde():
    for consulta in ("Medellin", "Itagui", "Chia"):
        salida = await geo.divipola(consulta=consulta, limite=3)
        assert "Sin coincidencias" not in salida["texto"], consulta


# ------------------------------------------------------ alias curados -----
async def test_cada_alias_curado_sigue_encontrando_su_entidad():
    """La tabla se cura a mano y caduca: un alias muerto convierte una búsqueda
    legítima en cero filas. Así se detecta el día que pase.

    INVIAS y UNGRD figuran en SECOP con su sigla y nada más; expandirlas a su
    razón social daba cero.
    """
    fallidos = []
    for sigla, alias in reg.ALIAS_ENTIDADES.items():
        r = await socrata.consultar(
            reg.SECOP["contratos"].id, seleccionar="count(*) as total",
            donde=socrata.filtro_texto_libre("nombre_entidad", alias))
        if int(r["filas"][0]["total"]) == 0:
            fallidos.append(f"{sigla} -> {alias!r}")
    assert not fallidos, f"alias que ya no encuentran nada: {fallidos}"


async def test_rtvc_sigue_ausente_del_dataset_de_contratos():
    """Documenta por qué RTVC no está en ALIAS_ENTIDADES. Si algún día apareciera
    en contratos, habría que añadirlo."""
    r = await socrata.consultar(
        reg.SECOP["contratos"].id, seleccionar="count(*) as total",
        donde=socrata.filtro_texto_libre("nombre_entidad", "RADIO TELEVISION"))
    assert int(r["filas"][0]["total"]) == 0


# ------------------------------------------------------------- crimen ----
async def test_los_datasets_de_crimen_siguen_existiendo():
    """23 IDs curados de MinDefensa. Si uno rota, el módulo entero se cae."""
    faltantes = []
    for clave, ds in reg.CRIMEN.items():
        if not await socrata.esquema(ds.id):
            faltantes.append(f"{clave}={ds.id}")
    assert not faltantes, f"datasets de crimen desaparecidos: {faltantes}"


async def test_el_esquema_de_crimen_sigue_siendo_comun():
    """El módulo asume que todos traen fecha_hecho, cantidad y cod_muni."""
    from colombia_datos_mcp.adapters.socrata import campos_validos

    fallan = []
    for clave, ds in reg.CRIMEN.items():
        campos = await campos_validos(ds.id)
        if not {"fecha_hecho", "cantidad", "cod_muni"} <= campos:
            fallan.append(clave)
    assert not fallan, f"esquema cambiado en: {fallan}"


async def test_los_operativos_siguen_midiendo_otra_cosa():
    """Justifica excluirlos del registro: en ERRADICACIÓN la cantidad son
    hectáreas. Si algún día se unificara la unidad, podrían entrar."""
    r = await socrata.consultar("p72f-qcvk", seleccionar="unidad, count(*) as n",
                                agrupar="unidad", limite=5)
    unidades = {f.get("unidad") for f in r["filas"]}
    assert "HECTAREA" in unidades


async def test_los_dos_hurtos_ya_no_son_el_mismo_dato():
    """Lo fueron: hasta la recarga del 21-oct-2026 los dos servían 614.669 casos
    y el registro advertía de no sumarlos. Esta prueba es la que destapó que la
    nota había caducado, y ahora vigila la afirmación contraria —que son dos
    series— porque es la que el registro afirma hoy. Si vuelven a coincidir, la
    fuente volvió a publicar una encima de la otra y la nota miente otra vez.

    No basta comparar totales: podrían diferir por filas nuevas y seguir siendo
    la misma serie. Se comprueba año por año.
    """
    por_anio = {}
    for clave in ("hurto_comercio", "hurto_residencias"):
        r = await socrata.consultar(
            reg.CRIMEN[clave].id,
            seleccionar="date_extract_y(fecha_hecho) as anio, sum(cantidad) as v",
            agrupar="anio", limite=50)
        por_anio[clave] = {f["anio"]: int(float(f["v"])) for f in r["filas"]}
    c, d = por_anio["hurto_comercio"], por_anio["hurto_residencias"]
    comunes = set(c) & set(d)
    assert comunes, por_anio
    iguales = {a for a in comunes if c[a] == d[a]}
    assert not iguales, f"vuelven a coincidir en {sorted(iguales)}"


async def test_la_serie_de_los_dos_hurtos_sigue_rota_en_2017():
    """La trampa que queda viva después de deshacerse la duplicación: los dos
    hurtos más que duplican su cifra entre 2016 y 2017 mientras el homicidio se
    queda plano, así que el salto es de esos datasets y no del registro. Las
    notas lo advierten; si la fuente alguna vez lo alisa, hay que quitarlas."""
    async def dos_anios(ident):
        r = await socrata.consultar(
            ident, seleccionar="date_extract_y(fecha_hecho) as anio, sum(cantidad) as v",
            agrupar="anio", teniendo="anio in (2016, 2017)", limite=5)
        return {f["anio"]: int(float(f["v"])) for f in r["filas"]}

    for clave in ("hurto_comercio", "hurto_residencias"):
        v = await dos_anios(reg.CRIMEN[clave].id)
        assert v["2017"] > 1.8 * v["2016"], (clave, v)
    h = await dos_anios(reg.CRIMEN["homicidio"].id)
    assert abs(h["2017"] - h["2016"]) < 0.05 * h["2016"], h


# ---------------------------------------------------------- geometría ----
async def test_la_replica_de_geometria_sigue_sirviendo_el_mgn():
    """La geometría no viene de una fuente oficial, y sigue sin venir.

    El servicio del IGAC volvió a responder, pero no publica capa municipal
    (ver más abajo), así que esta réplica no es un respaldo: es la **única**
    fuente de los 1.122 polígonos. Si desaparece o cambia, `co_geo_limites` se
    queda sin geometría, y esto lo detecta antes de que alguien dibuje un mapa
    con agujeros."""
    from colombia_datos_mcp.adapters import geometria

    datos = await geometria.cargar()
    fs = datos["features"]
    assert len(fs) == 1122
    assert len({f["properties"]["MPIO_CCNCT"] for f in fs}) == 1122
    assert len({f["properties"]["DPTO_CCDGO"] for f in fs}) == 33


async def test_la_geometria_cruza_con_divipola_por_codigo():
    """Es la razón de ser del adaptador: unir por código, no por nombre."""
    from colombia_datos_mcp.adapters import geometria

    datos = await geometria.cargar()
    codigos_geo = {f["properties"]["MPIO_CCNCT"] for f in datos["features"]}
    r = await socrata.consultar(reg.DIVIPOLA_MUNICIPIOS.id,
                                seleccionar="cod_mpio", limite=2000)
    codigos_div = {f["cod_mpio"] for f in r["filas"]}
    faltan = codigos_div - codigos_geo
    # Nuevo Belén de Bajirá (27493) se creó después del corte de 2018.
    assert len(faltan) <= 2, f"DIVIPOLA tiene códigos sin geometría: {sorted(faltan)}"


# El servicio del IGAC volvió a responder el 05-nov-2026, después de meses de
# HTTP 500. La prueba que vigilaba su vuelta —`test_el_servicio_oficial_del_igac_
# sigue_caido`— cumplió su función y se fue: lo que vigila ahora es por qué,
# habiendo vuelto, la geometría SIGUE sin poder migrar. El motivo no es que el
# servicio esté caído, es que no publica el dato.

IGAC_SERVICIO = ("https://mapas.igac.gov.co/server/rest/services/"
                 "atlas/politicoadministrativo/MapServer")


def _igac(ruta: str = "", **params):
    """GET al servicio del IGAC. Lo que se consulta aquí son documentos de
    metadatos, que el servicio sirve en menos de un segundo. Sus consultas de
    datos son otra historia y no se piden desde CI."""
    import httpx

    return httpx.get(f"{IGAC_SERVICIO}{ruta}",
                     params={"f": "json", **params}, timeout=60).json()


async def test_el_igac_responde_pero_no_publica_capa_municipal():
    """**La prueba que decide si la geometría puede migrar.**

    El servicio responde —ya no da 500— y sin embargo de sus seis capas
    ninguna es municipal: trae transporte, distritos, capitales, áreas
    metropolitanas y departamentos. Los 1.122 polígonos municipales sobre los
    que se sostiene `co_geo_limites` no están ahí.

    El día que el IGAC añada una capa municipal, esta prueba falla, y ESE es el
    momento de escribir `adapters/arcgis.py`. Que responda no basta; tiene que
    publicar el dato.
    """
    doc = _igac()
    assert "error" not in doc, f"el IGAC volvió a caerse: {doc.get('error')}"
    assert doc["mapName"] == "División Político-Administrativa", doc.get("mapName")

    capas = {c["name"]: c["geometryType"] for c in doc["layers"]}
    assert "Departamento" in capas, capas

    municipales = [n for n in capas
                   if "municip" in n.lower() or "mpio" in n.lower()]
    assert not municipales, (
        f"el IGAC ya publica capa(s) municipal(es) {municipales}: "
        "toca evaluar la migración y escribir adapters/arcgis.py"
    )


async def test_la_capa_departamental_del_igac_no_usa_los_campos_del_mgn():
    """Si algún día se migra, el adaptador no puede reutilizar `CAMPOS`.

    La capa departamental del IGAC nombra sus columnas `DeCodigo`/`DeNombre`,
    no `DPTO_CCDGO`/`DPTO_CNMBR` como el MGN. Apuntar `CO_GEOMETRIA_URL` a esta
    capa sin tocar el adaptador no daría un mapa raro: daría `KeyError`, y por
    eso `_valida` lo rechaza antes (ver `test_geometria.py`).
    """
    from colombia_datos_mcp.adapters import geometria

    campos = {c["name"] for c in _igac("/5")["fields"]}
    assert {"DeCodigo", "DeNombre"} <= campos, campos
    assert not ({geometria.CAMPOS["cod_dpto"],
                 geometria.CAMPOS["departamento"]} & campos), (
        "el IGAC adoptó los nombres del MGN: revisar si ya se puede migrar"
    )


async def test_el_igac_falla_con_un_200_y_el_error_en_el_cuerpo():
    """**La trampa de forma que cualquier `adapters/arcgis.py` futuro heredaría.**

    `FeatureServer` es la vía para consultar por atributo y traer GeoJSON por
    página, y no está instalado. Lo interesante es cómo lo dice: **HTTP 200 con
    el fallo dentro del cuerpo.** `core/http.py` decide reintentos y errores por
    el status, así que una respuesta así se le cuela como válida — hay que mirar
    la clave `error` del JSON, no el código de la respuesta.

    El mensaje concreto **no** es estable, y por eso se aceptan los dos que da:
    «Server object extension 'featureserver' not found» en 0,6 s cuando el
    servicio está desahogado, y «Wait timeout for the request exceeded» a los
    60 s cuando no — o sea que a veces ni siquiera consigue contarte que la
    extensión no está. Lo que se afirma aquí es lo que sí se sostiene: 200, y un
    `error` en el cuerpo. El timeout es holgado a propósito, porque la rama
    lenta tarda poco más de 60 s.
    """
    import httpx

    r = httpx.get(IGAC_SERVICIO.replace("MapServer", "FeatureServer"),
                  params={"f": "json"}, timeout=90)
    assert r.status_code == 200, r.status_code
    cuerpo = r.json()
    assert "error" in cuerpo, cuerpo
    mensaje = cuerpo["error"]["message"].lower()
    assert ("featureserver" in mensaje or "wait timeout" in mensaje), cuerpo["error"]


# =========================================================================
# Fuentes de 0.16.0. Cada aserción es un supuesto sobre el que está escrito
# el código: si una cae, hay que cambiar el código, no la prueba.
# Verificadas el 05-nov-2026.
# =========================================================================

async def _cuenta(dataset_id, donde=None):
    return await socrata.contar(dataset_id, donde=donde)


# ------------------------------------------------------------------ RUES --
async def test_rues_la_categoria_de_matricula_lleva_la_o_acentuada():
    """`domain.empresas` filtra las sociedades con este literal exacto. Si la
    fuente lo normalizara, `solo_juridicas=True` devolvería cero."""
    from colombia_datos_mcp.core import privacidad
    valores = await socrata.valores_distintos(
        reg.EMPRESAS["rues"].id, "categoria_matricula")
    assert privacidad.RUES_JURIDICA in valores, valores
    assert privacidad.RUES_NATURAL in valores, valores


async def test_rues_la_mayoria_son_personas_naturales():
    """Es la premisa del motor de privacidad: el RUES no es un registro de
    empresas con algunas personas, son sobre todo personas."""
    from colombia_datos_mcp.core import privacidad
    rues = reg.EMPRESAS["rues"].id
    naturales = await _cuenta(
        rues, f"categoria_matricula = '{socrata.escapa(privacidad.RUES_NATURAL)}'")
    juridicas = await _cuenta(
        rues, f"categoria_matricula = '{socrata.escapa(privacidad.RUES_JURIDICA)}'")
    assert naturales > juridicas, (naturales, juridicas)
    assert naturales > 5_000_000


async def test_rues_la_clase_de_identificacion_no_discrimina_personas():
    """Por esto el motor de privacidad mira `categoria_matricula` y no la clase
    de documento: hay cientos de miles de personas naturales con clase NIT. Si
    se hubiera apoyado en la clase, habrían pasado por empresas."""
    from colombia_datos_mcp.core import privacidad
    n = await _cuenta(
        reg.EMPRESAS["rues"].id,
        f"categoria_matricula = '{socrata.escapa(privacidad.RUES_NATURAL)}' "
        "AND clase_identificacion = 'NIT'")
    assert n > 100_000, f"solo {n} naturales con clase NIT: revisar privacidad"


async def test_rues_el_nit_es_texto_y_exige_comillas():
    """Filtrarlo como número da `query.soql.type-mismatch`, no cero filas."""
    from colombia_datos_mcp.core.errors import ErrorValidacion
    rues = reg.EMPRESAS["rues"].id
    r = await socrata.consultar(rues, seleccionar="razon_social, nit",
                                donde="nit = '890903938'", limite=1)
    assert r["filas"], "Bancolombia ya no está en el RUES por su NIT"
    with pytest.raises(ErrorValidacion):
        await socrata.consultar(rues, donde="nit = 890903938", limite=1)


async def test_rues_hay_sociedades_sin_nit_en_la_columna_nit():
    """La razón de que toda búsqueda por documento mire las dos columnas.
    SECOLINSA S A S tiene estados financieros y su `nit` aquí está vacío."""
    rues = reg.EMPRESAS["rues"].id
    por_nit = await _cuenta(rues, "nit = '830010665'")
    por_identificacion = await _cuenta(rues, "numero_identificacion = '830010665'")
    assert por_identificacion > 0, "cambió el caso de referencia"
    assert por_nit == 0, (
        "SECOLINSA ya tiene `nit`; busca otro caso o revisa si la fuente lo "
        "rellenó entero, que permitiría simplificar `_donde_documento`")


async def test_rues_las_fechas_son_yyyymmdd_en_texto():
    """`between` no funciona sobre ellas y `fecha_rues` las parte a mano."""
    r = await socrata.consultar(reg.EMPRESAS["rues"].id,
                                seleccionar="fecha_matricula",
                                donde="nit = '890903938'", limite=1)
    valor = r["filas"][0]["fecha_matricula"]
    assert valor.isdigit() and len(valor) == 8, valor


# -------------------------------------------- Supersociedades · importes --
async def test_el_ranking_son_diez_mil_por_ano_no_diez_mil_en_total():
    """El título dice «10.000 Empresas»; sin filtrar el año cada empresa sale
    una vez por corte."""
    ds = reg.EMPRESAS["mas_grandes"].id
    total = await _cuenta(ds)
    r = await socrata.consultar(ds, seleccionar="a_o_de_corte, count(*) as n",
                                agrupar="a_o_de_corte", ordenar="a_o_de_corte DESC",
                                limite=20)
    anios = len(r["filas"])
    assert anios >= 4, r["filas"]
    assert total > 10_000 * (anios - 1), (total, anios)


async def test_los_importes_del_ranking_traen_signo_de_peso():
    """De aquí sale que `::number` directo falle y que la unidad sean billones."""
    r = await socrata.consultar(
        reg.EMPRESAS["mas_grandes"].id,
        seleccionar="raz_n_social, ingresos_operacionales",
        donde="nit = 899999068", ordenar="a_o_de_corte DESC", limite=1)
    assert r["filas"], "Ecopetrol salió del ranking"
    valor = r["filas"][0]["ingresos_operacionales"]
    assert valor.strip().startswith(("$", "-$")), valor
    # Ecopetrol en billones de pesos: decenas, no millones ni unidades.
    from colombia_datos_mcp.core import format as fmt
    assert 20 < (fmt.a_numero(valor) or 0) < 400, valor


async def test_el_casteo_directo_del_importe_sigue_fallando():
    """Documenta por qué `_orden_importe` envuelve dos `replace`. Si algún día
    la fuente guardara números, esto empieza a pasar y se puede simplificar."""
    from colombia_datos_mcp.core.errors import CoDatosError
    with pytest.raises(CoDatosError):
        await socrata.consultar(
            reg.EMPRESAS["mas_grandes"].id, seleccionar="raz_n_social",
            donde="a_o_de_corte = 2025", ordenar="ingresos_operacionales::number DESC",
            limite=1)


async def test_el_orden_con_replace_si_funciona_y_pone_a_ecopetrol_primero():
    from colombia_datos_mcp.domain import empresas
    r = await socrata.consultar(
        reg.EMPRESAS["mas_grandes"].id, seleccionar="raz_n_social",
        donde="a_o_de_corte = 2025",
        ordenar=f"{empresas._orden_importe('ingresos_operacionales')} DESC",
        limite=1)
    assert "ECOPETROL" in r["filas"][0]["raz_n_social"].upper()


# ------------------------------------- Supersociedades · estados financieros --
async def test_el_concepto_con_tilde_no_se_puede_pedir_por_igualdad():
    """El byte guardado es el carácter de reemplazo, así que la igualdad con la
    tilde correcta devuelve cero. Es la razón de `PATRONES_RESULTADO`."""
    ds = reg.EMPRESAS["eeff_resultados"].id
    con_tilde = await _cuenta(ds, "concepto = 'Ganancia (pérdida)'")
    con_like = await _cuenta(ds, "concepto like 'Ganancia (p_rdida)'")
    assert con_tilde == 0, "la fuente arregló el mojibake: simplificar el filtro"
    assert con_like > 100_000, con_like


async def test_los_conceptos_sin_tilde_si_casan_por_igualdad():
    from colombia_datos_mcp.domain import empresas
    for concepto in empresas.CONCEPTOS_BALANCE:
        n = await _cuenta(reg.EMPRESAS["eeff_situacion"].id,
                          f"concepto = '{socrata.escapa(concepto)}'")
        assert n > 1000, f"{concepto}: {n}"


async def test_el_periodo_de_los_estados_financieros_es_relativo():
    """«Periodo Actual» no es un año: el año está en `fecha_corte`. Fijarlo es
    lo que evita duplicar cada corte con su comparativo."""
    r = await socrata.consultar(
        reg.EMPRESAS["eeff_situacion"].id,
        seleccionar="periodo, count(*) as n", agrupar="periodo",
        ordenar="n DESC", limite=3)
    etiquetas = {f["periodo"] for f in r["filas"]}
    assert "Periodo Actual" in etiquetas, etiquetas


async def test_los_bancos_no_reportan_a_supersociedades():
    """Por esto «sin estados financieros» no significa «no opera»."""
    n = await _cuenta(reg.EMPRESAS["eeff_situacion"].id, "nit = 890903938")
    assert n == 0, f"Bancolombia tiene {n} filas: revisar el aviso de la herramienta"


# ------------------------------------------------------------ integridad --
async def test_secop2_multas_son_sobre_todo_comentarios_positivos():
    """El dataset se llama «Multas y Sanciones» y es la tabla de
    retroalimentación de proveedores. Sin filtrar, el conteo engaña."""
    ds = reg.INTEGRIDAD["sanciones_secop2"].id
    positivos = await _cuenta(ds, "tipo = 'Comentarios negativos'")
    total = await _cuenta(ds)
    assert total < 2000, f"{total}: creció mucho, revisar los avisos"
    assert positivos * 3 < total, (positivos, total)


async def test_secop2_la_mayoria_de_filas_no_esta_publicada():
    ds = reg.INTEGRIDAD["sanciones_secop2"].id
    publicadas = await _cuenta(
        ds, "estado = 'Publicado por el administrador de la plataforma'")
    total = await _cuenta(ds)
    assert publicadas < total / 2, (publicadas, total)


async def test_siri_casi_no_tiene_contratistas():
    """La cifra que hace honesta la herramienta de screening: para verificar a
    un proveedor del Estado, SIRI está vacío en la práctica."""
    ds = reg.INTEGRIDAD["siri"].id
    contratistas = await _cuenta(ds, "calidad_persona = 'CONTRATISTA'")
    total = await _cuenta(ds)
    assert total > 30_000, total
    assert contratistas < 500, f"{contratistas} contratistas: revisar el aviso"


async def test_la_responsabilidad_fiscal_sigue_siendo_residual():
    """60 filas. Si alguna vez se convierte en el Boletín de Responsables
    Fiscales, el aviso de la herramienta deja de ser cierto."""
    n = await _cuenta(reg.INTEGRIDAD["responsabilidad_fiscal"].id)
    assert n < 5000, f"{n} filas: ya no es una muestra residual"


# --------------------------------------------------------------- educación --
async def test_saber11_el_puntaje_es_texto_y_hay_que_castearlo():
    ds = reg.EDUCACION["saber11"].id
    esquema = await socrata.esquema(ds)
    tipos = {c["campo"]: c["tipo"] for c in esquema["columnas"]}
    assert tipos.get("punt_global", "").lower() == "text", tipos.get("punt_global")


async def test_saber11_los_periodos_de_marzo_son_una_poblacion_distinta():
    """Promediar 20224 junto a 20221 mezcla 1,1 M de estudiantes con 15 mil."""
    r = await socrata.consultar(
        reg.EDUCACION["saber11"].id, seleccionar="periodo, count(*) as n",
        agrupar="periodo", ordenar="periodo DESC", limite=30)
    por_periodo = {f["periodo"]: int(f["n"]) for f in r["filas"]}
    masivos = [n for p, n in por_periodo.items() if p.endswith("4")]
    menores = [n for p, n in por_periodo.items() if p.endswith("1")]
    assert masivos and menores
    assert min(masivos) > max(menores) * 5, (masivos, menores)


async def test_men_los_nombres_de_campo_tienen_la_tilde_comida():
    """`a_o`, `deserci_n`, `poblaci_n_5_16`: el código los cita literalmente."""
    esquema = await socrata.esquema(reg.EDUCACION["men_municipio"].id)
    campos = {c["campo"] for c in esquema["columnas"]}
    for esperado in ("a_o", "deserci_n", "poblaci_n_5_16", "c_digo_municipio"):
        assert esperado in campos, sorted(campos)


# -------------------------------------------------------------- territorio --
async def test_el_mdm_tiene_cuatro_indicadores_y_se_paro_en_2020():
    ds = reg.TERRITORIO["mdm"].id
    indicadores = await socrata.valores_distintos(ds, "indicador")
    assert len(indicadores) == 4, indicadores
    r = await socrata.consultar(ds, seleccionar="max(anio) as a", limite=1)
    assert int(r["filas"][0]["a"]) <= 2021, (
        "el DNP volvió a cargar el MDM: actualizar la nota del registro")


# ------------------------------------------------------------------ macro --
async def test_una_trm_rige_varios_dias_cuando_hay_fin_de_semana():
    """Por esto la TRM se busca por rango y no por igualdad de fecha."""
    r = await socrata.consultar(
        reg.MACRO["trm"].id,
        donde="vigenciadesde <= '2024-01-21T23:59:59' AND "
              "vigenciahasta >= '2024-01-21T00:00:00'", limite=1)
    assert r["filas"], "sin TRM vigente el domingo 21-ene-2024"
    fila = r["filas"][0]
    assert fila["vigenciadesde"][:10] == "2024-01-20"
    assert fila["vigenciahasta"][:10] == "2024-01-22"


async def test_preguntar_por_igualdad_de_fecha_perderia_los_domingos():
    """El defecto que el rango evita, documentado."""
    r = await socrata.consultar(
        reg.MACRO["trm"].id, seleccionar="count(*) as total",
        donde="vigenciadesde = '2024-01-21'", limite=1)
    assert r["filas"][0]["total"] == "0"


# ------------------------------------------- lo que no tiene fuente abierta --
async def test_el_dane_no_publica_poblacion_municipal_en_el_catalogo():
    """La razón de `SIN_FUENTE_ABIERTA['poblacion_municipal']`, y de que el
    servidor no ofrezca tasas por 100.000 habitantes. Si esto deja de ser
    cierto, se puede construir el denominador."""
    r = await socrata.buscar_datasets(
        atribucion=reg.ATRIBUCIONES["DANE"], limite=50)
    nombres = [x["resource"]["name"] for x in r["datos"].get("results", [])]
    assert all("oblaci" not in n for n in nombres), nombres


async def test_el_rues_tiene_matriculas_mal_clasificadas():
    """El caso de referencia de `privacidad.resuelve_persona`: el NIT de
    Bancolombia tiene dos matrículas y la de Cali figura como PERSONA NATURAL.

    Si algún día la fuente lo arregla, la regla cruzada sigue siendo correcta
    pero deja de tener un caso que la justifique: conviene saberlo.
    """
    from colombia_datos_mcp.core import privacidad
    r = await socrata.consultar(
        reg.EMPRESAS["rues"].id,
        seleccionar="razon_social, categoria_matricula, camara_comercio",
        donde="(nit in ('890903938', '8909039388') OR "
              "numero_identificacion in ('890903938', '8909039388'))",
        limite=10)
    categorias = [f.get("categoria_matricula") for f in r["filas"]]
    assert len(r["filas"]) >= 2, r["filas"]
    assert privacidad.RUES_NATURAL in categorias, (
        "el RUES arregló la matrícula de Bancolombia en Cali: la regla cruzada "
        "de `resuelve_persona` se queda sin caso de referencia")
    # Y la regla la resuelve del lado correcto.
    natural, aviso = privacidad.resuelve_persona("890903938", categorias)
    assert natural is False and aviso


# ------------------------------------------- supuestos de la revisión del PR 1 --
async def test_el_rues_sigue_teniendo_exactamente_dos_categorias():
    """`juridica_en_rues` comprueba en POSITIVO que la categoría sea la de
    sociedad, en vez de descartar «PERSONA NATURAL». La diferencia solo importa
    si aparece un tercer valor: con el descarte, ese tercero se daría por
    empresa y el documento saldría sin enmascarar. Esto vigila el supuesto."""
    r = await socrata.consultar("c82u-588k",
                                seleccionar="categoria_matricula, count(*) as n",
                                agrupar="categoria_matricula", limite=10)
    categorias = {f["categoria_matricula"] for f in r["filas"]}
    assert categorias == {privacidad.RUES_JURIDICA, privacidad.RUES_NATURAL}, categorias


async def test_un_nombre_de_dos_terminos_encuentra_personas_en_siri():
    """El falso cero que destapó la revisión: SIRI guarda el nombre en cuatro
    columnas y ninguna tiene el completo, así que buscar la cadena entera en
    cada una devolvía cero con la persona dentro. Si esto vuelve a dar cero, el
    filtro por términos se rompió."""
    donde = " AND ".join(
        "(" + " OR ".join(socrata.filtro_texto_libre(c, t) for c in
                          ("primer_nombre", "segundo_nombre", "primer_apellido",
                           "segundo_apellido")) + ")"
        for t in ("ANA", "PEREZ"))
    r = await socrata.consultar("iaeu-rcn6", seleccionar="count(*) as n", donde=donde,
                                limite=1)
    assert int(r["filas"][0]["n"]) > 0


async def test_la_trm_de_un_dia_sin_certificacion_esta_en_un_intervalo_anterior():
    """La TRM del 21-ene-2024 es la certificada el 20, vigente hasta el 22.
    Filtrar por `vigenciadesde >= desde` la perdía, y entonces la misma fecha
    daba dos respuestas según se preguntara por `fecha` o por rango."""
    r = await socrata.consultar(
        "32sa-8pi3",
        donde=("vigenciahasta >= '2024-01-21T00:00:00' AND "
               "vigenciadesde <= '2024-01-21T23:59:59'"),
        ordenar="vigenciadesde DESC", limite=5)
    assert r["filas"], "el rango que solapa el 21-ene-2024 quedó vacío"
    assert r["filas"][0]["vigenciadesde"][:10] < "2024-01-21"


async def test_el_ranking_sigue_sirviendo_el_nit_con_decimales():
    """`"899999068.00"` en una columna declarada Number. Si la fuente lo
    arreglara, `_nit_entero` sobra; mientras no lo haga, es lo que evita que el
    NIT del ranking encadenado a la ficha consulte otro documento."""
    r = await socrata.consultar("6cat-2gcs", seleccionar="nit", limite=1)
    assert "." in str(r["filas"][0]["nit"])
