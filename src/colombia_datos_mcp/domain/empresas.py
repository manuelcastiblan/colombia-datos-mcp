"""Registro mercantil y societario: RUES, Supersociedades, ranking.

Lo que este módulo absorbe, verificado contra la fuente el 05-nov-2026:

* **Una fila del RUES es una matrícula, no una empresa.** De 9.436.330
  matrículas, 5.091.481 están canceladas y 6.962.889 son de personas
  naturales. «Cuántas empresas hay en Colombia» no se responde contando filas.
* **El NIT vive en dos columnas y a veces en ninguna.** `nit` está vacío en
  485.630 sociedades; el número aparece entonces solo en
  `numero_identificacion`. Buscar por una sola columna pierde en silencio:
  SECOLINSA S A S tiene estados financieros en Supersociedades y su `nit` en
  RUES está vacío. Toda consulta por documento mira las dos.
* **`categoria_matricula` es el único discriminador fiable de persona.**
  `clase_identificacion` no sirve: 517.527 personas naturales figuran con clase
  `NIT`. Si el motor de privacidad se hubiera apoyado en la clase, medio millón
  de personas habrían pasado por empresas.
* **Los estados financieros son formato largo XBRL.** El balance de una empresa
  son cientos de filas, `periodo` dice «Periodo Actual» o «Periodo Anterior»
  —relativo al radicado, no un año— y el año real está en `fecha_corte`.
* **No todas las empresas reportan a Supersociedades.** Bancolombia no tiene
  una sola fila en los estados financieros porque los bancos reportan a la
  Superfinanciera. Ausencia aquí no es ausencia de actividad.
"""

from __future__ import annotations

from ..adapters import socrata
from ..core import format as fmt
from ..core import nit as nit_mod
from ..core import privacidad
from ..core.envelope import Fuente, Sobre, Total
from ..core.errors import ErrorValidacion
from ..registry import datasets as reg

_LIC = "CC BY-SA 4.0"
_ATRIB_RUES = "Confecámaras (Registro Único Empresarial y Social)"
_ATRIB_SUPER = "Superintendencia de Sociedades"

RUES = reg.EMPRESAS["rues"]
ESTABLECIMIENTOS = reg.EMPRESAS["establecimientos"]
EEFF_SITUACION = reg.EMPRESAS["eeff_situacion"]
EEFF_RESULTADOS = reg.EMPRESAS["eeff_resultados"]
MAS_GRANDES = reg.EMPRESAS["mas_grandes"]

AVISO_MATRICULA = (
    "Una fila es una MATRÍCULA mercantil, no una empresa. De los 9.436.330 "
    "registros del RUES, 5.091.481 están CANCELADAS. No cuentes filas como "
    "empresas activas sin filtrar `estado`."
)
AVISO_DOS_COLUMNAS = (
    "La búsqueda por documento mira `nit` y `numero_identificacion`: en 485.630 "
    "sociedades la columna `nit` está vacía y el número solo aparece en la otra."
)
AVISO_ESCALA_EEFF = (
    "El dataset NO declara la escala de `valor`. Las cifras parecen estar en "
    "miles de pesos, pero eso es una inferencia, no un dato de la fuente: "
    "verifica contra el estado financiero publicado antes de citar un importe."
)
# Aquí sí se puede afirmar la escala, y por eso se afirma: Ecopetrol 2025
# figura con ingresos «$ 100.59» y activos «$ 198.11», que contra sus estados
# publicados son billones de pesos. La comprobación está en la suite de
# contrato para que deje de ser cierta en voz alta si la fuente cambia de
# unidad sin avisar.
AVISO_ESCALA_RANKING = (
    "Los importes vienen como texto con signo de peso y punto decimal («$ "
    "100.59») y están en BILLONES de pesos: ese valor son 100,59 billones. La "
    "fuente no lo declara en ninguna columna; se deduce de contrastar Ecopetrol "
    "con sus estados financieros publicados."
)


def _fuente(ds: reg.Dataset, atrib: str) -> Fuente:
    return Fuente(id=ds.id, nombre=ds.nombre, licencia=_LIC, atribucion=atrib)


