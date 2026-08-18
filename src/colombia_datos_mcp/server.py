"""colombia-datos-mcp — servidor MCP de datos públicos de Colombia.

Transporte dual (ADR-02): stdio por defecto, streamable HTTP con --http.
"""

from __future__ import annotations

import argparse
import json
import sys

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from . import __version__
from .adapters import socrata
from .core.errors import CoDatosError
from .domain import catalogo, geo, secop
from .registry import datasets as reg

PLAYBOOK = """
Servidor de datos públicos de Colombia (datos.gov.co / SECOP / DIVIPOLA).

CÓMO TRABAJAR AQUÍ

1. Para CONTAR usa siempre detalle="conteo". Nunca traigas filas para contar:
   el conteo cuesta ~200 tokens y traer filas cuesta miles.
2. Para cifras agregadas usa las herramientas de agregación, NO sumes filas tú.
   El servidor agrega del lado del servidor y devuelve grupos, no registros.
3. Antes de filtrar por un campo, consulta el esquema con
   co_datos_describir_dataset. Los nombres técnicos están truncados y sin
   acentos: `valor_pendiente_de` es "Valor Pendiente de Amortizacion".
4. Si tienes el NIT o la cédula, úsalos. Son mucho más precisos que el nombre.
   Si solo tienes el nombre, pasa PRIMERO por co_secop_resolver_entidad.
5. Los nombres de entidad en SECOP no son los coloquiales: RTVC se escribe
   "RADIO TELEVISION NACIONAL DE COLOMBIA." (con punto final).
6. SECOP II es la plataforma vigente. Busca ahí antes que en SECOP I. Para
   análisis que crucen ambas, el dataset es rpmr-utcd (SECOP Integrado).
7. Las "modificaciones contractuales" se llaman ADICIONES (cb9c-h8sn).
   Buscar "modificaciones" en el catálogo devuelve cero resultados.
8. Los códigos DIVIPOLA son TEXTO de 5 dígitos con ceros a la izquierda
   ("05", "08"). Tratarlos como enteros rompe todos los joins.
9. Los montos son nominales y sin deflactar. No compares valores entre años
   distintos sin advertirlo.
10. Escribe los nombres como quieras, con tilde o sin ella: el servidor los
   resuelve contra los valores reales de la fuente. Si un término no existe
   allí, te lo dice explícitamente en vez de devolver una tabla vacía.

CÓMO LEER LAS RESPUESTAS

Cada respuesta trae un pie con el número de filas devueltas, el total de
coincidencias, el orden aplicado y la URL exacta reproducible. Si devueltos <
total, NO concluyas nada cuantitativo a partir de esas filas: usa agregación.
Cuando una respuesta venga marcada como truncada, refina el filtro en vez de
paginar a ciegas.

Un error con código FUENTE_CAIDA significa que el backend falló. Es distinto de
una respuesta con cero filas, que significa que la consulta no encontró nada.
No los confundas al explicarle el resultado al usuario.
""".strip()

mcp = FastMCP(name="colombia-datos", instructions=PLAYBOOK, version=__version__)

SOLO_LECTURA = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": True}


async def _ejecuta(corrutina) -> str:
    """Ejecuta una herramienta y traduce los errores tipados a ToolError.

    Así el cliente MCP recibe isError=True con el código estable y la
    sugerencia accionable, en vez de una traza. Un fallo de la fuente nunca se
    confunde con una respuesta de cero filas.
    """
    try:
        resultado = await corrutina
    except CoDatosError as e:
        raise ToolError(e.como_texto()) from e
    return resultado["texto"]


# ------------------------------------------------------------- catálogo ----
@mcp.tool(annotations=SOLO_LECTURA)
async def co_datos_buscar_datasets(consulta: str = "", categoria: str = "",
                                   entidad: str = "", limite: int = 20,
                                   offset: int = 0) -> str:
    """Busca conjuntos de datos oficiales en el catálogo nacional datos.gov.co.

    `entidad` acepta una sigla conocida (DANE, CCE, MinDefensa, Fiscalía,
    MinTIC) y la traduce a la cadena de atribución exacta que exige Socrata.
    """
    return await _ejecuta(catalogo.buscar_datasets(
        consulta=consulta or None, categoria=categoria or None,
        entidad=entidad or None, limite=limite, offset=offset))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_datos_describir_dataset(dataset_id: str) -> str:
    """Devuelve el esquema en vivo de un dataset: campo técnico, nombre
    legible, tipo y descripción. Úsala ANTES de escribir cualquier filtro."""
    return await _ejecuta(catalogo.describir_dataset(dataset_id))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_datos_consultar(dataset_id: str, seleccionar: str = "", donde: str = "",
                             ordenar: str = "", limite: int = 20, offset: int = 0,
                             detalle: str = "resumen") -> str:
    """Consulta SoQL sobre cualquier dataset de datos.gov.co.

    `detalle`: "conteo" (solo el número, sin filas), "resumen" (campos
    curados) o "completo". Las columnas se validan contra el esquema vivo.
    """
    return await _ejecuta(catalogo.consultar(
        dataset_id, seleccionar=seleccionar or None, donde=donde or None,
        ordenar=ordenar or None, limite=limite, offset=offset, detalle=detalle))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_datos_agregar(dataset_id: str, agrupar_por: str,
                           metricas: str = "count(*) as total", donde: str = "",
                           teniendo: str = "", limite: int = 20) -> str:
    """Agrega del lado del servidor: agrupa y devuelve grupos, no filas."""
    return await _ejecuta(catalogo.agregar(
        dataset_id, agrupar_por, metricas=metricas, donde=donde or None,
        teniendo=teniendo or None, limite=limite))


