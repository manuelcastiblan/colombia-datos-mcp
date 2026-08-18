"""Pruebas del núcleo. Corren sin red."""

import pytest

from colombia_datos_mcp.core import format as fmt
from colombia_datos_mcp.core.budget import Detalle, ajusta_filas, estima_tokens, siguiente_nivel
from colombia_datos_mcp.core.coords import normaliza_coord, normaliza_par
from colombia_datos_mcp.core.envelope import Fuente, Sobre
from colombia_datos_mcp.core.errors import ErrorValidacion

from .fixtures import CENTROS_POBLADOS, MUNICIPIOS


# ------------------------------------------------------------ coordenadas --
@pytest.mark.parametrize("bruto,eje,esperado", [
    ("-75,523505", "lon", -75.523505),
    ("5,261945", "lat", 5.261945),
    ("-75,581,775", "lon", -75.581775),   # Medellín, el registro envenenado
    ("6,246,631", "lat", 6.246631),
    ("-75.581775", "lon", -75.581775),    # por si algún día cambian el separador
    ("-81,7", "lon", -81.7),              # San Andrés
])
def test_normaliza_coord(bruto, eje, esperado):
    assert normaliza_coord(bruto, eje) == pytest.approx(esperado, abs=1e-9)


def test_parser_naive_falla_donde_el_nuestro_no():
    """Documenta el bug que este módulo existe para evitar."""
    with pytest.raises(ValueError):
        float("-75,581,775".replace(",", "."))
    assert normaliza_coord("-75,581,775", "lon") == pytest.approx(-75.581775)


@pytest.mark.parametrize("malo", ["", "abc", None, "0", "-95,5", "45,0"])
def test_rechaza_coordenadas_imposibles(malo):
    with pytest.raises(ErrorValidacion):
        normaliza_coord(malo, "lon")


def test_medellin_coincide_entre_las_dos_fuentes():
    """El mismo punto llega bien en gdxc-w37w y corrupto en xaxy-8nri."""
    cab = next(f for f in CENTROS_POBLADOS if f["tipo_centro_poblado"] == "CM")
    muni = next(f for f in MUNICIPIOS if f["cod_mpio"] == "05001")
    assert normaliza_par(cab) == pytest.approx(normaliza_par(muni), abs=1e-6)


def test_normaliza_par_devuelve_none_sin_reventar():
    assert normaliza_par({"longitud": "", "latitud": ""}) is None


# ---------------------------------------------------------------- formato --
def test_moneda_colombiana():
    assert fmt.moneda("12500000") == "$12.500.000"
    assert fmt.moneda(None) == "-"


def test_fecha_floating_timestamp():
    assert fmt.fecha("2025-05-02T00:00:00.000") == "2025-05-02"
    assert fmt.fecha("24/03/2026") == "2026-03-24"


def test_limpia_texto_repara_el_mojibake_de_origen():
    # El plegado de acentos vive en `core.texto`: tenerlo también aquí, con un
    # nombre que invitaba a construir `like` con él, fue el origen del defecto.
    assert fmt.limpia_texto("Ejecución") == "Ejecución"
    assert fmt.limpia_texto("  doble   espacio ") == "doble espacio"


def test_tabla_vacia_no_es_tabla_vacia():
    assert "Sin resultados" in fmt.tabla_markdown([])


# ------------------------------------------------------------ presupuesto --
def test_degradacion_de_niveles():
    assert siguiente_nivel(Detalle.COMPLETO) is Detalle.RESUMEN
    assert siguiente_nivel(Detalle.RESUMEN) is Detalle.CONTEO
    assert siguiente_nivel(Detalle.CONTEO) is None


def test_ajusta_filas_recorta_hasta_caber():
    filas = [{"x": "y" * 200} for _ in range(200)]
    render = lambda fs: "\n".join(str(f) for f in fs)
    recortadas, texto, recortado = ajusta_filas(filas, render, presupuesto=500)
    assert recortado is True
    assert 0 < len(recortadas) < len(filas)
    assert estima_tokens(texto) <= 500


def test_ajusta_filas_no_toca_lo_que_ya_cabe():
    filas = [{"x": 1}]
    _, _, recortado = ajusta_filas(filas, lambda fs: str(fs), presupuesto=6000)
    assert recortado is False