def _donde_documento(documento: str) -> str:
    """El filtro que mira las dos columnas donde puede estar el número.

    Ambas son de tipo text en RUES, así que van entre comillas. Pasarlas como
    número produce `query.soql.type-mismatch`, no cero filas, que al menos es
    un error honesto.
    """
    d = nit_mod.solo_digitos(documento)
    if not d:
        raise ErrorValidacion(
            f"Documento sin dígitos: {documento!r}.",
            "Pasa el NIT sin dígito de verificación o la cédula, solo números.",
        )
    formas = nit_mod.equivalentes(d)
    literales = ", ".join(f"'{socrata.escapa(f)}'" for f in formas)
    return f"(nit in ({literales}) OR numero_identificacion in ({literales}))"


# ------------------------------------------------------------------ buscar --
async def buscar(nombre: str | None = None, documento: str | None = None,
                 estado: str | None = None, camara: str | None = None,
                 solo_juridicas: bool = True, limite: int = 20, offset: int = 0,
                 detalle: str = "resumen", formato: str = "tabla",
                 finalidad: str | None = None):
    """Busca matrículas en el RUES por razón social o por documento.

    `solo_juridicas=True` —el valor por defecto— restringe a sociedades y ESAL,
    y entonces la consulta no identifica a ninguna persona natural y no pide
    finalidad. Bajarlo a False abre los 6.962.889 comerciantes matriculados a
    título personal, y eso sí pasa por el motor de privacidad.
    """
    if not (nombre or documento):
        raise ErrorValidacion(
            "Hace falta `nombre` o `documento`.",
            "Para explorar sin un objetivo concreto usa co_datos_agregar sobre "
            "c82u-588k: agrupar por cámara o por año no identifica a nadie.",
        )

    partes, avisos = [], []
    juridica_segura = solo_juridicas
    if solo_juridicas:
        partes.append(f"categoria_matricula = '{socrata.escapa(privacidad.RUES_JURIDICA)}'")
    else:
        finalidad = privacidad.exige_finalidad(
            finalidad,
            que="Buscar en el RUES incluyendo personas naturales",
            alternativa="solo_juridicas=True, o una agregación por cámara, "
                        "estado o año con co_datos_agregar",
        )

    if documento:
        partes.append(_donde_documento(documento))
        avisos.append(AVISO_DOS_COLUMNAS)
        if not privacidad.es_persona_juridica(documento) and solo_juridicas:
            avisos.append(
                f"El documento {privacidad.etiqueta_documento(documento)} no "
                f"tiene forma de NIT de sociedad "
                f"(clase: {privacidad.clase_documento(documento)}). Con "
                "`solo_juridicas=True` la búsqueda puede salir vacía aunque la "
                "persona esté matriculada."
            )
    if nombre:
        partes.append(socrata.filtro_texto_libre("razon_social", nombre))
    if estado:
        cat = await socrata.filtro_categorico(RUES.id, "estado_matricula", estado)
        if cat.filtro is None:
            return _sin_coincidencias(
                f"«{estado}» no es ninguno de los estados de matrícula del RUES",
                RUES, _ATRIB_RUES,
                "Los más frecuentes son ACTIVA y CANCELADA.")
        partes.append(cat.filtro)
        if cat.degradado:
            avisos.append(
                f"No se pudo enumerar los estados de matrícula, así que "
                f"«{estado}» se filtró por coincidencia de texto: puede incluir "
                "estados parecidos."
            )
    if camara:
        cat = await socrata.filtro_categorico(RUES.id, "camara_comercio", camara)
        if cat.filtro is None:
            return _sin_coincidencias(
                f"«{camara}» no es ninguna de las cámaras de comercio del RUES",
                RUES, _ATRIB_RUES,
                "Van sin la palabra «Cámara»: «MEDELLIN PARA ANTIOQUIA».")
        partes.append(cat.filtro)

    donde = " AND ".join(p for p in partes if p)
    tope = min(int(limite), 100)
    columnas = (list(RUES.campos_resumen) if detalle != "completo" else None)
    if not solo_juridicas and columnas:
        columnas = columnas + ["categoria_matricula", "numero_identificacion"]
    seleccionar = ", ".join(dict.fromkeys(columnas)) if columnas else None

    r = await socrata.consultar(RUES.id, seleccionar=seleccionar, donde=donde,
                                ordenar="razon_social", limite=tope, offset=offset)
    filas = [{k: fmt.limpia_texto(v) if isinstance(v, str) else v
              for k, v in f.items()} for f in r["filas"]]
    hay_naturales = any(not privacidad.juridica_en_rues(f) for f in filas)
    if juridica_segura:
        # El SoQL ya restringió a sociedades: no hay nada que enmascarar.
        hay_naturales = False
    else:
        # Fila por fila, y no por página: una sola persona natural en la página
        # enmascaraba también los NIT de las sociedades que la acompañaban, que
        # son justo los que sirven para cruzar con SECOP.
        filas = privacidad.redacta_filas(
            filas, es_juridica=privacidad.juridica_en_rues)

    consulta = r["consulta"]
    if documento and hay_naturales:
        consulta = privacidad.redacta_consulta(consulta, documento)
        avisos.append(privacidad.AVISO_CONSULTA_REDACTADA)
    sobre = Sobre(datos=filas, offset=offset, orden="razon_social",
                  consulta=consulta, fuente=_fuente(RUES, _ATRIB_RUES))
    sobre.total = Total.cupo_entero(r["filas"], tope, offset=offset)
    if not sobre.total.consta:
        sobre.total = Total.contado(await socrata.contar(RUES.id, donde=donde))
    sobre.advertir(AVISO_MATRICULA)
    for a in avisos:
        sobre.advertir(a)
    if hay_naturales or not juridica_segura:
        privacidad.avisa(sobre, finalidad=finalidad)
    return sobre.render(lambda f: fmt.tabla_markdown(f), formato=formato)


