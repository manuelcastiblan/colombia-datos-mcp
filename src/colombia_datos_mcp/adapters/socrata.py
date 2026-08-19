"""Adaptador de Socrata: Discovery API + SODA sobre datos.gov.co.

Hechos verificados que este cliente absorbe:

* `search_context` es obligatorio o `categories`/`tags` devuelven 0 en silencio.
* Por defecto `only=dataset` + `provenance=official`: `q=SECOP` sin filtrar
  devuelve 944 assets, la mayoría vistas comunitarias obsoletas.
* `$order` es obligatorio al paginar o el orden entre páginas no es estable.
* Los valores numéricos llegan como string; se castean con `dataTypeName`.
* Un token inválido produce 403, no degradación silenciosa.
"""

from __future__ import annotations

import os
import urllib.parse

from ..core import texto
from ..core.cache import TTL_DATOS, TTL_METADATOS, cache
from ..core.errors import ErrorEsquemaCambiado, ErrorNoEncontrado, ErrorValidacion
from ..core.http import ClienteHTTP

DOMINIO = "www.datos.gov.co"
BASE_DATOS = f"https://{DOMINIO}"
BASE_CATALOGO = "https://api.us.socrata.com/api/catalog/v1"

_http = ClienteHTTP(perfil="socrata")


def _cabeceras() -> dict:
    """El token va por header, nunca por query param: no se filtra en logs."""
    token = os.environ.get("SOCRATA_APP_TOKEN")
    return {"X-App-Token": token} if token else {}


def sin_token() -> bool:
    return not os.environ.get("SOCRATA_APP_TOKEN")


def url_reproducible(base: str, params: dict) -> str:
    """La URL exacta que va en el sobre. Sin el token, obviamente."""
    limpios = {k: v for k, v in params.items() if v not in (None, "")}
    return f"{base}?{urllib.parse.urlencode(limpios)}"


# --------------------------------------------------------------- catálogo --
async def buscar_datasets(
    consulta: str | None = None,
    categoria: str | None = None,
    atribucion: str | None = None,
    ids: list[str] | None = None,
    limite: int = 20,
    offset: int = 0,
    solo_oficiales: bool = True,
) -> dict:
    params = {
        "domains": DOMINIO,
        "search_context": DOMINIO,   # sin esto, categories/tags devuelven 0
        "only": "dataset",
        "limit": min(limite, 100),
        "offset": offset,
    }
    if solo_oficiales:
        params["provenance"] = "official"
    if consulta:
        params["q"] = consulta
    if categoria:
        params["categories"] = categoria
    if atribucion:
        params["attribution"] = atribucion
    if ids:
        params["ids"] = ",".join(ids)

    datos = await cache.obtener_o_calcular(
        ("catalogo", sorted(params.items())),
        lambda: _http.get_json(BASE_CATALOGO, params=params, headers=_cabeceras()),
        ttl=TTL_METADATOS,
        en_disco=True,
    )
    return {"datos": datos, "consulta": url_reproducible(BASE_CATALOGO, params)}


async def esquema(dataset_id: str) -> dict:
    """Esquema en vivo con caché de 24 h. Nunca se cablea (§7).

    Devuelve columnas con fieldName, nombre legible, tipo y descripción: sin el
    nombre legible el modelo no adivina slugs truncados como
    `valor_pendiente_de` = "Valor Pendiente de Amortizacion".
    """

    async def _traer():
        params = {"domains": DOMINIO, "search_context": DOMINIO, "ids": dataset_id}
        cat = await _http.get_json(BASE_CATALOGO, params=params, headers=_cabeceras())
        resultados = cat.get("results") or []
        if not resultados:
            return None
        r = resultados[0]["resource"]
        campos = r.get("columns_field_name") or []
        nombres = r.get("columns_name") or []
        tipos = r.get("columns_datatype") or []
        descripciones = r.get("columns_description") or []
        clasif = resultados[0].get("classification", {}) or {}
        return {
            "id": r.get("id"),
            "nombre": r.get("name"),
            "descripcion": r.get("description"),
            "atribucion": r.get("attribution"),
            "actualizado": r.get("updatedAt"),
            "provenance": r.get("provenance"),
            "es_vista_derivada": bool(r.get("parent_fxf")),
            "licencia": (resultados[0].get("metadata") or {}).get("license"),
            "categoria": clasif.get("domain_category"),
            "columnas": [
                {
                    "campo": campos[i] if i < len(campos) else None,
                    "nombre": nombres[i] if i < len(nombres) else None,
                    "tipo": tipos[i] if i < len(tipos) else None,
                    "descripcion": descripciones[i] if i < len(descripciones) else None,
                }
                for i in range(len(campos))
            ],
        }

    return await cache.obtener_o_calcular(
        ("esquema", dataset_id), _traer, ttl=TTL_METADATOS, en_disco=True
    )


async def campos_validos(dataset_id: str) -> set[str]:
    esq = await esquema(dataset_id)
    if not esq:
        return set()
    return {c["campo"] for c in esq["columnas"] if c["campo"]}


