"""Series temporales y perfilado de calidad, para cualquier dataset.

Las dos herramientas de aquí nacieron de errores cometidos usando el servidor,
no de una lista de deseos:

* **`serie`** existe porque escribir `date_extract_y(...)` a mano seis veces en
  una sesión es una señal, y porque comparar un año incompleto con años cerrados
  —sin que nada avise— produjo una cifra equivocada. Ahora el corte de datos se
  consulta y se anuncia.
* **`perfilar`** existe porque descubrir que nueve contratos aportaban el 94 %
  de la suma de SECOP costó una investigación entera. Debería costar una
  llamada, y por eso el perfil incluye la concentración: si unos pocos valores
  dominan el total, lo dice antes de que nadie cite la cifra.
"""

from __future__ import annotations

import asyncio

from . import agregacion
from ..adapters import socrata
from ..core import format as fmt
from ..core.envelope import Fuente, Sobre
from ..core.errors import ErrorValidacion

PERIODOS = {
    "anio": ("date_extract_y({c})", 4),
    "mes": ("date_trunc_ym({c})", 7),
    "dia": ("date_trunc_ymd({c})", 10),
}

# Umbrales para el reparto por orden de magnitud. Son los que hacen visible de
# un vistazo que una columna de dinero tiene valores imposibles.
_ESCALONES = (10**3, 10**6, 10**9, 10**12, 10**15, 10**18)


def _fuente(esq: dict | None, dataset_id: str) -> Fuente:
    if not esq:
        return Fuente(id=dataset_id)
    return Fuente(id=esq.get("id") or dataset_id, nombre=esq.get("nombre") or "",
                  actualizado=fmt.fecha(esq.get("actualizado")),
                  licencia=esq.get("licencia"), atribucion=esq.get("atribucion"))


async def _columna(dataset_id: str, campo: str) -> dict:
    esq = await socrata.esquema(dataset_id)
    if not esq:
        raise ErrorValidacion(
            f"No se encontró el dataset {dataset_id}.",
            "Los IDs de Socrata rotan. Búscalo con co_datos_buscar_datasets.",
        )
    col = next((c for c in esq["columnas"] if c["campo"] == campo), None)
    if not col:
        raise ErrorValidacion(
            f"La columna {campo!r} no existe en {dataset_id}.",
            "Campos válidos: " + ", ".join(sorted(c["campo"] for c in esq["columnas"] if c["campo"])),
        )
    return {"esq": esq, "col": col}


# ------------------------------------------------------------------ serie --
async def serie(dataset_id: str, campo_fecha: str, metrica: str = "count(*) as casos",
                periodo: str = "anio", desde: str | None = None, hasta: str | None = None,
                donde: str | None = None, formato: str = "tabla", grafica: bool = True):
    """Agrupa por periodo sobre una columna de fecha."""
    if periodo not in PERIODOS:
        raise ErrorValidacion(
            f"periodo debe ser uno de: {', '.join(PERIODOS)}.",
            "Con 'dia' acota el rango o saldrán miles de filas.",
        )
    info = await _columna(dataset_id, campo_fecha)
    tipo = (info["col"]["tipo"] or "").lower()
    if "calendar" not in tipo:
        # El caso real: en el Plan Anual de Adquisiciones (9sue-ezhx) las cinco
        # columnas de fecha son `text`. Agrupar por año sobre ellas falla, y
        # filtrarlas con `between` da resultados silenciosamente falsos.
        raise ErrorValidacion(
            f"`{campo_fecha}` es de tipo «{info['col']['tipo']}», no una fecha.",
            "Sobre una columna de texto no se puede agrupar por periodo ni "
            "comparar con between. Mira los tipos con co_datos_describir_dataset.",
        )

    expr = PERIODOS[periodo][0].format(c=campo_fecha)
    partes = [donde] if donde else []
    if desde:
        partes.append(f"{campo_fecha} >= '{socrata.escapa(desde)}'")
    if hasta:
        partes.append(f"{campo_fecha} <= '{socrata.escapa(hasta)}'")
    filtro = " AND ".join(partes) or None

    # 2.000 periodos sobran para años y meses, pero NO para días: SECOP II
    # abarca ~4.030, así que una serie diaria se cortaba por la mitad y el
    # sobre la daba por completa.
    TOPE = 2000
    SELECT = f"{expr} as periodo, {metrica}"
    r, extremos = await asyncio.gather(
        socrata.consultar(dataset_id, seleccionar=SELECT, donde=filtro,
                          agrupar=expr, ordenar="periodo", limite=TOPE),
        socrata.consultar(dataset_id, seleccionar=f"max({campo_fecha}) as h", limite=1),
    )
    corte = (extremos["filas"][0].get("h") or "")[:10] if extremos["filas"] else ""

    alias = _alias(metrica)
    crudos = [fmt.a_numero(f.get(alias)) or 0 for f in r["filas"]]
    largo = PERIODOS[periodo][1]
    filas = [{"periodo": str(f.get("periodo") or "")[:largo],
              alias: fmt.numero(f.get(alias)) if not fmt.es_monetario(alias)
                     else fmt.moneda(f.get(alias))} for f in r["filas"]]
    if grafica and formato == "tabla" and filas:
        for fila, barra in zip(filas, fmt.barras(crudos)):
            fila["gráfica"] = barra

    sobre = Sobre(datos=filas, orden="periodo", consulta=r["consulta"],
                  fuente=_fuente(info["esq"], dataset_id))
    await agregacion.anota_total(sobre, r["filas"], TOPE, dataset_id=dataset_id,
                                 seleccionar=SELECT, agrupar=expr, donde=filtro)
    _avisa_periodo_incompleto(sobre, filas, corte, periodo)
    if len(crudos) > 1:
        sobre.advertir(
            f"Máximo de la serie: {fmt.numero(max(crudos))} · mínimo: "
            f"{fmt.numero(min(crudos))}. El periodo que tomes como base cambia "
            "cualquier porcentaje que calcules, y a veces le cambia el signo."
        )
    return sobre.render(lambda f: fmt.tabla_markdown(f), formato=formato)


