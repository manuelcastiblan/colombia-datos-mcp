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


def contiene_corte(etiqueta: str | int | None, corte: str | None) -> bool:
    """¿`etiqueta` —«2026», «2026-08», «2026-08-24»— es el periodo donde se
    detuvo la carga de datos?

    Distinto de `incompleto`, y la diferencia importa. Hay dos preguntas:

    * ¿cerró el **calendario**? — se demuestra con la fecha (un año cierra el 31
      de diciembre, un día cierra siempre).
    * ¿terminó la **carga**? — no se puede demostrar, pero el periodo donde
      cortan los datos es justo donde la fuente dejó de cargar, así que casi
      nunca está completo.

    Para años y meses la primera implica la segunda. Para días no: el 24 de
    agosto cerró como día y aun así traía 1.194 contratos frente a los ~4.500 de
    un lunes normal, porque la carga se quedó a medias. Confundir las dos
    preguntas hacía que una serie diaria terminara en un desplome inventado.
    """
    if not (corte and etiqueta):
        return False
    texto = str(etiqueta)
    return texto == corte[:len(texto)]


def incompleto(etiqueta: str | int | None, corte: str | None, periodo: str = "anio") -> bool:
    """Incompleto DEMOSTRABLE: contiene el corte y el calendario dice que no
    ha cerrado. Es el caso que permite afirmarlo sin matices."""
    return contiene_corte(etiqueta, corte) and not cerrado(corte, periodo)


def comparables(filas: list[dict], corte: str | None, periodo: str = "anio",
                clave: str = "periodo") -> list[dict]:
    """La serie sin su último periodo, si ahí es donde cortan los datos.

    Para máximos, mínimos y cualquier comparación entre periodos. Se excluye
    aunque el calendario haya cerrado: un día a medio cargar puede salir como
    «mínimo de la serie» con la misma facilidad que un año a medias.
    """
    if filas and contiene_corte(filas[-1].get(clave), corte):
        return filas[:-1]
    return filas
