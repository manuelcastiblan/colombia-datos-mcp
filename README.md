# colombia-datos-mcp

Servidor MCP para datos públicos de Colombia: catálogo nacional de
`datos.gov.co`, contratación pública (SECOP) y división territorial (DIVIPOLA).
12 herramientas de solo lectura, sin credenciales.

Esta es la **fase F0 + la mitad Socrata de F1** del diseño: núcleo completo,
adaptador de Socrata y los módulos de catálogo, SECOP y DIVIPOLA.

## Instalación

```bash
pip install -e .
```

```bash
colombia-datos-mcp                      # stdio
colombia-datos-mcp --http --port 8080   # streamable HTTP
```

Requiere Python 3.11 o superior.

## Configuración en el cliente MCP

Claude Desktop o Claude Code:

```jsonc
{ "mcpServers": { "colombia-datos": {
    "command": "colombia-datos-mcp",
    "env": { "SOCRATA_APP_TOKEN": "opcional" } } } }
```

En Windows conviene apuntar al ejecutable con ruta absoluta
(`...\Scripts\colombia-datos-mcp.exe`): el cliente MCP no siempre hereda el
mismo `PATH` que tu terminal.

**No requiere credenciales.** `SOCRATA_APP_TOKEN` es opcional; sin él Socrata
limita por IP y el servidor lo advierte una vez en el sobre. El token viaja por
cabecera, nunca por query string, así que no aparece en logs ni en la URL
reproducible.

### Variables de entorno

Todas son opcionales y tienen valores conservadores.

| Variable | Defecto | Qué controla |
|---|---|---|
| `SOCRATA_APP_TOKEN` | — | Cuota propia en Socrata. Un token inválido produce `[CONFIG]`, no degradación silenciosa. |
| `CO_PRESUPUESTO_TOKENS` | `6000` | Tamaño máximo de respuesta antes de recortar filas. |
| `CO_TTL_DATOS` | `900` (15 min) | TTL de la caché en memoria. |
| `CO_TTL_METADATOS` | `86400` (24 h) | TTL de esquemas y dominios categóricos, en disco. |
| `CO_CACHE_DIR` | `~/.cache/colombia-datos-mcp` | Dónde vive la caché L2. |
| `CO_REQ_POR_SEGUNDO` | `5` | Autolímite por host. |
| `CO_MAX_REINTENTOS` | `4` | Intentos por petición antes de rendirse. |
| `CO_USER_AGENT` | `colombia-datos-mcp/<versión> (+URL del repo)` | Identificación ante la fuente. |

## Herramientas

| Herramienta | Qué hace |
|---|---|
| `co_datos_buscar_datasets` | Catálogo nacional; traduce siglas de entidad a la cadena de atribución exacta |
| `co_datos_describir_dataset` | Esquema en vivo: campo técnico + nombre legible + tipo + descripción |
| `co_datos_consultar` | SoQL con allow-list de columnas; `detalle` = conteo / resumen / completo |
| `co_datos_agregar` | Agrupa del lado del servidor |
| `co_secop_buscar_contratos` | Contratos de SECOP II |
| `co_secop_buscar_procesos` | Procesos de contratación |
| `co_secop_detalle_contrato` | Vista compuesta: contrato + adiciones + URL pública |
| `co_secop_perfil_proveedor` | Perfil agregado por cédula o NIT |
| `co_secop_resolver_entidad` | Nombre coloquial → nombre canónico + NIT |
| `co_secop_agregar` | Totales por departamento, entidad, modalidad, proveedor… |
| `co_geo_divipola` | Códigos y coordenadas de departamentos, municipios y centros poblados |
| `co_geo_cotejar_coordenadas` | Control de calidad entre las dos fuentes oficiales de coordenadas |

Más tres *resources*: `co://secop/datasets`, `co://secop/joins`,
`co://atribuciones`.

**Parámetros, topes y advertencias de cada una:
[docs/herramientas.md](docs/herramientas.md).** Secuencias que funcionan, con sus
trampas: [docs/recetas.md](docs/recetas.md).

## Qué hace distinto

