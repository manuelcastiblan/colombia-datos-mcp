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
from colombia_datos_mcp.core import texto
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
