"""Formateo para el modelo: tablas markdown, moneda es-CO, fechas, mojibake.

El diseño (§4.1) es explícito: nunca JSON indentado con miles de filas. La
forma es parte del contrato.
"""

from __future__ import annotations

import re
import unicodedata
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


def sin_acentos(valor: str) -> str:
    """Para comparar contra datos con acentos destruidos en origen."""
    s = unicodedata.normalize("NFKD", limpia_texto(valor))
    return "".join(c for c in s if not unicodedata.combining(c)).upper()


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


def tabla_markdown(filas: list[dict], columnas: list[str] | None = None) -> str:
    """Tabla markdown compacta. Sin filas devuelve una nota, no una tabla vacía."""
    if not filas:
        return "_Sin resultados para esta consulta._"
    columnas = columnas or list(filas[0].keys())
    cabecera = "| " + " | ".join(columnas) + " |"
    sep = "|" + "|".join("---" for _ in columnas) + "|"
    cuerpo = [
        "| " + " | ".join(str(f.get(c, "") or "").replace("|", "\\|") for c in columnas) + " |"
        for f in filas
    ]
    return "\n".join([cabecera, sep, *cuerpo])
