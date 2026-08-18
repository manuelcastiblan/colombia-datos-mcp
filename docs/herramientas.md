# Referencia de herramientas

12 herramientas, todas de solo lectura (`readOnlyHint`), todas contra
`datos.gov.co`. Los parámetros y sus valores por defecto salen del esquema que
el servidor publica; los topes de `limite` los impone el servidor y **no son
negociables desde el cliente**.

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
| `teniendo` | string | `""` | `$having` |
| `limite` | int | `20` | Sin tope propio. |

El orden se toma del primer `as <alias>` de `metricas`: con
`sum(valor_del_contrato) as valor` ordena por `valor DESC`. Sin alias, ordena
por la primera columna del agrupamiento.

Sin `donde` hace *full scan* y el sobre lo advierte: en datasets grandes puede
agotar el tiempo.

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
| `detalle` | string | `"resumen"` | |
| `limite` | int | `20` | Tope 100. |
| `offset` | int | `0` | |

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

`agrupar_por` admite exactamente: `departamento`, `entidad`, `modalidad`,
`proveedor`, `sector`, `tipo`, `estado`. Cualquier otro valor se rechaza con
`[VALIDACION]` y remite a `co_datos_agregar` sobre `jbjy-vk9h`.

Advierte siempre que los montos son **nominales y sin deflactar**: no compares
valores entre años distintos sin ajustar.

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

## Recursos MCP

| URI | Contenido |
|---|---|
| `co://secop/datasets` | Los 8 datasets de SECOP del registro, con su unidad de análisis y notas. |
| `co://secop/joins` | Joins verificados entre datasets. |
| `co://atribuciones` | Cadenas de atribución exactas que exige el facet de Socrata. |
