"""colombia-datos-mcp — servidor MCP de datos públicos de Colombia.

Transporte dual (ADR-02): stdio por defecto, streamable HTTP con --http.
"""

from __future__ import annotations

import argparse
import json
import sys

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools.tool import ToolResult

from . import __version__
from .adapters import socrata
from .core.errors import CoDatosError
from .domain import analisis, catalogo, crimen, exportar, geo, secop
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
# Exportar es la única herramienta que escribe. No destruye —crea o sobrescribe
# un fichero bajo CO_EXPORT_DIR— pero no puede anunciarse como de solo lectura.
ESCRIBE = {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True}


async def _ejecuta(corrutina) -> ToolResult:
    """Ejecuta una herramienta y devuelve markdown + contenido estructurado.

    Los errores tipados se traducen a ToolError, de modo que el cliente recibe
    isError=True con el código estable y la sugerencia accionable en vez de una
    traza. Un fallo de la fuente nunca se confunde con cero filas.

    El sobre ya calculaba `estructurado` con las filas y sus metadatos, pero se
    descartaba: el cliente recibía solo la prosa. Ahora viaja por el canal
    estructurado del protocolo, así que las filas se pueden consumir como datos
    —tipadas, con `_meta` y la URL reproducible— sin volver a parsear la tabla.
    """
    try:
        resultado = await corrutina
    except CoDatosError as e:
        raise ToolError(e.como_texto()) from e
    return ToolResult(content=resultado["texto"],
                      structured_content=resultado["estructurado"])


# ------------------------------------------------------------- catálogo ----
@mcp.tool(annotations=SOLO_LECTURA)
async def co_datos_buscar_datasets(consulta: str = "", categoria: str = "",
                                   entidad: str = "", limite: int = 20,
                                   offset: int = 0) -> ToolResult:
    """Busca conjuntos de datos oficiales en el catálogo nacional datos.gov.co.

    `entidad` acepta una sigla conocida (DANE, CCE, MinDefensa, Fiscalía,
    MinTIC) y la traduce a la cadena de atribución exacta que exige Socrata.
    """
    return await _ejecuta(catalogo.buscar_datasets(
        consulta=consulta or None, categoria=categoria or None,
        entidad=entidad or None, limite=limite, offset=offset))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_datos_describir_dataset(dataset_id: str) -> ToolResult:
    """Devuelve el esquema en vivo de un dataset: campo técnico, nombre
    legible, tipo y descripción. Úsala ANTES de escribir cualquier filtro."""
    return await _ejecuta(catalogo.describir_dataset(dataset_id))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_datos_consultar(dataset_id: str, seleccionar: str = "", donde: str = "",
                             ordenar: str = "", limite: int = 20, offset: int = 0,
                             detalle: str = "resumen", formato: str = "tabla") -> ToolResult:
    """Consulta SoQL sobre cualquier dataset de datos.gov.co.

    `detalle`: "conteo" (solo el número, sin filas), "resumen" (campos
    curados) o "completo". Las columnas se validan contra el esquema vivo.

    `formato`: "tabla" para leer, "csv" o "json" para extraer. Las filas van
    además en el contenido estructurado de la respuesta.
    """
    return await _ejecuta(catalogo.consultar(
        dataset_id, seleccionar=seleccionar or None, donde=donde or None,
        ordenar=ordenar or None, limite=limite, offset=offset, detalle=detalle,
        formato=formato))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_datos_agregar(dataset_id: str, agrupar_por: str,
                           metricas: str = "count(*) as total", donde: str = "",
                           teniendo: str = "", limite: int = 20,
                           formato: str = "tabla", grafica: bool = True) -> ToolResult:
    """Agrega del lado del servidor: agrupa y devuelve grupos, no filas.

    `grafica` añade una columna de barras proporcionales a la métrica, para
    comparar los grupos de un vistazo. `formato`: "tabla", "csv" o "json".
    """
    return await _ejecuta(catalogo.agregar(
        dataset_id, agrupar_por, metricas=metricas, donde=donde or None,
        teniendo=teniendo or None, limite=limite, formato=formato, grafica=grafica))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_datos_serie(dataset_id: str, campo_fecha: str,
                         metrica: str = "count(*) as casos", periodo: str = "anio",
                         desde: str = "", hasta: str = "", donde: str = "",
                         formato: str = "tabla", grafica: bool = True) -> ToolResult:
    """Serie temporal sobre cualquier dataset: agrupa por año, mes o día.

    Evita escribir `date_extract_y(...)` a mano, y sobre todo **avisa cuando el
    último periodo está incompleto**: comparar un año que llega hasta julio con
    años cerrados produce caídas que no existen.

    Rechaza las columnas de fecha que en realidad son texto, como las del Plan
    Anual de Adquisiciones: ahí agrupar por periodo falla y `between` miente.
    """
    return await _ejecuta(analisis.serie(
        dataset_id, campo_fecha, metrica=metrica, periodo=periodo,
        desde=desde or None, hasta=hasta or None, donde=donde or None,
        formato=formato, grafica=grafica))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_datos_perfilar(dataset_id: str, campo: str, donde: str = "") -> ToolResult:
    """Retrato de una columna antes de fiarte de ella.

    Nulos, rango, reparto por orden de magnitud y **concentración**: si unos
    pocos valores dominan la suma, lo dice. Es la comprobación que hace visible
    en una llamada que nueve contratos aportan el 94 % del valor de SECOP II.

    Úsala antes de citar cualquier agregado de una columna que no conozcas.
    """
    return await _ejecuta(analisis.perfilar(dataset_id, campo, donde=donde or None))


