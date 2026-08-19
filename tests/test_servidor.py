"""Pruebas de extremo a extremo a través de la capa MCP, con red simulada."""

import json

import pytest
from fastmcp.exceptions import ToolError

from colombia_datos_mcp.adapters import socrata
from colombia_datos_mcp.core.cache import Cache
from colombia_datos_mcp.server import mcp

from .fixtures import CATALOGO, CONTRATOS
from .test_dominio import RedFalsa, _filas_de_contratos


@pytest.fixture(autouse=True)
def entorno(monkeypatch, tmp_path):
    import colombia_datos_mcp.core.cache as mod
    fresca = Cache(dir_disco=tmp_path / "cache")
    monkeypatch.setattr(mod, "cache", fresca)
    monkeypatch.setattr(socrata, "cache", fresca)


async def test_inventario_de_herramientas():
    tools = await mcp.list_tools()
    nombres = {t.name for t in tools}
    assert nombres == {
        "co_datos_buscar_datasets", "co_datos_describir_dataset", "co_datos_consultar",
        "co_datos_agregar", "co_secop_buscar_contratos", "co_secop_buscar_procesos",
        "co_secop_detalle_contrato", "co_secop_perfil_proveedor",
        "co_secop_resolver_entidad", "co_secop_agregar",
        "co_geo_divipola", "co_geo_cotejar_coordenadas", "co_datos_exportar",
        "co_crimen_serie", "co_crimen_por_municipio", "co_crimen_comparar",
        "co_datos_serie", "co_datos_perfilar", "co_geo_limites",
    }
    # Exportar es la ÚNICA que escribe, y no puede anunciarse como solo lectura:
    # el cliente decide con esa anotación si pedir confirmación al usuario.
    escriben = {t.name for t in tools if not (t.annotations and t.annotations.readOnlyHint)}
    assert escriben == {"co_datos_exportar"}
    # Prefijo co_ para no colisionar con otros MCP en la misma sesión.
    assert all(t.name.startswith("co_") for t in tools)


async def test_toda_herramienta_esta_documentada():
    for t in await mcp.list_tools():
        assert t.description and len(t.description) > 30, t.name


async def test_playbook_presente():
    assert "detalle=\"conteo\"" in mcp.instructions
    assert "RADIO TELEVISION NACIONAL DE COLOMBIA." in mcp.instructions


async def test_recursos_publicados():
    uris = {str(r.uri) for r in await mcp.list_resources()}
    assert uris == {"co://secop/datasets", "co://secop/joins", "co://atribuciones"}


async def test_llamada_completa_devuelve_markdown_con_procedencia(monkeypatch):
    monkeypatch.setattr(socrata, "_http",
                        RedFalsa({"/resource/jbjy-vk9h.json": _filas_de_contratos}))
    r = await mcp.call_tool("co_secop_buscar_contratos", {"departamento": "Antioquia"})
    texto = r.content[0].text
    assert "$12.500.000" in texto            # moneda formateada
    assert "datos.gov.co/resource" in texto  # consulta reproducible en el pie
    assert "fila(s)" in texto                # sobre presente


async def test_error_tipado_llega_como_ToolError_accionable(monkeypatch):
    monkeypatch.setattr(socrata, "_http", RedFalsa({"api/catalog/v1": CATALOGO}))
    with pytest.raises(ToolError) as exc:
        await mcp.call_tool("co_datos_consultar",
                            {"dataset_id": "jbjy-vk9h", "donde": "inventada = '1'"})
    mensaje = str(exc.value)
    assert "[VALIDACION]" in mensaje       # código estable
    assert "Sugerencia:" in mensaje        # y qué hacer al respecto
    assert "nombre_entidad" in mensaje     # con la lista de campos válidos


async def test_recurso_de_joins_es_json_valido():
    resultado = await mcp.read_resource("co://secop/joins")
    joins = json.loads(resultado.contents[0].content)
    assert any(j["desde"].startswith("p6dx-8zbt") for j in joins)


async def test_la_respuesta_trae_contenido_estructurado(monkeypatch):
    """El sobre ya calculaba `datos` y `_meta`, pero se descartaban: el cliente
    solo recibía prosa y tenía que volver a parsear la tabla."""
    monkeypatch.setattr(socrata, "_http", RedFalsa(
        {"api/catalog/v1": CATALOGO, "/resource/jbjy-vk9h.json": _filas_de_contratos}))
    r = await mcp.call_tool("co_secop_buscar_contratos", {"departamento": "Antioquía"})
    assert r.structured_content is not None
    assert set(r.structured_content) == {"datos", "_meta"}
    meta = r.structured_content["_meta"]
    assert meta["orden"] and meta["consulta"].startswith("https://")


async def test_el_formato_csv_va_en_bloque_cercado(monkeypatch):
    """Así el pie del sobre no contamina lo que se copia."""
    monkeypatch.setattr(socrata, "_http", RedFalsa(
        {"api/catalog/v1": CATALOGO, "/resource/jbjy-vk9h.json": _filas_de_contratos}))
    r = await mcp.call_tool("co_secop_buscar_contratos",
                             {"departamento": "Antioquía", "formato": "csv"})
    texto = r.content[0].text
    assert texto.startswith("```csv")
    assert "```" in texto.split("```csv")[1]
    # El sobre sigue estando: procedencia y URL no son opcionales.
    assert "Consulta reproducible" in texto
