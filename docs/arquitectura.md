# Arquitectura

Tres capas y una regla: **el dominio no habla HTTP y el adaptador no sabe de
SECOP**.

```mermaid
flowchart TD
    cliente["Cliente MCP"]
    server["server.py<br/>19 herramientas · 3 recursos · playbook<br/>traduce los errores tipados y arma el ToolResult"]
    dominio["domain/ · catalogo · secop · geo · crimen · analisis · exportar<br/>construye filtros, proyecta columnas, arma el sobre"]
    adaptador["adapters/<br/>socrata.py · Discovery API + SODA<br/>geometria.py · límites del MGN"]
    fuente[("datos.gov.co")]
    registro["registry/<br/>unidad de análisis · campos clave · alias · atribuciones"]
    nucleo["core/<br/>sobre · presupuesto · caché · HTTP · errores · coordenadas · texto"]

    cliente --> server --> dominio --> adaptador --> fuente
    dominio -.- registro
    dominio -.- nucleo
    adaptador -.- nucleo
```

La flecha continua es la petición; la punteada, de qué se apoya cada capa. El
dominio nunca llama a `httpx` y el adaptador nunca sabe qué es un contrato.

| Módulo | Responsabilidad |
|---|---|
| `core/envelope.py` | El sobre: metadatos honestos alrededor de cada respuesta. |
| `core/budget.py` | Presupuesto de tokens y degradación explícita. |
| `core/cache.py` | Caché L1 en memoria + L2 en disco, con deduplicación en vuelo. |
| `core/http.py` | Autolímite por host, backoff, circuit breaker, errores tipados. |
| `core/errors.py` | Jerarquía de errores con código estable y sugerencia accionable. |
| `core/coords.py` | Saneamiento de coordenadas de DIVIPOLA. |
| `core/format.py` | Markdown, moneda es-CO, fechas, mojibake. |
| `core/texto.py` | Plegado y comparación de nombres contra fuentes acentuadas. |
| `core/nit.py` | Las dos formas de un NIT —con y sin dígito de verificación— y por qué una cédula no se pliega nunca. |
| `core/privacidad.py` | El guardarraíl de las tres fuentes que traen personas: política, finalidad, clasificación del documento y enmascarado. |
| `registry/datasets.py` | IDs, unidad de análisis, campos clave, alias, atribuciones. |
| `adapters/geometria.py` | Límites del MGN, con validación de forma y caché en disco. |
| `domain/analisis.py` | Series temporales y perfilado de calidad, para cualquier dataset. |
| `domain/crimen.py` | 23 datasets de MinDefensa: series, municipios y comparación entre años. |
| `domain/exportar.py` | La única operación que escribe: descarga paginada a disco. |
| `domain/agregacion.py` | Cuántos grupos hay de verdad. Lo usan las seis herramientas que agrupan; existe porque el mismo error apareció seis veces por separado. |
| `domain/empresas.py` | RUES y Supersociedades: matrícula, establecimientos, estados financieros y ranking. |
| `domain/integridad.py` | Las cinco fuentes de sanciones, y las cifras que explican por qué tres de ellas no sirven para lo que parece. |
| `domain/dossier.py` | La vista por entidad en vez de por dataset: un documento contra siete fuentes, enumerando lo que miró. |
| `domain/educacion.py` | Saber 11 solo agregado, e indicadores municipales del MinEducación. |
| `domain/territorio.py` | Índice de Desempeño Municipal del DNP. |
| `domain/macro.py` | TRM por rango de vigencia y conversión a dólares, que no es deflactar. |

---

## El motor de privacidad

Tres de las fuentes traen personas identificadas: RUES (6.962.889 personas
naturales), SIRI (42.124 sanciones con nombre y cédula) y Saber 11 (7.109.704
registros individuales). `ErrorPrivacidad` estaba definido desde el principio y
ningún camino lo lanzaba, porque hasta 0.16.0 ninguna fuente lo necesitaba.

```mermaid
flowchart TD
    consulta["Una herramienta recibe una consulta"] --> agrega{"¿agrega?"}
    agrega -->|sí| libre["Pasa sin finalidad<br/>panorama · saber11"]
    agrega -->|no| clase{"clase_documento()"}
    clase -->|nit| juridica["Persona jurídica:<br/>pasa, y el NIT NO se enmascara"]
    clase -->|"cedula · indeterminado"| puerta{"¿finalidad declarada?"}
    juridica --> rues{"¿el RUES dice<br/>PERSONA NATURAL?"}
    rues -->|sí| puerta
    rues -->|no| salida
    puerta -->|no| bloqueo["[PRIVACIDAD]<br/>+ la alternativa agregada"]
    puerta -->|sí| redacta["Documentos enmascarados<br/>+ finalidad en el sobre"]
    redacta --> salida["Respuesta"]
    libre --> salida
```

