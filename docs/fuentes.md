# Fuentes: datasets, unidades de análisis y joins

Lo que el servidor sabe de cada dataset vive en `registry/datasets.py`,
verificado contra la API el 18-ago-2026 y revalidado a diario por la suite de
contrato. Esta página es su lectura en prosa.

**Los IDs de Socrata rotan.** `6d52-qyqg` ya devuelve 403. Si uno deja de
responder, búscalo por nombre con `co_datos_buscar_datasets`; no lo des por
muerto.

## La unidad de análisis es lo primero

Cada dataset cuenta una cosa distinta, y sumar filas de dos de ellos produce
cifras sin significado. El servidor la repite en el sobre de cada respuesta por
esto mismo.

| Dataset | Una fila es… |
|---|---|
| `jbjy-vk9h` | un contrato |
| `p6dx-8zbt` | un proceso de compra |
| `cb9c-h8sn` | una modificación contractual |
| `qmzu-gj57` | un proveedor |
| `rpmr-utcd` | un contrato adjudicado |
| `f789-7hwg` | un proceso |
| `9sue-ezhx` | una línea del Plan Anual de Adquisiciones |
| `rgxm-mmea` | una orden de compra |
| `gdxc-w37w` | una entidad territorial |
| `xaxy-8nri` | un centro poblado |
| `vcjz-niiq` | un departamento |

Un proceso puede dar varios contratos, y un contrato puede tener muchas
adiciones: **26,1 M de adiciones para ~5,9 M de contratos**. Contar filas de
`cb9c-h8sn` no cuenta contratos modificados.

## SECOP

### `jbjy-vk9h` — SECOP II · Contratos Electrónicos

85 columnas, **~5,88 M filas**. Es el dataset central del servidor.

| Rol | Columna |
|---|---|
| Identificador | `id_contrato` (forma `CO1.PCCNTR.<n>`) |
| Entidad | `nombre_entidad`, `nit_entidad` |
| Proveedor | `proveedor_adjudicado`, `documento_proveedor` |
| Territorio | `departamento` |
| Modalidad | `modalidad_de_contratacion` |
| Fecha | `fecha_de_firma` |
| Valor | `valor_del_contrato` |
| Enlace | `proceso_de_compra`, `urlproceso` |

- `nit_entidad` es de tipo **number** aquí y **text** en `p6dx-8zbt`: no unir por
  tipo sin convertir.
- **Los contratos en estado `Borrador` están en el dataset.** No están firmados
  —no traen `fecha_de_firma` y su `valor_pagado` es 0— pero sí suman en
  `sum(valor_del_contrato)`. Si lo que quieres es contratación real, filtra por
  estado.
- `urlproceso` llega a veces como objeto JSON con clave `url`, no como cadena.

### `p6dx-8zbt` — SECOP II · Procesos de Contratación

**~9,02 M filas.** Procesos adjudicados y no adjudicados.

Ojo con los nombres: la entidad es `entidad` (no `nombre_entidad`), el
territorio es `departamento_entidad`, el valor es `precio_base` y la fecha es
`fecha_de_publicacion_del` — un slug truncado.

### `cb9c-h8sn` — SECOP II · Adiciones

**26,1 M filas.** Las modificaciones contractuales se llaman **Adiciones**:
buscar «modificaciones» en el catálogo devuelve cero. El join contra contratos
es 1:N y pesado.

Campos: `identificador`, `id_contrato`, `tipo`, `descripcion`, `fecharegistro`.

Sus campos de texto libre son los que **sí** traen el mojibake de origen
(`PRESTACIoN`, `EJECUCIoN`, `MaS`).

### `rpmr-utcd` — SECOP Integrado (I + II)

Solo adjudicados. La vista más simple para análisis que cruce las dos
plataformas. Columnas propias: `nombre_de_la_entidad`, `nit_de_la_entidad`,
`valor_contrato`, `fecha_de_firma_del_contrato`, `origen`.

Aquí viven entidades que no aparecen en `jbjy-vk9h`, como **RTVC**.

### Los demás

| ID | Qué es | Trampa |
|---|---|---|
| `qmzu-gj57` | Proveedores registrados | — |
| `f789-7hwg` | SECOP I · Procesos | Nombres de columna distintos de SECOP II |
| `9sue-ezhx` | Plan Anual de Adquisiciones | **Las columnas de fecha son `text`, no `calendar_date`: no se filtran con `between`** |
| `rgxm-mmea` | Tienda Virtual del Estado (TVEC) | El valor es `total` |

## DIVIPOLA

### `gdxc-w37w` — Municipios

**1.122 filas**: 1.103 municipios + 18 áreas no municipalizadas + 1 isla. No son
«1.122 municipios».

