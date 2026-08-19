"""Adaptador de geometría y `co_geo_limites`. Sin red."""

import pytest

from colombia_datos_mcp.adapters import geometria
from colombia_datos_mcp.core.cache import Cache
from colombia_datos_mcp.core.errors import ErrorFuenteCaida, ErrorValidacion
from colombia_datos_mcp.domain import exportar, geo


def _municipio(cod_dpto, cod, nombre, dpto, x=-75.0, y=5.0):
    return {"type": "Feature",
            "properties": {"DPTO_CCDGO": cod_dpto, "MPIO_CCNCT": cod,
                           "MPIO_CNMBR": nombre, "DPTO_CNMBR": dpto},
            "geometry": {"type": "Polygon",
                         "coordinates": [[[x, y], [x + 1, y], [x + 1, y + 1],
                                          [x, y + 1], [x, y]]]}}


def _coleccion(n=1122):
    fs = []
    for i in range(n):
        dpto = "05" if i % 2 else "27"
        nom = "CHOCÓ" if dpto == "27" else "ANTIOQUIA"
        fs.append(_municipio(dpto, f"{dpto}{i:03d}", f"MUNICIPIO {i}", nom))
    return {"type": "FeatureCollection", "features": fs}


class RedGeo:
    def __init__(self, payload):
        self.payload = payload
        self.llamadas = 0

    async def get_json(self, url, params=None, headers=None):
        self.llamadas += 1
        return self.payload


@pytest.fixture(autouse=True)
def entorno(monkeypatch, tmp_path):
    import colombia_datos_mcp.core.cache as mod
    fresca = Cache(dir_disco=tmp_path / "cache")
    monkeypatch.setattr(mod, "cache", fresca)
    monkeypatch.setattr(geometria, "cache", fresca)
    monkeypatch.setattr(exportar, "DIR_EXPORT", tmp_path / "export")
    return fresca


def _instala(monkeypatch, payload=None):
    red = RedGeo(payload if payload is not None else _coleccion())
    monkeypatch.setattr(geometria, "_http", red)
    return red


# ------------------------------------------------------------ validación --
async def test_rechaza_algo_que_no_sea_featurecollection(monkeypatch):
    """La fuente es una réplica de terceros: puede cambiar sin avisar."""
    _instala(monkeypatch, {"type": "Topology"})
    with pytest.raises(ErrorFuenteCaida):
        await geometria.cargar()


async def test_rechaza_una_coleccion_incompleta(monkeypatch):
    """Mejor fallar con un mensaje claro que dibujar un mapa con agujeros."""
    _instala(monkeypatch, _coleccion(n=20))
    with pytest.raises(ErrorFuenteCaida) as exc:
        await geometria.cargar()
    assert "1.122" in str(exc.value) or "1122" in str(exc.value)


async def test_rechaza_si_falta_el_codigo_divipola(monkeypatch):
    """Sin MPIO_CCNCT no se puede unir por código, que es todo el objetivo."""
    mala = _coleccion()
    for f in mala["features"]:
        del f["properties"]["MPIO_CCNCT"]
    _instala(monkeypatch, mala)
    with pytest.raises(ErrorFuenteCaida) as exc:
        await geometria.cargar()
    assert "MPIO_CCNCT" in str(exc.value)


async def test_la_geometria_se_cachea_y_no_se_vuelve_a_descargar(monkeypatch):
    red = _instala(monkeypatch)
    await geometria.cargar()
    await geometria.cargar()
    assert red.llamadas == 1


# --------------------------------------------------------------- filtros --
async def test_filtra_por_codigo_de_departamento(monkeypatch):
    _instala(monkeypatch)
    salida = await geo.limites(nivel="municipio", codigo="27", guardar="x")
    assert salida["estructurado"]["datos"][0]["geometrias"] == 561


async def test_filtra_por_codigo_de_municipio(monkeypatch):
    _instala(monkeypatch)
    salida = await geo.limites(nivel="municipio", codigo="27000")
    gj = salida["estructurado"]["datos"][0]
    assert len(gj["features"]) == 1


async def test_filtra_por_departamento_ignorando_acentos(monkeypatch):
    _instala(monkeypatch)
    salida = await geo.limites(nivel="municipio", codigo="27", departamento="choco",
                               guardar="x")
    assert salida["estructurado"]["datos"][0]["geometrias"] > 0


async def test_departamento_inexistente_no_revienta(monkeypatch):
    _instala(monkeypatch)
    salida = await geo.limites(nivel="municipio", departamento="Narnia")
    assert "no corresponde a ningún departamento" in salida["texto"]


# ------------------------------------------------------------ agrupación --
async def test_el_nivel_departamento_agrupa_en_multipolygon(monkeypatch):
    _instala(monkeypatch)
    salida = await geo.limites(nivel="departamento")
    fs = salida["estructurado"]["datos"][0]["features"]
    assert len(fs) == 2                       # 05 y 27
    assert fs[0]["geometry"]["type"] == "MultiPolygon"
    assert fs[0]["properties"]["municipios"] > 1


async def test_advierte_que_la_agrupacion_no_es_una_disolucion(monkeypatch):
    """Las aristas internas siguen ahí; trazar el borde las muestra."""
    _instala(monkeypatch)
    salida = await geo.limites(nivel="departamento")
    assert "aristas internas" in salida["texto"]


# ------------------------------------------------------------ contención --
async def test_sin_filtro_exige_acotar_o_guardar(monkeypatch):
    """1.122 polígonos en una respuesta reventarían al cliente."""
    _instala(monkeypatch)
    with pytest.raises(ErrorValidacion) as exc:
        await geo.limites(nivel="municipio")
    assert "guardar" in exc.value.sugerencia


async def test_guardar_escribe_geojson_y_devuelve_la_ruta(monkeypatch):
    _instala(monkeypatch)
    salida = await geo.limites(nivel="municipio", guardar="limites")
    ruta = exportar.DIR_EXPORT / "limites.geojson"
    assert ruta.exists()
    assert str(ruta) in salida["texto"]


async def test_nivel_invalido_se_rechaza(monkeypatch):
    _instala(monkeypatch)
    with pytest.raises(ErrorValidacion):
        await geo.limites(nivel="vereda")


# ----------------------------------------------------------- procedencia --
async def test_declara_de_donde_sale_la_geometria(monkeypatch):
    """No es la fuente oficial —el IGAC devuelve 500— y hay que decirlo."""
    _instala(monkeypatch)
    salida = await geo.limites(nivel="departamento")
    assert "Marco Geoestadístico Nacional 2018" in salida["texto"]
    assert "réplica" in salida["texto"]
    assert "2018" in salida["texto"]