def _sin_coincidencias(mensaje: str, ds: reg.Dataset, atrib: str,
                       sugerencia: str = ""):
    """Cero filas porque el término no existe en la fuente, no porque falle.

    Es la distinción que el servidor entero sostiene: un filtro que no casa
    nada se presenta como «el término no está», nunca como una tabla vacía que
    parece decir «no hay datos».
    """
    sobre = Sobre(datos=[], total=Total.completo(0), fuente=_fuente(ds, atrib))
    sobre.advertir(f"{mensaje}. No es un fallo de la fuente. {sugerencia}".strip())
    return sobre.render(lambda _f: "_Sin coincidencias._")


# ------------------------------------------------------------------ ficha --
async def ficha(documento: str, finalidad: str | None = None):
    """Todo lo que el registro mercantil dice de un documento, en una llamada.

    Resuelve matrícula principal, establecimientos a su nombre y presencia en
    el ranking de las 10.000 más grandes. Si el documento es de una persona
    natural, exige finalidad antes de devolver nada.
    """
    donde = _donde_documento(documento)
    TOPE_MATRICULAS = 10
    # `dict.fromkeys` no es decoración: `campos_resumen` ya trae
    # `categoria_matricula`, así que concatenar las columnas extra la repetía y
    # Socrata rechazaba la consulta entera con `query.soql.invalid`. Una columna
    # duplicada en el `$select` no es un aviso, es un 400.
    columnas = dict.fromkeys(list(RUES.campos_resumen) +
                             ["categoria_matricula", "numero_identificacion",
                              "tipo_sociedad", "fecha_cancelacion"])
    r = await socrata.consultar(
        RUES.id, seleccionar=", ".join(columnas),
        donde=donde, ordenar="fecha_matricula DESC", limite=TOPE_MATRICULAS)
    matriculas = r["filas"]
    # Dos señales que se corrigen la una a la otra, y que a veces discrepan
    # porque la fuente tiene filas mal clasificadas. `resuelve_persona` lo
    # decide en un sitio y devuelve el aviso cuando hay discrepancia.
    es_natural, aviso_clasificacion = privacidad.resuelve_persona(
        documento, [m.get("categoria_matricula") for m in matriculas])
    if es_natural or (not matriculas and not privacidad.es_persona_juridica(documento)):
        finalidad = privacidad.exige_finalidad(
            finalidad,
            que=f"La ficha de {privacidad.etiqueta_documento(documento)}",
            alternativa="co_empresas_buscar con solo_juridicas=True si lo que "
                        "buscas es una sociedad",
        )

    filas = []
    for m in matriculas:
        filas.append({
            "razón social": fmt.limpia_texto(m.get("razon_social")),
            "sigla": fmt.limpia_texto(m.get("sigla")),
            "documento": m.get("nit") or m.get("numero_identificacion"),
            "dv": m.get("digito_verificacion"),
            "categoría": fmt.limpia_texto(m.get("categoria_matricula")),
            "forma jurídica": fmt.limpia_texto(m.get("organizacion_juridica")),
            "estado": fmt.limpia_texto(m.get("estado_matricula")),
            "cámara": fmt.limpia_texto(m.get("camara_comercio")),
            "matriculada": fecha_rues(m.get("fecha_matricula")),
            "último año renovado": m.get("ultimo_ano_renovado"),
            "CIIU": m.get("cod_ciiu_act_econ_pri"),
        })
    filas = privacidad.redacta_filas(filas, persona_juridica=not es_natural)

    consulta = (privacidad.redacta_consulta(r["consulta"], documento)
                if es_natural else r["consulta"])
    sobre = Sobre(datos=filas, orden="fecha_matricula DESC",
                  consulta=consulta, fuente=_fuente(RUES, _ATRIB_RUES))
    if es_natural:
        sobre.advertir(privacidad.AVISO_CONSULTA_REDACTADA)
    # Diez matrículas es un tope, no una colección cerrada: hay documentos con
    # más. `Total.completo(len(filas))` habría dicho «10 de 10» habiendo doce.
    sobre.total = Total.cupo_entero(matriculas, TOPE_MATRICULAS)
    if not sobre.total.consta:
        sobre.total = Total.contado(await socrata.contar(RUES.id, donde=donde))
    if not filas:
        sobre.advertir(
            f"El documento {privacidad.etiqueta_documento(documento, persona_juridica=not es_natural)} "
            "no tiene matrícula en el RUES. Puede ser "
            "una entidad pública —que no se matricula en cámara de comercio— o "
            "un número que no existe. Compruébalo en SECOP con "
            "co_secop_perfil_proveedor antes de concluir que no existe."
        )
        return sobre.render(lambda _f: "_Sin matrícula en el RUES._")

    # Establecimientos y ranking son extras: si fallan, la ficha sale igual.
    # Pero el fallo se DICE. Omitir la línea en silencio deja al lector sin
    # saber si el dato es que no hay, o que no se pudo mirar.
    extras = []
    cuantos = await _cuenta(ESTABLECIMIENTOS.id,
                            f"nit_propietario in ({_literales(documento)})")
    extras.append(f"**Establecimientos a su nombre:** {fmt.numero(cuantos)}"
                  if cuantos is not None else
                  "**Establecimientos a su nombre:** no consultable (la fuente no respondió)")
    try:
        grandes = await en_ranking(documento)
    except Exception as exc:                                      # noqa: BLE001
        extras.append("**En las 10.000 más grandes:** no consultable "
                      f"({type(exc).__name__})")
    else:
        if grandes:
            extras.append("**En las 10.000 más grandes:** " + grandes)

    sobre.advertir(AVISO_MATRICULA)
    sobre.advertir(AVISO_DOS_COLUMNAS)
    if aviso_clasificacion:
        sobre.advertir(aviso_clasificacion)
    if len(filas) > 1:
        sobre.advertir(
            f"{len(filas)} matrículas para el mismo documento: una sociedad "
            "puede tener matrícula en varias cámaras, o renovaciones separadas. "
            "La más reciente va primero."
        )
    if es_natural:
        privacidad.avisa(sobre, finalidad=finalidad)

    def cuerpo(f):
        texto = fmt.tabla_markdown(f)
        return texto + ("\n\n" + "\n\n".join(extras) if extras else "")

    return sobre.render(cuerpo)