# ---------------------------------------------------------------- SECOP ----
@mcp.tool(annotations=SOLO_LECTURA)
async def co_secop_buscar_contratos(entidad: str = "", nit_entidad: str = "",
                                    proveedor: str = "", documento_proveedor: str = "",
                                    departamento: str = "", modalidad: str = "",
                                    desde: str = "", hasta: str = "", valor_min: float = 0,
                                    valor_max: float = 0,
                                    detalle: str = "resumen", limite: int = 20,
                                    offset: int = 0, formato: str = "tabla") -> ToolResult:
    """Busca contratos en SECOP II. Fechas en formato YYYY-MM-DD.

    `valor_max` acota por arriba. Sirve para dejar fuera los ~3.450 contratos
    con valores imposibles por error de digitación, que arrastran cualquier suma.

    `formato`: "tabla" para leer, "csv" o "json" para extraer.
    """
    return await _ejecuta(secop.buscar_contratos(
        entidad=entidad or None, nit_entidad=nit_entidad or None,
        proveedor=proveedor or None, documento_proveedor=documento_proveedor or None,
        departamento=departamento or None, modalidad=modalidad or None,
        desde=desde or None, hasta=hasta or None, valor_min=valor_min or None,
        valor_max=valor_max or None,
        detalle=detalle, limite=limite, offset=offset, formato=formato))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_secop_buscar_procesos(entidad: str = "", nit_entidad: str = "",
                                   departamento: str = "", modalidad: str = "",
                                   desde: str = "", hasta: str = "",
                                   detalle: str = "resumen", limite: int = 20,
                                   offset: int = 0, formato: str = "tabla") -> ToolResult:
    """Busca procesos de contratación en SECOP II (adjudicados o no)."""
    return await _ejecuta(secop.buscar_procesos(
        entidad=entidad or None, nit_entidad=nit_entidad or None,
        departamento=departamento or None, modalidad=modalidad or None,
        desde=desde or None, hasta=hasta or None,
        detalle=detalle, limite=limite, offset=offset, formato=formato))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_secop_detalle_contrato(id_contrato: str) -> ToolResult:
    """Ficha completa de un contrato: datos, modificaciones y URL pública de
    verificación, en una sola llamada."""
    return await _ejecuta(secop.detalle_contrato(id_contrato))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_secop_perfil_proveedor(documento: str, limite: int = 20) -> ToolResult:
    """Perfil agregado de un contratista por cédula o NIT."""
    return await _ejecuta(secop.perfil_proveedor(documento, limite=limite))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_secop_resolver_entidad(nombre: str, limite: int = 10) -> ToolResult:
    """Traduce un nombre coloquial de entidad a su nombre canónico y NIT.
    Úsala antes de buscar por nombre: evita falsos negativos."""
    return await _ejecuta(secop.resolver_entidad(nombre, limite=limite))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_secop_agregar(agrupar_por: str = "departamento", metrica: str = "valor",
                           entidad: str = "", desde: str = "", hasta: str = "",
                           limite: int = 20, formato: str = "tabla",
                           grafica: bool = True) -> ToolResult:
    """Totales de contratación por departamento, entidad, modalidad, proveedor,
    sector, tipo o estado.

    `grafica` añade barras proporcionales a la métrica por la que se ordena.
    """
    return await _ejecuta(secop.agregar(
        agrupar_por=agrupar_por, metrica=metrica, donde_entidad=entidad or None,
        desde=desde or None, hasta=hasta or None, limite=limite,
        formato=formato, grafica=grafica))


