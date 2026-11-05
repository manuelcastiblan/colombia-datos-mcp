"""Educación: Saber 11 del ICFES y los indicadores del MinEducación.

Dos fuentes con naturalezas opuestas, y de ahí las dos reglas del módulo.

**Saber 11 es microdato individual y aquí solo sale agregado.** Son 7.109.704
filas, una por estudiante y aplicación, con género, fecha de nacimiento,
estrato de la vivienda, escolaridad de la madre y del padre, y si el hogar
tiene automóvil, lavadora o internet. Ninguna herramienta de este módulo puede
devolver la fila de un estudiante: no es que esté bloqueada, es que no existe
el camino. Agregar no es una restricción impuesta sobre la fuente, es la única
forma en que la fuente entra al servidor.

**Los puntajes son texto y el periodo mezcla dos poblaciones.** `punt_global`
está declarado y guardado como text, así que promediar exige castear. Y
`periodo` es año y semestre pegados: los que acaban en 4 son la aplicación
masiva de octubre, con ~1,1 M de estudiantes, y los que acaban en 1 son la de
marzo, con ~15 mil, que presentan sobre todo repitentes y validantes. Promediar
`20224` junto a `20221` mezcla dos poblaciones que no se parecen, así que el
módulo obliga a elegir un periodo y, cuando no se elige, toma el más reciente
masivo y lo dice.

Del MinEducación (`nudc-7mev`) sale la única población municipal del servidor,
y es solo la de 5 a 16 años: **no sirve de denominador para tasas de
criminalidad**, que es para lo que se la va a querer usar.
"""

from __future__ import annotations

from . import agregacion
from ..adapters import socrata
from ..core import format as fmt
from ..core import privacidad
from ..core.envelope import Fuente, Sobre, Total
from ..core.errors import ErrorValidacion
from ..registry import datasets as reg

_LIC = "CC BY-SA 4.0"
_ATRIB_ICFES = "Instituto Colombiano para la Evaluación de la Educación - ICFES"
_ATRIB_MEN = "Ministerio de Educación Nacional"

SABER11 = reg.EDUCACION["saber11"]
MEN = reg.EDUCACION["men_municipio"]

# Las áreas del examen, con el nombre técnico de la fuente. `punt_global` no es
# la suma de estas cinco: lleva ponderaciones distintas por área.
AREAS = {
    "global": "punt_global",
    "lectura": "punt_lectura_critica",
    "matematicas": "punt_matematicas",
    "sociales": "punt_sociales_ciudadanas",
    "naturales": "punt_c_naturales",
    "ingles": "punt_ingles",
}

GRUPOS_SABER = {
    "departamento": ("cole_depto_ubicacion", "cole_depto_ubicacion"),
    "municipio": ("cole_mcpio_ubicacion, cole_cod_mcpio_ubicacion",
                  "cole_mcpio_ubicacion, cole_cod_mcpio_ubicacion"),
    "colegio": ("cole_nombre_establecimiento, cole_cod_dane_establecimiento, "
                "cole_mcpio_ubicacion",
                "cole_nombre_establecimiento, cole_cod_dane_establecimiento, "
                "cole_mcpio_ubicacion"),
    "naturaleza": ("cole_naturaleza", "cole_naturaleza"),
    "jornada": ("cole_jornada", "cole_jornada"),
    "estrato": ("fami_estratovivienda", "fami_estratovivienda"),
    "educacion_madre": ("fami_educacionmadre", "fami_educacionmadre"),
}


