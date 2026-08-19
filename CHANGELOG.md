# Registro de cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [0.7.0] — 2026-08-19

### Corregido

- **`co_datos_agregar` llamaba «total» a lo que cabía en la tabla.**
  `total_coincidencias` era `len(filas)`, de modo que una consulta recortada a
  12 grupos afirmaba «12 de 12» habiendo 2.881 entidades. Es el peor error
  posible en este servidor: no devolver de más, sino **parecer completo justo
  cuando no lo está**, que es lo único que el sobre existe para impedir. Ahora,
  si la fuente devuelve menos filas que el límite, no hay más y el total es
  exacto sin coste; si llena el límite, los grupos se cuentan con una
  subconsulta anidada; y si la fuente no admite anidar, el total se declara
  **desconocido** con su advertencia, en vez de inventarse uno.
- El aviso de respuesta parcial recomendaba «usa una herramienta de agregación,
  no estas filas» **dentro de la propia herramienta de agregación**. `Sobre`
  admite ahora `aviso_parcial`, y la agregación dice lo que corresponde: los
  grupos ocultos no se recuperan agregando otra vez, sino subiendo `limite` o
  afinando `donde`.
- **Las métricas con alias libre salían sin formato.** El formateo dependía de
  un vocabulario fijo (`total`, `contratos`, `cantidad`…), así que en una misma
  fila convivían `contratos: 293.546` y `personas: 130720`. El alias lo elige
  quien consulta y ninguna lista cerrada lo va a adivinar; la regla pasa a ser
  estructural: en una agregación, toda columna que no sea clave de grupo es una
  métrica.
- **Identificadores blindados frente a ese mismo cambio.** `documento`, `nit`,
  `cod_*` y `divipola` nunca se formatean como cifra: `"05001"` convertido en
  `"5.001"` pierde el cero inicial y rompe todos los cruces territoriales.

### Añadido

- **Operador anidado de SoQL (`|>`), vía el parámetro `luego` de
  `co_datos_agregar`.** Encadena una segunda agregación sobre el resultado de
  la primera, cuyas columnas son los alias de la etapa anterior. Cierra una
  pregunta que antes no tenía respuesta posible: `count(*)` con `having` cuenta
  **dentro** de cada grupo, nunca cuántos grupos quedan. «Cuántas personas
  tienen más de un contrato» exige agregar sobre los grupos:

      agrupar_por="documento_proveedor", metricas="count(*) as n",
      teniendo="count(*) > 1", luego="count(*) as personas, sum(n) as contratos"

- `socrata.arma_soql()` compone SoQL como texto —único modo de expresar `|>`,
  que `$select`/`$group` sueltos no admiten—, `consultar_soql()` lo ejecuta por
  `$query` y `contar_grupos()` lo usa para el conteo honesto de arriba.

## [0.6.1] — 2026-08-18

### Corregido

- **El sobre decía «Viendo 1 de 2 coincidencias» en respuestas cuyos `datos` no
  son filas.** En `co_geo_limites` los datos son un FeatureCollection y en la
  exportación la ficha del fichero, así que `devueltos` contaba el envoltorio y
  no su contenido: la geometría de San Andrés y Providencia salía con las dos
  islas dentro y el sobre afirmando que faltaba una, arrastrando además el aviso
  de no sacar conclusiones cuantitativas. Ahora ese aviso y `siguiente_offset`
  respetan `mostrar_conteo`, igual que ya hacía el pie.

## [0.6.0] — 2026-08-18

### Añadido

- **`co_geo_limites`** y el adaptador `adapters/geometria.py`: límites
  municipales y departamentales como GeoJSON, con la clave DIVIPOLA como
  identificador. Cierra el círculo de «DIVIPOLA es la clave de join universal»:
  ahora el servidor puede dibujar el territorio del que habla.