# ------------------------------------------------------------------ sobre --
def test_siguiente_offset_es_honesto():
    """Nunca se anuncia un salto mayor a lo realmente devuelto (§6.3)."""
    s = Sobre(datos=[{"a": i} for i in range(20)], total_coincidencias=8412, offset=0)
    assert s.devueltos == 20
    assert s.siguiente_offset == 20   # no 200, aunque se hubieran descargado 200


def test_sin_siguiente_pagina_al_final():
    s = Sobre(datos=[{"a": 1}], total_coincidencias=1, offset=0)
    assert s.siguiente_offset is None


def test_sobre_advierte_cuando_solo_muestra_una_parte():
    s = Sobre(datos=[{"a": i} for i in range(5)], total_coincidencias=1000,
              consulta="https://x", fuente=Fuente(id="jbjy-vk9h", nombre="SECOP II"))
    salida = s.render(lambda f: fmt.tabla_markdown(f))
    assert "5 de 1000" in " ".join(s.advertencias)
    assert "agregación" in " ".join(s.advertencias)
    assert "https://x" in salida["texto"]
    assert salida["estructurado"]["_meta"]["total_coincidencias"] == 1000


def test_sobre_marca_truncado_y_dice_que_hacer():
    s = Sobre(datos=[{"x": "y" * 400} for _ in range(100)], total_coincidencias=100)
    s.render(lambda f: fmt.tabla_markdown(f), presupuesto=300)
    assert s.truncado is True
    assert any("conteo" in a for a in s.advertencias)


# ------------------------------------------------- formato moneda/conteo --
def test_el_nombre_del_campo_decide_moneda_o_conteo():
    assert fmt.es_monetario("valor_del_contrato")
    assert fmt.es_monetario("cuantia_proceso")
    # "valor total" es dinero; "total" a secas es el alias de count(*).
    assert fmt.es_monetario("valor_total_esperado")
    assert not fmt.es_conteo("valor_total_esperado")
    assert fmt.es_conteo("total")
    assert fmt.es_conteo("contratos")
    assert not fmt.es_monetario("total")


# ------------------------------------------------------------------ HTTP --
def test_retry_after_se_lee_cuando_la_fuente_lo_da():
    import httpx

    from colombia_datos_mcp.core.http import _retry_after

    def resp(cabeceras):
        return httpx.Response(429, headers=cabeceras)

    assert _retry_after(resp({"Retry-After": "12"})) == 12.0
    assert _retry_after(resp({})) is None
    # La forma con fecha HTTP no se adivina: mejor el backoff propio.
    assert _retry_after(resp({"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})) is None


async def test_no_se_espera_despues_del_ultimo_intento(monkeypatch):
    """Dormir tras el intento final solo retrasaba el error sin cambiarlo."""
    import httpx

    from colombia_datos_mcp.core import http as mod

    esperas = []

    async def falso_sleep(s):
        esperas.append(s)

    monkeypatch.setattr(mod.asyncio, "sleep", falso_sleep)
    monkeypatch.setattr(mod, "MAX_REINTENTOS", 3)

    class ClienteQueFalla:
        is_closed = False

        async def get(self, url, params=None, headers=None):
            return httpx.Response(503, text="caida")

    cliente = mod.ClienteHTTP()
    monkeypatch.setattr(cliente, "_asegura_cliente", lambda: _async(ClienteQueFalla()))

    with pytest.raises(Exception):
        await cliente.get_json("https://ejemplo.co/x")
    # 3 intentos => a lo sumo 2 esperas entre ellos, nunca 3.
    assert len([e for e in esperas if e]) <= 2


async def _async(valor):
    return valor


# ----------------------------------------------------------------- caché --
async def test_el_fallo_cacheado_no_deja_una_excepcion_sin_recoger(tmp_path):
    """Un futuro con excepción que nadie espera ensucia stderr con
    'Future exception was never retrieved', y en stdio eso corrompe el canal."""
    import asyncio

    from colombia_datos_mcp.core.cache import Cache

    c = Cache(dir_disco=tmp_path / "cache")

    async def revienta():
        raise RuntimeError("la fuente falló")

    with pytest.raises(RuntimeError):
        await c.obtener_o_calcular(("k",), revienta)

    await asyncio.sleep(0)
    assert not c._en_vuelo  # el registro en vuelo se limpia siempre