Campos: `cod_dpto`, `dpto`, `cod_mpio`, `nom_mpio`, `tipo_municipio`,
`longitud`, `latitud`.

- Está **atribuido a la Gobernación de Guainía**: es una republicación de
  DIVIPOLA, cuyo origen real es el DANE.
- `longitud`/`latitud` son **text con coma decimal**.
- Los nombres van en mayúsculas **con tildes**: `MEDELLÍN`.

### `xaxy-8nri` — Cabeceras y centros poblados

**8.161 filas**: 1.104 cabeceras municipales (`CM`) + 7.057 centros poblados
(`CP`). Atribución DANE, CC BY-SA 4.0, corte 30-dic-2024.

**Exactamente un registro —Medellín— trae separador de miles en la coordenada**
(`-75,581,775`), y `float(s.replace(",", "."))` lanza `ValueError` sobre él. Es
el caso que `core/coords.py` absorbe y que la suite de contrato vigila.

### `vcjz-niiq` — Departamentos

33 valores. Sin campos clave registrados: se usa como catálogo.

## Joins verificados

```mermaid
flowchart LR
    hgi6["hgi6-6wh3<br/>id_procedimiento"]
    p6dx["p6dx-8zbt<br/>Procesos de Contratación<br/>una fila = un proceso"]
    jbjy["jbjy-vk9h<br/>Contratos Electrónicos<br/>una fila = un contrato"]
    cb9c["cb9c-h8sn<br/>Adiciones<br/>una fila = una modificación"]
    rgxm["rgxm-mmea<br/>TVEC · órdenes"]
    usqp["usqp-5nsn<br/>orden"]

    hgi6 -->|"id_procedimiento = id_del_proceso"| p6dx
    p6dx -->|"id_del_proceso = proceso_de_compra"| jbjy
    jbjy -->|"id_contrato = id_contrato · 1:N pesado"| cb9c
    rgxm -->|"identificador_de_la_orden = orden"| usqp
```

Disponibles como recurso MCP en `co://secop/joins`. `usqp-5nsn` y `hgi6-6wh3`
aparecen solo como destino de join: no están en el registro con unidad de
análisis propia.

Fíjate en que **la unidad de análisis cambia en cada salto**: un proceso puede
dar varios contratos y un contrato varias adiciones. Son 26,1 M de adiciones
para ~5,9 M de contratos, así que contar filas después de un join no cuenta
contratos.

**DIVIPOLA es la clave de join universal** entre fuentes territoriales, y los
códigos son **texto con ceros a la izquierda** (`05`, `08`). Tratarlos como
enteros rompe todos los joins.

## Cadenas de atribución

El facet `attribution` de la Discovery API solo acepta el literal completo:
`attribution=DANE` devuelve cero. `co_datos_buscar_datasets` traduce estas
siglas, y el recurso `co://atribuciones` las expone.

| Sigla | Cadena literal exacta |
|---|---|
| `DANE` | `Departamento Administrativo Nacional de Estadísticas - DANE, Bogotá D.C.` |
| `CCE` | `Agencia Nacional de Contratación Pública - Colombia Compra Eficiente, Bogotá D.C.` |
| `MinDefensa` | `Ministerio de Defensa Nacional - MinDefensa, Bogotá D.C.` |
| `Fiscalía` | `Fiscalía General de la Nación, Bogotá D.C.` |
| `MinTIC` | `Ministerio de Tecnologías de la Información y las Comunicaciones - MinTIC, Bogotá D.C.` |

Fíjate en `Estadísticas` **en plural**: no es el nombre real de la entidad, pero
es el literal que exige el facet.

## Alias de entidad

`co_secop_resolver_entidad` traduce estas siglas a un fragmento que sí aparece
en `nombre_entidad` de `jbjy-vk9h`:

| Sigla | Fragmento |
|---|---|
| `DANE` | `DEPARTAMENTO ADMINISTRATIVO NACIONAL DE ESTADISTICA` |
| `IGAC` | `INSTITUTO GEOGRAFICO AGUSTIN CODAZZI` |
| `ICBF` | `INSTITUTO COLOMBIANO DE BIENESTAR FAMILIAR` |
| `SENA` | `SERVICIO NACIONAL DE APRENDIZAJE` |
| `INVIAS` | `INVIAS` |
| `DIAN` | `DIRECCION DE IMPUESTOS Y ADUANAS NACIONALES` |
| `ANLA` | `AUTORIDAD NACIONAL DE LICENCIAS AMBIENTALES` |
| `UNGRD` | `UNGRD` |

**INVIAS y UNGRD figuran con su sigla y nada más.** Expandirlas a su razón
social daba cero; es el error que la suite de contrato vigila a diario.