Dos detalles que el diagrama hace evidentes:

- **La forma del número no es la última palabra.** `clase_documento` es una
  conjetura sobre el documento; lo que diga `categoria_matricula` en el RUES es
  un hecho. 517.527 personas naturales figuran con clase de identificación
  `NIT`, así que `co_empresas_ficha` y `co_dossier_documento` vuelven a pedir
  finalidad cuando la fuente contradice la conjetura — aunque el número
  pareciera un NIT de empresa.
- **`indeterminado` cuenta como persona.** Equivocarse hacia «es una empresa»
  expone a alguien; equivocarse hacia «es una persona» solo pide una finalidad
  de más.

La política se lee del entorno en **cada llamada**, no al importar, y cualquier
valor distinto de `permisiva` es `estricta`: un error de dedo del operador tiene
que fallar hacia el lado que protege. Ninguna herramienta recibe un parámetro
que afloje la política, de modo que ningún prompt puede pedirlo.

**Lo que no hace:** no anonimiza. Enmascarar un documento no impide
reidentificar a alguien cuyo nombre, cargo y municipio van en la misma fila.
Sirve para que el número no quede escrito en un historial de conversación, que
es un riesgo distinto y real.

---

## El total de una respuesta compuesta

`Total` existe para que no se pueda afirmar un total sin declarar su
procedencia, y funcionó: el defecto de `len(filas)` dejó de poder escribirse en
una consulta. Pero quedaba una vía, y 0.16.0 la encontró cuatro veces.

Cuando una respuesta junta **varias** consultas, cada una con su propio
`$limit`, `Total.completo(len(filas))` vuelve a ser una afirmación sin
comprobar — y cuesta más verla, porque cada consulta por separado parecía caber
y la que se pasó queda escondida dentro de la suma. Pasó en la ficha de empresa,
los estados financieros, el screening y las sanciones de contratación.

`Total.union` recibe los pares `(devueltos, límite)` y decide: si **ninguna**
llenó el suyo, no había más en ninguna fuente y la suma es exacta; si alguna lo
llenó, el total no consta. Es el mismo patrón de `cupo_entero`, aplicado a la
forma compuesta: **el constructor que se usaría por descuido decide él, en vez
de aceptar el número que alguien habría puesto.**

Lo destapó `tests/test_invariantes.py`, que obliga a clasificar cada herramienta
nueva. Al clasificar las quince, cuatro no pasaron.

---

## El ciclo de vida de una consulta

Lo que pasa entre que una herramienta pide datos y el cliente recibe la
respuesta. Las secciones siguientes explican cada pieza por separado; esto es
cómo encajan.

```mermaid
flowchart TD
    inicio["Una herramienta pide datos"] --> l1{"¿está en L1?<br/>memoria · 15 min"}
    l1 -->|sí| sobre
    l1 -->|no| l2{"¿está en L2?<br/>disco · 24 h"}
    l2 -->|sí| sobre
    l2 -->|no| vuelo{"¿la misma petición<br/>ya está en vuelo?"}
    vuelo -->|sí| comparte["Espera ese resultado<br/>en vez de duplicar la petición"]
    comparte --> sobre
    vuelo -->|no| breaker{"¿circuito abierto<br/>para este host?"}
    breaker -->|sí| caida["FUENTE_CAIDA<br/>sin tocar la red"]
    breaker -->|no| cubeta["Token bucket · 5 req/s por host"]
    cubeta --> get["GET a datos.gov.co"]
    get --> resp{"código de respuesta"}
    resp -->|200| sobre
    resp -->|"202 · 429 · 5xx"| backoff["Backoff exponencial<br/>o Retry-After si la fuente lo manda"]
    backoff --> cubeta
    resp -->|"400 · 403 · 404"| tipado["VALIDACION · NO_ENCONTRADO<br/>el host respondió: NO cuenta para el breaker"]
    sobre["Sobre: filas · total · orden<br/>URL reproducible · advertencias"] --> cabe{"¿cabe en el presupuesto<br/>de tokens?"}
    cabe -->|sí| salida["markdown + contenido estructurado"]
    cabe -->|no| recorta["Recorta filas por búsqueda binaria<br/>y marca truncado: true"]
    recorta --> salida
```

Dos detalles que el diagrama hace evidentes y la prosa escondía:

- **Un 4xx no abre el circuito.** El host respondió, así que está vivo; una
  consulta mal escrita no puede dejar fuera de servicio a los demás.
- **El recorte por presupuesto ocurre después del sobre**, no antes. Por eso el
  `siguiente_offset` se calcula sobre lo que realmente se devolvió.
- **Lo que se mide para recortar es el sobre entero**, con su pie y sus avisos,
  no solo la tabla. Medir una parte y estimar el resto tenía un fallo circular:
  recortar añade el aviso de recorte, y ese aviso empujaba la respuesta por
  encima del presupuesto que el recorte acababa de imponer.

