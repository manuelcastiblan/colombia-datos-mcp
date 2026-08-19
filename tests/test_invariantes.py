"""Invariantes que TODA herramienta debe cumplir.

Este fichero existe por un patrón, no por un fallo suelto. Los defectos de este
servidor no han sido de cálculo: han sido respuestas que afirmaban más de lo que
habían comprobado. `total_coincidencias = len(filas)` sobre un resultado ya
recortado por `$limit` apareció en SEIS herramientas por separado, se arregló en
una, siguió vivo en las otras cinco y hubo que arreglarlo otra vez.

Comprobarlo herramienta a herramienta no basta, porque el error no viene de
descuidos aislados sino de que cada sitio decide por su cuenta. Aquí se
comprueba en todas a la vez y, sobre todo, se obliga a clasificar cualquier
herramienta nueva: sin eso, el séptimo caso solo depende de que alguien se
acuerde.
"""

import pytest

from colombia_datos_mcp.adapters import socrata
from colombia_datos_mcp.core.cache import Cache
from colombia_datos_mcp.core.errors import ErrorTimeout
from colombia_datos_mcp.server import mcp

from .test_dominio import RedFalsa

# Herramientas que devuelven una tabla de filas traída con `$limit`. Les rige el
# invariante: si la fuente llenó el límite, la respuesta NO puede declararse
# completa.
CASOS = {
    "co_datos_buscar_datasets": {"consulta": "contratos", "limite": 5},
    "co_datos_consultar": {"dataset_id": "jbjy-vk9h", "limite": 5},
    "co_datos_agregar": {"dataset_id": "jbjy-vk9h", "agrupar_por": "nombre_entidad",
                         "limite": 5},
    "co_datos_serie": {"dataset_id": "jbjy-vk9h", "campo_fecha": "fecha_de_firma"},
    "co_secop_buscar_contratos": {"departamento": "Antioquia", "limite": 5},
    "co_secop_buscar_procesos": {"limite": 5},
    "co_secop_perfil_proveedor": {"documento": "900123456", "limite": 5},
    "co_secop_resolver_entidad": {"nombre": "municipio", "limite": 5},
    "co_secop_agregar": {"agrupar_por": "departamento", "limite": 5},
    "co_geo_divipola": {"consulta": "medellin", "limite": 5},
    "co_crimen_por_municipio": {"delito": "homicidio", "anio": 2025, "limite": 5},
    "co_crimen_serie": {"delito": "homicidio"},
}

# Exentas, cada una con su motivo. No vale con omitirlas: hay que decir por qué,
# porque «se me olvidó» y «no aplica» se parecen demasiado desde fuera.
EXENTAS = {
    "co_datos_describir_dataset": "lista el esquema entero; no hay `$limit` que llenar",
    "co_datos_perfilar": "sus filas son tramos calculados, no filas de la fuente",
    "co_secop_detalle_contrato": "un contrato concreto: no hay nada que recortar",
    "co_datos_exportar": "escribe a disco y devuelve una ficha del fichero, no filas",
    "co_geo_limites": "devuelve geometría; ya usa mostrar_conteo=False",
    "co_geo_cotejar_coordenadas": "compara dos fuentes y declara el total real de discrepancias",
    "co_crimen_comparar": "una fila por delito de una lista fija; no hay `$limit` que llenar",
}


@pytest.fixture(autouse=True)
def entorno(monkeypatch, tmp_path):
    import colombia_datos_mcp.core.cache as mod
    fresca = Cache(dir_disco=tmp_path / "cache")
    monkeypatch.setattr(mod, "cache", fresca)
    monkeypatch.setattr(socrata, "cache", fresca)


# Un esquema con la unión de los campos que citan las herramientas, para que la
# validación de columnas no rechace nada por culpa del fixture.
_CAMPOS = [
    "nombre_entidad", "nit_entidad", "documento_proveedor", "proveedor_adjudicado",
    "valor_del_contrato", "fecha_de_firma", "tipo_de_contrato", "tipodocproveedor",
    "estado_contrato", "sector", "modalidad_de_contratacion", "departamento",
    "ciudad", "id_contrato", "objeto_del_contrato", "municipio", "cod_muni",
    "cantidad", "fecha_hecho", "cod_dpto", "dpto", "cod_mpio", "nom_mpio",
    "longitud", "latitud", "tipo_municipio", "periodo", "casos",
]
CATALOGO_AMPLIO = {
    "resultSetSize": 151,
    "results": [{
        "resource": {
            "id": "jbjy-vk9h", "name": "Dataset de prueba", "attribution": "X",
            "updatedAt": "2026-08-19T00:00:00.000Z",
            "columns_field_name": _CAMPOS,
            "columns_name": _CAMPOS,
            # Los tipos importan: `co_datos_serie` rechaza —con razón— las
            # columnas de fecha que la fuente declara como texto.
            "columns_datatype": ["Calendar date" if c.startswith("fecha")
                                 else "Number" if c in ("valor_del_contrato", "cantidad")
                                 else "Text" for c in _CAMPOS],
            "columns_description": [""] * len(_CAMPOS),
        },
        "classification": {"domain_category": "Y"},
        "metadata": {"license": "CC BY-SA 4.0"},
    }],
}