- La geometría va en el **contenido estructurado**, no en el markdown, y por
  encima de 200 features hay que acotar o usar `guardar`, que escribe un
  `.geojson` bajo `CO_EXPORT_DIR`. Sin ese tope, 1.122 polígonos revientan al
  cliente.
- `nivel="departamento"` agrupa los municipios en un MultiPolygon. **No es una
  disolución real** —las aristas internas siguen ahí— y el sobre lo dice.
- `CO_GEOMETRIA_URL` para cambiar la fuente sin tocar código.
- 14 pruebas sin red (135 → 149) y 3 de contrato.

### Por qué la fuente no es oficial

Se buscó, y no hay endpoint utilizable:

- El servicio nacional del IGAC, `atlas/politicoadministrativo`, devuelve
  **HTTP 500 «Wait timeout»** en MapServer y en FeatureServer.
- Su carpeta `limites` solo contiene territorios cedidos por Colombia, y de las
  **952 capas** de `carto` ninguna es municipal ni departamental.
- `datos.gov.co` no publica los límites como dataset: `only=map` y `only=geo`
  devuelven cero resultados.

Así que la geometría sale de una réplica pública del **Marco Geoestadístico
Nacional 2018 del DANE**. El adaptador valida la forma antes de fiarse —que sea
un FeatureCollection, que traiga ~1.122 municipios, que tenga `MPIO_CCNCT`— y
falla con un mensaje claro si la réplica cambia, en vez de dibujar un mapa con
agujeros. Cada respuesta declara la procedencia completa.

Y está **muy simplificada**: mediana de 10 vértices por municipio, con el 48 %
por debajo de diez —San Andrés son 5 puntos—. Basta para colorear un mapa
nacional, pero no para medir áreas ni para resolver si un punto cae dentro cerca
de un límite. Se advierte en cada respuesta, porque es la diferencia entre un
uso legítimo y una cifra inventada.

Una prueba de contrato **vigila si el IGAC vuelve a responder**: el día que lo
haga, esto debería migrar a la fuente oficial.

## [0.5.0] — 2026-08-18

### Añadido

- **`co_datos_serie`** — serie temporal sobre cualquier dataset, por año, mes o
  día. Evita escribir `date_extract_y(...)` a mano, cosa que en una sola sesión
  hizo falta seis veces. Y hace lo que ninguna consulta hace sola: **avisa
  cuando el último periodo está incompleto**, comparando con `max(campo_fecha)`.
  Es el error que produjo una cifra equivocada en esta misma sesión —una serie
  anual cuyo último año llegaba hasta agosto parecía una caída del 30 %—. No
  salta si el periodo sí está cerrado: un aviso que salta siempre deja de leerse.
  Y rechaza las columnas de fecha que en realidad son `text`, como las cinco del
  Plan Anual de Adquisiciones, donde agrupar falla y `between` miente.
- **`co_datos_perfilar`** — retrato de una columna antes de fiarse de ella:
  nulas, rango, **reparto por orden de magnitud** y, sobre todo,
  **concentración**. Sobre `valor_del_contrato` de SECOP II responde que diez
  filas de 5.958.553 aportan el **95,5 %** de la suma. Ese hallazgo costó una
  investigación entera; ahora cuesta una llamada.
- 12 pruebas sin red (123 → 135), incluida la de que el aviso de periodo
  incompleto **no** salte cuando el periodo está cerrado.

## [0.4.0] — 2026-08-18

### Añadido

- **Módulo de criminalidad**: `co_crimen_serie`, `co_crimen_por_municipio` y
  `co_crimen_comparar`, sobre 23 datasets de MinDefensa con esquema común
  (`cod_muni`, `fecha_hecho`, `cantidad`) verificados uno a uno contra la API.
  Series desde 2003, con `cod_mpio` en la salida para cruzar por código.
- Registro curado de los 23 delitos, con su unidad de análisis y sus trampas.
- 4 pruebas de contrato que vigilan que los IDs no roten, que el esquema siga
  siendo común, y las dos suposiciones de abajo.
