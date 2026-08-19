"""Series temporales y perfilado. Sin red."""

import pytest

from colombia_datos_mcp.adapters import socrata
from colombia_datos_mcp.core.cache import Cache
from colombia_datos_mcp.core.errors import ErrorValidacion
from colombia_datos_mcp.domain import analisis

from .test_dominio import RedFalsa

ESQUEMA = {"results": [{
    "resource": {
        "id": "test-0001", "name": "Dataset de prueba", "description": "",
        "attribution": "Fuente", "updatedAt": "2026-08-18T00:00:00.000Z",
        "provenance": "official", "parent_fxf": [], "page_views": {},
        "columns_field_name": ["fecha_hecho", "fecha_texto", "valor", "ciudad"],
        "columns_name": ["Fecha", "Fecha en texto", "Valor", "Ciudad"],
        "columns_datatype": ["Calendar date", "Text", "Number", "Text"],
        "columns_description": ["", "", "Valor del contrato", ""],
    },
    "classification": {}, "metadata": {},
}]}


@pytest.fixture(autouse=True)
def cache_limpia(monkeypatch, tmp_path):
    import colombia_datos_mcp.core.cache as mod
    fresca = Cache(dir_disco=tmp_path / "cache")
    monkeypatch.setattr(mod, "cache", fresca)
    monkeypatch.setattr(socrata, "cache", fresca)


def _datos(corte="2026-08-17T00:00:00.000", cima=10):
    def responde(params):
        sel = params.get("$select", "")
        if "max(" in sel and "min(" not in sel:
            return [{"h": corte}]
        if "min(" in sel and "max(" in sel:
            return [{"mn": "0", "mx": "1000", "suma": "1000", "media": "10",
                     "h": corte}]
        if "count(*)" in sel and "as periodo" not in sel and "$group" not in params:
            return [{"total": "100"}]
        if "as periodo" in sel:
            return [{"periodo": "2024", "casos": "50"}, {"periodo": "2025", "casos": "80"},
                    {"periodo": "2026", "casos": "30"}]
        if params.get("$order", "").endswith("DESC") and "valor" == sel.strip():
            return [{"valor": str(cima)} for _ in range(10)]
        if "$group" in params:
            return [{"ciudad": "BOGOTA", "n": "40"}, {"ciudad": "CALI", "n": "20"}]
        return [{"valor": "1"}]
    return responde


def _instala(monkeypatch, **kw):
    red = RedFalsa({"api/catalog/v1": ESQUEMA, "/resource/": _datos(**kw)})
    monkeypatch.setattr(socrata, "_http", red)
    return red


# --------------------------------------------------------------- serie ----
async def test_la_serie_agrupa_por_el_periodo_pedido(monkeypatch):
    red = _instala(monkeypatch)
    await analisis.serie("test-0001", "fecha_hecho", periodo="mes")
    sel = [p["$select"] for _, p in red.llamadas if "as periodo" in p.get("$select", "")][0]
    assert "date_trunc_ym(fecha_hecho)" in sel


async def test_avisa_de_que_el_ultimo_periodo_esta_incompleto(monkeypatch):
    """El error que motivó la herramienta: un año que llega hasta agosto
    comparado con años cerrados parece una caída del 30 %."""
    _instala(monkeypatch, corte="2026-08-17T00:00:00.000")
    salida = await analisis.serie("test-0001", "fecha_hecho")
    assert "INCOMPLETO" in salida["texto"]
    assert "2026-08-17" in salida["texto"]


async def test_no_da_falsa_alarma_si_el_periodo_esta_cerrado(monkeypatch):
    """Un aviso que salta siempre deja de leerse."""
    _instala(monkeypatch, corte="2026-12-31T00:00:00.000")
    salida = await analisis.serie("test-0001", "fecha_hecho")
    assert "INCOMPLETO" not in salida["texto"]
    assert "llegan hasta 2026-12-31" in salida["texto"]


async def test_rechaza_una_columna_de_fecha_que_es_texto(monkeypatch):
    """En el Plan Anual de Adquisiciones las cinco columnas de fecha son `text`:
    agrupar por periodo falla y `between` da resultados falsos."""
    _instala(monkeypatch)
    with pytest.raises(ErrorValidacion) as exc:
        await analisis.serie("test-0001", "fecha_texto")
    assert "Text" in str(exc.value)
    assert "between" in exc.value.sugerencia


async def test_columna_inexistente_lista_las_validas(monkeypatch):
    _instala(monkeypatch)
    with pytest.raises(ErrorValidacion) as exc:
        await analisis.serie("test-0001", "no_existe")
    assert "fecha_hecho" in exc.value.sugerencia


async def test_periodo_invalido_se_rechaza(monkeypatch):
    _instala(monkeypatch)
    with pytest.raises(ErrorValidacion):
        await analisis.serie("test-0001", "fecha_hecho", periodo="quincena")


async def test_la_serie_recuerda_maximo_y_minimo(monkeypatch):
    _instala(monkeypatch)
    salida = await analisis.serie("test-0001", "fecha_hecho")
    assert "Máximo de la serie" in salida["texto"]


# ------------------------------------------------------------- perfilar ---
async def test_perfilar_avisa_cuando_unos_pocos_valores_dominan(monkeypatch):
    """Es el hallazgo que costó una investigación entera en SECOP: nueve
    contratos aportaban el 94 % de la suma."""
    _instala(monkeypatch, cima=95)          # 10 valores de 95 sobre una suma de 1000
    salida = await analisis.perfilar("test-0001", "valor")
    assert "ATENCIÓN" in salida["texto"]
    assert "de la suma" in salida["texto"]


async def test_perfilar_no_alarma_si_el_reparto_es_sano(monkeypatch):
    _instala(monkeypatch, cima=1)
    salida = await analisis.perfilar("test-0001", "valor")
    assert "ATENCIÓN" not in salida["texto"]


async def test_perfilar_reporta_el_reparto_por_magnitud(monkeypatch):
    _instala(monkeypatch)
    salida = await analisis.perfilar("test-0001", "valor")
    assert "Por encima de" in salida["texto"]


async def test_perfilar_una_columna_de_texto_da_los_valores_frecuentes(monkeypatch):
    _instala(monkeypatch)
    salida = await analisis.perfilar("test-0001", "ciudad")
    assert "BOGOTA" in salida["texto"]


async def test_perfilar_devuelve_estructurado_utilizable(monkeypatch):
    _instala(monkeypatch)
    salida = await analisis.perfilar("test-0001", "valor")
    d = salida["estructurado"]["datos"][0]
    assert d["campo"] == "valor" and d["tipo"] == "Number"