async def valida_campos(dataset_id: str, usados) -> None:
    """Allow-list de columnas derivada del esquema vivo, no solo escape de
    comillas. Un identificador desconocido se rechaza listando los válidos."""
    usados = {c for c in usados if c}
    if not usados:
        return
    validos = await campos_validos(dataset_id)
    if not validos:
        return  # sin esquema no bloqueamos; el 400 de Socrata dará el detalle
    desconocidos = sorted(usados - validos)
    if desconocidos:
        raise ErrorValidacion(
            f"Columnas inexistentes en {dataset_id}: {', '.join(desconocidos)}",
            "Campos válidos: " + ", ".join(sorted(validos)),
            dataset=dataset_id,
        )


# ------------------------------------------------------------------ datos --
def escapa(valor: str) -> str:
    return str(valor).replace("'", "''")


async def valores_distintos(dataset_id: str, campo: str, limite: int = 5000) -> list[str]:
    """Valores canónicos de una columna categórica, cacheados como metadatos.

    Es la pieza que permite filtrar por nombre sin perder los acentos: el
    término del usuario se resuelve contra estos literales y el filtro sale con
    `in (...)`. Cuesta una consulta agrupada —medida en 6,8 s sobre las 5,9 M
    filas de contratos— que se cachea 24 h en disco, así que se paga una vez.
    """

    async def _traer():
        filas = await _http.get_json(
            f"{BASE_DATOS}/resource/{dataset_id}.json",
            params={"$select": f"distinct {campo}", "$limit": limite},
            headers=_cabeceras(),
        )
        return [f.get(campo) for f in (filas or []) if f.get(campo) not in (None, "")]

    return await cache.obtener_o_calcular(
        ("distintos", dataset_id, campo), _traer, ttl=TTL_METADATOS, en_disco=True
    )


def filtro_en(campo: str, valores) -> str:
    """`campo in ('Atlántico')` con los literales exactos de la fuente."""
    return f"{campo} in ({', '.join(chr(39) + escapa(v) + chr(39) for v in valores)})"


# Se compara siempre en mayúsculas, así que basta con las formas mayúsculas.
_TILDES = (("Á", "A"), ("É", "E"), ("Í", "I"), ("Ó", "O"), ("Ú", "U"),
           ("Ü", "U"), ("Ñ", "N"))


def expr_sin_acentos(campo: str) -> str:
    """Expresión SoQL que pliega los acentos de `campo` EN EL SERVIDOR.

    SoQL sí soporta `replace()` —anidarlo siete veces cuesta unos 20 s sobre
    las 5,9 M filas de contratos— y es la única forma exacta de comparar contra
    una columna acentuada cuyo dominio no se puede enumerar.
    """
    expr = f"upper({campo})"
    for acentuada, base in _TILDES:
        expr = f"replace({expr}, '{acentuada}', '{base}')"
    return expr


def filtro_texto_libre(campo: str, termino: str) -> str:
    """Filtro para campos de dominio abierto (nombre de entidad o proveedor).

    Para dominios cerrados usa `filtro_categorico`: resolver contra los
    valores canónicos compara por igualdad y es 4-8 veces más rápido.
    """
    t = escapa(texto.sanea_like(termino))
    if not t:
        return ""
    return f"{expr_sin_acentos(campo)} like '%{t}%'"


async def filtro_categorico(dataset_id: str, campo: str, termino: str):
    """Resuelve un término contra el dominio enumerable de `campo`.

    Devuelve `(filtro_soql, valores_resueltos, truncado)`. Con cero
    coincidencias devuelve `(None, [], False)`: el llamador debe decir que el
    término no existe en la fuente en vez de lanzar un filtro que casa nada,
    que es indistinguible de "no hay datos".
    """
    try:
        dominio = await valores_distintos(dataset_id, campo)
    except ErrorValidacion:
        # El campo no admite `distinct` (o no existe): degradamos a texto libre
        # en vez de tumbar la consulta entera.
        return filtro_texto_libre(campo, termino), [], False
    casan = texto.coincidencias(termino, dominio)
    if not casan:
        return None, [], False
    truncado = len(casan) > texto.MAX_VALORES_EN
    if truncado:
        casan = casan[: texto.MAX_VALORES_EN]
    return filtro_en(campo, casan), casan, truncado


# Funciones que colapsan filas. Sobre ellas no se puede ordenar por `:id`
# —Socrata responde "Column ':id' is not in group by"— y además no hay nada
# que paginar, así que forzar el orden estable ahí no tendría sentido.
_AGREGADOS = ("count(", "sum(", "avg(", "min(", "max(", "median(",
              "stddev_pop(", "stddev_samp(", "var_pop(", "var_samp(", "distinct")


def es_agregada(seleccionar: str | None) -> bool:
    if not seleccionar:
        return False
    compacto = str(seleccionar).lower().replace(" ", "")
    return any(f in compacto for f in _AGREGADOS)


