"""Módulo de criminalidad. Sin red."""

import pytest

from colombia_datos_mcp.adapters import socrata
from colombia_datos_mcp.core.cache import Cache
from colombia_datos_mcp.core.errors import ErrorValidacion
from colombia_datos_mcp.domain import crimen
from colombia_datos_mcp.registry import datasets as reg

from .test_dominio import RedFalsa


@pytest.fixture(autouse=True)
def cache_limpia(monkeypatch, tmp_path):
    import colombia_datos_mcp.core.cache as mod
    fresca = Cache(dir_disco=tmp_path / "cache")
    monkeypatch.setattr(mod, "cache", fresca)
    monkeypatch.setattr(socrata, "cache", fresca)
    monkeypatch.setattr(crimen, "cache", fresca)


def _red(params):
    sel = params.get("$select", "")
    if "max(fecha_hecho)" in sel:
        return [{"h": "2026-07-31T00:00:00.000"}]
    if "date_extract_y" in sel:
        # `serie` pide el alias `periodo` y `comparar` el alias `a`. Antes se
        # devolvían las dos formas juntas, así que `serie` recibía además tres
        # filas SIN clave `periodo`: su última fila quedaba vacía y tapaba
        # cualquier comprobación sobre el último año.
        clave = "periodo" if " as periodo" in sel else "a"
        # 2026 lleva el valor más bajo a propósito: los datos cortan el 31 de
        # julio, así que si alguien lo cuela en el mínimo, la prueba lo caza.
        anios = [("2017", "195"), ("2025", "701"), ("2026", "120")]
        # Y se respeta el `hasta`: una fuente falsa que ignora el filtro no
        # permite comprobar qué pasa cuando la serie SÍ acaba en año cerrado.
        import re
        tope = re.search(r"fecha_hecho < '(\d{4})-", params.get("$where", "") or "")
        if tope:
            anios = [(a, c) for a, c in anios if a < tope.group(1)]
        return [{clave: a, "casos": c} for a, c in anios]
    return [{"municipio": "CUCUTA", "departamento": "NORTE DE SANTANDER",
             "cod_muni": "54001", "casos": "273"}]


def _instala(monkeypatch):
    red = RedFalsa({"/resource/": _red})
    monkeypatch.setattr(socrata, "_http", red)
    return red


# ------------------------------------------------------------- registro ---
def test_el_registro_solo_trae_delitos_no_operativos():
    """Los datasets de incautación y erradicación comparten esquema pero no
    unidad: en ERRADICACIÓN la `cantidad` son hectáreas. Mezclarlos con
    homicidios produce sumas sin significado."""
    ids = {d.id for d in reg.CRIMEN.values()}
    for operativo in ("p72f-qcvk", "26zg-9p9r", "g228-vp9d", "gr35-i7pm"):
        assert operativo not in ids, f"{operativo} es operativo, no delito"
    assert len(reg.CRIMEN) >= 20


def test_los_dos_hurtos_duplicados_estan_advertidos():
    """«HURTO A COMERCIO» y «HURTO A RESIDENCIAS» son el mismo dato con dos
    títulos: sumarlos duplicaría la cifra."""
    for clave in ("hurto_comercio", "hurto_residencias"):
        notas = " ".join(reg.CRIMEN[clave].notas).lower()
        assert "mismo dato" in notas or "idéntico" in notas


def test_cada_delito_declara_su_unidad_de_analisis():
    for clave, ds in reg.CRIMEN.items():
        assert ds.unidad and len(ds.unidad) > 8, clave
        assert ds.campos_clave.get("cantidad") == "cantidad", clave


# --------------------------------------------------------------- serie ----
async def test_la_serie_suma_cantidad_y_no_cuenta_filas(monkeypatch):
    """Un hecho puede tener varias víctimas: homicidio tiene 342.971 filas y
    343.680 víctimas."""
    red = _instala(monkeypatch)
    await crimen.serie("homicidio", desde=2017)
    sel = [p["$select"] for _, p in red.llamadas if "sum(cantidad)" in p.get("$select", "")]
    assert sel and "count(*)" not in sel[0]


async def test_la_serie_advierte_que_son_casos_registrados(monkeypatch):
    _instala(monkeypatch)
    salida = await crimen.serie("extorsion")
    assert "REGISTRADOS" in salida["texto"]


async def test_la_serie_avisa_del_corte_de_datos(monkeypatch):
    """Comparar un año incompleto con años cerrados inventa caídas."""
    _instala(monkeypatch)
    salida = await crimen.serie("homicidio")
    assert "2026-07-31" in salida["texto"]
    assert "INCOMPLETO" in salida["texto"]


