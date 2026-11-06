"""Adaptador de geometría y `co_geo_limites`. Sin red."""

import pytest

from colombia_datos_mcp.adapters import geometria
from colombia_datos_mcp.core.cache import Cache
from colombia_datos_mcp.core.errors import ErrorFuenteCaida, ErrorValidacion
from colombia_datos_mcp.domain import exportar, geo

from .fixtures import (
    DIVIPOLA_CODIGOS_DEPARTAMENTO,
    IGAC_CAMPOS_DEPARTAMENTO,
    IGAC_CODIGOS_DEPARTAMENTO,
    IGAC_CODIGOS_DEPARTAMENTO_OTRO_VOLCADO,
    IGAC_DEPARTAMENTOS,
    IGAC_ERROR_SIN_FEATURESERVER,
    IGAC_ERROR_TIMEOUT,
    IGAC_SERVICIO,
)


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


async def test_advierte_de_que_la_geometria_esta_simplificada(monkeypatch):
    """Mediana de 10 vértices por municipio: vale para colorear, no para medir."""
    _instala(monkeypatch)
    salida = await geo.limites(nivel="departamento")
    assert "SIMPLIFICADA" in salida["texto"]
    assert "medir áreas" in salida["texto"]


# =========================================================================
# El IGAC, con sus respuestas reales del 05-nov-2026 (ver `fixtures.py`).
#
# El servicio oficial volvió después de meses de HTTP 500, así que la pregunta
# «¿ya se puede migrar?» se responde aquí sin red y queda respondida por
# escrito, con el dato que la contesta delante.
# =========================================================================
async def test_el_servicio_del_igac_no_trae_ninguna_capa_municipal():
    """La razón entera por la que la geometría no migró.

    Seis capas, y la de menor granularidad es `Departamento`. Sin capa
    municipal no hay nada que migrar: `co_geo_limites` es municipal de raíz y
    el nivel departamental se deriva agrupando municipios.
    """
    capas = {c["name"]: c["geometryType"] for c in IGAC_SERVICIO["layers"]}
    assert len(capas) == 6, capas
    assert capas["Departamento"] == "esriGeometryPolygon"
    assert not [n for n in capas if "municip" in n.lower() or "mpio" in n.lower()]


async def test_apuntar_la_url_a_la_capa_del_igac_falla_con_mensaje_claro(monkeypatch):
    """`CO_GEOMETRIA_URL` sigue funcionando, y por eso esto importa.

    Alguien leerá que el IGAC ya responde y apuntará la variable a su capa
    departamental. Son los dos un `FeatureCollection` de polígonos, así que el
    cambio parece inocuo: lo que no casa son los nombres de campo. `_valida`
    tiene que rechazarlo nombrando los campos que faltan, no dejar pasar la
    colección para que `domain/geo.py` reviente luego con un `KeyError`
    ilegible.

    La carga real trae 33 rasgos, muy por debajo de 1.122, así que el control
    de cantidad salta primero. Pero quedarse corto **y** no traer los campos
    del MGN no es lo mismo que una réplica truncada, y el mensaje lo distingue:
    culpar a la réplica mandaría a revisar donde no está el problema.
    """
    _instala(monkeypatch, IGAC_DEPARTAMENTOS)
    with pytest.raises(ErrorFuenteCaida) as exc:
        await geometria.cargar()
    mensaje = str(exc.value)
    assert "3" in mensaje, mensaje
    assert "no son del MGN" in mensaje, mensaje
    for campo in geometria.CAMPOS.values():
        assert campo in mensaje, f"{campo} no se nombra: {mensaje}"
    # Y la sugerencia señala a CO_GEOMETRIA_URL, no a la réplica.
    assert "CO_GEOMETRIA_URL" in exc.value.sugerencia
    assert "réplica" not in exc.value.sugerencia.lower()


async def test_una_replica_truncada_si_culpa_a_la_replica(monkeypatch):
    """El otro camino del mismo control, que no hay que confundir.

    Si la colección se queda corta pero **sí** trae los campos del MGN, lo que
    pasó es que la réplica cambió de contenido, y eso es lo que dice. Es la
    distinción que el mensaje de arriba existe para no borrar.
    """
    _instala(monkeypatch, _coleccion(n=20))
    with pytest.raises(ErrorFuenteCaida) as exc:
        await geometria.cargar()
    assert "1.122" in str(exc.value) or "1122" in str(exc.value)
    assert "no son del MGN" not in str(exc.value)
    assert "réplica" in exc.value.sugerencia.lower()


async def test_la_capa_del_igac_no_trae_un_solo_campo_de_los_que_cita_el_adaptador(
        monkeypatch):
    """Aunque el IGAC llegara a servir 1.122 registros, seguiría sin casar.

    Se le pasa el recuento —replicando la colección real hasta 1.122— para que
    la validación llegue a mirar los campos, que es lo que se quiere probar.
    """
    rasgos = IGAC_DEPARTAMENTOS["features"]
    inflada = {"type": "FeatureCollection",
               "features": [rasgos[i % len(rasgos)] for i in range(1122)]}
    _instala(monkeypatch, inflada)
    with pytest.raises(ErrorFuenteCaida) as exc:
        await geometria.cargar()
    mensaje = str(exc.value)
    assert "MPIO_CCNCT" in mensaje, mensaje
    for campo in geometria.CAMPOS.values():
        assert campo in mensaje, f"{campo} no se nombra: {mensaje}"


