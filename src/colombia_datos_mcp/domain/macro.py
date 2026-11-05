"""TRM y tasas de interés de la Superfinanciera.

Existe por una carencia que el servidor arrastra desde el principio y declara
en cada respuesta de SECOP: **los montos son nominales y sin deflactar**. El
arreglo natural sería el IPC del DANE, y no hay forma de traerlo: ni el DANE ni
el Banco de la República publican sus series por API REST abierta, y en
`datos.gov.co` no están. Lo que sí hay es la TRM certificada por la
Superfinanciera, con la que un monto se puede expresar en dólares de la fecha
en que se firmó. No es un deflactor —el dólar también se mueve— pero es una
segunda unidad con la que comparar, y es verificable.

**La trampa de la TRM es que una fila cubre varios días.** La tasa de un
viernes rige sábado y domingo, y la fuente lo expresa con `vigenciadesde` y
`vigenciahasta`. Preguntar por `vigenciadesde = '2024-01-21'` —un domingo—
devuelve cero filas habiendo TRM vigente ese día: la de 2024-01-20, que vale
hasta el 22. Toda consulta por fecha busca el rango que la contiene.
"""

from __future__ import annotations

import datetime

from . import agregacion
from ..adapters import socrata
from ..core import format as fmt
from ..core.envelope import Fuente, Sobre, Total
from ..core.errors import ErrorNoEncontrado, ErrorValidacion
from ..registry import datasets as reg

_LIC = "CC BY-SA 4.0"
_ATRIB = "Superintendencia Financiera de Colombia"

TRM = reg.MACRO["trm"]
TASAS = reg.MACRO["tasas_captacion"]

AVISO_NO_DEFLACTOR = (
    "Convertir a dólares NO es deflactar. El dólar también cambia de valor, así "
    "que dos cifras en dólares de años distintos siguen sin ser directamente "
    "comparables en poder de compra. Es una segunda unidad verificable, no un "
    "índice de precios: el IPC del DANE no tiene API abierta."
)


def _fuente(ds: reg.Dataset) -> Fuente:
    return Fuente(id=ds.id, nombre=ds.nombre, licencia=_LIC, atribucion=_ATRIB)


def _normaliza_fecha(valor: str, etiqueta: str = "fecha") -> str:
    """Valida la fecha de verdad, no solo que tenga tres grupos de dígitos.

    La primera versión partía por guiones y comprobaba que los tres trozos
    fueran numéricos, y con eso `20-01-2024` pasaba: una fecha en el formato
    colombiano habitual se aceptaba, se mandaba a Socrata como si fuera ISO y
    volvía sin filas. El usuario veía «sin TRM para esa fecha», que es un
    diagnóstico falso sobre la fuente cuando el error estaba en la entrada.

    `date.fromisoformat` rechaza además los días que no existen (2024-02-30),
    que el recuento de dígitos tampoco veía.
    """
    f = str(valor or "").strip()[:10]
    try:
        datetime.date.fromisoformat(f)
    except ValueError:
        raise ErrorValidacion(
            f"{etiqueta} inválida: {valor!r}.",
            "Usa el formato YYYY-MM-DD, con el año primero: 2024-01-20.",
        ) from None
    return f


async def _trm_de(fecha: str) -> dict | None:
    """La TRM vigente en una fecha, buscando el rango que la contiene."""
    r = await socrata.consultar(
        TRM.id,
        donde=(f"vigenciadesde <= '{fecha}T23:59:59' AND "
               f"vigenciahasta >= '{fecha}T00:00:00'"),
        ordenar="vigenciadesde DESC", limite=1)
    filas = r["filas"]
    return {**filas[0], "_consulta": r["consulta"]} if filas else None