**El contrato de respuesta.** Toda respuesta trae un sobre con filas devueltas,
total de coincidencias, orden aplicado y **la URL exacta reproducible**. Si
`devueltos < total`, el servidor lo dice y advierte que no se concluya nada
cuantitativo desde esas filas.

**Presupuesto de tokens con degradación explícita.** Si la respuesta no cabe, se
recorta y se marca `truncado: true` con instrucciones de qué hacer. Contar nunca
implica traer filas: `detalle="conteo"` cuesta ~200 tokens.

**Paginación honesta.** `siguiente_offset` se calcula sobre lo realmente
devuelto, nunca sobre lo descargado. Y el orden estable se fuerza ya en la
primera página: si la página 1 no tiene orden, la 2 no puede tenerlo.

**Errores tipados.** `[VALIDACION]`, `[FUENTE_CAIDA]`, `[LIMITE_TASA]`… con
sugerencia accionable. Una fuente caída nunca se confunde con cero resultados.

**Esquema en vivo, nunca cableado.** Las columnas se validan contra el esquema
real; un campo inexistente se rechaza listando los válidos.

**Cero honesto.** Cuando un término no existe en la fuente, el servidor lo dice
en vez de devolver una tabla vacía. Una tabla vacía es indistinguible de «no hay
datos».

## Cómo se comparan los nombres

Es la pieza menos obvia del servidor, y nació de un defecto medido.

Las columnas **categóricas de la fuente conservan los acentos** —`departamento`
es `Atlántico`, `nom_mpio` es `MEDELLÍN`—, y SoQL no tiene `unaccent()`: su
`like` distingue acentos. La estrategia se elige por la cardinalidad del campo:

| Caso | Estrategia | Por qué |
|---|---|---|
| Dominio enumerable (`departamento`, `modalidad`, municipios) | Se traen los valores canónicos (cacheados 24 h), se resuelve el término en Python y se filtra con `in ('Atlántico')` | Exacto, y compara por igualdad: 1,7 s frente a 7-20 s |
| Texto libre (`nombre_entidad`, `proveedor_adjudicado`) | El plegado se hace **en el servidor**, con `replace()` anidado sobre la columna | No hay lista que enumerar; exacto y de coste constante en la longitud del término |

Se descartaron dos alternativas por medición contra los 1.122 municipios
reales, no por intuición: los comodines sobre las vocales alcanzaban el 100 % de
recall pero contaminaban el 32 % de las consultas —«ANDES» casaba con
«CALDAS»—, y un solo comodín por posición bajaba el ruido al 18 % pero perdía
los nombres con dos tildes («ITAGÜÍ», «EL PEÑÓN»). Las tres mediciones están en
`tests/test_texto.py`.

En la práctica: **escribe los nombres con tilde o sin ella, da igual.**

## Trampas de la fuente que el servidor absorbe

- `search_context` es obligatorio en la Discovery API o `categories`/`tags`
  devuelven **0 en silencio**.
- El facet `attribution` solo acepta la cadena literal completa.
  `attribution=DANE` da cero; hay que usar `Departamento Administrativo Nacional
  de Estadísticas - DANE, Bogotá D.C.` — con «Estadísticas» en plural, que no es
  el nombre real de la entidad.
- `$order` es obligatorio al paginar o se pierden o duplican filas. Pero **no se
  puede ordenar por `:id` una consulta agregada**: Socrata responde «Column
  ':id' is not in group by».
- Los números llegan como string; los códigos DIVIPOLA son texto con ceros a la
  izquierda.
- Los acentos vienen destruidos en origen **solo en el texto libre**
  (`descripcion` trae `EJECUCIoN`). Las columnas **categóricas los conservan**.
  Dar por buena la primera mitad y aplicarla a todo dejaba 392 de 1.122
  municipios, 12 de 33 departamentos y ~2,8 M de contratos inalcanzables por
  nombre. Ver *Cómo se comparan los nombres*.
- **SoQL sí soporta `replace()` anidado.** Una prueba con `curl` sugería lo
  contrario, pero era el shell corrompiendo el acento, no la API.
