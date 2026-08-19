# Cómo trabajar en este proyecto

```bash
pip install -e ".[dev]"
pytest
```

## Las tres capas de prueba

| Capa | Fichero | Red | Para qué |
|---|---|---|---|
| Núcleo | `tests/test_core.py` | No | Sobre, presupuesto, coordenadas, HTTP, caché, formato. |
| Texto | `tests/test_texto.py` | No | Plegado y comparación de nombres, con las mediciones que justifican la estrategia. |
| Dominio y servidor | `tests/test_dominio.py`, `tests/test_servidor.py` | No | Filtros, proyecciones y herramientas, con la red simulada por `RedFalsa`. |
| Contrato | `tests/test_contrato.py` | **Sí** | Los supuestos sobre la fuente viva. Se pide con `pytest -m contrato`. |

`pytest` a secas excluye la suite de contrato (`addopts = "-m 'not contrato'"`).

### Qué significa que falle el contrato

**No es un bug del servidor.** Cada aserción de `test_contrato.py` corresponde a
una suposición sobre la que está construido el código. Si una deja de cumplirse,
el Estado cambió algo: el esquema, la convención de acentos, un ID de dataset o
el nombre con el que se registra una entidad. Hay que cambiar el código, no la
prueba.

Corre a diario en CI con `continue-on-error`, para que un cambio en
`datos.gov.co` no bloquee un PR que no tiene nada que ver.

## Convenciones

**Todo en español**, incluidos los nombres de funciones y variables. El dominio
es colombiano y los campos de la fuente están en español; traducir a medias
produce `get_contratos_por_departamento`, que no ayuda a nadie.

**Los docstrings explican por qué, no qué.** El *qué* se lee en el código. Lo
que no se lee es que `search_context` es obligatorio, que un registro de 8.161
trae separador de miles, o que expandir «INVIAS» a su razón social da cero. Esa
es la información que hay que dejar escrita, y preferiblemente con el número
medido al lado.

**Nada de conocimiento cableado sin verificar.** Todo lo que va a
`registry/datasets.py` se comprueba primero contra la API viva y se acompaña de
una prueba de contrato que lo revalide. Los IDs de Socrata rotan y los alias
caducan.

**Fixtures reales, con sus defectos.** `tests/fixtures.py` son respuestas
capturadas de la API tal cual: coma decimal, números como string, mojibake. No
se «limpian», porque el defecto es justamente lo que hay que probar. Una fixture
idealizada esconde el bug: el defecto de acentos sobrevivió a 54 pruebas porque
las fixtures tenían los acentos bien puestos.

## Añadir un dataset al registro

1. Verifícalo contra la API: que el ID exista, qué columnas tiene y **qué cuenta
   una fila** (la `unidad`). Sumar filas de datasets con unidades distintas es el
   error más caro que puede cometer el modelo.
2. Añádelo a `registry/datasets.py` con `campos_clave`, `campos_resumen` y las
   `notas` que expliquen sus trampas.
3. Añade la prueba de contrato que compruebe que sigue existiendo y que sus
   campos clave no desaparecieron.

Si el dataset pertenece a una familia —como los 37 de MinDefensa que comparten
esquema— **verifica que la unidad sea la misma antes de meterlos juntos**. Ahí
`ERRADICACIÓN` cuenta hectáreas y `HOMICIDIO` cuenta víctimas: el esquema
idéntico no garantiza que se puedan sumar. Y comprueba que no sean duplicados:
`HURTO A COMERCIO` y `HURTO A RESIDENCIAS` resultaron ser el mismo dato con dos
nombres.

## Añadir un filtro de texto

Decide primero si el campo tiene **dominio cerrado**:

- **Cerrado** (pocos valores distintos, como `departamento` o `modalidad`):
  añade la clave a `secop.CATEGORICOS` y se resolverá contra los valores
  canónicos. Exacto y rápido.
- **Abierto** (nombres de entidad o proveedor): usa `_filtro_texto`, que pliega
  los acentos en el servidor.

Nunca compares el término plegado contra la columna cruda: es de donde salió el
defecto que documenta `core/texto.py`.

## Antes de abrir un PR

```bash
pytest
```

Si tocaste algo que hable con la fuente, corre también:

```bash
pytest -m contrato
```

Y si añadiste una suposición nueva sobre la fuente, añade la prueba de contrato
que la vigile.