def _literales(documento: str) -> str:
    return ", ".join(f"'{socrata.escapa(f)}'"
                     for f in nit_mod.equivalentes(nit_mod.solo_digitos(documento)))


def fecha_rues(valor) -> str:
    """`19841122` -> `1984-11-22`. Las fechas del RUES son text YYYYMMDD."""
    d = nit_mod.solo_digitos(valor)
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else (d or "")


async def _cuenta(dataset_id: str, donde: str) -> int | None:
    """Conteo de cortesía: ante cualquier fallo devuelve None, no una excepción.

    Es un extra sobre una respuesta que ya tiene lo esencial; dejar que su
    timeout tumbe la ficha cambia «un dato de menos» por «ninguna respuesta».
    """
    try:
        return await socrata.contar(dataset_id, donde=donde)
    except Exception:
        return None


async def en_ranking(documento: str) -> str:
    """Años en que el documento aparece en las 10.000 más grandes.

    Aquí `nit` es de tipo number, al contrario que en RUES: la misma columna
    con el mismo nombre y otro tipo en dos datasets del mismo portal.
    """
    d = nit_mod.solo_digitos(documento)
    if not d:
        return ""
    # Aquí NO se captura el fallo. Se capturaba, y devolver "" ante un timeout
    # hacía que el dossier escribiera «no figura»: una ausencia atribuida a una
    # fuente que no se pudo consultar, que es el error que este servidor está
    # entero construido para no cometer. Quien quiera tolerancia la pone en su
    # propio llamador, donde además sabe qué decir en su lugar.
    r = await socrata.consultar(
        MAS_GRANDES.id,
        seleccionar="a_o_de_corte, ingresos_operacionales, macrosector",
        donde=f"nit in ({', '.join(nit_mod.equivalentes(d))})",
        ordenar="a_o_de_corte DESC", limite=6)
    if not r["filas"]:
        return ""
    anios = [str(fmt.a_numero(f.get("a_o_de_corte")) or "")[:4] for f in r["filas"]]
    sector = fmt.limpia_texto(r["filas"][0].get("macrosector"))
    return (f"sí, en {', '.join(a for a in anios if a)}"
            f"{f' · macrosector {sector}' if sector else ''}")