def _alias(metrica: str) -> str:
    import re
    m = re.findall("(?:^|[ ,(])as +([A-Za-z_][A-Za-z0-9_]*)", str(metrica or ""), re.I)
    return m[0] if m else "valor"


def _avisa_periodo_incompleto(sobre: Sobre, filas: list, corte: str, periodo: str) -> None:
    """El último periodo casi nunca está cerrado, y nada en los datos lo dice.

    Es el error que motivó la herramienta: una serie anual cuyo último año llega
    hasta julio parece una caída del 40 % si se compara con los anteriores.
    """
    if not (corte and filas):
        return
    ultimo = filas[-1]["periodo"]
    cerrado = {"anio": corte.endswith("-12-31"),
               "mes": corte[8:10] in ("28", "29", "30", "31"),
               "dia": True}[periodo]
    if ultimo == corte[:len(ultimo)] and not cerrado:
        sobre.advertir(
            f"ATENCIÓN: los datos cortan el {corte}, así que «{ultimo}» está "
            "INCOMPLETO. Compararlo con periodos cerrados produce caídas que no "
            "existen. Exclúyelo o dilo al citarlo."
        )
    else:
        sobre.advertir(f"Los datos de la fuente llegan hasta {corte}.")


# --------------------------------------------------------------- perfilar --
async def perfilar(dataset_id: str, campo: str, donde: str | None = None):
    """Retrato de una columna: nulos, rango, reparto por magnitud y concentración."""
    info = await _columna(dataset_id, campo)
    col = info["col"]
    tipo = (col["tipo"] or "").lower()

    total, no_nulos = await asyncio.gather(
        socrata.contar(dataset_id, donde=donde),
        socrata.contar(dataset_id, donde=" AND ".join(
            [p for p in [donde, f"{campo} IS NOT NULL"] if p])),
    )
    nulos = max(0, total - no_nulos)
    lineas = [f"**{col['nombre'] or campo}** · `{campo}` · tipo {col['tipo']}", ""]
    lineas.append(f"- Filas: **{fmt.numero(total)}** · con valor: {fmt.numero(no_nulos)}"
                  + (f" · **nulas: {fmt.numero(nulos)}** ({nulos / total * 100:.1f} %)"
                     if total and nulos else ""))

    sobre = Sobre(datos=[], fuente=_fuente(info["esq"], dataset_id), mostrar_conteo=False)
    if col.get("descripcion"):
        lineas.append(f"- Descripción de la fuente: {fmt.recorta(col['descripcion'], 120)}")

    if "number" in tipo or "money" in tipo:
        await _perfil_numerico(dataset_id, campo, donde, lineas, sobre)
    elif "calendar" in tipo:
        await _perfil_fecha(dataset_id, campo, donde, lineas, sobre)
    else:
        await _perfil_texto(dataset_id, campo, donde, lineas, sobre)

    if nulos:
        sobre.advertir(
            "Socrata OMITE los campos nulos en vez de mandarlos vacíos: esas "
            f"{fmt.numero(nulos)} filas no traen la clave `{campo}` en el JSON."
        )
    sobre.datos = [{"campo": campo, "tipo": col["tipo"], "filas": total,
                    "con_valor": no_nulos, "nulos": nulos}]
    return sobre.render(lambda _f: "\n".join(lineas))