# ----------------------------------------------------------------- geo ----
@mcp.tool(annotations=SOLO_LECTURA)
async def co_geo_divipola(consulta: str = "", codigo: str = "", nivel: str = "municipio",
                          con_coordenadas: bool = True, limite: int = 25,
                          offset: int = 0, formato: str = "tabla") -> ToolResult:
    """Resuelve nombre y código DIVIPOLA con coordenadas.

    `nivel`: "departamento", "municipio" o "centro_poblado".
    """
    return await _ejecuta(geo.divipola(
        consulta=consulta or None, codigo=codigo or None, nivel=nivel,
        con_coordenadas=con_coordenadas, limite=limite, offset=offset,
        formato=formato))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_geo_cotejar_coordenadas(limite: int = 15) -> ToolResult:
    """Coteja las dos fuentes oficiales de coordenadas municipales y reporta
    las discrepancias mayores a ~1 km. Es un control de calidad del dato."""
    return await _ejecuta(geo.cotejar_coordenadas(limite=limite))


@mcp.tool(annotations=ESCRIBE)
async def co_datos_exportar(dataset_id: str, nombre_archivo: str, donde: str = "",
                            seleccionar: str = "", ordenar: str = "",
                            formato: str = "csv", max_filas: int = 50000) -> ToolResult:
    """Descarga un dataset filtrado ENTERO y lo guarda en disco.

    Es la única herramienta que escribe. Pagina hasta agotar el filtro, así que
    sirve para sacar volúmenes que no caben en una respuesta.

    `nombre_archivo` es un nombre, NO una ruta: el fichero se escribe siempre
    bajo `CO_EXPORT_DIR` (por defecto `~/colombia-datos-export`).

    `formato`: "csv" (sin dependencias), "json" o "parquet" (requiere pyarrow).
    Si se alcanza `max_filas` antes que el total, la respuesta lo dice: el
    fichero queda incompleto y hay que saberlo.
    """
    return await _ejecuta(exportar.exportar(
        dataset_id, nombre_archivo, donde=donde or None,
        seleccionar=seleccionar or None, ordenar=ordenar or None,
        formato=formato, max_filas=max_filas))


# --------------------------------------------------------------- crimen ----
@mcp.tool(annotations=SOLO_LECTURA)
async def co_crimen_serie(delito: str, desde: int = 0, hasta: int = 0,
                          agrupar_por: str = "anio", formato: str = "tabla",
                          grafica: bool = True) -> ToolResult:
    """Serie temporal de un delito, por año o por mes, desde 2003.

    23 delitos de MinDefensa con esquema comparable: homicidio, extorsión,
    secuestro, hurto_personas, violencia_intrafamiliar, delitos_sexuales,
    terrorismo, lesiones, trata_personas, delitos_informaticos y más.

    Mira SIEMPRE la serie antes de citar un porcentaje: el año que elijas de
    base cambia el resultado, y a veces lo invierte.
    """
    return await _ejecuta(crimen.serie(
        delito, desde=desde or None, hasta=hasta or None,
        agrupar_por=agrupar_por, formato=formato, grafica=grafica))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_crimen_por_municipio(delito: str, anio: int, limite: int = 20,
                                  departamento: str = "", formato: str = "tabla",
                                  grafica: bool = True) -> ToolResult:
    """Municipios con más casos de un delito en un año.

    Devuelve `cod_mpio`, la clave DIVIPOLA, para cruzar con otras fuentes.
    Son conteos absolutos: sin población, la lista se parece a una de
    municipios grandes.
    """
    return await _ejecuta(crimen.por_municipio(
        delito, anio, limite=limite, departamento=departamento or None,
        formato=formato, grafica=grafica))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_crimen_comparar(anio_a: int, anio_b: int, delitos: str = "",
                             formato: str = "tabla") -> ToolResult:
    """Compara varios delitos entre dos años, ordenados por variación.

    `delitos` es una lista separada por comas; vacío compara todos. El sobre
    recuerda que la elección del año base no es neutral.
    """
    return await _ejecuta(crimen.comparar(anio_a, anio_b, delitos=delitos,
                                          formato=formato))


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