# ----------------------------------------------------- estados financieros --
# Los conceptos que resumen un balance y un resultado. Son los literales
# exactos de la taxonomía; los demás son cientos de desagregaciones.
#
# **Los conceptos con tilde no se pueden pedir por igualdad.** El mojibake de
# la fuente no es un problema de cómo se muestra: el byte almacenado es el
# carácter de reemplazo U+FFFD, así que `concepto = 'Ganancia (pérdida)'`
# devuelve 0 filas habiendo 627.932. Se piden con `like` y un comodín de un
# solo carácter en el hueco, que es lo único que casa con lo que hay guardado.
CONCEPTOS_BALANCE = ("Total de activos", "Total pasivos", "Patrimonio total",
                     "Activos corrientes totales", "Efectivo y equivalentes al efectivo")
CONCEPTOS_RESULTADO = ("Ingresos de actividades ordinarias", "Costo de ventas",
                       "Ganancia bruta")
PATRONES_RESULTADO = ("Ganancia (p_rdida)",)
PATRONES_BALANCE = ()


def _filtro_conceptos(exactos, patrones) -> str:
    """`concepto in (...)` más un `like` por cada concepto con tilde."""
    partes = []
    if exactos:
        partes.append("concepto in (" + ", ".join(
            f"'{socrata.escapa(c)}'" for c in exactos) + ")")
    partes += [f"concepto like '{socrata.escapa(p)}'" for p in patrones]
    return "(" + " OR ".join(partes) + ")"