async def trm(fecha: str = "", desde: str = "", hasta: str = "",
              formato: str = "tabla"):
    """TRM de una fecha, de un rango, o la última certificada.

    Sin argumentos devuelve la última. Con `fecha` busca el rango de vigencia
    que la contiene, de modo que un domingo devuelve la tasa que rige ese
    domingo en vez de nada.
    """
    if fecha and (desde or hasta):
        raise ErrorValidacion(
            "`fecha` y el rango `desde`/`hasta` son excluyentes.",
            "Pasa una fecha suelta, o un rango, no las dos cosas.")

    if fecha:
        f = _normaliza_fecha(fecha)
        dato = await _trm_de(f)
        if not dato:
            raise ErrorNoEncontrado(
                f"Sin TRM vigente para {f}.",
                "La serie va de 2003 a hoy; comprueba el año, o pide el último "
                "valor sin argumentos.")
        filas = [{"fecha consultada": f,
                  "TRM": fmt.numero(dato.get("valor")),
                  "vigente desde": fmt.fecha(dato.get("vigenciadesde")),
                  "vigente hasta": fmt.fecha(dato.get("vigenciahasta")),
                  "unidad": dato.get("unidad")}]
        sobre = Sobre(datos=filas, total=Total.completo(1),
                      consulta=dato["_consulta"], fuente=_fuente(TRM))
        if str(dato.get("vigenciadesde"))[:10] != f:
            sobre.advertir(
                f"La TRM de {f} es la certificada el "
                f"{fmt.fecha(dato.get('vigenciadesde'))}: una misma tasa rige "
                "varios días cuando hay fin de semana o festivo.")
        return sobre.render(lambda x: fmt.tabla_markdown(x), formato=formato)

    # Una fila de esta fuente es un INTERVALO de vigencia, no un día. Filtrar
    # por `vigenciadesde >= desde` descartaba la tasa que ya regía al empezar el
    # rango: con desde=hasta=2024-01-21 se perdía la certificada el 20 y vigente
    # hasta el 22, que es justamente la TRM de ese día. Peor que incompleto:
    # `trm(fecha="2024-01-21")` sí la devolvía, así que la misma fecha daba dos
    # respuestas distintas según por dónde se preguntara. Se seleccionan los
    # intervalos que SE SOLAPAN con el rango, que es lo que significa la
    # pregunta.
    partes = []
    if desde:
        partes.append(f"vigenciahasta >= '{_normaliza_fecha(desde, 'desde')}T00:00:00'")
    if hasta:
        partes.append(f"vigenciadesde <= '{_normaliza_fecha(hasta, 'hasta')}T23:59:59'")
    donde = " AND ".join(partes) or None
    tope = 100 if donde else 1
    r = await socrata.consultar(TRM.id, donde=donde, ordenar="vigenciadesde DESC",
                                limite=tope)
    filas = [{"vigente desde": fmt.fecha(f.get("vigenciadesde")),
              "vigente hasta": fmt.fecha(f.get("vigenciahasta")),
              "TRM": fmt.numero(f.get("valor"))} for f in r["filas"]]
    sobre = Sobre(datos=filas, orden="vigenciadesde DESC",
                  consulta=r["consulta"], fuente=_fuente(TRM))
    sobre.total = Total.cupo_entero(r["filas"], tope)
    if not sobre.total.consta:
        sobre.total = Total.contado(await socrata.contar(TRM.id, donde=donde))
    if not donde:
        sobre.advertir("Último valor certificado. Para una serie pasa `desde` y `hasta`.")
    for n in TRM.notas:
        sobre.advertir(n)
    return sobre.render(lambda x: fmt.tabla_markdown(x), formato=formato)


async def convertir(monto: float, fecha: str, hacia: str = "usd"):
    """Pasa un monto entre pesos y dólares a la TRM de una fecha concreta.

    Es la herramienta que da una segunda unidad a los montos de SECOP, que son
    nominales. La fecha importa: el mismo contrato de mil millones son 271 mil
    dólares en 2015 y 229 mil en 2024, y la diferencia no dice nada del
    contrato.
    """
    if hacia.lower() not in ("usd", "cop"):
        raise ErrorValidacion(f"`hacia` debe ser 'usd' o 'cop', no {hacia!r}.",
                              "usd convierte de pesos a dólares; cop, al revés.")
    try:
        valor = float(monto)
    except (TypeError, ValueError):
        raise ErrorValidacion(f"Monto no numérico: {monto!r}.",
                              "Pásalo como número, sin separadores de miles.") from None

    f = _normaliza_fecha(fecha)
    dato = await _trm_de(f)
    if not dato:
        raise ErrorNoEncontrado(
            f"Sin TRM vigente para {f}.",
            "La serie va de 2003 a hoy; comprueba el año.")
    tasa = fmt.a_numero(dato.get("valor"))
    if not tasa:
        raise ErrorNoEncontrado(f"La TRM de {f} llegó vacía de la fuente.",
                                "Prueba con el día anterior.")

    if hacia.lower() == "usd":
        resultado = valor / tasa
        filas = [{"monto (COP)": fmt.moneda(valor), "TRM": fmt.numero(tasa),
                  "fecha de la TRM": fmt.fecha(dato.get("vigenciadesde")),
                  "monto (USD)": _usd(resultado)}]
    else:
        resultado = valor * tasa
        filas = [{"monto (USD)": _usd(valor),
                  "TRM": fmt.numero(tasa),
                  "fecha de la TRM": fmt.fecha(dato.get("vigenciadesde")),
                  "monto (COP)": fmt.moneda(resultado)}]

    sobre = Sobre(datos=filas, total=Total.completo(1), mostrar_conteo=False,
                  consulta=dato["_consulta"], fuente=_fuente(TRM))
    sobre.advertir(AVISO_NO_DEFLACTOR)
    if str(dato.get("vigenciadesde"))[:10] != f:
        sobre.advertir(
            f"Se usó la TRM certificada el {fmt.fecha(dato.get('vigenciadesde'))}, "
            f"que es la vigente el {f}.")
    return sobre.render(lambda x: fmt.tabla_markdown(x))


