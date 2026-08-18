"""Extracción estructurada, formatos y gráficas."""

import pytest

from colombia_datos_mcp.adapters import socrata
from colombia_datos_mcp.core import format as fmt
from colombia_datos_mcp.core.cache import Cache
from colombia_datos_mcp.core.errors import ErrorValidacion
from colombia_datos_mcp.domain import exportar

from .test_dominio import RedFalsa, _filas_de_contratos


@pytest.fixture(autouse=True)
def entorno(monkeypatch, tmp_path):
    import colombia_datos_mcp.core.cache as mod
    fresca = Cache(dir_disco=tmp_path / "cache")
    monkeypatch.setattr(mod, "cache", fresca)
    monkeypatch.setattr(socrata, "cache", fresca)
    monkeypatch.setattr(exportar, "DIR_EXPORT", tmp_path / "export")
    return fresca


# ------------------------------------------------------------- números ----
@pytest.mark.parametrize("crudo,esperado", [
    ("1.000", 1000.0),                  # agrupación: mil
    ("1.000.000", 1_000_000.0),
    ("1,234,567", 1_234_567.0),
    ("1,5", 1.5),
    ("$1.234.567,89", 1_234_567.89),
    ("2500000.75", 2_500_000.75),
    # Una suma agregada de Socrata: 22 dígitos enteros y 3 decimales. La regla
    # de agrupación NO aplica aquí, y aplicarla la hacía mil veces mayor.
    ("5093243848602202766138.364", 5.093243848602203e21),
    ("997507251206056.395194", 997507251206056.4),
])
def test_a_numero_respeta_la_convencion_colombiana(crudo, esperado):
    assert fmt.a_numero(crudo) == pytest.approx(esperado, rel=1e-12)


def test_a_numero_devuelve_none_si_no_es_numero():
    assert fmt.a_numero("n/d") is None
    assert fmt.a_numero(None) is None


def test_secop_numero_usa_la_misma_regla_que_format():
    """Había dos copias de la regla y divergieron."""
    from colombia_datos_mcp.domain.secop import _numero

    assert _numero("1.000.000", "valor_min") == fmt.a_numero("1.000.000")
    with pytest.raises(ErrorValidacion):
        _numero("mucho dinero", "valor_min")


# ------------------------------------------------------------- formatos ---
def test_csv_lleva_cabecera_y_entrecomilla_las_comas():
    salida = fmt.csv_texto([{"a": "x", "b": 1}, {"a": "y, con coma", "b": 2}])
    assert salida.splitlines()[0] == "a,b"
    assert '"y, con coma"' in salida


def test_csv_toma_las_columnas_de_todas_las_filas():
    salida = fmt.csv_texto([{"a": 1}, {"a": 2, "fecha": "2025-01-31"}])
    assert "fecha" in salida.splitlines()[0]


def test_json_no_escapa_los_acentos():
    assert "MEDELLÍN" in fmt.json_texto([{"m": "MEDELLÍN"}])


# --------------------------------------------------------------- barras ---
def test_las_barras_comparten_escala_y_respetan_el_cero():
    dibujos = fmt.barras([100, 50, 0, "n/d"], ancho=8)
    assert dibujos[0] == "█" * 8
    assert len(dibujos[1]) < len(dibujos[0])
    assert dibujos[2] == ""          # un cero no dibuja barra
    assert dibujos[3] == ""          # ni un valor no numérico


def test_un_valor_diminuto_no_desaparece():
    """Debe distinguirse de un cero: si no, la gráfica miente."""
    assert fmt.barras([1_000_000, 1])[1] != ""