async def test_no_avisa_de_incompleto_si_la_serie_acaba_en_un_ano_cerrado(monkeypatch):
    """La falsa alarma es cara: repetida, enseña a ignorar el aviso, y entonces
    no sirve el día que es verdad. Antes se avisaba siempre que existiera fecha
    de corte, aunque lo mostrado terminara en un año cerrado."""
    _instala(monkeypatch)
    salida = await crimen.serie("homicidio", hasta=2025)
    texto = salida["texto"]
    assert "2026-07-31" in texto                     # el alcance sí se declara
    assert "INCOMPLETO" not in texto, "falsa alarma: 2025 está cerrado"


async def test_el_minimo_de_la_serie_no_incluye_el_ano_a_medias(monkeypatch):
    """El aviso que existe para no elegir mal el año base ofrecía como «mínimo
    de la serie» un año que corta en julio."""
    _instala(monkeypatch)
    texto = (await crimen.serie("homicidio"))["texto"]
    assert "Mínimo: 195" in texto, "el mínimo debe salir del último año CERRADO"
    assert "Mínimo: 120" not in texto, "2026 está a medias y no puede ser el mínimo"
    assert "2026" in texto                           # pero la fila sigue ahí


async def test_comparar_avisa_si_uno_de_los_dos_anos_no_ha_cerrado(monkeypatch):
    """`co_crimen_comparar(2017, 2026)` devolvía una caída sin una sola
    advertencia: es el error fundacional del proyecto dentro de la propia
    función de comparar."""
    _instala(monkeypatch)
    texto = (await crimen.comparar(2017, 2026, delitos="homicidio"))["texto"]
    assert "ATENCIÓN" in texto and "2026" in texto and "cortan el" in texto


async def test_la_serie_recuerda_el_maximo_y_el_minimo(monkeypatch):
    """Es lo que impide citar un porcentaje sin mirar contra qué año se mide."""
    _instala(monkeypatch)
    salida = await crimen.serie("secuestro")
    assert "Máximo de la serie" in salida["texto"]


async def test_delito_desconocido_lista_los_validos(monkeypatch):
    _instala(monkeypatch)
    with pytest.raises(ErrorValidacion) as exc:
        await crimen.serie("robo de gallinas")
    assert "homicidio" in exc.value.sugerencia


async def test_el_nombre_del_delito_tolera_acentos_y_espacios(monkeypatch):
    _instala(monkeypatch)
    for variante in ("extorsión", "EXTORSION", "extorsion"):
        assert await crimen.serie(variante)


async def test_agrupar_por_invalido_se_rechaza(monkeypatch):
    _instala(monkeypatch)
    with pytest.raises(ErrorValidacion):
        await crimen.serie("homicidio", agrupar_por="semana")


# --------------------------------------------------------- por municipio --
async def test_por_municipio_devuelve_la_clave_divipola(monkeypatch):
    """Sin `cod_mpio` no se puede cruzar con geometría ni con otras fuentes."""
    _instala(monkeypatch)
    salida = await crimen.por_municipio("extorsion", 2025)
    assert salida["estructurado"]["datos"][0]["cod_mpio"] == "54001"


async def test_por_municipio_advierte_que_no_son_tasas(monkeypatch):
    """Sin población, la lista de municipios es casi una lista de los grandes."""
    _instala(monkeypatch)
    salida = await crimen.por_municipio("homicidio", 2025)
    assert "no tasas" in salida["texto"]


async def test_departamento_inexistente_no_consulta(monkeypatch):
    red = _instala(monkeypatch)
    salida = await crimen.por_municipio("homicidio", 2025, departamento="Narnia")
    assert "no corresponde a ningún departamento" in salida["texto"]


# ------------------------------------------------------------ comparar ----
async def test_comparar_ordena_por_variacion(monkeypatch):
    _instala(monkeypatch)
    salida = await crimen.comparar(2017, 2025, delitos="homicidio,secuestro")
    assert "+259 %" in salida["texto"]


async def test_comparar_advierte_que_el_ano_base_no_es_neutral(monkeypatch):
    """El secuestro subió 259 % contra 2017 y bajó 67 % contra 2003."""
    _instala(monkeypatch)
    salida = await crimen.comparar(2017, 2025, delitos="secuestro")
    assert "de qué año pongas de base" in salida["texto"]


async def test_comparar_rechaza_demasiados_delitos(monkeypatch):
    _instala(monkeypatch)
    with pytest.raises(ErrorValidacion):
        await crimen.comparar(2017, 2025, delitos=",".join(list(reg.CRIMEN)))
