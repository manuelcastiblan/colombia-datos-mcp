"""Presupuesto de tokens y degradación automática (§4.3).

El eje donde fallan los ocho servidores auditados: ninguno trata el tamaño de
respuesta como concepto de primera clase. Aquí sí, y la degradación es
explícita en el sobre — nunca truncado silencioso.
"""

from __future__ import annotations

import os
from enum import Enum

# Aproximación deliberadamente conservadora. El español con acentos y los
# nombres largos de entidades pesan más que el inglés: ~3.5 caracteres/token.
CARACTERES_POR_TOKEN = 3.5

PRESUPUESTO_POR_DEFECTO = int(os.environ.get("CO_PRESUPUESTO_TOKENS", "6000"))


class Detalle(str, Enum):
    CONTEO = "conteo"
    RESUMEN = "resumen"
    COMPLETO = "completo"


ORDEN_DEGRADACION = [Detalle.COMPLETO, Detalle.RESUMEN, Detalle.CONTEO]


def estima_tokens(texto: str) -> int:
    return int(len(texto) / CARACTERES_POR_TOKEN) + 1


def siguiente_nivel(actual: Detalle) -> Detalle | None:
    """Degrada completo -> resumen -> conteo. None si ya no se puede bajar."""
    try:
        i = ORDEN_DEGRADACION.index(actual)
    except ValueError:
        return Detalle.RESUMEN
    return ORDEN_DEGRADACION[i + 1] if i + 1 < len(ORDEN_DEGRADACION) else None


def ajusta_filas(filas: list, render, presupuesto: int = PRESUPUESTO_POR_DEFECTO):
    """Recorta la lista de filas hasta que `render(filas)` quepa.

    Devuelve (filas_que_caben, texto, se_recorto). Nunca devuelve cero filas si
    había al menos una: si ni una sola cabe, entrega esa y deja que el llamador
    marque el truncamiento.
    """
    if not filas:
        return filas, render(filas), False

    texto = render(filas)
    if estima_tokens(texto) <= presupuesto:
        return filas, texto, False

    bajo, alto = 1, len(filas)
    mejor = 1
    while bajo <= alto:
        medio = (bajo + alto) // 2
        if estima_tokens(render(filas[:medio])) <= presupuesto:
            mejor = medio
            bajo = medio + 1
        else:
            alto = medio - 1
    recortadas = filas[:mejor]
    return recortadas, render(recortadas), True