async def test_los_campos_del_igac_y_los_del_mgn_no_se_solapan_en_nada():
    """Documenta la incompatibilidad con la fuente a la vista.

    `DeCodigo`/`DeNombre` contra `DPTO_CCDGO`/`DPTO_CNMBR`. Ni un nombre en
    común, así que no hay migración «solo cambiando la URL».
    """
    del_igac = {c["name"] for c in IGAC_CAMPOS_DEPARTAMENTO}
    assert {"DeCodigo", "DeNombre"} <= del_igac
    assert not (del_igac & set(geometria.CAMPOS.values()))


async def test_los_33_del_igac_cuadran_en_total_y_no_son_los_mismos_33():
    """**El defecto más caro del servicio, y el que habría pasado la revisión.**

    La capa devuelve 33 registros y DIVIPOLA tiene 33 departamentos. Un
    `assert len(...) == 33` pasa, así que el recuento —que es la comprobación
    que cualquiera escribiría— da la migración por buena.

    Y los conjuntos no son el mismo: sobra «Area en Litigio Cauca - Huila» con
    código `00`, que no es un departamento, y **falta Bogotá D.C. (`11`)**,
    porque para el IGAC es un distrito y no un departamento. La intersección son
    32. Unir por código habría metido un polígono fantasma y dejado la capital
    del país sin contorno, sin que ningún total lo delatara.
    """
    igac, divipola = set(IGAC_CODIGOS_DEPARTAMENTO), set(DIVIPOLA_CODIGOS_DEPARTAMENTO)
    assert len(igac) == len(divipola) == 33, "los totales tienen que cuadrar"
    assert igac != divipola, "si llegan a coincidir, se puede reevaluar la migración"
    assert igac - divipola == {"00"}, igac - divipola
    assert divipola - igac == {"11"}, divipola - igac
    assert len(igac & divipola) == 32


async def test_el_igac_no_devuelve_los_departamentos_en_un_orden_estable():
    """Por qué paginar esta capa sería inseguro aunque respondiera siempre.

    Dos volcados del mismo `where=1=1`, un día de diferencia, devuelven el mismo
    conjunto en orden distinto: `52` salió decimoséptimo en uno y último en el
    otro. ArcGIS no garantiza orden sin `ORDER BY`, así que `resultOffset`
    sobre esta capa perdería y duplicaría rasgos en silencio. Es un argumento
    aparte del de la fiabilidad, y sigue en pie si algún día la arreglan.
    """
    a, b = IGAC_CODIGOS_DEPARTAMENTO, IGAC_CODIGOS_DEPARTAMENTO_OTRO_VOLCADO
    assert set(a) == set(b), "el conjunto sí es el mismo"
    assert a != b, "si el orden se vuelve estable, se puede reevaluar paginar"
    assert a.index("52") != b.index("52")


async def test_el_registro_sobrante_del_igac_es_un_area_en_litigio():
    """Qué es el `00`, con el nombre que la fuente le da."""
    props = [f["properties"] for f in IGAC_DEPARTAMENTOS["features"]]
    litigio = next(p for p in props if p["DeCodigo"] == "00")
    assert "Litigio" in litigio["DeNombre"], litigio
    assert litigio["DeCodigo"] == IGAC_CODIGOS_DEPARTAMENTO[0], "y llega primero"


async def test_los_nombres_del_igac_vienen_en_title_case():
    """El MGN y DIVIPOLA los traen en MAYÚSCULAS. `core/texto.py` pliega
    acentos, no caja, así que la diferencia se vería en cualquier tabla."""
    props = [f["properties"] for f in IGAC_DEPARTAMENTOS["features"]]
    antioquia = next(p for p in props if p["DeCodigo"] == "05")
    assert antioquia["DeNombre"] == "Antioquia"
    assert antioquia["DeNombre"] != antioquia["DeNombre"].upper()


async def test_los_errores_del_igac_llegan_dentro_de_un_cuerpo_json():
    """Por qué un 200 no demuestra que el servicio sirva.

    Los dos fallos del servicio —el timeout de las consultas en frío y el
    FeatureServer que no existe— viajan como `error.code` **dentro** del JSON,
    con HTTP 200. `core/http.py` decide reintentos y errores por el status, así
    que se le colarían como válidos: cualquier adaptador ArcGIS futuro tiene que
    mirar la clave `error` del cuerpo, no solo el código de la respuesta.
    """
    assert IGAC_ERROR_TIMEOUT["error"]["code"] == 503
    assert "Wait timeout" in IGAC_ERROR_TIMEOUT["error"]["message"]
    assert IGAC_ERROR_SIN_FEATURESERVER["error"]["code"] == 500
    assert "featureserver" in IGAC_ERROR_SIN_FEATURESERVER["error"]["message"].lower()
