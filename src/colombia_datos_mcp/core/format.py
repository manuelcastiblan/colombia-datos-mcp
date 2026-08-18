"""Formateo para el modelo: tablas markdown, moneda es-CO, fechas, mojibake.

El diseño (§4.1) es explícito: nunca JSON indentado con miles de filas. La
forma es parte del contrato.
"""

from __future__ import annotations

import re
from datetime import datetime

_MOJIBAKE = {
    "": "'", "": '"', "": '"', "": "-", "": "-",
    " ": " ",
}


def limpia_texto(valor) -> str:
    """Repara el mojibake de origen de SECOP y colapsa espacios."""
    if valor is None:
        return ""
    s = str(valor)
    for malo, bueno in _MOJIBAKE.items():
        s = s.replace(malo, bueno)
    return re.sub(r"\s+", " ", s).strip()


# El nombre del campo decide el formato. El orden importa: "valor total" es
# dinero, pero "total" a secas es el alias que Socrata da a `count(*)`, y
# formatearlo como pesos convertía "125 municipios" en "$125".
_MONETARIOS = ("valor", "precio", "cuantia", "saldo", "monto", "pagado", "presupuesto")
_CONTEOS = ("total", "conteo", "count", "contratos", "cantidad", "numero", "registros")


def es_monetario(campo: str) -> bool:
    return any(p in campo.lower() for p in _MONETARIOS)


def es_conteo(campo: str) -> bool:
    """Solo si no es monetario: `valor_total` es dinero, `total` es un conteo."""
    n = campo.lower()
    return not es_monetario(n) and any(p in n for p in _CONTEOS)


def moneda(valor) -> str:
    """Formato colombiano: $1.234.567 (punto de miles, sin decimales)."""
    if valor in (None, ""):
        return "-"
    try:
        n = float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return limpia_texto(valor)
    entero = f"{abs(n):,.0f}".replace(",", ".")
    return f"{'-' if n < 0 else ''}${entero}"


def fecha(valor) -> str:
    """Socrata devuelve floating timestamps sin zona; se muestran como fecha."""
    if not valor:
        return "-"
    s = str(valor)
    for formato in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, formato).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return limpia_texto(s)


def numero(valor) -> str:
    if valor in (None, ""):
        return "-"
    try:
        n = float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return limpia_texto(valor)
    if n == int(n):
        return f"{int(n):,}".replace(",", ".")
    return f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def recorta(valor, ancho: int = 60) -> str:
    s = limpia_texto(valor)
    return s if len(s) <= ancho else s[: ancho - 1] + "…"


def columnas_union(filas: list[dict]) -> list[str]:
    """Unión de las claves de todas las filas, en orden de aparición.

    Socrata OMITE los campos nulos en vez de mandarlos vacíos, así que dos
    filas del mismo dataset traen juegos de claves distintos. Deducir las
    columnas solo de la primera fila perdía en silencio los datos de las demás:
    un contrato en borrador sin `fecha_de_firma` a la cabeza de la tabla
    borraba la fecha de las once filas que sí la tenían.
    """
    vistas = {}
    for f in filas:
        for k in f:
            vistas.setdefault(k, None)
    return list(vistas)


def tabla_markdown(filas: list[dict], columnas: list[str] | None = None) -> str:
    """Tabla markdown compacta. Sin filas devuelve una nota, no una tabla vacía."""
    if not filas:
        return "_Sin resultados para esta consulta._"
    columnas = columnas or columnas_union(filas)
    cabecera = "| " + " | ".join(columnas) + " |"
    sep = "|" + "|".join("---" for _ in columnas) + "|"
    cuerpo = [
        "| " + " | ".join(str(f.get(c, "") or "").replace("|", "\\|") for c in columnas) + " |"
        for f in filas
    ]
    return "\n".join([cabecera, sep, *cuerpo])
