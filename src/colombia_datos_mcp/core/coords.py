"""Normalización de coordenadas de DIVIPOLA (Anexo F del diseño).

Socrata entrega `longitud`/`latitud` como texto con coma decimal. En
`xaxy-8nri` exactamente un registro de 8.161 -- Medellín -- trae además
separadores de miles (`"-75,581,775"`), y `float(s.replace(",", "."))` lanza
`ValueError` sobre él.

Regla: la PRIMERA coma o punto es el separador decimal; los siguientes son
ruido. Funciona porque en Colombia la parte entera de la longitud tiene dos
dígitos y la de la latitud una o dos. La caja envolvente es la red de
seguridad.
"""

from __future__ import annotations

import re

from .errors import ErrorValidacion

# Caja envolvente de Colombia con holgura, incluyendo San Andrés y Malpelo.
LON_MIN, LON_MAX = -82.0, -66.8
LAT_MIN, LAT_MAX = -4.4, 13.6

_BASURA = re.compile(r"[^\d,.\-+]")
_SEPARADOR = re.compile(r"[,.]")


def normaliza_coord(bruto, eje: str) -> float:
    """Convierte una coordenada en texto de Socrata a float validado.

    `eje` es "lon" o "lat".
    """
    if eje not in ("lon", "lat"):
        raise ValueError("eje debe ser 'lon' o 'lat'")
    if bruto is None:
        raise ErrorValidacion(
            "Coordenada ausente",
            "El registro no trae longitud/latitud; descártalo o usa la geometría del MGN.",
        )

    s = _BASURA.sub("", str(bruto).strip())
    if not s or s in ("-", "+"):
        raise ErrorValidacion(
            f"Coordenada vacía o no numérica: {bruto!r}",
            "Verifica el campo de origen; en DIVIPOLA algunos registros vienen sin coordenada.",
        )

    signo = -1.0 if s.startswith("-") else 1.0
    s = s.lstrip("+-")

    partes = _SEPARADOR.split(s)
    if len(partes) == 1:
        valor = float(partes[0])
    else:
        # La primera es el decimal; el resto son separadores de miles espurios.
        valor = float(f"{partes[0]}.{''.join(partes[1:])}")
    valor *= signo

    minimo, maximo = (LON_MIN, LON_MAX) if eje == "lon" else (LAT_MIN, LAT_MAX)
    if not (minimo <= valor <= maximo):
        raise ErrorValidacion(
            f"Coordenada {valor} fuera de Colombia para {eje} (crudo: {bruto!r})",
            "Revisa si el registro tiene lon/lat invertidas o si el dato de origen está corrupto.",
        )
    return valor


def normaliza_par(fila: dict, campo_lon="longitud", campo_lat="latitud"):
    """Devuelve (lon, lat) o None si la fila no tiene coordenada utilizable."""
    try:
        return (
            normaliza_coord(fila.get(campo_lon), "lon"),
            normaliza_coord(fila.get(campo_lat), "lat"),
        )
    except ErrorValidacion:
        return None