async def saber11(agrupar_por: str = "departamento", periodo: str = "",
                  area: str = "global", departamento: str | None = None,
                  minimo_estudiantes: int = 20, limite: int = 20,
                  formato: str = "tabla", grafica: bool = True):
    """Promedios de Saber 11 agregados por territorio, colegio o condición social.

    `minimo_estudiantes` descarta los grupos con pocos casos. No es cosmética:
    un colegio con tres estudiantes produce un promedio que parece comparable
    con el de uno de mil y no lo es, y además acerca el agregado a identificar
    a quien lo compone. Por debajo de 20 hay que subirlo a propósito.
    """
    if agrupar_por not in GRUPOS_SABER:
        raise ErrorValidacion(
            f"Agrupación desconocida: {agrupar_por!r}.",
            "Válidas: " + ", ".join(sorted(GRUPOS_SABER)))
    if area not in AREAS:
        raise ErrorValidacion(f"Área desconocida: {area!r}.",
                              "Válidas: " + ", ".join(sorted(AREAS)))
    campo_area = AREAS[area]
    seleccion, agrupar = GRUPOS_SABER[agrupar_por]

    avisos = []
    if not periodo:
        periodo = await _ultimo_periodo_masivo()
        avisos.append(
            f"Periodo no indicado: se usa {periodo}, la última aplicación "
            "masiva de octubre. Mezclar periodos de octubre con los de marzo "
            "promedia dos poblaciones distintas."
        )
    periodo = str(periodo).strip()
    if not periodo.isdigit():
        raise ErrorValidacion(
            f"Periodo inválido: {periodo!r}.",
            "Es año y semestre pegados, como 20224 (octubre de 2022).")

    partes = [f"periodo = '{socrata.escapa(periodo)}'"]
    if departamento:
        cat = await socrata.filtro_categorico(
            SABER11.id, "cole_depto_ubicacion", departamento)
        if cat.filtro is None:
            sobre = Sobre(datos=[], total=Total.completo(0),
                          fuente=_fuente_icfes())
            sobre.advertir(
                f"«{departamento}» no aparece como departamento del colegio en "
                "Saber 11. No es un fallo de la fuente.")
            return sobre.render(lambda _f: "_Sin coincidencias._")
        partes.append(cat.filtro)
    donde = " AND ".join(partes)

    tope = min(int(limite), 100)
    minimo = max(int(minimo_estudiantes), 1)
    # El casteo va en el `avg` porque la columna es text: sin él Socrata
    # promedia cadenas y devuelve un 400, que al menos es ruidoso.
    SELECT = (f"{seleccion}, count(*) as estudiantes, "
              f"avg({campo_area}::number) as promedio")
    TENIENDO = f"count(*) >= {minimo}"
    r = await socrata.consultar(SABER11.id, seleccionar=SELECT, donde=donde,
                                agrupar=agrupar, teniendo=TENIENDO,
                                ordenar="promedio DESC", limite=tope)

    crudos = [fmt.a_numero(f.get("promedio")) or 0 for f in r["filas"]]
    filas = []
    for f in r["filas"]:
        fila = {}
        for clave, valor in f.items():
            if clave in ("estudiantes", "promedio"):
                continue
            fila[_legible(clave)] = fmt.limpia_texto(valor) or "(sin dato)"
        fila["estudiantes"] = fmt.numero(f.get("estudiantes"))
        promedio = fmt.a_numero(f.get("promedio"))
        fila[f"promedio {area}"] = f"{promedio:.1f}" if promedio is not None else ""
        filas.append(fila)
    if grafica and formato == "tabla" and filas:
        for fila, barra in zip(filas, fmt.barras(crudos)):
            fila["gráfica"] = barra

    sobre = Sobre(datos=filas, orden="promedio DESC", consulta=r["consulta"],
                  fuente=_fuente_icfes())
    await agregacion.anota_total(sobre, r["filas"], tope, dataset_id=SABER11.id,
                                 seleccionar=SELECT, agrupar=agrupar,
                                 donde=donde, teniendo=TENIENDO)
    sobre.advertir(privacidad.AVISO_SOLO_AGREGADO)
    for a in avisos:
        sobre.advertir(a)
    sobre.advertir(
        f"Grupos con menos de {minimo} estudiantes excluidos. Un promedio sobre "
        "tres personas no es comparable con uno sobre mil, y además se acerca a "
        "identificar a quien lo compone.")
    if area == "global":
        sobre.advertir(
            "`punt_global` no es la suma de las cinco áreas: cada una entra con "
            "su propia ponderación. No lo reconstruyas sumando.")
    sobre.advertir(
        "Ordenar colegios por promedio NO los ordena por calidad: el puntaje "
        "correlaciona fuerte con el estrato y la escolaridad de los padres, que "
        "están en la misma fuente. Agrupa por `estrato` o `educacion_madre` "
        "para verlo.")
    sobre.advertir(
        "La fuente no se actualiza desde el 23-ago-2023: la serie termina en "
        "2022-4. No hay resultados posteriores aquí.")
    return sobre.render(lambda f: fmt.tabla_markdown(f), formato=formato)


