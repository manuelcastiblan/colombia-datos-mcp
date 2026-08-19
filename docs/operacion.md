# Operación y diagnóstico

## Comprobar que el servidor está vivo

```bash
claude mcp list
```

Debe aparecer `colombia-datos … ✔ Connected`. Para verlo por fuera del cliente
MCP:

```bash
colombia-datos-mcp --http --port 8080
```

## El servidor no recoge los cambios del código

**El síntoma más desconcertante del proyecto.** Editas el código, las pruebas
pasan, y el MCP sigue comportándose como antes.

Causa: el cliente MCP lanza el servidor como un proceso hijo de larga vida.
Python no recarga módulos en caliente, así que **un proceso arrancado antes de tu
cambio sigue ejecutando el código viejo indefinidamente**, incluso con una
instalación editable.

Cómo confirmarlo sin adivinar:

1. Mira la `Consulta reproducible` del sobre. Es el mejor delator, porque
   muestra el SoQL que el proceso generó de verdad. Si esperabas un
   `replace(replace(...))` y ves un `upper(campo) like '%…%'` plano, el proceso
   es anterior al arreglo del plegado de acentos.
2. Compara la hora de arranque del proceso con la de tu commit. `Get-Process`
   no sirve aquí: el ejecutable es `python.exe` y el nombre del servidor solo
   aparece en la línea de comandos, así que hay que preguntar por ella.

```bash
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name like '%python%'\" | Where-Object { $_.CommandLine -like '*colombia*' } | Select-Object ProcessId, CreationDate"
```

### Reiniciar la sesión NO basta

Es el error que más tiempo cuesta, porque parece que debería funcionar.
Verificado el 19-ago-2026: tras reiniciar la sesión del cliente, los PID eran
**los mismos de una hora antes** y las respuestas seguían sin un campo recién
añadido. Los procesos del servidor sobreviven al reinicio.

Lo que sí funciona es matarlos. El cliente levanta uno nuevo en la siguiente
llamada, ya con el código actual:

```bash
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name like '%python%'\" | Where-Object { $_.CommandLine -like '*colombia*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
```

**Salvo que hayas cambiado la firma de una herramienta.** Ahí sí hace falta que
el usuario reinicie la sesión, porque la *lista de herramientas* —los nombres y
parámetros que el cliente conoce— se negocia al conectar y no se renegocia.
Son dos cosas distintas y confundirlas manda a reiniciar cuando no hacía falta,
o a no reiniciar cuando sí:

| Qué cambiaste | Basta con matar el proceso | Hay que reiniciar la sesión |
|---|:---:|:---:|
| Contenido de las respuestas, avisos, formato | ✅ | |
| Lógica interna, corrección de un cálculo | ✅ | |
| Parámetros nuevos en una herramienta | | ✅ |
| Herramienta nueva, o renombrada | | ✅ |

### `pip install -e .` falla con «El proceso no tiene acceso al archivo»

En Windows, si el servidor MCP está corriendo, tiene abierto
`Scripts\colombia-datos-mcp.exe` y pip no puede reescribirlo:

```
ERROR: Could not install packages due to an OSError: [WinError 32] ...
  'colombia-datos-mcp.exe' -> 'colombia-datos-mcp.exe.deleteme'
```

**No suele ser grave.** El lanzador `.exe` es genérico y no depende de la
versión: si el resto de la instalación se completó, el paquete funciona. Verifica:

```bash
pip show colombia-datos-mcp
```

```bash
pip check
```

Si `pip show` no lo encuentra o `pip check` protesta, cierra el cliente MCP y
repite la instalación. Puede quedar un `~olombia_datos_mcp-*.dist-info` huérfano
en `site-packages`; borrarlo silencia el aviso de «invalid distribution».

## Throttling y token

Sin `SOCRATA_APP_TOKEN`, Socrata limita por IP y el servidor lo advierte una vez
en el sobre. Se nota en consultas seguidas y sobre todo en runners de CI, cuya IP
es compartida.

El token es gratuito y no da acceso a nada privado: solo separa tu cuota de la
del resto. Va por cabecera, nunca en la URL, así que no aparece en logs ni en la
consulta reproducible.

Un token **inválido** produce `[CONFIG]`, no degradación silenciosa: se distingue
de un 403 por recurso privado.

## Caché

| Nivel | Dónde | TTL |
|---|---|---|
| L1 | Memoria del proceso | `CO_TTL_DATOS` = 900 s |
| L2 | `CO_CACHE_DIR`, por defecto `~/.cache/colombia-datos-mcp` | `CO_TTL_METADATOS` = 86400 s |

En L2 viven los esquemas y los **dominios de las columnas categóricas**, que
cuestan una consulta agrupada de varios segundos.

Para forzar datos frescos, borra el directorio:

```bash
rm -rf ~/.cache/colombia-datos-mcp
```

Es útil cuando el Estado publica una corrección y no quieres esperar 24 h. La
caché es *best-effort*: si el disco falla, el servidor sigue sin ella.

## Consultas lentas o que expiran

El timeout contra Socrata es de 90 s, con hasta 4 intentos. Lo que expira casi
siempre son **agregaciones sin filtro** sobre datasets de millones de filas.

Órdenes de magnitud medidos sobre `jbjy-vk9h` (~5,9 M filas):

| Operación | Tiempo |
|---|---|
| `in ('Atlántico')` — igualdad sobre valor canónico | ~1,7 s |
| `distinct <columna>` | ~7 s |
| `replace()` anidado + `like` — texto libre | ~20 s |
| OR de varios `like` | >240 s, expira |

De ahí la regla de diseño: los campos de dominio cerrado se resuelven a
igualdad, y el plegado de acentos del texto libre se hace con `replace()`, no con
un OR de patrones.

Si algo expira: añade un filtro de fecha o de territorio, o cuenta primero.

## El transporte stdio es frágil

En modo stdio, **stdout es el canal del protocolo**. Cualquier `print` fuera del
protocolo lo corrompe. El servidor escribe su línea de arranque en stderr por eso,
y por eso mismo se corrigió el futuro con excepción sin recoger de la caché: el
`Future exception was never retrieved` de asyncio salía por stderr en cada fallo
cacheado.

Si añades diagnóstico, que vaya a stderr.

## Diagnosticar un resultado que no cuadra

En orden:

1. **Copia la `Consulta reproducible` y pégala en el navegador.** Muestra
   exactamente lo que se pidió. La mayoría de las sorpresas se explican aquí.
2. **Lee `devueltos` y `total`.** Si son distintos, estás viendo una parte y
   cualquier suma propia está mal.
3. **Comprueba el estado de los registros.** En SECOP, los contratos en
   `Borrador` están en el dataset, no tienen `fecha_de_firma` y suman en
   `sum(valor_del_contrato)`.
4. **Comprueba la unidad de análisis.** Un contrato no es un proceso y una
   adición no es un contrato.
5. **Si sospechas del esquema**, corre la suite de contrato:

```bash
pytest -m contrato
```

Su fallo indica que la fuente cambió, no que el servidor esté roto.

## Campos que faltan en una tabla

Socrata **omite los campos nulos** en vez de enviarlos vacíos, así que dos filas
del mismo dataset llegan con juegos de claves distintos.

El renderizador toma la unión de las claves de todas las filas, precisamente
porque fiarse de la primera perdía datos en silencio: un contrato en borrador sin
`fecha_de_firma` a la cabeza de la tabla borraba la fecha de las once filas que
sí la tenían. Si ves una celda vacía, ese registro no trae el campo — no es que
se haya perdido.