# ------------------------------------------------------------- exportar ---
async def test_exportar_escribe_csv_y_reporta_la_ruta(monkeypatch):
    monkeypatch.setattr(socrata, "_http", RedFalsa(
        {"api/catalog/v1": {"results": []}, "/resource/jbjy-vk9h.json": _filas_de_contratos}))
    salida = await exportar.exportar("jbjy-vk9h", "contratos", formato="csv")
    ruta = exportar.DIR_EXPORT / "contratos.csv"
    assert ruta.exists()
    assert str(ruta) in salida["texto"]
    assert salida["estructurado"]["datos"][0]["completo"] is True
    # BOM para que Excel no destroce los acentos.
    assert ruta.read_text(encoding="utf-8").startswith("﻿")


async def test_exportar_no_deja_salir_del_directorio(monkeypatch):
    """`nombre_archivo` es un nombre, no una ruta: un modelo que la compone a
    partir del texto del usuario no debe poder escribir donde quiera."""
    monkeypatch.setattr(socrata, "_http", RedFalsa(
        {"api/catalog/v1": {"results": []}, "/resource/jbjy-vk9h.json": _filas_de_contratos}))
    salida = await exportar.exportar("jbjy-vk9h", "../../../etc/passwd", formato="csv")
    escrito = salida["estructurado"]["datos"][0]["ruta"]
    assert escrito.startswith(str(exportar.DIR_EXPORT))
    assert ".." not in escrito


async def test_exportar_avisa_cuando_el_fichero_queda_incompleto(monkeypatch):
    def muchas(params):
        if "count(*)" in params.get("$select", ""):
            return [{"total": "5000"}]
        pedidas = int(params.get("$limit", 1))
        return [{"id_contrato": f"C{i}"} for i in range(pedidas)]

    monkeypatch.setattr(socrata, "_http", RedFalsa(
        {"api/catalog/v1": {"results": []}, "/resource/jbjy-vk9h.json": muchas}))
    salida = await exportar.exportar("jbjy-vk9h", "recortado", max_filas=10)
    assert "NO es el conjunto completo" in salida["texto"]
    assert salida["estructurado"]["datos"][0]["completo"] is False


async def test_exportar_rechaza_un_formato_desconocido(monkeypatch):
    monkeypatch.setattr(socrata, "_http", RedFalsa({}))
    with pytest.raises(ErrorValidacion):
        await exportar.exportar("jbjy-vk9h", "x", formato="xlsx")


async def test_exportar_sin_filas_no_crea_fichero(monkeypatch):
    monkeypatch.setattr(socrata, "_http", RedFalsa(
        {"api/catalog/v1": {"results": []},
         "/resource/jbjy-vk9h.json": lambda p: [{"total": "0"}] if "count(*)" in p.get("$select", "") else []}))
    salida = await exportar.exportar("jbjy-vk9h", "vacio")
    assert "no se escribió ningún fichero" in salida["texto"]
    assert not (exportar.DIR_EXPORT / "vacio.csv").exists()


# ------------------------------------------------------------ atípicos ----
async def test_valor_max_acota_por_arriba(monkeypatch):
    """Sin un tope, dejar fuera los valores imposibles obliga a escribir SoQL
    a mano en una herramienta que existe para no tener que escribirlo."""
    from colombia_datos_mcp.domain import secop

    red = RedFalsa({"/resource/jbjy-vk9h.json": _filas_de_contratos})
    monkeypatch.setattr(socrata, "_http", red)
    await secop.buscar_contratos(valor_max="1.000.000.000.000", detalle="conteo")
    donde = [p["$where"] for _, p in red.llamadas if "$where" in p][0]
    assert "valor_del_contrato <= 1000000000000.0" in donde


async def test_valor_min_y_valor_max_se_combinan(monkeypatch):
    from colombia_datos_mcp.domain import secop

    red = RedFalsa({"/resource/jbjy-vk9h.json": _filas_de_contratos})
    monkeypatch.setattr(socrata, "_http", red)
    await secop.buscar_contratos(valor_min=1_000_000, valor_max=1_000_000_000,
                                 detalle="conteo")
    donde = [p["$where"] for _, p in red.llamadas if "$where" in p][0]
    assert ">= 1000000.0" in donde and "<= 1000000000.0" in donde