async def _perfil_numerico(dataset_id, campo, donde, lineas, sobre):
    base, mayores = await asyncio.gather(
        socrata.consultar(dataset_id,
                          seleccionar=f"min({campo}) as mn, max({campo}) as mx, "
                                      f"sum({campo}) as suma, avg({campo}) as media",
                          donde=donde, limite=1),
        socrata.consultar(dataset_id, seleccionar=campo, donde=donde,
                          ordenar=f"{campo} DESC", limite=10),
    )
    f = base["filas"][0] if base["filas"] else {}
    mn, mx = fmt.a_numero(f.get("mn")), fmt.a_numero(f.get("mx"))
    suma = fmt.a_numero(f.get("suma")) or 0
    lineas += ["", f"- Rango: **{fmt.numero(mn)}** a **{fmt.numero(mx)}**",
               f"- Suma: {fmt.numero(suma)} · media: {fmt.numero(f.get('media'))}"]

    # Reparto por orden de magnitud: es lo que delata una segunda población.
    escalones = [e for e in _ESCALONES if mx and e <= mx]
    if escalones:
        conteos = await asyncio.gather(*[
            socrata.contar(dataset_id, donde=" AND ".join(
                [p for p in [donde, f"{campo} > {e}"] if p])) for e in escalones])
        lineas += ["", "| Por encima de | Filas |", "|---|---|"]
        for e, n in zip(escalones, conteos):
            lineas.append(f"| {fmt.numero(e)} | {fmt.numero(n)} |")

    # Concentración: el hallazgo que costó una investigación entera en SECOP.
    top = [fmt.a_numero(x.get(campo)) or 0 for x in mayores["filas"]]
    if suma > 0 and top:
        parte = sum(top) / suma * 100
        lineas += ["", f"- Los **{len(top)} valores mayores** aportan el "
                       f"**{parte:.1f} %** de la suma."]
        if parte > 50:
            sobre.advertir(
                f"ATENCIÓN: {len(top)} filas de {fmt.numero(await socrata.contar(dataset_id, donde=donde))} "
                f"aportan el {parte:.1f} % de la suma de `{campo}`. Una suma así no "
                "describe al conjunto: revisa si son valores reales o errores de "
                "digitación antes de citarla."
            )


async def _perfil_fecha(dataset_id, campo, donde, lineas, sobre):
    r = await socrata.consultar(
        dataset_id, seleccionar=f"min({campo}) as mn, max({campo}) as mx",
        donde=donde, limite=1)
    f = r["filas"][0] if r["filas"] else {}
    mn, mx = (f.get("mn") or "")[:10], (f.get("mx") or "")[:10]
    lineas += ["", f"- Rango: **{mn}** a **{mx}**"]
    if mx and not mx.endswith("-12-31"):
        sobre.advertir(
            f"La serie corta el {mx}: el último periodo está incompleto. "
            "Compararlo con periodos cerrados inventa caídas."
        )


async def _perfil_texto(dataset_id, campo, donde, lineas, sobre):
    r = await socrata.consultar(
        dataset_id, seleccionar=f"{campo}, count(*) as n", donde=donde,
        agrupar=campo, ordenar="n DESC", limite=10)
    filas = r["filas"]
    lineas += ["", "| Valor más frecuente | Filas |", "|---|---|"]
    for x in filas:
        lineas.append(f"| {fmt.recorta(x.get(campo), 46) or '—'} | {fmt.numero(x.get('n'))} |")
    if len(filas) >= 10:
        sobre.advertir(
            "Solo se muestran los 10 valores más frecuentes: la columna tiene más. "
            "Si vas a filtrar por ella, mira el dominio completo con co_datos_agregar."
        )
