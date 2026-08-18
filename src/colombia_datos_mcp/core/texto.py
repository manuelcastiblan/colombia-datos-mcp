"""Comparación de texto contra datos oficiales que SÍ conservan los acentos.

El servidor asumía que «los acentos vienen destruidos en origen». Medido
contra la API viva, eso es cierto solo en los campos de TEXTO LIBRE de SECOP
—`descripcion` trae literalmente `EJECUCIoN`— y falso en las columnas
categóricas: `departamento` es "Atlántico", `nom_mpio` es "MEDELLÍN". Comparar
el término plegado contra ellas devolvía cero en silencio: 392 de 1.122
municipios, 12 de 33 departamentos y ~2,8 M de contratos eran inalcanzables
por nombre.

SoQL no tiene `unaccent()` ni `replace()` (el parser los rechaza) y `like`
distingue acentos, así que la estrategia se elige por la cardinalidad del
campo:

* **Dominio enumerable** (departamentos, modalidades, municipios): se traen
  los valores canónicos una vez, se pliegan aquí y se filtra con `in (...)`
  sobre los literales exactos. Recall 100 % y compara por igualdad, no por
  `like`.
* **Texto libre** (nombre de entidad o proveedor): no se puede enumerar, así
  que el plegado se hace EN EL SERVIDOR con `replace()` anidado sobre la
  columna. Es exacto y de coste constante en la longitud del término.

Medido sobre `nombre_entidad` con el término "gobernacion": el `like` plegado
original devolvía 206.958 filas —se dejaba fuera 186.495, las escritas
"GOBERNACIÓN"— y el plegado en servidor devuelve las 393.453 en ~20 s.
"""

from __future__ import annotations

import unicodedata

# Tope de literales en un `in (...)`: por encima, la consulta se vuelve enorme
# y el término es tan genérico que conviene que el usuario lo afine.
MAX_VALORES_EN = 200


def plegar(valor) -> str:
    """Quita acentos y pasa a mayúsculas, para comparar en Python.

    Único punto donde se pliegan acentos para comparar. Antes había un gemelo
    en `format` cuyo nombre invitaba a construir `like` con él contra una
    fuente que sí los conserva, que es de donde salió el defecto.
    """
    if valor is None:
        return ""
    s = unicodedata.normalize("NFKD", str(valor))
    return "".join(c for c in s if not unicodedata.combining(c)).upper().strip()


def coincidencias(termino: str, valores) -> list[str]:
    """Valores canónicos cuyo texto plegado contiene el término plegado.

    Devuelve los literales EXACTOS de la fuente (con sus acentos), que es lo
    que hay que meter en el `in (...)`.
    """
    t = plegar(termino)
    if not t:
        return []
    vistos, salida = set(), []
    for v in valores:
        if v is None:
            continue
        if t in plegar(v) and v not in vistos:
            vistos.add(v)
            salida.append(v)
    return salida


def sanea_like(termino: str) -> str:
    """Pliega el término y quita los comodines que escriba el usuario.

    Un `%` o un `_` sueltos pasarían por comodines de SoQL y ensancharían la
    búsqueda sin que nadie lo haya pedido.
    """
    return plegar(termino).replace("%", "").replace("_", "")