async def consultar(
    dataset_id: str,
    seleccionar: str | None = None,
    donde: str | None = None,
    agrupar: str | None = None,
    teniendo: str | None = None,
    ordenar: str | None = None,
    limite: int = 20,
    offset: int = 0,
    ttl: int = TTL_DATOS,
) -> dict:
    """Ejecuta SoQL. `$order` se fuerza siempre que la consulta sea paginable.

    Antes solo se forzaba cuando `offset` era distinto de cero, y eso rompía
    justo lo que pretendía arreglar: la página 1 salía con el orden natural de
    la fuente y la página 2 con `:id`, dos órdenes distintos, de modo que al
    paginar se perdían y duplicaban filas igual. Si la primera página no tiene
    orden estable, la segunda no puede tenerlo.
    """
    if agrupar is None and not ordenar and not es_agregada(seleccionar):
        ordenar = ":id"  # sin orden estable se pierden o duplican filas
    params = {
        "$select": seleccionar,
        "$where": donde,
        "$group": agrupar,
        "$having": teniendo,
        "$order": ordenar,
        "$limit": limite,
        "$offset": offset or None,
    }
    params = {k: v for k, v in params.items() if v not in (None, "")}
    url = f"{BASE_DATOS}/resource/{dataset_id}.json"

    filas = await cache.obtener_o_calcular(
        ("soda", dataset_id, sorted(params.items())),
        lambda: _http.get_json(url, params=params, headers=_cabeceras()),
        ttl=ttl,
    )
    return {"filas": filas or [], "consulta": url_reproducible(url, params),
            "orden": ordenar}


async def contar(dataset_id: str, donde: str | None = None) -> int:
    """Contar sin traer filas. La diferencia entre 200 tokens y 10 MB."""
    r = await consultar(dataset_id, seleccionar="count(*) as total", donde=donde, limite=1)
    filas = r["filas"]
    return int(filas[0]["total"]) if filas and "total" in filas[0] else 0


# ------------------------------------------------------- consulta anidada --
def arma_soql(
    seleccionar: str,
    donde: str | None = None,
    agrupar: str | None = None,
    teniendo: str | None = None,
    ordenar: str | None = None,
    limite: int | None = None,
    offset: int = 0,
    luego: str | None = None,
) -> str:
    """Compone SoQL como texto, que es lo único que admite el operador `|>`.

    Los parámetros sueltos (`$select`, `$group`, `$having`) describen UNA
    consulta; encadenar etapas exige `$query`.
    """
    partes = [f"SELECT {seleccionar}"]
    if donde:
        partes.append(f"WHERE {donde}")
    if agrupar:
        partes.append(f"GROUP BY {agrupar}")
    if teniendo:
        partes.append(f"HAVING {teniendo}")
    if luego:
        # La etapa siguiente ve como tabla el resultado de la anterior: sus
        # columnas son los ALIAS de la etapa previa, no los campos del dataset.
        partes.append(f"|> SELECT {luego}")
    if ordenar:
        partes.append(f"ORDER BY {ordenar}")
    if limite is not None:
        partes.append(f"LIMIT {limite}")
    if offset:
        partes.append(f"OFFSET {offset}")
    return " ".join(partes)


async def consultar_soql(dataset_id: str, consulta: str, ttl: int = TTL_DATOS) -> dict:
    """Ejecuta SoQL completo por `$query`. Vía única para subconsultas anidadas."""
    params = {"$query": consulta}
    url = f"{BASE_DATOS}/resource/{dataset_id}.json"
    filas = await cache.obtener_o_calcular(
        ("soql", dataset_id, consulta),
        lambda: _http.get_json(url, params=params, headers=_cabeceras()),
        ttl=ttl,
    )
    return {"filas": filas or [], "consulta": url_reproducible(url, params)}


async def contar_grupos(
    dataset_id: str,
    seleccionar: str,
    agrupar: str,
    donde: str | None = None,
    teniendo: str | None = None,
) -> int | None:
    """Cuenta GRUPOS, no filas.

    `count(*)` sobre una consulta agrupada devuelve el tamaño de cada grupo, no
    cuántos grupos hay: para saberlo hay que agregar sobre el resultado, y eso
    solo se puede anidando.

    Devuelve None si la fuente no admite el operador. Un total desconocido se
    puede declarar; uno inventado contamina todo lo que toque.
    """
    consulta = arma_soql(seleccionar, donde=donde, agrupar=agrupar,
                         teniendo=teniendo, luego="count(*) AS grupos")
    try:
        filas = (await consultar_soql(dataset_id, consulta))["filas"]
    except (ErrorValidacion, ErrorNoEncontrado, ErrorEsquemaCambiado):
        return None
    if not filas or "grupos" not in filas[0]:
        return None
    try:
        return int(filas[0]["grupos"])
    except (TypeError, ValueError):
        return None


async def cerrar() -> None:
    await _http.cerrar()
