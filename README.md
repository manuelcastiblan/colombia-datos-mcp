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
- Los acentos vienen destruidos en origen (`EJECUCIoN`): los filtros se construyen con `upper()` sin acentos.
- **Coordenadas:** en `xaxy-8nri` exactamente un registro de 8.161 —Medellín— trae separador de miles (`-75,581,775`), y `float(s.replace(",", "."))` **lanza `ValueError`** sobre él. `core/coords.py` aplica "la primera coma es el decimal" y valida contra la caja envolvente del país.
- Las "modificaciones contractuales" se llaman **Adiciones**; buscar "modificaciones" devuelve cero.

## Pruebas

```bash
pip install -e ".[dev]"
pytest            # 54 pruebas, sin red
```

Las fixtures son respuestas **reales** capturadas de la API el 18-ago-2026, con sus defectos intactos. Falta añadir la suite de contrato contra la API viva en CI diario: su fallo es la señal de que el Estado cambió el esquema.

## Estado y siguiente paso

Implementado: núcleo (sobre, presupuesto, caché de dos niveles, HTTP con autolímite y circuit breaker, errores, coordenadas), adaptador Socrata, y los módulos de catálogo, SECOP y DIVIPOLA.

Pendiente, en orden: adaptador SDMX para Banco de la República, adaptador ArcGIS (IGAC/DANE MGN) con descubrimiento dinámico del corte vigente, el motor de privacidad, y solo después los módulos de seguridad y DDHH.

Licencia MIT. Los datos son CC BY-SA 4.0: propaga la atribución.
