# Referencia de herramientas

19 herramientas contra `datos.gov.co`, todas de solo lectura salvo
`co_datos_exportar`, la única que escribe.

Los parámetros y sus valores por defecto salen del esquema que el servidor
publica; los topes de `limite` los impone el servidor y **no son negociables
desde el cliente**.

Toda respuesta es markdown con el [sobre](arquitectura.md#el-sobre) al pie:
filas devueltas, total de coincidencias, orden aplicado y la URL reproducible.

Convenios que se repiten:

- **`detalle`** — `"conteo"` (solo el número, sin traer filas, ~200 tokens),
  `"resumen"` (campos curados del dataset) o `"completo"` (todas las columnas).
- **`offset`** — paginación. El sobre indica el `siguiente_offset` correcto; no
  lo calcules sumando el límite que pediste, porque el servidor pudo recortar.
- **Fechas** — siempre `YYYY-MM-DD`.
- **Nombres** — escríbelos con tilde o sin ella, es indiferente. Ver
  [cómo se comparan los nombres](../README.md#cómo-se-comparan-los-nombres).
- **`formato`** — `"tabla"` (por defecto) para leer, `"csv"` o `"json"` para
  extraer. El cuerpo sale en un bloque cercado y el sobre sigue debajo.
- **Contenido estructurado** — al margen del formato, TODA respuesta lleva
  `datos` y `_meta` por el canal estructurado del protocolo.

---

## Catálogo nacional

### `co_datos_buscar_datasets`

Busca conjuntos de datos oficiales en el catálogo.

| Parámetro | Tipo | Defecto | Notas |
|---|---|---|---|
| `consulta` | string | `""` | Texto libre. |
| `categoria` | string | `""` | Categoría del portal. |
| `entidad` | string | `""` | Sigla conocida o cadena de atribución. |
| `limite` | int | `20` | Tope 100. |
| `offset` | int | `0` | |

`entidad` acepta estas siglas y las traduce a la cadena de atribución literal
que exige Socrata: **DANE, CCE, MinDefensa, Fiscalía, MinTIC**. El facet solo
funciona con el literal completo —`attribution=DANE` devuelve cero— y cuando se
aplica la traducción el sobre lo advierte. Cualquier otro valor se pasa tal cual.

Por defecto solo devuelve `provenance=official`: `q=SECOP` sin filtrar trae 944
assets, en su mayoría vistas comunitarias obsoletas.

### `co_datos_describir_dataset`

Esquema **en vivo**: campo técnico, nombre legible, tipo y descripción.

| Parámetro | Tipo | Defecto |
|---|---|---|
| `dataset_id` | string | obligatorio |

Úsala antes de escribir cualquier filtro. Los nombres técnicos vienen truncados
y sin acentos: `valor_pendiente_de` es «Valor Pendiente de Amortizacion», y sin
el nombre legible el slug es indescifrable.

Advierte si el asset es una **vista derivada o comunitaria** en vez de la fuente
oficial, y añade la unidad de análisis y las notas curadas cuando el dataset
está en el registro.

Lanza `[NO_ENCONTRADO]` si el ID no existe: los IDs de Socrata rotan.

### `co_datos_consultar`

SoQL sobre cualquier dataset, con allow-list de columnas.

| Parámetro | Tipo | Defecto | Notas |
|---|---|---|---|
| `dataset_id` | string | obligatorio | |
| `seleccionar` | string | `""` | `$select` |
| `donde` | string | `""` | `$where` |
| `ordenar` | string | `""` | `$order`. Si se omite y la consulta es paginable, el servidor fuerza `:id`. |
| `limite` | int | `20` | Tope 200 con `resumen`, 20 con `completo`. |
| `offset` | int | `0` | |
| `detalle` | string | `"resumen"` | |
| `formato` | string | `"tabla"` | `tabla`, `csv` o `json`. |

Los identificadores citados en `seleccionar`, `donde` y `ordenar` se validan
contra el esquema vivo. Una columna inexistente se rechaza con `[VALIDACION]`
listando las válidas, en vez de dejar que Socrata devuelva un 400 opaco.

`detalle="conteo"` no descarga filas: solo ejecuta `count(*)`.

### `co_datos_agregar`

Agrupa del lado del servidor: devuelve grupos, no filas.

| Parámetro | Tipo | Defecto | Notas |
|---|---|---|---|
| `dataset_id` | string | obligatorio | |
| `agrupar_por` | string | obligatorio | Una o varias columnas separadas por coma. |
| `metricas` | string | `"count(*) as total"` | El orden se deriva del **primer alias**. |
| `donde` | string | `""` | |
| `teniendo` | string | `""` | `$having`: filtra **grupos** por su métrica. |
| `luego` | string | `""` | Segunda agregación sobre el resultado de la primera (`|>`). |
| `limite` | int | `20` | Sin tope propio. |
| `formato` | string | `"tabla"` | `tabla`, `csv` o `json`. |
| `grafica` | bool | `true` | Añade la columna de barras. Se ignora si `formato` no es tabla. |

El orden se toma del primer `as <alias>` de `metricas`: con
`sum(valor_del_contrato) as valor` ordena por `valor DESC`. Sin alias, ordena
por la primera columna del agrupamiento. Con `luego`, el orden se toma del
primer alias de `luego`: la segunda etapa no ve los alias de la primera.

Sin `donde` hace *full scan* y el sobre lo advierte: en datasets grandes puede
agotar el tiempo.

#### `luego`: agregar sobre los grupos

`count(*)` con `teniendo` cuenta **dentro** de cada grupo, nunca cuántos grupos
quedan. Son dos preguntas distintas y solo la primera tenía respuesta:

```python
# «cuántos contratos tiene cada persona que repite» — una fila por persona
agrupar_por="documento_proveedor", metricas="count(*) as n", teniendo="count(*) > 1"

# «cuántas PERSONAS repiten» — una sola fila, y hace falta `luego`
agrupar_por="documento_proveedor", metricas="count(*) as n", teniendo="count(*) > 1",
luego="count(*) as personas, sum(n) as contratos"
#   -> personas: 130.720   contratos: 293.546
```

La segunda etapa recibe como tabla el resultado de la primera: sus columnas son
los **alias** de `metricas` (`n`), no los campos del dataset. Referirse ahí a
`documento_proveedor` o a `valor_del_contrato` da un 400.

#### Cuántos grupos hay en realidad

`total_coincidencias` cuenta **grupos**, no las filas mostradas. Si la fuente
devolvió menos de `limite`, no hay más y el total es exacto sin petición extra;
si llenó el límite, se cuentan aparte anidando. Cuando la fuente no admite el
operador anidado el total sale **desconocido** y el sobre lo advierte: es
preferible a un número inventado que luego alguien cite.

Con `grafica` (por defecto activa):

```
co_datos_agregar(dataset_id="gdxc-w37w", agrupar_por="dpto", limite=6)
```

```markdown
| dpto | total | gráfica |
|---|---|---|
| ANTIOQUIA | 125 | ████████████████ |
| BOYACÁ | 123 | ███████████████▊ |
| CUNDINAMARCA | 116 | ██████████████▉ |
| SANTANDER | 87 | ███████████▏ |
| NARIÑO | 64 | ████████▎ |
| TOLIMA | 47 | ██████ |
```

La barra se calcula sobre el valor **crudo** del primer alias, antes de darle
formato: si se midiera sobre `$1.234` ya formateado, el separador de miles
falsearía la escala. Los bloques son de un octavo, así que 87 y 64 se
distinguen sin leer los números.

### `co_datos_serie`

Serie temporal sobre cualquier dataset.

| Parámetro | Tipo | Defecto | Notas |
|---|---|---|---|
| `dataset_id` | string | obligatorio | |
| `campo_fecha` | string | obligatorio | Debe ser de tipo `Calendar date`. |
| `metrica` | string | `"count(*) as casos"` | El nombre de la columna sale del alias. |
| `periodo` | string | `"anio"` | `anio`, `mes` o `dia`. |
| `desde` / `hasta` | string | `""` | `YYYY-MM-DD`. |
| `donde` | string | `""` | `$where` adicional. |
| `formato` | string | `"tabla"` | |
| `grafica` | bool | `true` | |

**Avisa cuando el último periodo está incompleto.** Consulta
`max(campo_fecha)` y compara: si la serie anual termina en un año cuyos datos
cortan en agosto, lo dice con la fecha exacta. Es lo que convierte «2026» en
una caída del 30 % que no existe. Y **no da falsa alarma**: si el último mes
cerró el día 31, se limita a informar del alcance.

**Rechaza las columnas de fecha que son texto.** En el Plan Anual de
Adquisiciones (`9sue-ezhx`) las cinco columnas de fecha son `Text`: agrupar por
periodo falla y `between` da resultados silenciosamente falsos. El error dice el
tipo real y remite al esquema.

### `co_datos_perfilar`

Retrato de una columna antes de fiarte de ella.

| Parámetro | Tipo | Defecto | Notas |
|---|---|---|---|
| `dataset_id` | string | obligatorio | |
| `campo` | string | obligatorio | |
| `donde` | string | `""` | Perfila solo el subconjunto que te importa. |

Devuelve, según el tipo de la columna:

- **Numérica** — rango, suma, media, **reparto por orden de magnitud** y qué
  parte de la suma aportan los diez valores mayores.
- **Fecha** — rango, y aviso si el último periodo está sin cerrar.
- **Texto** — los diez valores más frecuentes.

Siempre: filas totales, filas con valor y **nulas**. Socrata omite los campos
nulos en vez de mandarlos vacíos, así que esas filas ni siquiera traen la clave.

La comprobación que la justifica es la **concentración**: si unos pocos valores
dominan la suma, lo advierte. Sobre `valor_del_contrato` de SECOP II devuelve
que **diez filas de 5.958.553 aportan el 95,5 %** — el hallazgo que costó una
investigación entera, en una llamada.

---

## Contratación pública (SECOP)

### `co_secop_buscar_contratos`

Contratos de SECOP II (`jbjy-vk9h`, ~5,9 M filas).

| Parámetro | Tipo | Defecto | Notas |
|---|---|---|---|
| `entidad` | string | `""` | Texto libre sobre `nombre_entidad`. |
| `nit_entidad` | string | `""` | Se le quitan puntos y guiones. |
| `proveedor` | string | `""` | Texto libre. |
| `documento_proveedor` | string | `""` | Cédula o NIT; solo dígitos. |
| `departamento` | string | `""` | Dominio cerrado: se resuelve al valor canónico. |
| `modalidad` | string | `""` | Dominio cerrado. |
| `desde` / `hasta` | string | `""` | Sobre `fecha_de_firma`. |
| `valor_min` | number | `0` | Acepta `1000000`, `"1.000.000"` y `"$1.000.000"`. |
| `valor_max` | number | `0` | Tope por arriba. Sirve para dejar fuera los ~3.450 valores imposibles. |
| `detalle` | string | `"resumen"` | |
| `limite` | int | `20` | Tope 100. |
| `offset` | int | `0` | |
| `formato` | string | `"tabla"` | `tabla`, `csv` o `json`. |

Ordena por `valor_del_contrato DESC`. Sin filtros, el sobre avisa de que estás
viendo los registros de mayor valor del dataset completo, no una muestra.

Si `departamento` o `modalidad` no corresponden a ningún valor real de la
fuente, **no se consulta**: se devuelve cero explicando que el término no
existe. Un cero silencioso es indistinguible de «no hay datos».

Prefiere `nit_entidad` y `documento_proveedor` sobre los nombres: son exactos.

### `co_secop_buscar_procesos`

Procesos de contratación (`p6dx-8zbt`, ~9 M filas), adjudicados o no.

Mismos parámetros que `co_secop_buscar_contratos` salvo `proveedor`,
`documento_proveedor` y `valor_min`, que no aplican a un proceso. El filtro de
fecha va sobre `fecha_de_publicacion_del` y el de territorio sobre
`departamento_entidad`.

### `co_secop_detalle_contrato`

Ficha completa en una sola llamada: contrato, modificaciones y URL pública.

| Parámetro | Tipo | Defecto |
|---|---|---|
| `id_contrato` | string | obligatorio |

El identificador tiene la forma `CO1.PCCNTR.<n>`. Compone dos consultas en
paralelo (contrato + adiciones). **Si la consulta de adiciones falla, lo dice**:
no afirma que el contrato no tenga modificaciones.

Las modificaciones se llaman **Adiciones** en la fuente (`cb9c-h8sn`); buscar
«modificaciones» en el catálogo devuelve cero.

Lanza `[NO_ENCONTRADO]` si el contrato no existe.

### `co_secop_perfil_proveedor`

Totales agregados por contratista, no volcado de filas.

| Parámetro | Tipo | Defecto | Notas |
|---|---|---|---|
| `documento` | string | obligatorio | Cédula o NIT sin dígito de verificación. |
| `limite` | int | `20` | Tope 50 entidades contratantes. |

Devuelve número de contratos, valor total y desglose por entidad contratante
ordenado por valor.

Solo cubre SECOP II. Con cero resultados advierte que puede tratarse de un
proveedor presente únicamente en SECOP I, y apunta a `rpmr-utcd`.

### `co_secop_resolver_entidad`

Nombre coloquial → nombre canónico + NIT. **Úsala antes de filtrar por nombre.**

| Parámetro | Tipo | Defecto | Notas |
|---|---|---|---|
| `nombre` | string | obligatorio | Mínimo 3 caracteres. |
| `limite` | int | `10` | Tope 30. |

Tiene alias curados para **DANE, IGAC, ICBF, SENA, INVIAS, DIAN, ANLA, UNGRD**,
verificados contra la fuente y revalidados a diario por la suite de contrato.

Cuidado con la tentación de escribir la razón social «correcta»: varias
entidades se registran con su sigla y nada más —INVIAS y UNGRD figuran así—. Si
un alias curado deja de encontrar nada, el servidor **reintenta con lo que
escribiste** y avisa de que el alias está caduco.

**RTVC** no está en el dataset de contratos con ningún nombre; solo en SECOP
Integrado (`rpmr-utcd`), como `RADIO TELEVISION NACIONAL DE COLOMBIA.` —con
punto final—. La herramienta lo indica.

### `co_secop_agregar`

Totales de contratación por dimensión.

| Parámetro | Tipo | Defecto | Notas |
|---|---|---|---|
| `agrupar_por` | string | `"departamento"` | Lista cerrada, ver abajo. |
| `metrica` | string | `"valor"` | `"valor"` ordena por importe; cualquier otro valor, por conteo. |
| `entidad` | string | `""` | Filtra por `nombre_entidad`. |
| `desde` / `hasta` | string | `""` | Sobre `fecha_de_firma`. |
| `limite` | int | `20` | Tope 50. |
| `formato` | string | `"tabla"` | `tabla`, `csv` o `json`. |
| `grafica` | bool | `true` | Barras proporcionales a la métrica. |

`agrupar_por` admite exactamente: `departamento`, `entidad`, `modalidad`,
`proveedor`, `sector`, `tipo`, `estado`. Cualquier otro valor se rechaza con
`[VALIDACION]` y remite a `co_datos_agregar` sobre `jbjy-vk9h`.

Advierte siempre que los montos son **nominales y sin deflactar**: no compares
valores entre años distintos sin ajustar.

Y advierte, con las cifras del filtro que hayas pedido, cuántos contratos
superan el billón de pesos y qué parte de la suma representan. Sobre el dataset
completo, **9 contratos aportan el 94 %** de la suma y los 3.452 que pasan del
billón aportan el 99,99998 %.

Ojo: **filtrar por estado no arregla esto**. El 97 % de los atípicos está en
`Cancelado` o `Borrador`, pero los 83 que sobreviven siguen dominando el total.
Acota con `valor_max` en `co_secop_buscar_contratos`, o agrega sobre
`valor_pagado`, que en los atípicos es cero sin excepción.

---

## Geografía (DIVIPOLA)

### `co_geo_divipola`

Códigos, nombres y coordenadas. Es la clave de join universal del servidor.

| Parámetro | Tipo | Defecto | Notas |
|---|---|---|---|
| `consulta` | string | `""` | Nombre, con tilde o sin ella. |
| `codigo` | string | `""` | Código DIVIPOLA. |
| `nivel` | string | `"municipio"` | `departamento`, `municipio` o `centro_poblado`. |
| `con_coordenadas` | bool | `true` | |
| `limite` | int | `25` | Tope 200. |
| `offset` | int | `0` | |
| `formato` | string | `"tabla"` | `tabla`, `csv` o `json`. |

Los códigos son **texto con ceros a la izquierda** (`05`, `08`). Tratarlos como
enteros rompe todos los joins, y el sobre lo repite en cada respuesta.

Las coordenadas se sanean y se validan contra la caja envolvente del país; las
inutilizables se devuelven como `null` y se cuentan en el sobre.

Con `nivel="centro_poblado"`, `CM` = cabecera municipal y `CP` = centro poblado.

### `co_geo_cotejar_coordenadas`

Control de calidad entre las dos fuentes oficiales de coordenadas.

| Parámetro | Tipo | Defecto | Notas |
|---|---|---|---|
| `limite` | int | `15` | Discrepancias a mostrar. |

Compara la cabecera municipal de `xaxy-8nri` con el punto del municipio en
`gdxc-w37w` y reporta las diferencias mayores a ~1 km, ordenadas.

Una discrepancia grande **no implica que una fuente esté mal**: las áreas no
municipalizadas y los municipios con cabecera trasladada aparecen aquí de forma
legítima. Es un hallazgo sobre la calidad del dato oficial, no un error del
servidor.

---

## Criminalidad

23 datasets de **MinDefensa** con esquema común (`cod_muni`, `fecha_hecho`,
`cantidad`), verificados uno a uno contra la API. `delito` acepta cualquiera de
estas claves, con o sin acentos:

`abigeato`, `afectacion_fuerza_publica`, `delitos_ambientales`,
`delitos_informaticos`, `delitos_sexuales`, `extorsion`, `homicidio`,
`homicidio_transito`, `hurto_comercio`, `hurto_financieras`, `hurto_personas`,
`hurto_residencias`, `hurto_vehiculos`, `invasion_tierras`, `lesiones`,
`lesiones_transito`, `pirateria_terrestre`, `secuestro`, `terrorismo`,
`trata_personas`, `violencia_intrafamiliar`, `voladura_oleoductos`,
`voladura_puentes`.

Tres avisos van en **todas** las respuestas del módulo, y no son decorativos:

- **Son casos registrados, no delitos cometidos.** Una subida puede ser más
  denuncia y no más delito. El homicidio es el indicador menos sensible a eso.
- **Se suma `cantidad`, nunca se cuentan filas.** Un hecho puede tener varias
  víctimas: homicidio tiene 342.971 filas y 343.680 víctimas.
- **Cada dataset corta por su cuenta.** Se consulta `max(fecha_hecho)` y se
  avisa de que el último año está incompleto.

### `co_crimen_serie`

Serie temporal de un delito desde 2003.

| Parámetro | Tipo | Defecto | Notas |
|---|---|---|---|
| `delito` | string | obligatorio | Una de las claves de arriba. |
| `desde` / `hasta` | int | `0` | Años. `0` = sin límite. |
| `agrupar_por` | string | `"anio"` | `anio` o `mes`. |
| `formato` | string | `"tabla"` | `tabla`, `csv` o `json`. |
| `grafica` | bool | `true` | Barras proporcionales. |

Devuelve además el **máximo y el mínimo de la serie**. No es adorno: es lo que
impide citar un porcentaje sin ver contra qué año se mide.

### `co_crimen_por_municipio`

Municipios con más casos de un delito en un año.

| Parámetro | Tipo | Defecto | Notas |
|---|---|---|---|
| `delito` | string | obligatorio | |
| `anio` | int | obligatorio | |
| `limite` | int | `20` | Tope 100. |
| `departamento` | string | `""` | Dominio cerrado: se resuelve al valor canónico. |
| `formato` | string | `"tabla"` | |
| `grafica` | bool | `true` | |

Devuelve `cod_mpio`, la clave DIVIPOLA, para cruzar con geometría u otras
fuentes sin pasar por el nombre.

**Son conteos absolutos, no tasas.** La fuente no publica proyecciones
municipales de población —se buscaron, incluido el facet del DANE, y no están—,
así que la lista se parece mucho a una lista de municipios grandes.

### `co_crimen_comparar`

Varios delitos entre dos años, ordenados por variación.

| Parámetro | Tipo | Defecto | Notas |
|---|---|---|---|
| `anio_a` | int | obligatorio | Año base. |
| `anio_b` | int | obligatorio | Año contra el que se compara. |
| `delitos` | string | `""` | Lista separada por comas; vacío compara todos. Máximo 12. |
| `formato` | string | `"tabla"` | |

**El año base decide el titular**, y el sobre lo recuerda. El secuestro subió
259 % contra 2017 y bajó 67 % contra 2003: es la misma serie —2.121 casos en
2003, 195 en 2017, 701 en 2025—. Mira `co_crimen_serie` antes de citar un
porcentaje.

---

## Exportación

### `co_datos_exportar`

Descarga un filtro **entero** y lo escribe en disco. Pagina hasta agotarlo, así
que sirve para volúmenes que no caben en una respuesta.

| Parámetro | Tipo | Defecto | Notas |
|---|---|---|---|
| `dataset_id` | string | obligatorio | |
| `nombre_archivo` | string | obligatorio | Un **nombre**, no una ruta. |
| `donde` | string | `""` | `$where` |
| `seleccionar` | string | `""` | `$select` |
| `ordenar` | string | `""` | `$order` |
| `formato` | string | `"csv"` | `csv`, `json` o `parquet`. |
| `max_filas` | int | `50000` | Tope duro 200.000. |

**Es la única herramienta que escribe**, y está anotada con
`readOnlyHint: false` para que el cliente pueda pedir confirmación al usuario.

El fichero se escribe siempre bajo `CO_EXPORT_DIR` (por defecto
`~/colombia-datos-export`). `nombre_archivo` se reduce a un fichero plano: rutas,
`..` y caracteres raros se neutralizan. La extensión se corrige al formato.

`parquet` necesita `pyarrow`; sin él la herramienta lo dice con un
`[VALIDACION]` en vez de fallar de forma opaca. `csv` y `json` no necesitan nada.

El CSV lleva **BOM** para que Excel en Windows no destroce los acentos. Si lo
lees con pandas, usa `encoding="utf-8-sig"`.

Si se alcanza `max_filas` antes que el total, **el fichero queda incompleto y la
respuesta lo dice** con las dos cifras. El contenido estructurado trae `ruta`,
`filas`, `bytes`, `formato` y `completo`, para encadenar sin parsear la prosa.

Con cero filas no se crea ningún fichero, y se explica que es el filtro y no un
fallo de la fuente.

### `co_geo_limites`

Límites municipales o departamentales como GeoJSON, para dibujar mapas.

| Parámetro | Tipo | Defecto | Notas |
|---|---|---|---|
| `nivel` | string | `"municipio"` | `municipio` o `departamento`. |
| `codigo` | string | `""` | DIVIPOLA de 2 dígitos (departamento) o 5 (municipio). |
| `departamento` | string | `""` | Nombre, con tilde o sin ella. |
| `guardar` | string | `""` | Nombre de fichero: escribe un `.geojson` bajo `CO_EXPORT_DIR`. |

**La geometría va en el contenido estructurado**, no en el markdown: un polígono
no se lee en una tabla y llenaría el presupuesto de tokens. El cuerpo trae el
resumen —código, nombre y extensión de cada geometría—.

Por encima de **200 geometrías** hay que acotar o usar `guardar`. Sin filtro son
1.122 polígonos, que en una respuesta revientan al cliente.

Con `nivel="departamento"` agrupa los municipios de cada uno en un MultiPolygon.
**No es una disolución real**: fusionar los polígonos y borrar las aristas
internas necesitaría una librería de geometría. Para recortar, rellenar o
encuadrar es equivalente; si trazas el borde verás las divisiones municipales.
El sobre lo advierte.

#### De dónde sale, y por qué importa

**No hay endpoint oficial utilizable.** El servicio nacional del IGAC
—`atlas/politicoadministrativo`— devuelve HTTP 500 «Wait timeout» tanto en
MapServer como en FeatureServer; su carpeta `limites` solo tiene territorios
cedidos, y de las 952 capas de `carto` ninguna es municipal. `datos.gov.co`
tampoco los publica: buscar con `only=map` y `only=geo` devuelve cero.

Así que se usa una **réplica pública del Marco Geoestadístico Nacional 2018 del
DANE**, capa municipal política simplificada, configurable con
`CO_GEOMETRIA_URL`. Se descarga una vez y se cachea en disco 24 h, así que
después funciona sin red.

El adaptador **valida la forma antes de fiarse**: que sea un FeatureCollection,
que traiga ~1.122 municipios y que tenga `MPIO_CCNCT`. Si la réplica cambia,
falla con un mensaje claro en vez de dibujar un mapa con agujeros. Y hay tres
pruebas de contrato: una comprueba la réplica a diario, otra que los códigos
crucen con DIVIPOLA, y otra **vigila si el IGAC vuelve a responder** — el día que
lo haga, esto debería migrar a la fuente oficial.

Es un corte de **2018**: los municipios creados después no están. Falta Nuevo
Belén de Bajirá, que en DIVIPOLA sí existe.

**Está muy simplificada**: mediana de **10 vértices por municipio**, y el 48 %
tiene menos de diez. San Andrés son 5 puntos. Eso basta para colorear un mapa
nacional —el contorno del país se reconoce— pero **no sirve para medir áreas ni
para resolver si un punto cae dentro** cerca de un límite. Cada respuesta lo
advierte.

---

## Recursos MCP

| URI | Contenido |
|---|---|
| `co://secop/datasets` | Los 8 datasets de SECOP del registro, con su unidad de análisis y notas. |
| `co://secop/joins` | Joins verificados entre datasets. |
| `co://atribuciones` | Cadenas de atribución exactas que exige el facet de Socrata. |