async def estados_financieros(documento: str, anio: int = 0, limite: int = 30,
                              formato: str = "tabla"):
    """Cifras clave del balance y del resultado reportado a Supersociedades.

    Se piden los conceptos agregados por nombre exacto, no las cientos de
    desagregaciones de la taxonomía. `periodo` se fija en «Periodo Actual»
    porque «Periodo Anterior» es el comparativo del mismo radicado y duplicaría
    cada año.
    """
    d = nit_mod.solo_digitos(documento)
    if not d:
        raise ErrorValidacion(f"Documento sin dígitos: {documento!r}.",
                              "Pasa el NIT solo con números.")
    numeros = ", ".join(nit_mod.equivalentes(d))
    tope = min(int(limite), 100)
    filas, consultas, trozos = [], [], []
    for ds, exactos, patrones, cual in (
            (EEFF_SITUACION, CONCEPTOS_BALANCE, PATRONES_BALANCE, "balance"),
            (EEFF_RESULTADOS, CONCEPTOS_RESULTADO, PATRONES_RESULTADO, "resultado")):
        partes = [f"nit in ({numeros})", "periodo = 'Periodo Actual'",
                  _filtro_conceptos(exactos, patrones)]
        if anio:
            partes.append(f"fecha_corte >= '{int(anio)}-01-01'")
            partes.append(f"fecha_corte < '{int(anio) + 1}-01-01'")
        r = await socrata.consultar(
            ds.id, seleccionar="fecha_corte, concepto, valor",
            donde=" AND ".join(partes), ordenar="fecha_corte DESC",
            limite=tope)
        consultas.append(r["consulta"])
        trozos.append((len(r["filas"]), tope))
        for f in r["filas"]:
            filas.append({"corte": fmt.fecha(f.get("fecha_corte")),
                          "estado": cual,
                          "concepto": fmt.limpia_texto(f.get("concepto")),
                          "valor": fmt.numero(f.get("valor"))})

    filas.sort(key=lambda f: (f["corte"], f["estado"], f["concepto"]), reverse=True)
    # Dos consultas con su propio `$limit`: si alguna lo llenó, la suma de lo
    # devuelto no es el total de conceptos reportados.
    sobre = Sobre(datos=filas, total=Total.union(trozos),
                  orden="corte DESC",
                  consulta=" · ".join(consultas),
                  fuente=Fuente(id=f"{EEFF_SITUACION.id} + {EEFF_RESULTADOS.id}",
                                nombre="Supersociedades · Estados Financieros NIIF",
                                licencia=_LIC, atribucion=_ATRIB_SUPER))
    if not filas:
        sobre.advertir(
            f"Sin estados financieros para {documento} en Supersociedades. No "
            "significa que la empresa no exista ni que no opere: los bancos y "
            "las aseguradoras reportan a la Superfinanciera, y Bancolombia no "
            "tiene una sola fila aquí. Verifica la matrícula con "
            "co_empresas_ficha."
        )
        return sobre.render(lambda _f: "_Sin reportes en Supersociedades._")
    if not sobre.total.consta:
        sobre.advertir(
            "Total desconocido: alguna de las dos consultas llenó su límite, así "
            f"que hay más cortes o conceptos de los {len(filas)} mostrados. Sube "
            "`limite` o fija `anio`.")
    sobre.advertir(AVISO_ESCALA_EEFF)
    sobre.advertir(
        "Formato largo XBRL: solo se piden los conceptos agregados. El reporte "
        "completo tiene cientos de líneas por corte; para verlas usa "
        f"co_datos_consultar sobre {EEFF_SITUACION.id}."
    )
    sobre.advertir(
        "Montos nominales del año de cada corte, sin deflactar. Comparar dos "
        "cortes compara pesos de distinto poder de compra."
    )
    return sobre.render(lambda f: fmt.tabla_markdown(f), formato=formato)