def _fila(i: int) -> dict:
    return {
        "nombre_entidad": f"ENTIDAD {i}", "nit_entidad": f"80000{i}",
        "documento_proveedor": f"9001234{i}", "proveedor_adjudicado": f"PROVEEDOR {i}",
        "valor_del_contrato": "12500000", "valor": "12500000", "v": "12500000",
        "fecha_de_firma": "2026-02-01T00:00:00.000", "tipo_de_contrato": "Suministros",
        "estado_contrato": "Modificado", "departamento": "ANTIOQUIA",
        "id_contrato": f"CO1.PCCNTR.{i}", "objeto_del_contrato": f"OBJETO {i}",
        "municipio": f"MUNICIPIO {i}", "cod_muni": f"0500{i}", "casos": "10",
        "cantidad": "10", "periodo": f"20{10 + i}", "total": "10", "n": "10",
        "cod_dpto": "05", "dpto": "ANTIOQUIA", "cod_mpio": f"0500{i}",
        "nom_mpio": f"MUNICIPIO {i}", "longitud": "-75,581775", "latitud": "6,246631",
        "tipo_municipio": "Municipio",
    }


def _fuente_saturada(params):
    """Una fuente que SIEMPRE llena el límite: devuelve exactamente tantas filas
    como se le piden. Es la única situación en la que una respuesta no puede
    saber si vio todo, y por tanto la única en la que puede mentir."""
    if "$query" in params:
        # Y encima no deja contar los grupos: el total tiene que salir
        # «desconocido», nunca igualado al número de filas mostradas.
        raise ErrorTimeout("la fuente no pudo contar los grupos")
    seleccionar = params.get("$select", "") or ""
    if seleccionar.startswith("distinct "):
        # Dominio categórico canónico, CON acentos, como lo devuelve la fuente:
        # es contra estos literales contra lo que se resuelve el término.
        campo = seleccionar.split(" ", 1)[1].strip()
        return [{campo: v} for v in
                ("MEDELLÍN", "ANTIOQUIA", "BOGOTÁ D.C.", "ATLÁNTICO", "MUNICIPIO 1")]
    if "max(" in seleccionar:
        return [{"h": "2026-08-01T00:00:00.000"}]
    if "count(*)" in seleccionar and "$group" not in params:
        return [{"total": "9999", "n": "9999", "valor": "1", "v": "1"}]
    return [_fila(i) for i in range(int(params.get("$limit", 20) or 20))]


def _instala(monkeypatch):
    monkeypatch.setattr(socrata, "_http", RedFalsa({
        "api/catalog/v1": CATALOGO_AMPLIO,
        "/resource/": _fuente_saturada,
    }))


async def test_toda_herramienta_esta_clasificada():
    """La que impide el séptimo caso.

    Una herramienta nueva rompe esta prueba hasta que alguien decida si le rige
    el invariante. Que la decisión sea obligatoria es justamente lo que faltaba:
    las seis instancias del error no se escribieron a la vez, se fueron
    añadiendo una a una sin que nada preguntara.
    """
    nombres = {t.name for t in await mcp.list_tools()}
    sin_clasificar = nombres - set(CASOS) - set(EXENTAS)
    assert not sin_clasificar, (
        f"Herramientas sin clasificar: {sorted(sin_clasificar)}. Añádelas a CASOS "
        "si devuelven filas traídas con `$limit`, o a EXENTAS con el motivo."
    )
    sobran = (set(CASOS) | set(EXENTAS)) - nombres
    assert not sobran, f"Clasificadas pero inexistentes: {sorted(sobran)}"


@pytest.mark.parametrize("herramienta", sorted(CASOS))
async def test_ninguna_se_declara_completa_si_la_fuente_lleno_el_limite(
        herramienta, monkeypatch):
    """El invariante: `devueltos == total` solo es legítimo si consta que no
    había más. Con una fuente que siempre llena el límite y que no deja contar,
    no consta, así que el total debe salir desconocido o mayor que lo mostrado.
    """
    _instala(monkeypatch)
    resultado = await mcp.call_tool(herramienta, CASOS[herramienta])
    meta = resultado.structured_content["_meta"]
    devueltos, total = meta["devueltos"], meta.get("total_coincidencias")
    assert devueltos > 0, f"{herramienta} no devolvió filas: el caso no prueba nada"
    assert total is None or total > devueltos, (
        f"{herramienta} afirma {total} coincidencias mostrando {devueltos} filas, "
        "con una fuente que llenó el límite y no dejó contar los grupos. "
        "O el total se comprobó, o se declara desconocido."
    )
    if total is None:
        assert any("desconocido" in a.lower() for a in meta.get("advertencias", [])), (
            f"{herramienta} deja el total sin declarar y no lo advierte")
