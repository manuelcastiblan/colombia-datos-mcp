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

from ..core.cache import TTL_DATOS, TTL_METADATOS, cache
from ..core.errors import ErrorValidacion
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
    """Ejecuta SoQL. `$order` se fuerza si hay paginación (§6.3)."""
    if agrupar is None and offset and not ordenar:
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
    return {"filas": filas or [], "consulta": url_reproducible(url, params)}


async def contar(dataset_id: str, donde: str | None = None) -> int:
    """Contar sin traer filas. La diferencia entre 200 tokens y 10 MB."""
    r = await consultar(dataset_id, seleccionar="count(*) as total", donde=donde, limite=1)
    filas = r["filas"]
    return int(filas[0]["total"]) if filas and "total" in filas[0] else 0


async def cerrar() -> None:
    await _http.cerrar()
