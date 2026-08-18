"""Criminalidad: la familia de datasets de MinDefensa.

Son 37 datasets con el mismo esquema (`cod_muni`, `fecha_hecho`, `cantidad`),
pero **no son la misma cosa**, y ahí está el trabajo de este módulo:

* **Solo se exponen los delitos.** Los datasets operativos —incautaciones,
  erradicación, minas intervenidas— comparten esquema y no comparten unidad: en
  `ERRADICACIÓN` la `cantidad` son HECTÁREAS, y en las incautaciones la columna
  `unidad` trae valores como `0.002`. Sumarlos junto a homicidios sería sumar
  kilos con personas, así que se quedan fuera del registro.
* **`cantidad` no siempre es uno.** Un hecho puede tener varias víctimas: en
  homicidio hay 342.971 filas y 343.680 víctimas. Se suma `cantidad`, nunca se
  cuentan filas.
* **Casos registrados no son delitos cometidos.** Una subida en extorsión o en
  violencia intrafamiliar puede ser más denuncia y no más delito. El sobre lo
  advierte siempre, porque es la confusión que arruina cualquier lectura.
* **El año base decide el titular.** El secuestro subió 259 % contra 2017 y bajó
  67 % contra 2003: la misma serie. `comparar` obliga a declarar los dos años y
  el sobre recuerda que la elección no es neutral.
"""

from __future__ import annotations

from ..adapters import socrata
from ..core import format as fmt
from ..core import texto
from ..core.cache import TTL_METADATOS, cache
from ..core.envelope import Fuente, Sobre
from ..core.errors import ErrorValidacion
from ..registry import datasets as reg

_ATRIB = "Ministerio de Defensa Nacional - MinDefensa"
_LIC = "CC BY-SA 4.0"

AVISO_REGISTRO = (
    "Son casos REGISTRADOS, no delitos cometidos. Una subida puede ser más "
    "denuncia y no más delito; el homicidio es el indicador menos sensible a eso."
)


def _ds(delito: str) -> reg.Dataset:
    clave = texto.plegar(delito).lower().replace(" ", "_").replace("-", "_")
    ds = reg.CRIMEN.get(clave)
    if not ds:
        raise ErrorValidacion(
            f"Delito desconocido: {delito!r}.",
            "Disponibles: " + ", ".join(sorted(reg.CRIMEN)),
        )
    return ds


async def _corte(ds: reg.Dataset) -> str | None:
    """Última fecha con datos. Cada dataset corta por su cuenta.

    Sin esto se comparan años incompletos con años cerrados sin saberlo, que es
    la forma más fácil de inventarse una caída.
    """

    async def _traer():
        r = await socrata.consultar(ds.id, seleccionar="max(fecha_hecho) as h", limite=1)
        filas = r["filas"]
        return filas[0]["h"][:10] if filas and filas[0].get("h") else None

    return await cache.obtener_o_calcular(
        ("corte", ds.id), _traer, ttl=TTL_METADATOS, en_disco=True
    )


def _fuente(ds: reg.Dataset) -> Fuente:
    return Fuente(id=ds.id, nombre=ds.nombre, licencia=_LIC, atribucion=_ATRIB)


def _avisos_dataset(sobre: Sobre, ds: reg.Dataset, corte: str | None) -> None:
    sobre.advertir(f"Unidad de análisis: {ds.unidad}. Se suma `cantidad`, no filas.")
    sobre.advertir(AVISO_REGISTRO)
    for n in ds.notas:
        sobre.advertir(n)
    if corte:
        sobre.advertir(
            f"Los datos de este dataset cortan el {corte}: el último año está "
            "incompleto y no es comparable con años cerrados."
        )


async def serie(delito: str, desde: int | None = None, hasta: int | None = None,
                agrupar_por: str = "anio", formato: str = "tabla", grafica: bool = True):
    """Serie temporal de un delito. Un año por fila, o un mes."""
    if agrupar_por not in ("anio", "mes"):
        raise ErrorValidacion(
            "agrupar_por debe ser 'anio' o 'mes'.",
            "Con 'mes' acota el rango: veinte años de meses son 280 filas.",
        )
    ds = _ds(delito)
    expr = "date_extract_y(fecha_hecho)" if agrupar_por == "anio" else \
           "date_trunc_ym(fecha_hecho)"
    partes = []
    if desde:
        partes.append(f"fecha_hecho >= '{int(desde)}-01-01'")
    if hasta:
        partes.append(f"fecha_hecho < '{int(hasta) + 1}-01-01'")
    donde = " AND ".join(partes) or None

    r = await socrata.consultar(
        ds.id, seleccionar=f"{expr} as periodo, sum(cantidad) as casos",
        donde=donde, agrupar=expr, ordenar="periodo", limite=400)
    corte = await _corte(ds)

    crudos = [fmt.a_numero(f.get("casos")) or 0 for f in r["filas"]]
    filas = [{"periodo": str(f.get("periodo") or "")[:7] if agrupar_por == "mes"
              else str(f.get("periodo") or "")[:4],
              "casos": fmt.numero(f.get("casos"))} for f in r["filas"]]
    if grafica and formato == "tabla" and filas:
        for fila, barra in zip(filas, fmt.barras(crudos)):
            fila["gráfica"] = barra

    sobre = Sobre(datos=filas, total_coincidencias=len(filas), orden="periodo",
                  consulta=r["consulta"], fuente=_fuente(ds))
    _avisos_dataset(sobre, ds, corte)
    if crudos and len(crudos) > 1:
        sobre.advertir(
            f"Máximo de la serie: {fmt.numero(max(crudos))}. Mínimo: "
            f"{fmt.numero(min(crudos))}. Elegir uno u otro como base cambia "
            "por completo el porcentaje que salga."
        )
    return sobre.render(lambda f: fmt.tabla_markdown(f), formato=formato)


