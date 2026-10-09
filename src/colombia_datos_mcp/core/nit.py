"""NIT colombianos: el mismo número aparece con y sin dígito de verificación.

En SECOP II el NIT de Bogotá está cargado como `899999061` y como `8999990619`,
y el del SENA como `899999034` y `8999990341`. Son 92 parejas que tocan el
28,9 % de los contratos de prestación de servicios de 2026, así que filtrar por
una sola forma pierde en silencio la mitad de los organismos de la entidad —y
agrupar por `nit_entidad` sin unificarlas infla cualquier conteo de «contratista
en varias entidades».

El dígito de verificación se calcula con el algoritmo de la DIAN.
"""

from __future__ import annotations

PESOS = (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71)


def solo_digitos(valor) -> str:
    return "".join(c for c in str(valor or "") if c.isdigit())


def digito_verificacion(base: str) -> int | None:
    """DV de un NIT ya reducido a dígitos. None si no hay nada que calcular."""
    base = solo_digitos(base)
    if not base or len(base) > len(PESOS):
        return None
    resto = sum(int(c) * p for c, p in zip(reversed(base), PESOS)) % 11
    return resto if resto < 2 else 11 - resto


def equivalentes(valor) -> list[str]:
    """Las dos formas del mismo NIT, la corta primero.

    Solo se expanden los números que empiezan por 8 o 9, que es el rango de los
    NIT de entidades. Una cédula de diez dígitos tiene 1 posibilidad entre 11 de
    pasar la prueba del dígito de verificación por azar, y plegarla a nueve
    dígitos buscaría los contratos de otra persona: ese error es peor que no
    expandir nada.
    """
    d = solo_digitos(valor)
    if not d:
        return []
    if d[0] not in "89":
        return [d]
    if len(d) == 9:
        return [d, d + str(digito_verificacion(d))]
    if len(d) == 10 and digito_verificacion(d[:9]) == int(d[9]):
        return [d[:9], d]
    return [d]


def misma_entidad(a, b) -> bool:
    """True si dos NIT son el mismo número con y sin dígito de verificación."""
    ea, eb = equivalentes(a), equivalentes(b)
    return bool(ea) and len(ea) == 2 and ea == eb and solo_digitos(a) != solo_digitos(b)