def _legible(campo: str) -> str:
    bonitos = {
        "cole_depto_ubicacion": "departamento",
        "cole_mcpio_ubicacion": "municipio",
        "cole_cod_mcpio_ubicacion": "cod_mpio",
        "cole_nombre_establecimiento": "colegio",
        "cole_cod_dane_establecimiento": "cod_dane",
        "cole_naturaleza": "naturaleza",
        "cole_jornada": "jornada",
        "fami_estratovivienda": "estrato",
        "fami_educacionmadre": "educación de la madre",
    }
    return bonitos.get(campo, campo)


def _fuente_icfes() -> Fuente:
    return Fuente(id=SABER11.id, nombre=SABER11.nombre, licencia=_LIC,
                  atribucion=_ATRIB_ICFES)


async def _ultimo_periodo_masivo() -> str:
    """El último periodo acabado en 4: la aplicación de octubre.

    Tomar `max(periodo)` sin más daría a veces un periodo de marzo con quince
    mil estudiantes y se presentaría como «el último año», que es un error de
    población, no de fecha.
    """
    r = await socrata.consultar(
        SABER11.id, seleccionar="periodo, count(*) as n", agrupar="periodo",
        ordenar="periodo DESC", limite=20)
    for f in r["filas"]:
        p = str(f.get("periodo") or "")
        if p.endswith("4") and (fmt.a_numero(f.get("n")) or 0) > 100_000:
            return p
    return "20224"


# ---------------------------------------------------- MinEducación · ETC ----
INDICADORES_MEN = {
    "cobertura_neta": "cobertura_neta",
    "cobertura_bruta": "cobertura_bruta",
    "desercion": "deserci_n",
    "aprobacion": "aprobaci_n",
    "reprobacion": "reprobaci_n",
    "repitencia": "repitencia",
    "poblacion_5_16": "poblaci_n_5_16",
    "tasa_matriculacion": "tasa_matriculaci_n_5_16",
    "tamano_grupo": "tama_o_promedio_de_grupo",
}