# ---------------------------------------------------------------- ranking --
async def ranking(anio: int = 0, macrosector: str | None = None,
                  departamento: str | None = None, metrica: str = "ingresos",
                  limite: int = 20, formato: str = "tabla", grafica: bool = True):
    """Las empresas más grandes por ingresos, activos o patrimonio.

    El dataset se llama «10.000 Empresas más Grandes» y tiene 50.000 filas: son
    10.000 por año, de 2021 a 2025. Sin fijar el año cada empresa sale cinco
    veces, así que `anio` vacío toma el más reciente disponible y lo dice.
    """
    columnas = {"ingresos": "ingresos_operacionales", "activos": "total_activos",
                "patrimonio": "total_patrimonio", "ganancia": "ganancia_p_rdida"}
    if metrica not in columnas:
        raise ErrorValidacion(
            f"Métrica desconocida: {metrica!r}.",
            "Válidas: " + ", ".join(columnas))
    campo = columnas[metrica]

    avisos = []
    if not anio:
        anio = await _ultimo_anio_ranking()
        avisos.append(
            f"Año no indicado: se usa {anio}, el corte más reciente del "
            "dataset. Sin fijarlo, cada empresa aparecería una vez por año."
        )
    partes = [f"a_o_de_corte = {int(anio)}"]
    if macrosector:
        cat = await socrata.filtro_categorico(MAS_GRANDES.id, "macrosector", macrosector)
        if cat.filtro is None:
            return _sin_coincidencias(
                f"«{macrosector}» no es ninguno de los macrosectores",
                MAS_GRANDES, _ATRIB_SUPER,
                "Son agrupaciones amplias: Comercio, Manufactura, Servicios…")
        partes.append(cat.filtro)
    if departamento:
        cat = await socrata.filtro_categorico(
            MAS_GRANDES.id, "departamento_domicilio", departamento)
        if cat.filtro is None:
            return _sin_coincidencias(
                f"«{departamento}» no es ninguno de los departamentos de domicilio",
                MAS_GRANDES, _ATRIB_SUPER)
        partes.append(cat.filtro)

    donde = " AND ".join(partes)
    tope = min(int(limite), 100)
    r = await socrata.consultar(
        MAS_GRANDES.id,
        seleccionar="raz_n_social, nit, macrosector, departamento_domicilio, "
                    "ingresos_operacionales, total_activos, total_patrimonio, "
                    "ganancia_p_rdida",
        donde=donde, ordenar=f"{_orden_importe(campo)} DESC", limite=tope)

    crudos = [fmt.a_numero(f.get(campo)) or 0 for f in r["filas"]]
    filas = [{"empresa": fmt.limpia_texto(f.get("raz_n_social")),
              "NIT": _nit_entero(f.get("nit")),
              "macrosector": fmt.limpia_texto(f.get("macrosector")),
              "departamento": fmt.limpia_texto(f.get("departamento_domicilio")),
              "ingresos": fmt.numero(f.get("ingresos_operacionales")),
              "activos": fmt.numero(f.get("total_activos")),
              "patrimonio": fmt.numero(f.get("total_patrimonio")),
              "ganancia": fmt.numero(f.get("ganancia_p_rdida"))}
             for f in r["filas"]]
    if grafica and formato == "tabla" and filas:
        for fila, barra in zip(filas, fmt.barras(crudos)):
            fila["gráfica"] = barra

    sobre = Sobre(datos=filas, orden=f"{campo} DESC", consulta=r["consulta"],
                  fuente=_fuente(MAS_GRANDES, _ATRIB_SUPER))
    sobre.total = Total.cupo_entero(r["filas"], tope)
    if not sobre.total.consta:
        sobre.total = Total.contado(await socrata.contar(MAS_GRANDES.id, donde=donde))
    for a in avisos:
        sobre.advertir(a)
    sobre.advertir(
        "Es el ranking de quien REPORTA a Supersociedades. Los bancos y las "
        "aseguradoras reportan a la Superfinanciera y no están aquí, así que no "
        "es la lista de las empresas más grandes del país."
    )
    sobre.advertir(AVISO_ESCALA_RANKING)
    return sobre.render(lambda f: fmt.tabla_markdown(f), formato=formato)


def _nit_entero(valor) -> str:
    """El NIT del ranking, servido como `"899999068.00"`, como entero.

    La columna está declarada `Number` y la fuente la sirve con dos decimales.
    Devolverla tal cual rompía el encadenamiento silenciosamente: el modelo
    copiaba `899999068.00` a `co_empresas_ficha`, donde `solo_digitos` lo
    convierte en `89999906800` y consulta otro documento, de modo que la ficha
    de Ecopetrol salía vacía sin que nada avisara de por qué.
    """
    d = str(valor or "").strip()
    if not d:
        return ""
    try:
        return str(int(float(d)))
    except (TypeError, ValueError):
        return d


def _orden_importe(campo: str) -> str:
    """Expresión por la que ordenar un importe que la fuente guarda como texto.

    `{campo}::number` no sirve: el valor es «$ 100.59» y el casteo falla con
    `invalid input syntax for type numeric`. Ordenar por el texto tal cual es
    peor, porque es silencioso: «$ 9.03» quedaría por encima de «$ 100.59».
    Hay que quitar el signo y el separador de miles ANTES de castear.
    """
    return f"replace(replace({campo}, '$ ', ''), ',', '')::number"


async def _ultimo_anio_ranking() -> int:
    r = await socrata.consultar(MAS_GRANDES.id,
                                seleccionar="max(a_o_de_corte) as a", limite=1)
    filas = r["filas"]
    valor = fmt.a_numero(filas[0].get("a")) if filas else None
    return int(valor) if valor else 2025
