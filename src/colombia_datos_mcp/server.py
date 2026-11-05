"""colombia-datos-mcp — servidor MCP de datos públicos de Colombia.

Transporte dual (ADR-02): stdio por defecto, streamable HTTP con --http.
"""

from __future__ import annotations

import argparse
import json
import sys

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

try:                                     # fastmcp >= 4 lo reexporta en el paquete
    from fastmcp.tools import ToolResult
except ImportError:                      # fastmcp 2.x y 3.x
    from fastmcp.tools.tool import ToolResult

from . import __version__
from .adapters import socrata
from .core.errors import CoDatosError
from .core import privacidad
from .domain import (analisis, catalogo, crimen, dossier, educacion, empresas,
                     exportar, geo, integridad, macro, secop, territorio)
from .registry import datasets as reg

PLAYBOOK = """
Servidor de datos públicos de Colombia: catálogo nacional, contratación,
criminalidad, territorio, registro mercantil, sanciones, educación y macro.

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
11. Para una empresa, empieza por co_dossier_documento: cruza RUES, SECOP,
   Supersociedades y cuatro fuentes de sanciones en una llamada, y enumera lo
   que miró. Después baja al detalle con la herramienta de la fuente concreta.
12. En el RUES una fila es una MATRÍCULA, no una empresa: 5.091.481 de las
   9.436.330 están canceladas. Y el número puede estar en `nit` o solo en
   `numero_identificacion`; las herramientas del servidor miran las dos.

DATOS DE PERSONAS

Tres fuentes traen personas identificadas: RUES (6.962.889 personas naturales),
SIRI de la Procuraduría (42.124 sanciones con nombre y cédula) y Saber 11 (7,1 M
de registros individuales).

- Agregar NUNCA pide permiso. co_integridad_panorama y co_educacion_saber11
  responden sobre poblaciones y no identifican a nadie.
- Identificar a una persona natural EXIGE declarar `finalidad`:
  investigacion, periodismo, control_fiscal o debida_diligencia. NO te la
  inventes ni elijas una por descarte: pregúntasela a quien te lo pidió, con
  sus palabras. Si no te la da, usa la herramienta agregada.
- Un error [PRIVACIDAD] no es un fallo ni una negativa definitiva: es la
  petición de un dato que falta. Explícalo así y nombra la alternativa que el
  propio error te sugiere.
- Los números de documento salen enmascarados. Es decisión del operador, no un
  parámetro: no hay forma de pedir que no lo estén.

LO QUE ESTE SERVIDOR NO PUEDE HACER

Dilo cuando te lo pidan, en vez de buscar un sustituto que no lo es:

- NO hay población municipal total, así que NO hay tasas por 100.000
  habitantes. El DANE no publica las proyecciones por API. Lo único parecido es
  la población de 5 a 16 años del MinEducación, que no sirve de denominador.
- NO hay IPC, así que los montos siguen sin deflactar. Lo que sí hay es la TRM
  (co_macro_convertir), que da una segunda unidad, no un deflactor.
- NO hay procesos judiciales, Registraduría, RUNT, SIMIT ni Boletín de
  Deudores Morosos: solo se consultan por formulario web con captcha.
- Las fuentes de sanciones son INCOMPLETAS y un cero en ellas no es un
  certificado de antecedentes limpio. Dilo siempre que devuelvas un cero.

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
                           teniendo: str = "", luego: str = "", ordenar: str = "",
                           limite: int = 20, offset: int = 0,
                           formato: str = "tabla", grafica: bool = True) -> ToolResult:
    """Agrega del lado del servidor: agrupa y devuelve grupos, no filas.

    `agrupar_por` acepta columnas y también expresiones, con alias opcional:
    `date_trunc_ym(fecha_de_firma) as mes`, `upper(nombre_entidad)`.

    `ordenar` manda sobre el orden por defecto, que es la métrica descendente.
    Puede citar un alias: `ordenar="mes"` devuelve una serie cronológica en vez
    de ordenada por el conteo.

    `offset` pagina los grupos. Para llevarse la tabla ENTERA a disco en vez de
    paginarla, `co_datos_exportar` acepta los mismos `agrupar_por` y `metricas`.

    `teniendo` filtra grupos por su métrica (`count(*) > 1`).

    `luego` encadena una SEGUNDA agregación sobre el resultado de la primera.
    Sus columnas son los alias de la primera etapa, no los campos del dataset.
    Sirve para preguntas sobre los grupos mismos:

        agrupar_por="documento_proveedor", metricas="count(*) as n",
        teniendo="count(*) > 1", luego="count(*) as personas, sum(n) as contratos"

    devuelve cuántas PERSONAS repiten, no cuántos contratos tiene cada una.
    Sin `luego` esa pregunta no tiene respuesta: `count(*)` con `having` cuenta
    dentro de cada grupo, nunca los grupos.

    `grafica` añade una columna de barras proporcionales a la métrica, para
    comparar los grupos de un vistazo. `formato`: "tabla", "csv" o "json".
    """
    return await _ejecuta(catalogo.agregar(
        dataset_id, agrupar_por, metricas=metricas, donde=donde or None,
        teniendo=teniendo or None, luego=luego or None, ordenar=ordenar or None,
        limite=limite, offset=offset, formato=formato, grafica=grafica))


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
                           nit_entidad: str = "", tipo: str = "",
                           limite: int = 20, formato: str = "tabla",
                           grafica: bool = True) -> ToolResult:
    """Totales de contratación por departamento, entidad, modalidad, proveedor,
    sector, tipo o estado.

    `nit_entidad` filtra por entidad con precisión —busca el NIT con y sin
    dígito de verificación— y `tipo` por tipo de contrato («prestación de
    servicios»), resuelto contra los valores reales de la fuente.

    `grafica` añade barras proporcionales a la métrica por la que se ordena.
    """
    return await _ejecuta(secop.agregar(
        agrupar_por=agrupar_por, metrica=metrica, donde_entidad=entidad or None,
        desde=desde or None, hasta=hasta or None, nit_entidad=nit_entidad or None,
        tipo=tipo or None, limite=limite, formato=formato, grafica=grafica))


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
                            formato: str = "csv", max_filas: int = 50000,
                            agrupar_por: str = "", metricas: str = "",
                            teniendo: str = "") -> ToolResult:
    """Descarga un dataset filtrado ENTERO y lo guarda en disco.

    Es la única herramienta que escribe. Pagina hasta agotar el filtro, así que
    sirve para sacar volúmenes que no caben en una respuesta.

    Con `agrupar_por` (y `metricas`, `teniendo`) exporta la TABLA DE GRUPOS
    completa en vez de las filas: es la vía para una agregación con más grupos
    de los que caben en una respuesta —pedirla en CSV no evita el presupuesto de
    tokens—, por ejemplo los 2.000 organismos que contrataron en un periodo.

    `nombre_archivo` es un nombre, NO una ruta: el fichero se escribe siempre
    bajo `CO_EXPORT_DIR` (por defecto `~/colombia-datos-export`).

    `formato`: "csv" (sin dependencias), "json" o "parquet" (requiere pyarrow).
    Si se alcanza `max_filas` antes que el total, la respuesta lo dice: el
    fichero queda incompleto y hay que saberlo.
    """
    return await _ejecuta(exportar.exportar(
        dataset_id, nombre_archivo, donde=donde or None,
        seleccionar=seleccionar or None, ordenar=ordenar or None,
        formato=formato, max_filas=max_filas, agrupar_por=agrupar_por or None,
        metricas=metricas or None, teniendo=teniendo or None))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_geo_limites(nivel: str = "municipio", codigo: str = "",
                         departamento: str = "", guardar: str = "") -> ToolResult:
    """Límites municipales o departamentales como GeoJSON, para dibujar mapas.

    La geometría va en el contenido estructurado, no en el texto. Filtra con
    `codigo` (DIVIPOLA de 2 o 5 dígitos) o `departamento`; por encima de 200
    geometrías hay que acotar o usar `guardar`, que las escribe en disco.

    Procede del Marco Geoestadístico Nacional 2018 del DANE por réplica pública:
    el servicio oficial del IGAC devuelve error 500. La respuesta lo declara.
    """
    return await _ejecuta(geo.limites(
        nivel=nivel, codigo=codigo or None, departamento=departamento or None,
        guardar=guardar or None))


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


# ------------------------------------------------------------- empresas ----
@mcp.tool(annotations=SOLO_LECTURA)
async def co_empresas_buscar(nombre: str = "", documento: str = "",
                             estado: str = "", camara: str = "",
                             solo_juridicas: bool = True, limite: int = 20,
                             offset: int = 0, detalle: str = "resumen",
                             formato: str = "tabla",
                             finalidad: str = "") -> ToolResult:
    """Busca en el RUES por razón social o por documento (9,4 M de matrículas).

    Una fila es una MATRÍCULA, no una empresa: 5.091.481 están canceladas, así
    que filtra `estado="ACTIVA"` si lo que quieres son empresas vivas.

    `solo_juridicas=True` (el valor por defecto) restringe a sociedades y ESAL
    y no identifica a ninguna persona natural. Bajarlo abre los 6.962.889
    comerciantes matriculados a título personal y exige `finalidad`.

    Busca el documento en `nit` y en `numero_identificacion`: en 485.630
    sociedades la primera está vacía.
    """
    return await _ejecuta(empresas.buscar(
        nombre=nombre or None, documento=documento or None, estado=estado or None,
        camara=camara or None, solo_juridicas=solo_juridicas, limite=limite,
        offset=offset, detalle=detalle, formato=formato,
        finalidad=finalidad or None))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_empresas_ficha(documento: str, finalidad: str = "") -> ToolResult:
    """Ficha del registro mercantil de un documento: matrícula, forma jurídica,
    estado, cámara, establecimientos a su nombre y si está en las 10.000 más
    grandes.

    Si el documento resulta ser de una persona natural, pide `finalidad` antes
    de devolver nada.
    """
    return await _ejecuta(empresas.ficha(documento, finalidad=finalidad or None))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_empresas_estados_financieros(documento: str, anio: int = 0,
                                          limite: int = 30,
                                          formato: str = "tabla") -> ToolResult:
    """Activos, pasivos, patrimonio, ingresos y resultado reportados a
    Supersociedades, por año de corte.

    Son estados financieros NIIF en formato largo XBRL: se piden solo los
    conceptos agregados. **No todas las empresas están**: los bancos y las
    aseguradoras reportan a la Superfinanciera, y Bancolombia no tiene una sola
    fila aquí. La fuente no declara la escala de los importes.
    """
    return await _ejecuta(empresas.estados_financieros(
        documento, anio=anio, limite=limite, formato=formato))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_empresas_ranking(anio: int = 0, macrosector: str = "",
                              departamento: str = "", metrica: str = "ingresos",
                              limite: int = 20, formato: str = "tabla",
                              grafica: bool = True) -> ToolResult:
    """Las empresas más grandes por ingresos, activos, patrimonio o ganancia.

    `metrica`: "ingresos", "activos", "patrimonio" o "ganancia". Los importes
    están en BILLONES de pesos y vienen como texto («$ 100.59»).

    El dataset se llama «10.000 Empresas» y tiene 50.000 filas: son 10.000 por
    año, de 2021 a 2025. Sin `anio` se usa el más reciente y se dice.
    """
    return await _ejecuta(empresas.ranking(
        anio=anio, macrosector=macrosector or None,
        departamento=departamento or None, metrica=metrica, limite=limite,
        formato=formato, grafica=grafica))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_dossier_documento(documento: str, finalidad: str = "",
                               formato: str = "tabla") -> ToolResult:
    """TODO lo que este servidor sabe de un NIT o una cédula, en una llamada.

    Cruza registro mercantil (RUES), contratación estatal (SECOP II), estados
    financieros y ranking (Supersociedades) y cuatro fuentes de sanciones, y
    **enumera lo que miró**: el alcance de la búsqueda queda escrito junto al
    resultado, así que un cero se puede interpretar.

    Empieza por aquí cuando te pregunten por una empresa, y baja al detalle
    después. Cada bloque falla por su cuenta: si una fuente cae, el resto sale.
    """
    return await _ejecuta(dossier.de_documento(
        documento, finalidad=finalidad or None, formato=formato))


# ------------------------------------------------------------ integridad ----
@mcp.tool(annotations=SOLO_LECTURA)
async def co_integridad_screening(documento: str, finalidad: str = "",
                                  limite: int = 10,
                                  formato: str = "tabla") -> ToolResult:
    """Busca un documento en las cinco fuentes de sanciones y antecedentes.

    SIRI (Procuraduría), multas de SECOP I, sanciones a contadores y
    responsabilidad fiscal de la Contraloría. Devuelve una fila por fuente con
    cuántas coincidencias hay, más el detalle.

    **NO es un certificado de antecedentes.** Las fuentes son incompletas y con
    rezago: en SIRI solo 18 de 42.124 sanciones son a contratistas, y la de la
    Contraloría tiene 60 filas parada desde 2022. Un cero aquí no limpia a
    nadie, y la respuesta lo dice.
    """
    return await _ejecuta(integridad.screening(
        documento, finalidad=finalidad or None, limite=limite, formato=formato))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_integridad_disciplinarias(documento: str = "", nombre: str = "",
                                       entidad: str = "", finalidad: str = "",
                                       limite: int = 20, offset: int = 0,
                                       formato: str = "tabla") -> ToolResult:
    """Sanciones disciplinarias del SIRI por documento, nombre o entidad.

    Exige `finalidad` siempre: las 42.124 filas traen nombre, cédula y cargo.
    Buscar por nombre devuelve homónimos y no hay forma de distinguirlos sin el
    documento.

    Para el reparto de sanciones sin identificar a nadie usa
    co_integridad_panorama, que no pide finalidad.
    """
    return await _ejecuta(integridad.disciplinarias(
        documento=documento or None, nombre=nombre or None,
        entidad=entidad or None, finalidad=finalidad or None, limite=limite,
        offset=offset, formato=formato))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_integridad_panorama(agrupar_por: str = "calidad", limite: int = 20,
                                 formato: str = "tabla",
                                 grafica: bool = True) -> ToolResult:
    """El reparto de las sanciones del SIRI, sin una sola persona identificada.

    `agrupar_por`: "calidad", "entidad", "departamento", "sancion",
    "autoridad", "inhabilidad" o "cargo". No pide finalidad, porque responde
    sobre poblaciones y no sobre personas: es la alternativa que el motor de
    privacidad ofrece cuando bloquea una consulta nominal.
    """
    return await _ejecuta(integridad.panorama(
        agrupar_por=agrupar_por, limite=limite, formato=formato, grafica=grafica))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_integridad_sanciones_contratacion(documento: str = "", nombre: str = "",
                                               finalidad: str = "", limite: int = 20,
                                               formato: str = "tabla") -> ToolResult:
    """Multas y sanciones de SECOP I y II a contratistas del Estado.

    Las dos plataformas publican cosas distintas: SECOP I trae el documento del
    contratista y SECOP II solo el nombre, así que **sin `nombre` no se mira
    SECOP II**.

    De las 588 filas de SECOP II, 533 son «Comentarios positivos» y solo 145
    están publicadas: aquí se filtran los negativos publicados.
    """
    return await _ejecuta(integridad.sanciones_contratacion(
        documento=documento or None, nombre=nombre or None,
        finalidad=finalidad or None, limite=limite, formato=formato))


# -------------------------------------------------------------- educación ----
@mcp.tool(annotations=SOLO_LECTURA)
async def co_educacion_saber11(agrupar_por: str = "departamento", periodo: str = "",
                               area: str = "global", departamento: str = "",
                               minimo_estudiantes: int = 20, limite: int = 20,
                               formato: str = "tabla",
                               grafica: bool = True) -> ToolResult:
    """Promedios de Saber 11 agregados. La fuente es microdato individual y
    aquí solo sale agregada: no existe el camino para pedir un estudiante.

    `agrupar_por`: "departamento", "municipio", "colegio", "naturaleza",
    "jornada", "estrato" o "educacion_madre". Las dos últimas son las que hacen
    visible que el puntaje mide sobre todo origen social.

    `area`: "global", "lectura", "matematicas", "sociales", "naturales",
    "ingles". `punt_global` no es la suma de las cinco.

    `periodo` es año y semestre pegados (20224). Los que acaban en 4 son la
    aplicación masiva de octubre y los que acaban en 1 la de marzo, con quince
    mil estudiantes: promediarlos juntos mezcla dos poblaciones.
    """
    return await _ejecuta(educacion.saber11(
        agrupar_por=agrupar_por, periodo=periodo, area=area,
        departamento=departamento or None,
        minimo_estudiantes=minimo_estudiantes, limite=limite, formato=formato,
        grafica=grafica))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_educacion_indicadores(municipio: str = "", departamento: str = "",
                                   anio: int = 0, indicador: str = "",
                                   limite: int = 25, formato: str = "tabla",
                                   grafica: bool = True) -> ToolResult:
    """Cobertura, deserción, aprobación y repitencia por municipio y año.

    Con `indicador` devuelve el ranking de municipios; sin él, la ficha
    completa. Válidos: cobertura_neta, cobertura_bruta, desercion, aprobacion,
    reprobacion, repitencia, poblacion_5_16, tasa_matriculacion, tamano_grupo.

    La cobertura BRUTA pasa de 100 % con normalidad; la NETA no puede.
    `poblacion_5_16` es la única población municipal del servidor y NO sirve de
    denominador para tasas de criminalidad.
    """
    return await _ejecuta(educacion.indicadores(
        municipio=municipio or None, departamento=departamento or None,
        anio=anio, indicador=indicador, limite=limite, formato=formato,
        grafica=grafica))


# ------------------------------------------------------------- territorio ----
@mcp.tool(annotations=SOLO_LECTURA)
async def co_territorio_desempeno(municipio: str = "", departamento: str = "",
                                  anio: int = 0, indicador: str = "mdm",
                                  limite: int = 25, formato: str = "tabla",
                                  grafica: bool = True) -> ToolResult:
    """Índice de Desempeño Municipal del DNP, por municipio y año.

    `indicador`: "mdm", "gestion", "resultados" o "dotaciones". El MDM solo se
    compara DENTRO del mismo grupo de dotaciones iniciales: un ranking nacional
    mezcla municipios que no parten del mismo sitio.

    La serie va de 2016 a 2020 y se paró ahí, aunque la ficha del dataset diga
    que se actualizó en 2022.
    """
    return await _ejecuta(territorio.desempeno(
        municipio=municipio or None, departamento=departamento or None,
        anio=anio, indicador=indicador, limite=limite, formato=formato,
        grafica=grafica))


# ------------------------------------------------------------------ macro ----
@mcp.tool(annotations=SOLO_LECTURA)
async def co_macro_trm(fecha: str = "", desde: str = "", hasta: str = "",
                       formato: str = "tabla") -> ToolResult:
    """TRM de una fecha, de un rango, o la última certificada.

    Con `fecha` busca el rango de vigencia que la contiene, así que un domingo
    devuelve la tasa que rige ese domingo —la del viernes— en vez de nada.
    Fechas en YYYY-MM-DD.
    """
    return await _ejecuta(macro.trm(fecha=fecha, desde=desde, hasta=hasta,
                                    formato=formato))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_macro_convertir(monto: float, fecha: str,
                             hacia: str = "usd") -> ToolResult:
    """Pasa un monto entre pesos y dólares a la TRM de una fecha concreta.

    Es la segunda unidad para los montos de SECOP, que son nominales. **No es
    deflactar**: el dólar también cambia de valor, así que dos cifras en
    dólares de años distintos siguen sin ser comparables en poder de compra. El
    IPC del DANE no tiene API abierta.

    `hacia`: "usd" (de pesos a dólares) o "cop" (al revés).
    """
    return await _ejecuta(macro.convertir(monto, fecha, hacia=hacia))


@mcp.tool(annotations=SOLO_LECTURA)
async def co_macro_tasas(descripcion: str = "", desde: str = "", hasta: str = "",
                         limite: int = 20, formato: str = "tabla",
                         grafica: bool = True) -> ToolResult:
    """Tasas de captación por producto, promediadas sobre un periodo.

    Hace falta al menos `desde` o `descripcion`: la fuente tiene 2,1 M de filas
    y sin filtro la agregación agota el tiempo.

    La tasa es un promedio SIMPLE de lo que reportó cada entidad, no la tasa del
    sistema: esa se pondera por el monto captado, que va al lado.
    """
    return await _ejecuta(macro.tasas(
        descripcion=descripcion or None, desde=desde, hasta=hasta,
        limite=limite, formato=formato, grafica=grafica))


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

@mcp.resource("co://privacidad/politica")
def recurso_privacidad() -> str:
    """La política de privacidad vigente y las finalidades admitidas.

    Se expone como recurso para que el cliente pueda leerla sin provocar un
    error: cuáles son las finalidades válidas, qué fuentes traen personas y qué
    hace el servidor con los documentos.
    """
    return json.dumps({
        "politica": privacidad.politica(),
        "configurable_por": "CO_PRIVACIDAD (variable de entorno del operador, "
                            "no un parámetro de herramienta)",
        "finalidades": privacidad.FINALIDADES,
        "fuentes_con_personas": {
            "c82u-588k": "RUES · 6.962.889 personas naturales de 9.436.330 matrículas",
            "iaeu-rcn6": "SIRI · 42.124 sanciones con nombre, cédula y cargo",
            "fs36-azrv": "Contadores · 1.451 sanciones con nombre y cédula",
            "kgxf-xxbe": "Saber 11 · 7.109.704 registros individuales (solo agregado)",
        },
        "enmascarado": "dos primeros y dos últimos dígitos del documento",
        "sin_finalidad": "las herramientas agregadas (co_integridad_panorama, "
                         "co_educacion_saber11) nunca la piden",
    }, ensure_ascii=False, indent=2)


@mcp.resource("co://fuentes/familias")
def recurso_familias() -> str:
    """Las familias de datasets del registro, con su unidad de análisis."""
    return json.dumps(
        {familia: {clave: {"id": d.id, "nombre": d.nombre, "unidad": d.unidad}
                   for clave, d in miembros.items()}
         for familia, miembros in reg.FAMILIAS.items()},
        ensure_ascii=False, indent=2)


@mcp.resource("co://sin-fuente-abierta")
def recurso_sin_fuente() -> str:
    """Lo que este servidor NO puede responder, y por qué.

    Está como recurso porque la pregunta se hace sola al ver el resto del
    catálogo, y porque la respuesta correcta a «dame la tasa de homicidios por
    100.000» es decir que no hay denominador, no inventarse uno.
    """
    return json.dumps(reg.SIN_FUENTE_ABIERTA, ensure_ascii=False, indent=2)



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
