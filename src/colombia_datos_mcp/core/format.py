"""Formateo para el modelo: tablas markdown, moneda es-CO, fechas, mojibake.

El diseño (§4.1) es explícito: nunca JSON indentado con miles de filas. La
forma es parte del contrato.
"""

from __future__ import annotations

import csv
import io
import json
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
# Códigos que PARECEN números y no lo son. Formatear un DIVIPOLA como cifra le
# mete puntos de miles y le come el cero inicial: "05001" -> "5.001", y con eso
# se rompe todo join territorial.
_IDENTIFICADORES = ("documento", "nit", "codigo", "cod_", "cedula", "cédula",
                    "divipola", "id_entidad", "_id", "id_proceso", "proveedor")


def es_monetario(campo: str) -> bool:
    return any(p in campo.lower() for p in _MONETARIOS)


def es_identificador(campo: str) -> bool:
    return any(p in campo.lower() for p in _IDENTIFICADORES)


def es_entero(valor) -> bool:
    """Entero puro en texto. Ni decimales ni notación científica."""
    s = str(valor).strip().lstrip("-")
    return bool(s) and s.isdigit()


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


# ------------------------------------------------------------- extracción --
FORMATOS = ("tabla", "csv", "json")


def a_numero(valor):
    """Número a partir de lo que manda Socrata, o None si no lo es.

    Los valores llegan como string y a veces ya formateados (`$1.234`), así que
    se limpia todo lo que no sea dígito o separador y se aplica la convención
    colombiana: el punto separa miles y la coma es decimal.
    """
    if isinstance(valor, (int, float)):
        return float(valor)
    crudo = re.sub(r"[^\d,.\-]", "", str(valor or ""))
    if not crudo or crudo in ("-", ".", ","):
        return None
    comas, puntos = crudo.count(","), crudo.count(".")
    if comas and puntos:
        corte = max(crudo.rfind(","), crudo.rfind("."))
    elif comas + puntos == 1:
        corte = max(crudo.rfind(","), crudo.rfind("."))
        # "1.000" son mil, no uno con milésimas. Pero la forma de agrupación
        # exige AMBAS mitades: hasta tres dígitos delante y exactamente tres
        # detrás. Sin la primera condición, una suma agregada como
        # `5093243848602202766138.364` se leía como separador de miles y salía
        # mil veces mayor de lo que es.
        entera, decimal = crudo[:corte].lstrip("-"), crudo[corte + 1:]
        if len(decimal) == 3 and 1 <= len(entera) <= 3:
            corte = -1
    else:
        corte = -1  # varios separadores iguales: todos son de miles
    try:
        if corte == -1:
            return float(re.sub(r"[,.]", "", crudo))
        return float(re.sub(r"[,.]", "", crudo[:corte]) + "." + crudo[corte + 1:])
    except ValueError:
        return None


def csv_texto(filas: list[dict], columnas: list[str] | None = None) -> str:
    """CSV con cabecera, separador coma y comillas RFC 4180.

    Existe para que el resultado se pueda pegar en una hoja de cálculo o leer
    desde un script sin volver a parsear una tabla markdown.
    """
    if not filas:
        return ""
    columnas = columnas or columnas_union(filas)
    buffer = io.StringIO()
    escritor = csv.DictWriter(buffer, fieldnames=columnas, extrasaction="ignore",
                              lineterminator="\n")
    escritor.writeheader()
    for f in filas:
        escritor.writerow({c: f.get(c, "") for c in columnas})
    return buffer.getvalue().rstrip("\n")


def json_texto(filas: list[dict]) -> str:
    """JSON legible y sin escapar los acentos."""
    return json.dumps(filas, ensure_ascii=False, indent=1)


def cuerpo_por_formato(formato: str):
    """Función `filas -> texto` para el formato pedido.

    Se invoca dentro del presupuesto de tokens, así que tiene que funcionar con
    cualquier subconjunto de filas.
    """
    if formato == "csv":
        return csv_texto
    if formato == "json":
        return json_texto
    return tabla_markdown


# ----------------------------------------------------------------- barras --
# Bloques de un octavo: dan resolución sin salirse de una celda de la tabla.
_BLOQUES = "▏▎▍▌▋▊▉█"


def barras(valores, ancho: int = 16) -> list[str]:
    """Barras proporcionales al máximo absoluto, para leer una agregación de un
    vistazo sin salir de la terminal.

    Todas comparten escala, que es lo que las hace comparables. Un valor que no
    es número devuelve cadena vacía: más honesto que dibujar una barra de cero.
    """
    nums = [a_numero(v) for v in valores]
    tope = max((abs(n) for n in nums if n is not None), default=0.0)
    salida = []
    for n in nums:
        if n is None or tope <= 0:
            salida.append("")
            continue
        octavos = round(abs(n) / tope * ancho * 8)
        llenos, resto = divmod(octavos, 8)
        barra = "█" * llenos + (_BLOQUES[resto - 1] if resto else "")
        # Un valor pequeño pero no nulo no debe verse igual que un cero.
        if not barra and n:
            barra = _BLOQUES[0]
        salida.append(barra)
    return salida
