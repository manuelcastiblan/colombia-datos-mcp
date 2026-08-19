"""Cuándo un periodo de una serie todavía no ha cerrado.

Es el error fundacional del proyecto: una serie anual cuyo último año llega
hasta julio parece una caída del 40 % que no existe. Cada módulo lo resolvía por
su cuenta —o no lo resolvía—, con tres consecuencias distintas:

* `co_crimen_serie` calculaba el máximo y el mínimo de la serie **incluyendo** el
  año incompleto, y ofrecía como «mínimo histórico» un año que corta en julio,
  justo en el aviso que existe para evitar elegir mal el año base.
* `co_crimen_por_municipio` y `co_crimen_serie` afirmaban «el último año está
  incompleto» siempre que hubiera fecha de corte, aunque la serie pedida
  terminara en un año cerrado. Una falsa alarma acaba enseñando a ignorar el
  aviso, que es peor que no darlo.
* `co_crimen_comparar` no avisaba en absoluto: comparar 2017 con 2026 devolvía
  una caída del 31 % en homicidios sin una sola advertencia.
"""

from __future__ import annotations

import calendar

_LARGO = {"anio": 4, "mes": 7, "dia": 10}


def cerrado(corte: str | None, periodo: str) -> bool:
    """¿La fecha de corte cae justo al final de su periodo?

    Se calcula con el calendario, no con una lista de días plausibles: febrero
    cierra el 28 o el 29 según el año, y abril el 30.
    """
    if not corte or len(corte) < 10:
        return True
    if periodo == "dia":
        return True
    anio, mes, dia = int(corte[0:4]), int(corte[5:7]), int(corte[8:10])
    if periodo == "mes":
        return dia == calendar.monthrange(anio, mes)[1]
    return (mes, dia) == (12, 31)


def incompleto(etiqueta: str | int | None, corte: str | None, periodo: str = "anio") -> bool:
    """¿`etiqueta` —«2026», «2026-08»— es el periodo donde cortan los datos y
    ese periodo aún no ha cerrado?"""
    if not (corte and etiqueta):
        return False
    texto = str(etiqueta)
    return texto == corte[:len(texto)] and not cerrado(corte, periodo)


def comparables(filas: list[dict], corte: str | None, periodo: str = "anio",
                clave: str = "periodo") -> list[dict]:
    """La serie sin su último periodo, si ese periodo no ha cerrado.

    Para máximos, mínimos y cualquier comparación entre periodos: mezclar uno
    incompleto con los cerrados produce extremos que no existen.
    """
    if filas and incompleto(filas[-1].get(clave), corte, periodo):
        return filas[:-1]
    return filas
