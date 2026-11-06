"""Geometría municipal y departamental.

**Sigue sin haber endpoint oficial utilizable, pero ya no por la razón de
antes, y la diferencia importa.** El servicio nacional del IGAC
—`atlas/politicoadministrativo`— **volvió a responder** el 05-nov-2026 después
de meses de HTTP 500: contesta 200 con ArcGIS Server 11.3 y se anuncia como
«División Político-Administrativa» del Atlas de Colombia Edición 2024. Lo que
volvió, sin embargo, es su documento de metadatos, no el dato que hace falta:

- **De sus seis capas ninguna es municipal.** Publica transporte terrestre,
  distritos, capitales, áreas metropolitanas y departamentos. Los 1.122
  polígonos municipales no están ahí, y son la granularidad que este módulo
  existe para servir.
- **No hay `FeatureServer`**, que es la vía para consultar por atributo y traer
  GeoJSON paginado: la extensión no está instalada («Server object extension
  'featureserver' not found») y lo dice **con un HTTP 200 y el error dentro del
  cuerpo**, que es una trampa aparte — `core/http.py` juzga por el status. Ni el
  mensaje es estable: cuando el servicio está cargado contesta a los 60 s con el
  timeout en vez de con eso, o sea que a veces ni comprueba si la extensión
  existe. Solo
  `MapServer`, sobre una caché de teselas (`singleFusedMapCache`), y su `/query`
  es lento y poco de fiar: el volcado entero de la capa departamental acertó
  **2 de 5** intentos secuenciales —33 MB en ~9 s cuando salió— y paginar fue
  peor, **1 de 5** páginas, porque `resultOffset>0` no funcionó ni una vez. El
  resto murió con 503 «Wait timeout for the request exceeded» a los 60 s.
- **Las capas municipales que sí existen son temáticas** y tampoco se pueden
  consultar: `atlas/potmunicipal` (`COD_MPIO`, `NOM_MPIO`) y
  `ordenamientoterritorial/clasificacionsegunley617del2000` (`MpCodigo`,
  `MpNombre`) fallaron las tres formas de consulta —recuento, atributos sin
  geometría y dos rasgos con geometría— con el mismo 503, seis de seis, pedidas
  de una en una con tres segundos entre ellas.
- La carpeta `limites` sigue teniendo **un solo servicio**, territorios cedidos,
  y de los 952 de `carto` ninguno casa con municipio ni con límite.

Y aunque la capa departamental respondiera siempre, no serviría de atajo: sus
campos son `DeCodigo`/`DeNombre`, no los del MGN, y sus nombres vienen en Title
Case y no en mayúsculas. Pero el defecto que de verdad muerde es el recuento.
Devuelve **33 registros y DIVIPOLA tiene 33 departamentos**, así que comparar
totales da la migración por buena — y los conjuntos no son el mismo: sobra
«Area en Litigio Cauca - Huila» con código `00` y **falta Bogotá D.C. (`11`)**,
que para el IGAC es un distrito y no un departamento. La intersección son 32.
Unir por código habría metido un polígono fantasma y perdido la capital, en
silencio y sin que ningún recuento chistara.

`datos.gov.co` tampoco publica los límites como dataset: la búsqueda en el
catálogo con `only=map` y `only=geo` devuelve cero.

Así que la geometría se sigue descargando de una **réplica del Marco
Geoestadístico Nacional 2018 del DANE**, capa municipal política, simplificada.
No es un respaldo: es la única fuente de los 1.122 polígonos. La URL es
configurable con `CO_GEOMETRIA_URL` justamente porque una réplica de terceros no
es una garantía — pero ojo, apuntarla a la capa del IGAC no funciona, y
`_valida` lo rechaza diciendo que esos rasgos no son del MGN y nombrando los
campos que les faltan, en vez de dejar pasar un mapa vacío.

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
    "del IGAC —que desde el 05-nov-2026 vuelve a responder— no publica capa "
    "municipal en atlas/politicoadministrativo, y las capas municipales "
    "temáticas de sus otros servicios no respondieron a ninguna de las "
    "consultas probadas"
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
    propiedades = (fs[0].get("properties") or {}) if fs else {}
    faltan = [c for c in CAMPOS.values() if c not in propiedades]

    if len(fs) < 1000:
        # Quedarse corto tiene dos causas que conviene no confundir, porque
        # llevan a arreglos distintos. Una réplica que se trunca sigue trayendo
        # los campos del MGN: ahí el aviso correcto es que cambió de contenido.
        # Pero si tampoco trae los campos, lo que hay al otro lado de
        # CO_GEOMETRIA_URL no es el MGN —el error fácil es apuntarla a la capa
        # departamental del IGAC, que también es un FeatureCollection de
        # polígonos—, y culpar a la réplica manda a revisar donde no es.
        if fs and faltan:
            raise ErrorFuenteCaida(
                f"La geometría trae {len(fs)} rasgos y no son del MGN: les "
                f"faltan {', '.join(faltan)}.",
                "Esto no es la capa municipal del MGN. Si CO_GEOMETRIA_URL "
                "apunta a otra fuente —la capa departamental del IGAC, por "
                "ejemplo— no sirve: sin MPIO_CCNCT no se puede unir por "
                "código DIVIPOLA.",
            )
        raise ErrorFuenteCaida(
            f"La geometría trae {len(fs)} municipios; se esperaban ~1.122.",
            "La réplica cambió de contenido. Ajusta CO_GEOMETRIA_URL.",
        )
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