- **Coordenadas:** en `xaxy-8nri` exactamente un registro de 8.161 —Medellín—
  trae separador de miles (`-75,581,775`), y `float(s.replace(",", "."))`
  **lanza `ValueError`** sobre él. `core/coords.py` aplica «la primera coma es el
  decimal» y valida contra la caja envolvente del país. Cuidado: esa regla es
  correcta para coordenadas y **falsa para dinero**, donde `1.000.000` es un
  millón.
- Las «modificaciones contractuales» se llaman **Adiciones**; buscar
  «modificaciones» devuelve cero.
- **Socrata omite los campos nulos** en vez de mandarlos vacíos, así que dos
  filas del mismo dataset llegan con juegos de claves distintos. Un contrato en
  `Borrador` no trae `fecha_de_firma`, y deducir las columnas de la primera fila
  borraba la fecha de todas las demás.
- **Los contratos en `Borrador` están en el dataset** y suman en
  `sum(valor_del_contrato)`, pero no están firmados y su `valor_pagado` es 0.
  Filtra por estado si lo que quieres es contratación real.
- Varias entidades se registran en SECOP con su sigla y nada más: **INVIAS** y
  **UNGRD** figuran así, y expandirlas a su razón social da cero. **RTVC** no
  está en el dataset de contratos con ningún nombre, solo en SECOP Integrado.

## Pruebas

```bash
pip install -e ".[dev]"
```

```bash
pytest              # 83 pruebas, sin red
```

```bash
pytest -m contrato  # 13 pruebas contra la API viva (~5 min)
```

Las fixtures son respuestas **reales** capturadas de la API el 18-ago-2026, con
sus defectos intactos: coma decimal, separador de miles en Medellín, números
como string.

La suite de contrato comprueba los supuestos sobre los que está construido el
código —que DIVIPOLA y SECOP siguen acentuando, que SoQL sigue aceptando
`replace()` anidado, que los alias curados siguen resolviendo, que el registro
envenenado de Medellín sigue ahí, que los IDs no rotaron—. Corre a diario en CI
y **su fallo no es un bug del servidor: es la señal de que el Estado cambió el
esquema.**

## Documentación

| Documento | Para qué |
|---|---|
| [docs/herramientas.md](docs/herramientas.md) | Las 12 herramientas: parámetros, valores por defecto y topes. |
| [docs/recetas.md](docs/recetas.md) | Secuencias que funcionan, con las trampas de cada una y cómo leer el sobre. |
| [docs/fuentes.md](docs/fuentes.md) | Los 11 datasets: unidad de análisis, campos clave, joins y atribuciones. |
| [docs/arquitectura.md](docs/arquitectura.md) | Cómo está construido, y qué **no** hace todavía. |
| [docs/operacion.md](docs/operacion.md) | Diagnóstico: caché, throttling, timeouts, y por qué el servidor no recoge tus cambios. |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Las capas de prueba y cómo añadir un dataset o un filtro. |
| [CHANGELOG.md](CHANGELOG.md) | Qué cambió en cada versión. |

## Estado y siguiente paso

Implementado: núcleo (sobre, presupuesto, caché de dos niveles, HTTP con
autolímite y circuit breaker, errores tipados, coordenadas), adaptador Socrata,
comparación de nombres tolerante a acentos, y los módulos de catálogo, SECOP y
DIVIPOLA. CI con las pruebas sin red en Python 3.11-3.13 y el contrato
programado a diario.

Pendiente, en orden: adaptador SDMX para Banco de la República, adaptador ArcGIS
(IGAC / MGN del DANE) con descubrimiento dinámico del corte vigente, el motor de
privacidad, y solo después los módulos de seguridad y DDHH.

Lo que hoy **no** hace, para que nadie lo dé por hecho, está enumerado en
[docs/arquitectura.md](docs/arquitectura.md#lo-que-todavía-no-hace).

## Licencia y atribución

Código bajo licencia MIT.

Los datos son de la Nación y se publican bajo **CC BY-SA 4.0**: si los
redistribuyes, propaga la atribución. Cada respuesta del servidor la trae en el
sobre, junto con la URL reproducible.