def _usd(valor: float) -> str:
    """Dólares con la convención es-CO: punto de miles, coma decimal.

    `f"{v:,.2f}".replace(",", ".")` parecía bastar y convertía también el punto
    decimal: 250.000,00 salía como «250.000.00», que es la misma cifra leída
    como doscientos cincuenta mil con dos decimales o como algo sin sentido,
    según quien lo lea. Hay que separar la parte entera antes de sustituir.
    """
    entero, decimales = f"{valor:,.2f}".split(".")
    return f"US$ {entero.replace(',', '.')},{decimales}"


async def tasas(descripcion: str | None = None, desde: str = "", hasta: str = "",
                limite: int = 20, formato: str = "tabla", grafica: bool = True):
    """Tasas de captación por tipo de producto, promediadas sobre un periodo.

    Una fila de la fuente es lo que UNA entidad reportó en un corte, no una
    tasa de mercado. El promedio simple de los reportes no es la tasa del
    sistema, que se pondera por el monto captado; esto devuelve las dos para
    que la diferencia sea visible.
    """
    partes = []
    if desde:
        partes.append(f"fechacorte >= '{_normaliza_fecha(desde, 'desde')}'")
    if hasta:
        partes.append(f"fechacorte <= '{_normaliza_fecha(hasta, 'hasta')}T23:59:59'")
    if descripcion:
        cat = await socrata.filtro_categorico(TASAS.id, "descripcion", descripcion)
        if cat.filtro is None:
            sobre = Sobre(datos=[], total=Total.completo(0), fuente=_fuente(TASAS))
            sobre.advertir(
                f"«{descripcion}» no es ninguno de los productos de esta fuente. "
                "No es un fallo.")
            return sobre.render(lambda _f: "_Sin coincidencias._")
        partes.append(cat.filtro)
    # Se comprueba lo que de verdad acota, no que haya SALIDO un filtro: con
    # solo `hasta` había filtro —y por tanto pasaba—, pero un límite superior
    # posterior al último reporte no descarta nada, así que la agregación
    # recorría los 2,1 M de filas: exactamente la consulta que esta validación
    # existe para evitar.
    if not (desde or descripcion):
        raise ErrorValidacion(
            "Hace falta al menos `desde` o `descripcion`.",
            "La fuente tiene 2.102.178 filas: sin filtro la agregación hace un "
            "recorrido completo y agota el tiempo. `hasta` por sí solo no "
            "acota nada: pasa también `desde`.")
    donde = " AND ".join(partes) or None

    tope = min(int(limite), 100)
    SELECT = ("descripcion, count(*) as reportes, avg(tasa) as tasa_promedio, "
              "sum(monto) as monto_total")
    r = await socrata.consultar(TASAS.id, seleccionar=SELECT, donde=donde,
                                agrupar="descripcion", ordenar="monto_total DESC",
                                limite=tope)
    crudos = [fmt.a_numero(f.get("monto_total")) or 0 for f in r["filas"]]
    filas = [{"producto": fmt.limpia_texto(f.get("descripcion")),
              "reportes": fmt.numero(f.get("reportes")),
              "tasa promedio (simple)": _pct(f.get("tasa_promedio")),
              "monto captado": fmt.moneda(f.get("monto_total"))}
             for f in r["filas"]]
    if grafica and formato == "tabla" and filas:
        for fila, barra in zip(filas, fmt.barras(crudos)):
            fila["gráfica"] = barra

    sobre = Sobre(datos=filas, orden="monto_total DESC", consulta=r["consulta"],
                  fuente=_fuente(TASAS))
    await agregacion.anota_total(sobre, r["filas"], tope, dataset_id=TASAS.id,
                                 seleccionar=SELECT, agrupar="descripcion",
                                 donde=donde)
    sobre.advertir(
        "La tasa es un PROMEDIO SIMPLE de los reportes de cada entidad, no la "
        "tasa del sistema: esa se pondera por el monto captado, que va en la "
        "columna de al lado. Una entidad pequeña con tasa alta pesa aquí lo "
        "mismo que un banco grande.")
    for n in TASAS.notas:
        sobre.advertir(n)
    return sobre.render(lambda f: fmt.tabla_markdown(f), formato=formato)


def _pct(valor) -> str:
    n = fmt.a_numero(valor)
    return f"{n:.2f} %" if n is not None else ""
