# Registro de cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [0.3.0] — 2026-08-18

### Añadido

- **Contenido estructurado en todas las respuestas.** El sobre ya calculaba
  `datos` y `_meta` y se descartaban: las herramientas devolvían solo prosa.
  Ahora viajan por el canal estructurado del protocolo, con las filas tipadas
  —las coordenadas son `float`, no texto— y los metadatos accesibles sin volver
  a parsear la tabla.
- **`formato` en las herramientas de consulta**: `"csv"` o `"json"` en vez de
  tabla. El cuerpo va en un bloque cercado para que se copie limpio, y el sobre
  se mantiene debajo: extraer no puede costar la procedencia.
- **`co_datos_exportar`**, la primera herramienta que escribe. Pagina hasta
  agotar el filtro y guarda CSV, JSON o Parquet bajo `CO_EXPORT_DIR`.
  `nombre_archivo` es un nombre y no una ruta: `../../etc/passwd` se neutraliza.
  Anotada con `readOnlyHint: false` para que el cliente pueda pedir
  confirmación. Si se alcanza `max_filas`, el fichero queda incompleto y la
  respuesta lo dice. El CSV lleva BOM para que Excel respete los acentos.
- **Barras en las agregaciones**, proporcionales a la métrica y a escala
  compartida. Cero dependencias. Se apagan con `grafica=false`.
- **Aviso de valores imposibles.** SECOP tiene 3.452 contratos por encima del
  billón de pesos —el mayor son 881,8 trillones, unas 560.000 veces el PIB del
  país— que
  son errores de digitación y aportan el **99,99998 %** de la suma de los 5,96 M
  de contratos. `co_secop_agregar` ahora cuenta cuántos caen en el filtro y qué
  parte de la suma representan. Lo destapó una de las barras nuevas: un solo
  departamento llenaba la escala.
- 22 pruebas nuevas (83 → 105), incluidas las del saneamiento de rutas.

### Documentación

- **Cinco diagramas Mermaid** donde la prosa escondía la estructura: las capas y
  el ciclo de vida completo de una consulta —caché, dedup, breaker, reintentos,
  presupuesto— en `arquitectura.md`; el árbol de decisión de la comparación de
  nombres en el README, que es lo único que muestra la rama del cero honesto; el
  flujo de buscar a una persona natural en `recetas.md`, con un rombo en cada
  sitio donde se puede dar por buena una cifra equivocada; y el grafo de joins
  en `fuentes.md`, donde se ve que la unidad de análisis cambia en cada salto.
- Los ejemplos de gráficas de los `.md` eran **inventados**: valores elididos con
  `…`, columnas alineadas a mano y, sobre todo, ilustraban la función con las
  sumas corruptas que el propio README declara inservibles. Sustituidos por
  salida capturada de la fuente, con la llamada que la reproduce al lado y
  verificada fila a fila contra la ejecución real. El caso de las sumas
  imposibles se queda, pero como lo que es: el ejemplo de una gráfica que delata
  un problema del dato, no la demostración de la función.

### Corregido

- **`a_numero` leía mil veces de más los números grandes con tres decimales.**
  La regla «un separador con tres dígitos detrás es de miles» necesita también
  que la parte entera tenga uno a tres dígitos: sin eso, una suma agregada como
  `5093243848602202766138.364` se convertía en 5,09·10²⁴. Salió al calcular el
  porcentaje del aviso anterior, que daba 100.000 %.
- `secop._numero` era una copia de esa misma regla que había divergido; ahora
  delega en `format.a_numero`.
- El pie del sobre ya no anuncia «0 fila(s)» ni una página siguiente en
  respuestas donde contar filas no significa nada, como la exportación.

## [0.2.1] — 2026-08-18

### Corregido

- **Columnas perdidas en silencio cuando la primera fila era más corta.**
  Socrata omite los campos nulos en vez de mandarlos vacíos, y las columnas de
  la tabla se deducían de `filas[0]`. Un contrato en `Borrador` —que no trae
  `fecha_de_firma`— encabezando el resultado **borraba la fecha de las once
  filas que sí la tenían**. Ahora se toma la unión de las claves de todas las
  filas, y con proyección curada se conserva el orden curado.

### Añadido

- `docs/fuentes.md` — los 11 datasets con su unidad de análisis, campos clave,
  joins, atribuciones y trampas propias. Hasta ahora eso solo existía dentro de
  `registry/datasets.py`.
- `docs/recetas.md` — secuencias que funcionan, con la trampa de cada una: buscar
  a una persona natural, resolver una entidad antes de filtrar, agregar por
  territorio, y cómo leer el sobre señal por señal.
- `docs/operacion.md` — diagnóstico: caché, throttling, timeouts medidos, la
  fragilidad de stdio y **por qué el servidor sigue ejecutando código viejo**
  aunque la instalación sea editable.
- **README reestructurado para ser claro por sí solo**, sin obligar a abrir
  `docs/`: un ejemplo real de respuesta con el sobre anotado línea por línea, la
  sección «Antes de citar una cifra» con las siete reglas que el servidor no
  puede decidir por ti, la lista explícita de lo que el servidor NO hace, y el
  aviso de que un proceso MCP viejo sigue ejecutando código viejo. Las trampas
  se separan en las que absorbe el servidor y las que te tocan a ti.
- Índice de documentación en el README.
- 2 pruebas de regresión de las columnas dispersas (81 → 83).

## [0.2.0] — 2026-08-18

Corrige un defecto que hacía inalcanzable por nombre una parte grande de los
datos, y otros ocho encontrados al verificar contra la API viva.

### Corregido

