# Registro de cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

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