# ---------------------------------------------------------------- SECOP ----
@mcp.tool(annotations=SOLO_LECTURA)
async def co_secop_buscar_contratos(entidad: str = "", nit_entidad: str = "",
                                    proveedor: str = "", documento_proveedor: str = "",
                                    departamento: str = "", modalidad: str = "",
                                    desde: str = "", hasta: str = "", valor_min: float = 0,
                                    detalle: str = "resumen", limite: int = 20,
                                    offset: int = 0) -> str:
    """Busca contratos en SECOP II. Fechas en formato YYYY-MM-DD."""
    return await _ejecuta(secop.buscar_contratos(
        entidad=entidad or None, nit_entidad=nit_entidad or None,
        proveedor=proveedor or None, documento_proveedor=documento_proveedor or None,
        departamento=departamento or None, modalidad=modalidad or None,
        desde=desde or None, hasta=hasta or None, valor_min=valor_min or None,
        detalle=detalle, limite=limite, offset=offset))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_secop_buscar_procesos(entidad: str = "", nit_entidad: str = "",
                                   departamento: str = "", modalidad: str = "",
                                   desde: str = "", hasta: str = "",
                                   detalle: str = "resumen", limite: int = 20,
                                   offset: int = 0) -> str:
    """Busca procesos de contratación en SECOP II (adjudicados o no)."""
    return await _ejecuta(secop.buscar_procesos(
        entidad=entidad or None, nit_entidad=nit_entidad or None,
        departamento=departamento or None, modalidad=modalidad or None,
        desde=desde or None, hasta=hasta or None,
        detalle=detalle, limite=limite, offset=offset))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_secop_detalle_contrato(id_contrato: str) -> str:
    """Ficha completa de un contrato: datos, modificaciones y URL pública de
    verificación, en una sola llamada."""
    return await _ejecuta(secop.detalle_contrato(id_contrato))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_secop_perfil_proveedor(documento: str, limite: int = 20) -> str:
    """Perfil agregado de un contratista por cédula o NIT."""
    return await _ejecuta(secop.perfil_proveedor(documento, limite=limite))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_secop_resolver_entidad(nombre: str, limite: int = 10) -> str:
    """Traduce un nombre coloquial de entidad a su nombre canónico y NIT.
    Úsala antes de buscar por nombre: evita falsos negativos."""
    return await _ejecuta(secop.resolver_entidad(nombre, limite=limite))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_secop_agregar(agrupar_por: str = "departamento", metrica: str = "valor",
                           entidad: str = "", desde: str = "", hasta: str = "",
                           limite: int = 20) -> str:
    """Totales de contratación por departamento, entidad, modalidad, proveedor,
    sector, tipo o estado."""
    return await _ejecuta(secop.agregar(
        agrupar_por=agrupar_por, metrica=metrica, donde_entidad=entidad or None,
        desde=desde or None, hasta=hasta or None, limite=limite))


# ----------------------------------------------------------------- geo ----
@mcp.tool(annotations=SOLO_LECTURA)
async def co_geo_divipola(consulta: str = "", codigo: str = "", nivel: str = "municipio",
                          con_coordenadas: bool = True, limite: int = 25,
                          offset: int = 0) -> str:
    """Resuelve nombre y código DIVIPOLA con coordenadas.

    `nivel`: "departamento", "municipio" o "centro_poblado".
    """
    return await _ejecuta(geo.divipola(
        consulta=consulta or None, codigo=codigo or None, nivel=nivel,
        con_coordenadas=con_coordenadas, limite=limite, offset=offset))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_geo_cotejar_coordenadas(limite: int = 15) -> str:
    """Coteja las dos fuentes oficiales de coordenadas municipales y reporta
    las discrepancias mayores a ~1 km. Es un control de calidad del dato."""
    return await _ejecuta(geo.cotejar_coordenadas(limite=limite))


# ----------------------------------------------------------- resources ----
@mcp.resource("co://secop/datasets")
def recurso_datasets() -> str:
    """Catálogo curado de SECOP: IDs, unidad de análisis y trampas conocidas."""
    return json.dumps(
        {k: {"id": d.id, "nombre": d.nombre, "unidad": d.unidad,
             "campos_resumen": list(d.campos_resumen), "notas": list(d.notas)}
         for k, d in reg.SECOP.items()},
        ensure_ascii=False, indent=2)


@mcp.resource("co://secop/joins")
def recurso_joins() -> str:
    """Joins verificados entre datasets de SECOP."""
    return json.dumps([{"desde": a, "hacia": b} for a, b in reg.JOINS],
                      ensure_ascii=False, indent=2)


@mcp.resource("co://atribuciones")
def recurso_atribuciones() -> str:
    """Cadenas de atribución exactas. El facet de Socrata solo acepta el
    literal completo: `attribution=DANE` devuelve cero."""
    return json.dumps(reg.ATRIBUCIONES, ensure_ascii=False, indent=2)


# ----------------------------------------------------------------- CLI ----
def main() -> None:
    p = argparse.ArgumentParser(prog="colombia-datos-mcp")
    p.add_argument("--http", action="store_true", help="streamable HTTP en vez de stdio")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    args = p.parse_args()

    if args.http:
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        # stdio: jamás escribir en stdout fuera del protocolo.
        print("colombia-datos-mcp listo (stdio)", file=sys.stderr)
        mcp.run()


if __name__ == "__main__":
    main()