- **Comparación de nombres contra columnas acentuadas.** La premisa «los acentos
  vienen destruidos en origen» solo es cierta en los campos de texto libre de
  SECOP; las columnas categóricas los conservan (`departamento` es `Atlántico`,
  `nom_mpio` es `MEDELLÍN`). Plegar el término y compararlo con `like` no casaba
  nada: **392 de 1.122 municipios, 12 de 33 departamentos y ~2,8 M de contratos**
  eran inalcanzables, y el cero era indistinguible de «no hay datos».

  Ahora la estrategia depende de la cardinalidad del campo: dominio enumerable →
  se resuelve contra los valores canónicos y se filtra con `in (...)`; texto
  libre → el plegado se hace en el servidor con `replace()` anidado. Ambas son
  exactas. Se descartaron dos alternativas con comodines por medición, no por
  intuición (32 % y 18 % de consultas contaminadas).

- **Cero honesto.** Un término categórico que no existe en la fuente ya no se
  consulta: se devuelve cero explicando que el término no existe.

- **`co_datos_agregar` con métrica propia.** `ORDER BY total` estaba cableado
  mientras `metricas` era un parámetro libre, así que cualquier métrica con otro
  alias producía un 400 de Socrata («No such column: total»). El orden se deriva
  ahora del primer alias real.

- **Conteos formateados como moneda.** `count(*) as total` se mostraba como
  `$125`: «125 municipios» se leía como «125 pesos». El criterio moneda/conteo
  vive en `format.es_monetario` / `format.es_conteo`, y el orden importa —
  `valor_total` es dinero, `total` a secas es un conteo.

- **Falsos `[VALIDACION]` en la allow-list.** `distinct` y una veintena de
  palabras reservadas de SoQL se tomaban por nombres de columna y se rechazaban
  como inexistentes.

- **Orden estable en la primera página.** `$order` solo se forzaba con `offset`
  distinto de cero, de modo que la página 1 usaba el orden natural de la fuente
  y la 2 usaba `:id`: al paginar se perdían y duplicaban filas igual. Ahora se
  fuerza siempre, **salvo en consultas agregadas**, donde Socrata rechaza
  ordenar por una columna que no está en el `group by`.

- **`valor_min` con separadores colombianos.** `"1.000.000"` escapaba un
  `ValueError` crudo, sin código ni sugerencia. Se acepta `1000000`,
  `"1.000.000"` y `"$1.000.000"`. Ojo: aquí el punto separa miles, al contrario
  que en `core/coords.py`, donde la primera coma es el decimal.

- **Cliente HTTP atado a un event loop muerto.** El `AsyncClient` era un
  singleton por proceso y `is_closed` no detecta que su loop se cerró: la
  siguiente petición moría con «Event loop is closed». Ahora se compara el loop
  y se reconstruye si cambió.

- **Excepción sin recoger en la caché.** Un fallo cacheado dejaba un futuro con
  excepción que nadie esperaba, y asyncio lo denunciaba en stderr — ruido que
  contamina el transporte stdio.

- **Espera inútil tras el último reintento**, que retrasaba el error unos
  segundos sin cambiarlo. Y se ignoraba **`Retry-After`**, la única cifra real
  frente a un backoff inventado.

- **Alias de entidad erróneos.** SECOP registra **INVIAS** y **UNGRD** con su
  sigla y nada más; expandirlas a su razón social daba cero. **RTVC** no está en
  el dataset de contratos con ningún nombre, solo en SECOP Integrado. Un alias
  caduco ahora reintenta con lo que escribió el usuario y lo advierte, en vez de
  rendirse.

### Añadido

- **Suite de contrato contra la API viva** (`pytest -m contrato`, 13 pruebas):
  vigila los supuestos sobre los que está construido el código. Su fallo señala
  que el Estado cambió el esquema, no que el servidor se rompiera.
- **CI en GitHub Actions**: pruebas sin red en Python 3.11–3.13 por push, y el
  contrato programado a diario con `continue-on-error`.
- **Documentación**: referencia completa de las 12 herramientas con parámetros y
  topes, documento de arquitectura —incluida una lista explícita de lo que
  todavía **no** hace—, guía de contribución y este registro. El README
  documenta por primera vez las ocho variables de entorno.
- `core/texto.py`: único punto donde se pliegan acentos para comparar.
- 27 pruebas nuevas sin red (54 → 81).

### Cambiado

- La versión vive solo en `src/colombia_datos_mcp/__init__.py`; `pyproject.toml`
  la lee de ahí y el `User-Agent` la compone. Antes estaba repetida en cuatro
  sitios.
- El playbook del servidor dice al modelo que puede escribir los nombres con
  tilde o sin ella.

### Eliminado

- **`format.sin_acentos`** (cambio incompatible). Su nombre invitaba justo al
  error que causó el defecto: construir un `like` con el término plegado contra
  una fuente que conserva los acentos. Usa `core.texto.plegar` para comparar en
  memoria, o `socrata.expr_sin_acentos` para plegar en el servidor.

## [0.1.0] — 2026-08-18

Versión inicial: fase F0 + la mitad Socrata de F1.

- Núcleo: sobre de respuesta con URL reproducible, presupuesto de tokens con
  degradación explícita, caché de dos niveles con deduplicación en vuelo, HTTP
  con autolímite y circuit breaker, errores tipados, saneamiento de coordenadas.
- Adaptador de Socrata: Discovery API + SODA.
- 12 herramientas sobre catálogo nacional, SECOP y DIVIPOLA, más 3 recursos.
- 54 pruebas sin red sobre fixtures reales capturadas el 18-ago-2026.