async def por_municipio(delito: str, anio: int, limite: int = 20,
                        departamento: str | None = None, formato: str = "tabla",
                        grafica: bool = True):
    """Los municipios con más casos de un delito en un año."""
    ds = _ds(delito)
    partes = [f"fecha_hecho >= '{int(anio)}-01-01'",
              f"fecha_hecho < '{int(anio) + 1}-01-01'"]
    avisos = []
    if departamento:
        filtro, valores, _t = await socrata.filtro_categorico(ds.id, "departamento", departamento)
        if filtro is None:
            sobre = Sobre(datos=[], total_coincidencias=0, fuente=_fuente(ds))
            sobre.advertir(
                f"«{departamento}» no corresponde a ningún departamento en este "
                "dataset. No es un fallo de la fuente."
            )
            return sobre.render(lambda _f: "_Sin coincidencias._")
        partes.append(filtro)
        if len(valores) > 1:
            avisos.append(f"«{departamento}» resolvió a: {', '.join(valores[:6])}")

    r = await socrata.consultar(
        ds.id, seleccionar="municipio, departamento, cod_muni, sum(cantidad) as casos",
        donde=" AND ".join(partes), agrupar="municipio, departamento, cod_muni",
        ordenar="casos DESC", limite=min(int(limite), 100))
    corte = await _corte(ds)

    crudos = [fmt.a_numero(f.get("casos")) or 0 for f in r["filas"]]
    filas = [{"municipio": fmt.limpia_texto(f.get("municipio")),
              "departamento": fmt.limpia_texto(f.get("departamento")),
              "cod_mpio": f.get("cod_muni"),
              "casos": fmt.numero(f.get("casos"))} for f in r["filas"]]
    if grafica and formato == "tabla" and filas:
        for fila, barra in zip(filas, fmt.barras(crudos)):
            fila["gráfica"] = barra

    sobre = Sobre(datos=filas, total_coincidencias=len(filas), orden="casos DESC",
                  consulta=r["consulta"], fuente=_fuente(ds))
    for a in avisos:
        sobre.advertir(a)
    _avisos_dataset(sobre, ds, corte)
    sobre.advertir(
        "Conteos absolutos, no tasas: la fuente no publica población municipal, "
        "así que esta lista se parece mucho a una lista de municipios grandes. "
        "`cod_mpio` es la clave DIVIPOLA para cruzar con otras fuentes."
    )
    return sobre.render(lambda f: fmt.tabla_markdown(f), formato=formato)


async def comparar(anio_a: int, anio_b: int, delitos: str = "", formato: str = "tabla"):
    """Compara varios delitos entre dos años. El orden de los años importa."""
    claves = [c.strip() for c in delitos.split(",") if c.strip()] or list(reg.CRIMEN)
    if len(claves) > 12:
        raise ErrorValidacion(
            f"Demasiados delitos ({len(claves)}): son dos consultas por cada uno.",
            "Pide como mucho 12, o deja `delitos` vacío para la selección corta.",
        )
    filas, incompletos = [], []
    for clave in claves:
        ds = _ds(clave)
        r = await socrata.consultar(
            ds.id, seleccionar="date_extract_y(fecha_hecho) as a, sum(cantidad) as casos",
            donde=f"fecha_hecho >= '{min(anio_a, anio_b)}-01-01' AND "
                  f"fecha_hecho < '{max(anio_a, anio_b) + 1}-01-01'",
            agrupar="date_extract_y(fecha_hecho)", ordenar="a", limite=100)
        por_anio = {int(fmt.a_numero(f["a"])): fmt.a_numero(f.get("casos")) or 0
                    for f in r["filas"] if f.get("a")}
        va, vb = por_anio.get(int(anio_a)), por_anio.get(int(anio_b))
        if not va or vb is None:
            incompletos.append(ds.nombre)
            continue
        filas.append({"delito": ds.nombre.title(), str(anio_a): fmt.numero(va),
                      str(anio_b): fmt.numero(vb),
                      "cambio": f"{(vb / va - 1) * 100:+.0f} %"})
    filas.sort(key=lambda f: -float(f["cambio"].replace(" %", "").replace("+", "")))

    sobre = Sobre(datos=filas, total_coincidencias=len(filas),
                  orden=f"cambio {anio_a}→{anio_b} DESC",
                  fuente=Fuente(id="MinDefensa", nombre="Delitos comparados",
                                licencia=_LIC, atribucion=_ATRIB))
    sobre.advertir(AVISO_REGISTRO)
    sobre.advertir(
        f"El resultado depende de qué año pongas de base. Contra {anio_a} sale "
        "una cifra; contra otro año, otra distinta, y ambas son ciertas. Mira la "
        "serie completa con co_crimen_serie antes de citar un porcentaje."
    )
    if incompletos:
        sobre.advertir(
            "Sin datos en alguno de los dos años, quedan fuera: "
            + ", ".join(incompletos)
        )
    return sobre.render(lambda f: fmt.tabla_markdown(f), formato=formato)