---

## El sobre

Toda respuesta lleva al pie los mismos metadatos, y son parte del contrato:

- **filas devueltas** y **total de coincidencias** — si `devueltos < total`, el
  sobre lo dice y advierte que no se concluya nada cuantitativo desde esas filas.
- **`origen_del_total`: cómo se supo ese total.** `contado` (lo contó la
  fuente), `cabia_entero` (devolvió menos de lo pedido, así que no había más) o
  `completo` (la colección no sale de una consulta con `$limit`). Está porque un
  entero desnudo no distingue «lo conté» de «supuse», y esa indistinción metió
  `total = len(filas)` en seis herramientas. Hoy el total es un `Total` que no
  se construye sin declarar su procedencia, así que la afirmación sin comprobar
  ya no se puede escribir. Si no consta, el campo no aparece y se advierte.
- **orden aplicado** — para que el resultado sea interpretable.
- **la URL exacta y reproducible** que produjo el resultado, sin el token. Para
  uso periodístico o de control fiscal, una cifra sin su consulta no sirve.
- **advertencias** — unidad de análisis, montos sin deflactar, coordenadas
  inutilizables, cadenas de atribución traducidas, alias caducos.

Cómo leerlo en la práctica, señal por señal:
[recetas](recetas.md#leer-el-sobre).

### Columnas dispersas

Socrata **omite los campos nulos** en vez de enviarlos vacíos, así que dos filas
del mismo dataset llegan con juegos de claves distintos. Las columnas de una
tabla se toman de la unión de todas las filas —y, cuando hay proyección curada,
en el orden curado—. Deducirlas de la primera fila perdía datos en silencio: un
contrato en `Borrador` sin `fecha_de_firma` a la cabeza borraba la fecha de las
once filas que sí la tenían.

### Paginación honesta

`siguiente_offset` se calcula sobre lo **realmente devuelto**, nunca sobre lo
descargado, y es `None` cuando no queda nada por ver. Nunca se anuncia un salto
que deje filas sin mostrar.

El orden estable es la otra mitad: si la página 1 no tiene `$order`, la página 2
no puede tenerlo, porque el orden natural de la fuente no está garantizado entre
peticiones. El adaptador fuerza `$order=:id` en toda consulta paginable a la que
no se le haya dado uno. **Se excluyen las agregadas** (`count`, `sum`,
`distinct`…): ahí no hay nada que paginar y Socrata rechaza ordenar por una
columna que no está en el `group by`.

---

## Presupuesto de tokens

`CO_PRESUPUESTO_TOKENS` (6000 por defecto) acota el tamaño de la respuesta. Si
no cabe, se recortan filas por búsqueda binaria hasta que quepa y se marca
`truncado: true` con instrucciones de qué hacer: refinar el filtro, contar en vez
de traer filas, o paginar. **Nunca hay truncamiento silencioso**, y nunca se
devuelven cero filas habiendo al menos una.

Contar no implica traer filas: `detalle="conteo"` ejecuta `count(*)` y cuesta
unos 200 tokens frente a los miles de un volcado.

La estimación es deliberadamente conservadora —3,5 caracteres por token— porque
el español acentuado y los nombres largos de entidades pesan más que el inglés.

**Lo que se mide es la respuesta completa**, con su pie: procedencia, URL
reproducible y advertencias cuentan, porque se envían. Durante un tiempo se midió
solo el cuerpo y se descontó el pie por aritmética, y no funcionó por un motivo
circular: recortar **añade** el aviso de recorte, así que ese aviso empujaba la
respuesta por encima del presupuesto que el recorte acababa de imponer. La
función que la búsqueda binaria evalúa es hoy exactamente la que se manda, de
modo que no queda reserva que pueda quedarse corta.

Es el mismo patrón que aparece en varios sitios del servidor: **cuando algo se
repite, casi siempre hay un cálculo intermedio donde debería haber una
medición.**

---

## Caché

| Nivel | Dónde | TTL por defecto | Para qué |
|---|---|---|---|
| L1 | Memoria | `CO_TTL_DATOS` = 900 s | Consultas repetidas en una sesión. |
| L2 | Disco (JSON) | `CO_TTL_METADATOS` = 86400 s | Esquemas y dominios categóricos. |

Más **deduplicación de peticiones idénticas en vuelo**: dos llamadas simultáneas
a la misma URL producen una sola petición.

La caché es *best-effort* y nunca *load-bearing*: si el disco falla, se sigue
sin ella. Los valores canónicos de las columnas categóricas viven en L2 porque
cuestan una consulta agrupada de varios segundos y cambian rarísimamente.

---

## Política HTTP

Ninguna fuente colombiana publica sus cuotas. El límite existe, simplemente no
se conoce, así que el servidor se autolimita a ciegas:

- **Token bucket por host**, `CO_REQ_POR_SEGUNDO` = 5.
- **Reintentos** con backoff exponencial y jitter, `CO_MAX_REINTENTOS` = 4.
  Reintentables: 202 —el «Request Processing» de Socrata para queries lentas—,
  408, 429, 500, 502, 503, 504. Un 4xx no reintentable se lanza de inmediato:
  reintentar solo amplifica el problema.
- **`Retry-After`** se respeta cuando la fuente lo envía, con tope de 60 s. Es la
  única cifra real frente a un backoff inventado.
- **Circuit breaker por host**: 5 ciclos fallidos abren el circuito 60 s. Un 4xx
  no cuenta como fallo del host —el host respondió—, así que una consulta mal
  escrita no abre el circuito.
- **Timeouts por perfil**: 90 s Socrata, 30 s ArcGIS, 45 s por defecto.

Con varios backends, el fallo parcial es el caso normal: si el IGAC cae, SECOP
sigue funcionando.

El cliente `httpx` se reconstruye si cambia el event loop. Un `AsyncClient`
queda atado al loop donde se creó, y `is_closed` no detecta que el loop murió:
hay que comparar el loop o la siguiente petición falla con «Event loop is
closed».

---

## Errores

Todos derivan de `CoDatosError` y llegan al cliente como `ToolError` con el
código entre corchetes, el mensaje y una sugerencia accionable. La regla es que
el modelo pueda **distinguir siempre «no hay resultados» de «la fuente falló»**.

| Código | Cuándo | Qué hacer |
|---|---|---|
| `VALIDACION` | Columna inexistente, `nivel` inválido, `valor_min` no numérico, o un 400 de la fuente. | Corregir la entrada; el mensaje lista lo válido. |
| `NO_ENCONTRADO` | El recurso no existe: dataset retirado, contrato inexistente, 403/404. | Buscar el ID por nombre en el catálogo. |
| `LIMITE_TASA` | HTTP 429. | Configurar `SOCRATA_APP_TOKEN`. |
| `FUENTE_CAIDA` | Error de red, respuesta no-JSON, circuito abierto, 5xx agotado. | Reintentar; otras fuentes siguen vivas. |
| `TIMEOUT` | Se agotó el tiempo. | Reducir el rango o añadir filtros: las agregaciones sin filtro hacen full scan. |
| `CONFIG` | 403 con token configurado: el token es inválido. | Verificar o quitar el token. |
| `PRIVACIDAD` | La consulta identifica a una persona natural y no se declaró `finalidad`. | Declarar la finalidad —preguntándosela al usuario, no suponiéndola— o usar la herramienta agregada que el propio error nombra. |

Un `FUENTE_CAIDA` **nunca** significa cero resultados, y cero resultados nunca
se presenta como fallo.

`ESQUEMA_CAMBIADO` y `FUERA_DE_JURISDICCION` están definidos pero **ningún
camino de código los lanza todavía**: pertenecen al guardarraíl de gestor
catastral, no implementado. `PRIVACIDAD` sí se lanza desde 0.16.0 — ver
[el motor de privacidad](#el-motor-de-privacidad).

---

## Comparación de nombres

La pieza menos obvia del servidor. Está explicada en
[el README](../README.md#cómo-se-comparan-los-nombres) y vive en
`core/texto.py` + `adapters/socrata.py`.

En resumen: las columnas categóricas de la fuente **conservan los acentos**, y
SoQL no tiene `unaccent()`. Para dominios enumerables se resuelve el término
contra los valores canónicos y se filtra con `in (...)`; para texto libre se
pliegan los acentos en el servidor con `replace()` anidado.

---

## Lo que todavía no hace

Ser explícito aquí evita que alguien dé por implementado lo que no está:

- **El presupuesto solo recorta el markdown**, y el `estructurado` va con las
  mismas filas ya recortadas: no hay una vía para recibir todas las filas en una
  sola respuesta. Para eso está `co_datos_exportar`, que pagina a disco.
- **Sin adaptador SDMX** (Banco de la República) ni **ArcGIS** (IGAC, MGN del
  DANE) con descubrimiento del corte vigente.
- **Sin tasas por habitante**: no hay población municipal total con fuente
  abierta, así que el servidor no puede dividir por nada. Declarado en
  `registry.SIN_FUENTE_ABIERTA`.
- **Sin deflactor**: no hay IPC con API abierta. `domain/macro.py` ofrece la TRM
  como segunda unidad y declara que no es lo mismo.
- **La degradación automática entre niveles de detalle** existe en
  `budget.siguiente_nivel` pero no se usa: hoy se recortan filas, no se baja de
  `completo` a `resumen`.
