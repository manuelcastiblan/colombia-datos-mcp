# colombia-datos-mcp

Servidor MCP para datos públicos de Colombia. Esta es la **fase F0 + la mitad Socrata de F1** del diseño: núcleo completo, adaptador de Socrata, y 12 herramientas sobre catálogo nacional, SECOP y DIVIPOLA.

```bash
pip install -e .
colombia-datos-mcp                      # stdio
colombia-datos-mcp --http --port 8080   # streamable HTTP
```

Claude Desktop / Claude Code:

```jsonc
{ "mcpServers": { "colombia-datos": {
    "command": "colombia-datos-mcp",
    "env": { "SOCRATA_APP_TOKEN": "opcional" } } } }
```

**No requiere credenciales.** `SOCRATA_APP_TOKEN` es opcional; sin él Socrata aplica throttling por IP y el servidor lo advierte una vez en el sobre.

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

Más tres *resources*: `co://secop/datasets`, `co://secop/joins`, `co://atribuciones`.

## Qué hace distinto

**El contrato de respuesta.** Toda respuesta trae un sobre con filas devueltas, total de coincidencias, orden aplicado y **la URL exacta reproducible**. Si `devueltos < total`, el servidor lo dice y advierte que no se concluya nada cuantitativo desde esas filas.

**Presupuesto de tokens con degradación explícita.** Si la respuesta no cabe, se recorta y se marca `truncado: true` con instrucciones de qué hacer. Contar nunca implica traer filas: `detalle="conteo"` cuesta ~200 tokens.

**Paginación honesta.** `siguiente_offset` se calcula sobre lo realmente devuelto, nunca sobre lo descargado.

**Errores tipados.** `[VALIDACION]`, `[FUENTE_CAIDA]`, `[LIMITE_TASA]`… con sugerencia accionable. Una fuente caída nunca se confunde con cero resultados.

**Esquema en vivo, nunca cableado.** Las columnas se validan contra el esquema real; un campo inexistente se rechaza listando los válidos.

## Trampas de la fuente que el servidor absorbe

- `search_context` es obligatorio en la Discovery API o `categories`/`tags` devuelven **0 en silencio**.
- El facet `attribution` solo acepta la cadena literal completa. `attribution=DANE` da cero; hay que usar `Departamento Administrativo Nacional de Estadísticas - DANE, Bogotá D.C.` — con "Estadísticas" en plural, que no es el nombre real de la entidad.
- `$order` es obligatorio al paginar o se pierden o duplican filas.
- Los números llegan como string; los códigos DIVIPOLA son texto con ceros a la izquierda.
- Los acentos vienen destruidos en origen **solo en el texto libre** (`descripcion` trae `EJECUCIoN`). Las columnas **categóricas los conservan**: `departamento` es `Atlántico`, `nom_mpio` es `MEDELLÍN`. Plegar el término y comparar con `like` devolvía cero en silencio para 392 de 1.122 municipios, 12 de 33 departamentos y ~2,8 M de contratos. Ver *Cómo se comparan los nombres*.
- **Coordenadas:** en `xaxy-8nri` exactamente un registro de 8.161 —Medellín— trae separador de miles (`-75,581,775`), y `float(s.replace(",", "."))` **lanza `ValueError`** sobre él. `core/coords.py` aplica "la primera coma es el decimal" y valida contra la caja envolvente del país.
- Las "modificaciones contractuales" se llaman **Adiciones**; buscar "modificaciones" devuelve cero.

## Cómo se comparan los nombres

SoQL no tiene `unaccent()` y su `like` distingue acentos, así que la estrategia
se elige por la cardinalidad del campo:

| Caso | Estrategia | Por qué |
|---|---|---|
| Dominio enumerable (`departamento`, `modalidad`, municipios) | Se traen los valores canónicos (cacheados 24 h), se resuelve el término en Python y se filtra con `in ('Atlántico')` | Exacto y compara por igualdad: 1,7 s frente a 7-20 s |
| Texto libre (`nombre_entidad`, `proveedor_adjudicado`) | El plegado se hace **en el servidor**, con `replace()` anidado sobre la columna | No hay lista que enumerar; exacto y de coste constante en la longitud del término |

Un término categórico que no corresponde a ningún valor real **no se consulta**:
se devuelve cero diciendo que el término no existe en la fuente. Un cero
silencioso es indistinguible de «no hay datos».

## Pruebas

```bash
pip install -e ".[dev]"
pytest              # 80 pruebas, sin red
pytest -m contrato  # 11 pruebas contra la API viva (~80 s)
```

Las fixtures son respuestas **reales** capturadas de la API el 18-ago-2026, con sus defectos intactos.

La suite de contrato comprueba los supuestos sobre los que está construido el código —que DIVIPOLA y SECOP siguen acentuando, que SoQL sigue aceptando `replace()` anidado, que el registro envenenado de Medellín sigue ahí, que los IDs del registro no rotaron—. Corre a diario en CI y **su fallo no es un bug del servidor: es la señal de que el Estado cambió el esquema.**

## Estado y siguiente paso

Implementado: núcleo (sobre, presupuesto, caché de dos niveles, HTTP con autolímite y circuit breaker, errores, coordenadas), adaptador Socrata, comparación de nombres tolerante a acentos, y los módulos de catálogo, SECOP y DIVIPOLA. CI con pruebas sin red en Python 3.11-3.13 y la suite de contrato programada a diario.

Pendiente, en orden: adaptador SDMX para Banco de la República, adaptador ArcGIS (IGAC/DANE MGN) con descubrimiento dinámico del corte vigente, el motor de privacidad, y solo después los módulos de seguridad y DDHH.

Licencia MIT. Los datos son CC BY-SA 4.0: propaga la atribución.