async def indicadores(municipio: str | None = None, departamento: str | None = None,
                      anio: int = 0, indicador: str = "", limite: int = 25,
                      formato: str = "tabla", grafica: bool = True):
    """Cobertura, deserción, aprobación y repitencia por municipio y año.

    Con `indicador` devuelve el ranking de municipios por ese indicador; sin
    él, la ficha completa de los municipios que casen con el filtro.
    """
    if indicador and indicador not in INDICADORES_MEN:
        raise ErrorValidacion(
            f"Indicador desconocido: {indicador!r}.",
            "Válidos: " + ", ".join(sorted(INDICADORES_MEN)))

    avisos, partes = [], []
    if not anio:
        anio = await _ultimo_anio_men()
        avisos.append(f"Año no indicado: se usa {anio}, el más reciente de la fuente.")
    partes.append(f"a_o = '{int(anio)}'")
    if municipio:
        cat = await socrata.filtro_categorico(MEN.id, "municipio", municipio)
        if cat.filtro is None:
            return _sin_men(f"«{municipio}» no aparece como municipio en esta fuente")
        partes.append(cat.filtro)
    if departamento:
        cat = await socrata.filtro_categorico(MEN.id, "departamento", departamento)
        if cat.filtro is None:
            return _sin_men(f"«{departamento}» no aparece como departamento en esta fuente")
        partes.append(cat.filtro)
    donde = " AND ".join(partes)

    tope = min(int(limite), 100)
    if indicador:
        campo = INDICADORES_MEN[indicador]
        seleccionar = f"a_o, c_digo_municipio, municipio, departamento, {campo}"
        ordenar = f"{campo}::number DESC"
    else:
        seleccionar = ", ".join(MEN.campos_resumen)
        ordenar = "municipio"
    r = await socrata.consultar(MEN.id, seleccionar=seleccionar, donde=donde,
                                ordenar=ordenar, limite=tope)

    filas = [{_legible_men(k): fmt.limpia_texto(v) if isinstance(v, str) else v
              for k, v in f.items()} for f in r["filas"]]
    if indicador and grafica and formato == "tabla" and filas:
        crudos = [fmt.a_numero(f.get(INDICADORES_MEN[indicador])) or 0
                  for f in r["filas"]]
        for fila, barra in zip(filas, fmt.barras(crudos)):
            fila["gráfica"] = barra

    sobre = Sobre(datos=filas, orden=ordenar, consulta=r["consulta"],
                  fuente=Fuente(id=MEN.id, nombre=MEN.nombre, licencia=_LIC,
                                atribucion=_ATRIB_MEN))
    sobre.total = Total.cupo_entero(r["filas"], tope)
    if not sobre.total.consta:
        sobre.total = Total.contado(await socrata.contar(MEN.id, donde=donde))
    for a in avisos:
        sobre.advertir(a)
    sobre.advertir(
        "Los indicadores son porcentajes y la cobertura BRUTA pasa de 100 % con "
        "normalidad: cuenta matriculados de cualquier edad sobre la población "
        "del rango teórico. Medellín 2023 estaba en 107,16 %. La NETA es la que "
        "no puede pasar de 100.")
    sobre.advertir(
        "`poblaci_n_5_16` es población de 5 a 16 años, no población total: es la "
        "única población municipal que publica alguna fuente del servidor y NO "
        "sirve de denominador para tasas de criminalidad ni de nada más.")
    sobre.advertir(
        "`c_digo_municipio` es la clave DIVIPOLA, así que cruza con criminalidad "
        "y con geometría por código, sin pasar por el nombre.")
    return sobre.render(lambda f: fmt.tabla_markdown(f), formato=formato)


def _legible_men(campo: str) -> str:
    traduce = {"a_o": "año", "c_digo_municipio": "cod_mpio",
               "c_digo_departamento": "cod_dpto", "poblaci_n_5_16": "pobl. 5-16",
               "deserci_n": "deserción", "aprobaci_n": "aprobación",
               "reprobaci_n": "reprobación", "tasa_matriculaci_n_5_16": "tasa matr. 5-16",
               "tama_o_promedio_de_grupo": "tamaño grupo"}
    return traduce.get(campo, campo)


def _sin_men(mensaje: str):
    sobre = Sobre(datos=[], total=Total.completo(0),
                  fuente=Fuente(id=MEN.id, nombre=MEN.nombre, licencia=_LIC,
                                atribucion=_ATRIB_MEN))
    sobre.advertir(f"{mensaje}. No es un fallo de la fuente.")
    return sobre.render(lambda _f: "_Sin coincidencias._")


async def _ultimo_anio_men() -> int:
    r = await socrata.consultar(MEN.id, seleccionar="max(a_o) as a", limite=1)
    filas = r["filas"]
    valor = fmt.a_numero(filas[0].get("a")) if filas else None
    return int(valor) if valor else 2023
