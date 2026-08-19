"""Geometría municipal y departamental.

**No hay endpoint oficial utilizable, y conviene decirlo antes que nada.** El
único servicio nacional del IGAC con límites político-administrativos
—`atlas/politicoadministrativo`— devuelve HTTP 500 «Wait timeout for the
request» tanto en MapServer como en FeatureServer; su carpeta `limites` solo
contiene territorios cedidos, y de las 952 capas de `carto` ninguna es
municipal. `datos.gov.co` tampoco publica los límites como dataset: la búsqueda
en el catálogo con `only=map` y `only=geo` devuelve cero.

Así que la geometría se descarga de una **réplica del Marco Geoestadístico
Nacional 2018 del DANE**, capa municipal política, simplificada. La URL es
configurable con `CO_GEOMETRIA_URL` justamente porque una réplica de terceros no
es una garantía: si desaparece o si algún día el IGAC arregla su servicio, se
cambia por variable de entorno sin tocar código.

Se descarga una vez y se guarda en la caché de disco, así que después funciona
sin red. Cada respuesta declara la procedencia completa, porque un mapa sin
saber de dónde salió su contorno no es verificable.
"""

from __future__ import annotations

import os

from ..core.cache import TTL_METADATOS, cache
from ..core.errors import ErrorFuenteCaida
from ..core.http import ClienteHTTP

URL_GEOMETRIA = os.environ.get(
    "CO_GEOMETRIA_URL",
    "https://raw.githubusercontent.com/caticoa3/colombia_mapa/master/"
    "co_2018_MGN_MPIO_POLITICO.geojson",
)
PROCEDENCIA = (
    "Marco Geoestadístico Nacional 2018 del DANE, capa municipal política "
    "(simplificada), obtenida de una réplica pública porque el servicio oficial "
    "del IGAC no responde"
)

# Nombres de campo del MGN. Se validan al cargar: si cambian, es mejor fallar
# con un mensaje claro que producir un mapa vacío.
CAMPOS = {"codigo": "MPIO_CCNCT", "municipio": "MPIO_CNMBR",
          "cod_dpto": "DPTO_CCDGO", "departamento": "DPTO_CNMBR"}

_http = ClienteHTTP(perfil="defecto")


async def cargar() -> dict:
    """Devuelve el GeoJSON completo, cacheado 24 h en disco."""

    async def _traer():
        datos = await _http.get_json(URL_GEOMETRIA)
        _valida(datos)
        return datos

    return await cache.obtener_o_calcular(
        ("geometria", URL_GEOMETRIA), _traer, ttl=TTL_METADATOS, en_disco=True
    )


def _valida(datos) -> None:
    """Comprueba la forma antes de fiarse: una réplica puede cambiar sin avisar."""
    if not isinstance(datos, dict) or datos.get("type") != "FeatureCollection":
        raise ErrorFuenteCaida(
            "La fuente de geometría no devolvió un FeatureCollection.",
            f"Revisa CO_GEOMETRIA_URL (ahora {URL_GEOMETRIA}).",
        )
    fs = datos.get("features") or []
    if len(fs) < 1000:
        raise ErrorFuenteCaida(
            f"La geometría trae {len(fs)} municipios; se esperaban ~1.122.",
            "La réplica cambió de contenido. Ajusta CO_GEOMETRIA_URL.",
        )
    faltan = [c for c in CAMPOS.values() if c not in (fs[0].get("properties") or {})]
    if faltan:
        raise ErrorFuenteCaida(
            f"A la geometría le faltan campos: {', '.join(faltan)}.",
            "Sin MPIO_CCNCT no se puede unir por código DIVIPOLA.",
        )


def bbox(geom: dict) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []

    def rec(c):
        if c and isinstance(c[0], (int, float)):
            xs.append(c[0])
            ys.append(c[1])
        else:
            for x in c:
                rec(x)

    rec(geom["coordinates"])
    return (min(xs), min(ys), max(xs), max(ys))


def anillos(geom: dict) -> list:
    """Todos los anillos de un Polygon o MultiPolygon, sin distinguir huecos."""
    if geom["type"] == "Polygon":
        return geom["coordinates"]
    return [anillo for poly in geom["coordinates"] for anillo in poly]


async def cerrar() -> None:
    await _http.cerrar()