- 16 pruebas sin red del módulo (107 → 123).

### Documentación

- **Las reglas de «Antes de citar una cifra» eran todas de contratación.** Quien
  leía la sección estrella del README no recibía ni un aviso sobre criminalidad.
  Ahora se agrupan en tres bloques —las que valen para cualquier consulta, las de
  contratación y las de crimen— y las cinco nuevas cubren lo que el módulo
  advierte: casos registrados frente a delitos cometidos, el año base, la falta
  de tasas, el corte de cada dataset y que `cantidad` no vale uno.
- `docs/herramientas.md`, `docs/fuentes.md`, `docs/recetas.md`,
  `docs/arquitectura.md` y `CONTRIBUTING.md` documentan el módulo, los 23
  datasets, los 14 que quedan fuera y por qué, y las dos lecciones de MinDefensa.

### Decisiones que documenta el registro

- **Se excluyen los datasets operativos.** MinDefensa publica 37 con el mismo
  esquema, pero incautaciones y erradicación no comparten unidad: en
  `ERRADICACIÓN` la `cantidad` son HECTÁREAS y en las incautaciones la columna
  `unidad` trae valores como `0.002`. Mezclarlos con homicidios produce sumas
  sin significado, así que el registro solo expone delitos.
- **«HURTO A COMERCIO» y «HURTO A RESIDENCIAS» son el mismo dato**, con cifras
  idénticas año por año: 613.637 filas y 614.669 casos en ambos. Uno de los dos
  títulos está mal en la fuente. Sumarlos duplicaría la cifra de hurtos, y las
  notas del registro lo advierten en los dos.
- **`cantidad` no siempre vale uno**: homicidio tiene 342.971 filas y 343.680
  víctimas. Se suma `cantidad`, nunca se cuentan filas.

### Lo que el sobre advierte, y por qué

- **Casos registrados no son delitos cometidos.** Una subida en extorsión o en
  violencia intrafamiliar puede ser más denuncia y no más delito; el homicidio
  es el indicador menos sensible a eso.
- **El año base decide el titular.** El secuestro subió 259 % contra 2017 y bajó
  67 % contra 2003: la misma serie. `co_crimen_serie` devuelve el máximo y el
  mínimo junto a los datos, y `comparar` recuerda que la elección no es neutral.
- **Cada dataset corta por su cuenta.** Se consulta `max(fecha_hecho)` y se
  avisa de que el último año está incompleto: comparar un año a medias con años
  cerrados es la forma más fácil de inventarse una caída.
- **Sin población no hay tasas.** Se buscaron proyecciones municipales en la
  fuente, incluido el facet del DANE, y no están. Las listas por municipio se
  parecen a listas de municipios grandes, y el sobre lo dice.

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
- **Aviso de valores imposibles.** De los 5.958.553 contratos de SECOP II,
  **nueve aportan el 94 %** de la suma. El mayor son 881,8 trillones de pesos
  —unas 560.000 veces el PIB del país—, y en la banda de 1 a 10 billones hay
  contratos de un enfermero por 9,97 billones. Ampliando al umbral del billón,
  son 3.452 registros que aportan el 99,99998 % del total; el **100 %** tiene
  `valor_pagado = 0`. `co_secop_agregar` cuenta cuántos caen en tu filtro y qué
  parte de la suma representan. Lo destapó una de las barras nuevas: un solo
  departamento llenaba la escala.
- **`valor_max` en `co_secop_buscar_contratos`**, simétrico de `valor_min`.
  Acotar por magnitud es la ÚNICA forma de sacar los imposibles: filtrar por
  estado no basta —el 97 % están cancelados o en borrador, pero los 83 que
  sobreviven siguen dominando la suma—. Cifras utilizables: $997,5 billones
  contratados sin los imposibles, $251,6 billones efectivamente pagados.
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
