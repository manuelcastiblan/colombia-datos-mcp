# Registro de cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [Sin publicar]

### El IGAC volvió, y la geometría se queda donde está

`test_el_servicio_oficial_del_igac_sigue_caido` llevaba meses pasando y el
05-nov-2026 falló: el servicio nacional del IGAC
`atlas/politicoadministrativo` dejó de devolver HTTP 500 y ahora contesta 200
con ArcGIS Server 11.3, «División Político-Administrativa» del Atlas de Colombia
Edición 2024. El README decía que el día que respondiera, la geometría debería
migrar. Respondió. **No migró**, y esta entrada es sobre por qué.

Lo que volvió es el documento de metadatos del servicio, no el dato. Sondeado
entero:

- **De sus seis capas ninguna es municipal**: transporte terrestre, distritos,
  capitales, áreas metropolitanas y `Departamento`. Los 1.122 polígonos
  municipales sobre los que se sostiene `co_geo_limites` no están ahí.
- **No expone `FeatureServer`**, que es la vía para consultar por atributo y
  traer GeoJSON paginado: la extensión no está instalada. Lo avisa con un HTTP
  200 y el error en el cuerpo.
- **Sus consultas son lentas y poco de fiar.** Volcar la capa departamental
  entera acertó 2 de 5 intentos secuenciales —33 MB en unos 9 s cuando salió— y
  paginar con `resultOffset` acertó 1 de 5, porque `resultOffset>0` no funcionó
  ni una vez. El resto murió con 503 «Wait timeout for the request exceeded» a
  los 60 s: el mismo error que documentaba el adaptador desde el principio,
  ahora envuelto en 503 en vez de 500. Y llega de dos formas según el formato
  —HTTP 200 con el error en el cuerpo si se pide `f=json`, 503 de verdad si se
  pide `f=geojson`—, lo que importa porque `core/http.py` juzga por el status.
- **Las capas municipales temáticas tampoco se pueden consultar.**
  `atlas/potmunicipal` (`COD_MPIO`, `NOM_MPIO`) y
  `ordenamientoterritorial/clasificacionsegunley617del2000` (`MpCodigo`,
  `MpNombre`) tienen los campos que harían falta y fallaron las tres formas de
  consulta —recuento, atributos sin geometría, dos rasgos con geometría— con el
  mismo 503, seis de seis, pedidas una a una con tres segundos entre ellas.
- **Y su capa departamental no habría servido de atajo**: campos
  `DeCodigo`/`DeNombre` en vez de los del MGN y nombres en Title Case. Pero el
  hallazgo que más caro habría salido es otro, y es el que habría pasado
  cualquier revisión: la capa trae **33 registros y DIVIPOLA tiene 33
  departamentos**, así que comparar totales —la comprobación que cualquiera
  escribiría— da la migración por buena. Los conjuntos no son el mismo: sobra
  «Area en Litigio Cauca - Huila» con código `00`, y **falta Bogotá D.C.
  (`11`)**, que para el IGAC es un distrito y no un departamento. La
  intersección son 32, así que unir por código habría dejado la capital del país
  sin contorno sin que ningún recuento chistara.
- Y un detalle que sale de comparar dos volcados de días distintos: **el orden
  de los registros no es estable** —`52` salió decimoséptimo en uno y último en
  el otro—, así que paginar esta capa perdería y duplicaría rasgos aunque el
  servicio respondiera siempre.

Escribir `adapters/arcgis.py` habría añadido una vía que gasta los 30 s del
perfil `arcgis` antes de caer a la réplica, que sirve el país entero en 0,9 s, y
habría puesto el nivel departamental en una fuente de 2024 incoherente con el
nivel municipal de 2018 — dos contornos que no encajan entre sí, en un servidor
cuya premisa es que todo se une por DIVIPOLA. Así que el adaptador no se
escribió y la decisión quedó documentada con los números delante.

### Cambiado

- **`adapters/geometria.py` dice la verdad de hoy.** Su docstring explicaba que
  el IGAC devuelve 500; ahora explica que responde y por qué sigue sin servir.
  La cadena `PROCEDENCIA`, que viaja al sobre de cada respuesta de
  `co_geo_limites`, decía «porque el servicio oficial del IGAC no responde» —una
  afirmación que había dejado de ser cierta— y ahora dice que no publica capa
  municipal en `atlas/politicoadministrativo`, y que las capas municipales
  temáticas de sus otros servicios no respondieron a ninguna de las consultas
  probadas. Acotar el servicio importa: el IGAC **sí** tiene capas municipales
  —temáticas, en otros servicios— y su capa departamental **sí** respondió dos
  veces, así que decir «no permite consultar» habría sido la clase de
  afirmación de más que este servidor existe para no hacer.
- **`_valida` distingue por qué se quedó corta la colección.** Antes, cualquier
  colección con menos de 1.000 rasgos culpaba a la réplica de haber cambiado de
  contenido. Con la capa del IGAC —33 rasgos y ninguno con los campos del MGN—
  eso mandaba a revisar donde no estaba el problema. Ahora, cuando además faltan
  los campos, el error dice que esos rasgos no son del MGN, los enumera y señala
  `CO_GEOMETRIA_URL`. El camino de la réplica truncada sigue igual.
- **La réplica dejó de ser «la fuente provisional» para ser lo que es.** No es
  un respaldo: es la única fuente de los 1.122 polígonos, y así se nombra en el
  README, en `docs/fuentes.md`, en `docs/herramientas.md` y en la prueba de
  contrato que la vigila.

### Añadido

- **`docs/fuentes.md` tiene por fin un apartado de geometría**, con los campos
  del MGN, los dos límites que hay que declarar al dibujar (corte de 2018,
  geometría simplificada) y la tabla de supuesto contra hallazgo del sondeo al
  IGAC.
- **Fixtures reales del IGAC en `tests/fixtures.py`** —documento de servicio,
  campos de la capa departamental, los tres primeros rasgos del único volcado
  que llegó a servir, las dos listas de códigos en el orden en que llegaron y
  los cuerpos de sus dos errores— con sus defectos intactos, el área en litigio
  incluida.
- **Diez pruebas sin red** en `tests/test_geometria.py` (15 -> 25 en el fichero). La que importa:
  apuntar `CO_GEOMETRIA_URL` a la capa del IGAC —que también es un
  FeatureCollection de polígonos, así que el cambio parece inocuo— se rechaza
  con un mensaje que nombra los campos que faltan, en vez de dejar pasar la
  colección para que `domain/geo.py` reviente luego con un `KeyError` ilegible.
  Otras fijan por escrito que los 33 del IGAC cuadran en total con los 33 de
  DIVIPOLA **sin ser el mismo conjunto**, y que su orden no es estable.

### Corregido

- **`test_el_servicio_oficial_del_igac_sigue_caido` se fue, habiendo cumplido.**
  Vigilaba la vuelta del IGAC y la detectó. En su lugar hay tres pruebas de
  contrato que comprueban los supuestos de verdad: que el servicio responde, que
  **sigue sin publicar capa municipal** —y el día que esa falle, es cuando toca
  escribir el adaptador— y que su capa departamental no ha adoptado los nombres
  del MGN. Son rápidas a propósito: solo piden metadatos, que el servicio sirve
  en menos de un segundo. Una aserción que tarda cinco minutos en fallar no sirve
  en CI.

## [0.16.0] — 2026-11-05

Registro mercantil, sanciones, educación, desempeño municipal y TRM: cinco
familias de fuentes nuevas y **el motor de privacidad**, que llevaba desde el
principio definido como error y sin implementar.

El criterio para elegir qué añadir fue el inventario de fuentes oficiales
colombianas que publica Croma. De sus 59 fuentes, la mayoría se consulta por
formulario web con captcha y queda fuera de un servidor que se define como «sin
credenciales». Pero sus tres piezas centrales —RUES, antecedentes de la
Procuraduría y estados financieros de Supersociedades— **están publicadas como
datasets abiertos en `datos.gov.co`**, así que se pueden servir sin pedirle una
llave a nadie. Verificado contra la API en vivo el 05-nov-2026.

### Añadido

**Motor de privacidad (`core/privacidad.py`).** `ErrorPrivacidad` existía en
`core/errors.py` desde el principio y ningún camino de código lo lanzaba, porque
hasta ahora ninguna fuente traía personas. Las nuevas sí: 6.962.889 de las
9.436.330 matrículas del RUES son de personas naturales, las 42.124 sanciones del
SIRI llevan nombre y cédula, y Saber 11 son 7.109.704 registros individuales con
estrato y escolaridad de los padres.

Tres reglas:

- **Agregar nunca pide permiso.** `co_integridad_panorama` y
  `co_educacion_saber11` responden sobre poblaciones y no pasan por el motor.
  Que el camino barato sea también el que no identifica a nadie es deliberado.
- **Identificar a una persona natural exige declarar `finalidad`**
  —investigación, periodismo, control fiscal o debida diligencia—, que viaja al
  sobre y queda en la respuesta: la consulta es auditable por quien la lea
  después. El error de bloqueo nombra siempre la herramienta agregada que
  responde la misma pregunta sin identificar a nadie, porque un bloqueo que no
  dice qué hacer en su lugar enseña a reintentar con otras palabras.
- **Quién relaja la política es el operador, no el modelo.** `CO_PRIVACIDAD` es
  variable de entorno y ninguna herramienta recibe un parámetro que la afloje,
  así que ningún prompt puede pedirlo. Un valor mal escrito cae del lado que
  protege.

Los números de documento salen enmascarados conservando los dos primeros y los
dos últimos dígitos, lo que deja comprobar que dos filas hablan de la misma
persona sin escribir el número. El NIT de una sociedad no se enmascara: es
información mercantil pública y ocultarlo dejaría la respuesta inútil para
cruzarla con SECOP.

**15 herramientas nuevas**, de 19 a 34:

| Familia | Herramientas |
|---|---|
| Empresas | `co_empresas_buscar`, `co_empresas_ficha`, `co_empresas_estados_financieros`, `co_empresas_ranking` |
| Cruzada | `co_dossier_documento` |
| Integridad | `co_integridad_screening`, `co_integridad_disciplinarias`, `co_integridad_panorama`, `co_integridad_sanciones_contratacion` |
| Educación | `co_educacion_saber11`, `co_educacion_indicadores` |
| Territorio | `co_territorio_desempeno` |
| Macro | `co_macro_trm`, `co_macro_convertir`, `co_macro_tasas` |

Y tres *resources*: `co://privacidad/politica`, `co://fuentes/familias` y
`co://sin-fuente-abierta`.

**`co_dossier_documento` es la vista que faltaba.** El servidor estaba
organizado por dataset, que es como están los datos, no como están las
preguntas: «qué publica el Estado sobre este NIT» exigía cinco llamadas y saber
de antemano en qué dataset mirar. El dossier las hace de una vez y, sobre todo,
**enumera lo que miró**. Su valor no está en lo que encuentra —muchas veces casi
nada— sino en que el alcance de la búsqueda quede escrito junto al resultado, de
modo que un cero se pueda interpretar. Cada bloque falla por su cuenta.

**`Total.union`** para las respuestas que juntan varias consultas con su propio
`$limit`. Ver más abajo: salió de un defecto.

**18 datasets nuevos** en el registro, con sus trampas verificadas, y
`SIN_FUENTE_ABIERTA`, que declara por escrito lo que el servidor no puede
responder y por qué.

### Corregido

**Cuatro herramientas nuevas afirmaban ser completas sin saberlo, y lo atrapó
la prueba de invariantes, no la revisión.** `co_empresas_ficha`,
`co_empresas_estados_financieros`, `co_integridad_screening` y
`co_integridad_sanciones_contratacion` declaraban `Total.completo(len(filas))`
sobre filas traídas con `$limit`: es exactamente el defecto que `Total` vino a
hacer inexpresable, reaparecido en la única forma que el tipo no cubría.

En una respuesta **compuesta** cuesta más verlo: cada consulta por separado
parecía caber, y la que se pasaba quedaba escondida dentro de la suma. Ahora hay
`Total.union`, que recibe los pares `(devueltos, límite)` de cada consulta y
declara el total desconocido si alguna llenó el suyo. El patrón se repite: donde
había un cálculo intermedio, tenía que haber una medición.

`tests/test_invariantes.py` hizo su trabajo dos veces: obligó a clasificar las
quince herramientas nuevas y, al clasificarlas, destapó el defecto en cuatro.

**El motor de privacidad bloqueaba la ficha de Bancolombia.** La primera
versión pedía `finalidad` en cuanto **una** matrícula del RUES dijera `PERSONA
NATURAL`, por quedarse del lado que protege. El efecto real fue dejar
`co_empresas_ficha` y `co_dossier_documento` inútiles para su caso central:
el NIT 890903938 tiene dos matrículas, la de Medellín como sociedad anónima y
**la de Cali clasificada como persona natural**, con la razón social del banco
escrita en la fila. Es un error de la fuente, no un caso límite.

Ahora las dos señales se cruzan en un sitio (`privacidad.resuelve_persona`):
manda `categoria_matricula`, salvo que el documento tenga forma inequívoca de
NIT de empresa —nueve dígitos empezando por 8 o 9, un rango al que la
numeración de cédulas no llegó nunca—. Y la discrepancia **no se resuelve en
silencio**: la fila se conserva y el sobre declara que la fuente la tiene mal
clasificada. Lo encontró la primera llamada contra la fuente viva; con red
simulada no se veía.

**Una columna duplicada en el `$select` tumbaba la ficha.** `campos_resumen`
del RUES ya trae `categoria_matricula`, así que concatenarle las columnas
extra la repetía y Socrata rechazaba la consulta entera con
`query.soql.invalid`. Una columna duplicada no es un aviso, es un 400, y la red
simulada no valida SoQL.

**El screening anunciaba «5 filas de 0 coincidencias».** Su respuesta son dos
tablas en una —cinco filas de resumen, una por fuente, más los detalles—, así
que contarlas juntas daba un pie verdadero por separado y absurdo leído
seguido. Ahora usa `mostrar_conteo=False`, como las otras respuestas donde «N
filas» no significa nada.

**Una fecha en formato colombiano se aceptaba como ISO.** `_normaliza_fecha`
partía por guiones y comprobaba que los tres trozos fueran numéricos, así que
`20-01-2024` pasaba, se mandaba a Socrata como si fuera ISO y volvía sin filas:
el usuario veía «sin TRM para esa fecha», un diagnóstico falso sobre la fuente
cuando el error estaba en la entrada. Ahora valida con `date.fromisoformat`, que
además rechaza los días que no existen.

**La conversión a dólares rompía el separador decimal.**
`f"{v:,.2f}".replace(",", ".")` convertía también el punto de los decimales, así
que 250.000,00 salía como «250.000.00» — la misma cifra leída como doscientos
cincuenta mil con dos decimales o como algo sin sentido, según quien lo lea.

**`ToolResult` dejó de importarse donde ya no está.** fastmcp 4 lo reexporta en
`fastmcp.tools` y el servidor lo pedía en `fastmcp.tools.tool`, así que con la
versión actual no arrancaba: `ModuleNotFoundError`. El `pyproject` pedía
`fastmcp>=2.0` y no acotaba por arriba. Ahora el import prueba las dos rutas.

### Trampas nuevas que el servidor absorbe

Cada una se verificó contra la fuente y tiene prueba de contrato:

- **El literal de persona jurídica del RUES lleva la `ó` acentuada**
  (`SOCIEDAD ó PERSONA JURIDICA PRINCIPAL ó ESAL`). Escribirlo con una `o`
  normal devuelve cero filas.
- **`clase_identificacion` no discrimina personas**: 517.527 personas naturales
  figuran con clase `NIT`. Si el motor de privacidad se hubiera apoyado en la
  clase, medio millón de personas habrían pasado por empresas. El discriminador
  fiable es `categoria_matricula`.
- **El NIT del RUES vive en dos columnas y a veces en ninguna.** En 485.630
  sociedades la columna `nit` está vacía y el número solo aparece en
  `numero_identificacion`: SECOLINSA S A S tiene estados financieros en
  Supersociedades y su `nit` en RUES está en blanco. Toda consulta por documento
  mira las dos.
- **`nit` es `text` en el RUES y `number` en los demás datasets.** La misma
  columna, el mismo nombre, dos tipos: sin comillas en el RUES la consulta falla
  con `type-mismatch`, y con comillas en los otros, también.
- **Los conceptos con tilde de los estados financieros no se pueden pedir por
  igualdad.** El byte guardado es el carácter de reemplazo U+FFFD, así que
  `concepto = 'Ganancia (pérdida)'` devuelve 0 filas habiendo 627.932. Se piden
  con `like` y un comodín de un carácter en el hueco.
- **Los importes del ranking son texto con signo de peso** («$ 100.59») y están
  en **billones**. `ingresos_operacionales::number` falla con `invalid input
  syntax for type numeric`, y ordenar por el texto tal cual es peor porque es
  silencioso: «$ 9.03» quedaría por encima de «$ 100.59». Hay que quitar el
  signo con dos `replace` antes de castear.
- **«10.000 Empresas más Grandes» son 50.000 filas**: 10.000 por año, de 2021 a
  2025. Sin fijar el año cada empresa sale cinco veces.
- **`periodo` en los estados financieros es relativo**, no un año: vale «Periodo
  Actual» o «Periodo Anterior» respecto al radicado. El año está en
  `fecha_corte`.
- **Una TRM rige varios días.** La del viernes vale sábado y domingo, y
  preguntar por `vigenciadesde = '2024-01-21'` —un domingo— devuelve cero
  habiendo tasa vigente. Se busca el rango que contiene la fecha.
- **`periodo` de Saber 11 mezcla dos poblaciones.** Los periodos acabados en 4
  son la aplicación masiva de octubre (~1,1 M de estudiantes) y los acabados en
  1 la de marzo (~15 mil, sobre todo repitentes y validantes). `max(periodo)`
  devolvía a veces la de marzo presentada como «el último año», que es un error
  de población, no de fecha.
- **Los nombres de campo del MinEducación tienen la tilde comida por el slug**:
  `a_o`, `deserci_n`, `poblaci_n_5_16`, `c_digo_municipio`.

### Tres fuentes que se exponen para poder decir que no sirven

Es lo contrario de lo que haría un catálogo comercial, y es el punto:

- **SECOP II «Multas y Sanciones» no es un registro de sanciones.** De sus 588
  filas, **533 son «Comentarios positivos»** y 55 negativos; y solo 145 están
  publicadas, frente a 379 a la espera de aprobación, 33 rechazadas y 31 en
  borrador. Es la tabla de retroalimentación de proveedores. Además,
  `as_codigo_proveedor_objeto` es un código interno de la plataforma, no el NIT,
  así que no se puede cruzar por documento.
- **SIRI casi no tiene contratistas.** De 42.124 sanciones, 26.091 son a
  miembros de la fuerza pública y 15.736 a servidores públicos; **18 a
  contratistas** y 8 a particulares. Para verificar a un proveedor del Estado,
  está vacío en la práctica.
- **La Responsabilidad Fiscal de la Contraloría tiene 60 filas** y está parada
  desde el 23-mar-2022. No es el Boletín de Responsables Fiscales: su cero no
  informa de nada.

Ninguna consulta de `domain/integridad.py` devuelve un cero desnudo. Cada
respuesta sin coincidencias lo dice con estas cifras, porque una tabla en blanco
se lee como una absolución y no lo es.

### Trece defectos que encontró una revisión externa del PR

Cuatro patrones, no trece despistes. Los cuatro consisten en lo mismo: la regla
se escribió en un sitio y la vía de acceso era otra.

**1. La política de privacidad vivía en la herramienta, no en la fuente.**
`co_datos_consultar` acepta cualquier `dataset_id`, así que pedir `iaeu-rcn6`
con `detalle="completo"` devolvía las 42.124 sanciones del SIRI con nombre y
cédula **sin finalidad ni enmascarado**, y `co_datos_exportar` escribía en disco
el microdato de Saber 11 fila por fila. El motor entero se eludía cambiando de
herramienta. Ahora `core/privacidad.py` declara `MICRODATO` —Saber 11, Pro y
TyT, nunca fila a fila por ninguna vía— y `PERSONALES` —RUES, SIRI, multas de
SECOP I, contadores y responsabilidad fiscal: filas solo con finalidad y
enmascaradas—, y las tres vías genéricas pasan por la misma puerta. Agrupar por
documento también: devuelve una fila por persona, así que no es agregar.

**2. El enmascarado cubría las celdas y no el texto.** La misma respuesta
ocultaba el documento en la tabla y lo escribía completo en el título del
dossier, en los avisos y en la consulta reproducible del pie. `etiqueta_
documento` y `redacta_consulta` lo cierran. La URL publicada deja de ser
ejecutable tal cual en una consulta nominal, y la respuesta lo advierte: se
conserva el dataset, el resto del filtro y la forma; se va el número, que lo
tiene quien preguntó.

**3. Decisiones por página donde el dato es por fila.** Una sola persona natural
en una página del RUES enmascaraba también los NIT de las sociedades que la
acompañaban, que son justo los que sirven para cruzar con SECOP; `redacta_filas`
acepta ahora un predicado por fila. Y una búsqueda de sanciones por nombre se
daba por jurídica sin mirar nada, publicando las cédulas de los contratistas
personas naturales de SECOP I: ahora se decide con los documentos que volvieron,
que es la regla de `resuelve_persona` otra vez.

**4. Cifras que afirmaban más de lo que se midió.**

- `Total.cupo_entero` no conocía el `offset`. Una página corta no dice que el
  total sea lo que trajo, dice que no hay nada **después**: con 25
  coincidencias, `offset=20` y `limite=20` el sobre anunciaba «5 fila(s) de 5
  coincidencias». `agregacion` ya lo corregía a mano en su propio sitio, y por
  eso el descuido reapareció en `buscar` y en `disciplinarias`; ahora el offset
  va al constructor. Una página vacía con offset no autoriza a afirmar nada.
- El dossier anunciaba «3 matrículas» con `limite=3`: el tamaño de la muestra
  presentado como el del documento. Dice «3 o más».
- **`en_ranking` se tragaba toda excepción y devolvía `""`**, así que `_seguro`
  nunca veía el fallo y el dossier publicaba «no figura» cuando la fuente había
  dado timeout: una ausencia atribuida a una fuente que no se pudo consultar,
  que es el error que este servidor está entero construido para no cometer. Ya
  propaga. La ficha, que sí quiere tolerancia, la pone en su propio llamador y
  **dice** que no pudo mirar, en vez de omitir la línea.

**Y tres consultas mal escritas, una de ellas grave:**

- **SIRI guarda el nombre en cuatro columnas y ninguna tiene el completo**, y se
  buscaba la cadena entera dentro de cada una: `nombre="ANA PEREZ"` no casaba
  con `primer_nombre="ANA"` ni con `primer_apellido="PEREZ"` y devolvía **cero**
  con la persona dentro del dataset. Un falso cero en una consulta de
  antecedentes es el peor fallo posible aquí. Ahora cada término se exige en
  alguna de las cuatro columnas: contra la fuente viva, «ANA PEREZ» pasó de 0 a
  **29 coincidencias**.
- El rango de TRM filtraba por `vigenciadesde >= desde` y perdía el intervalo
  que ya regía al empezar: `desde=hasta=2024-01-21` devolvía vacío aunque la
  TRM de ese día es la certificada el 20 y vigente hasta el 22, que
  `trm(fecha=…)` sí encontraba. La misma fecha daba dos respuestas según por
  dónde se preguntara. Ahora se seleccionan los intervalos que **se solapan**.
- `co_macro_tasas` exigía `desde` o `descripcion` comprobando que hubiera
  salido un filtro, y `hasta` producía filtro: un límite superior posterior al
  último reporte no descarta nada, así que la agregación recorría los 2,1 M de
  filas. Es la consulta que la validación existía para evitar.
- El ranking devolvía el NIT como `"899999068.00"` —la fuente lo sirve así
  aunque esté declarado `Number`—. Encadenado a `co_empresas_ficha`,
  `solo_digitos` lo convertía en `89999906800` y consultaba otro documento: la
  ficha de Ecopetrol salía vacía sin que nada avisara de por qué.

26 pruebas nuevas en `tests/test_revision_pr1.py`, una por defecto, y las dos
tablas de la revisión comprobadas contra la API viva.

### Una nota del registro que caducó, y la suite de contrato lo destapó

**«HURTO A COMERCIO» y «HURTO A RESIDENCIAS» ya no son el mismo dato.** Lo
fueron: hasta agosto de 2026 los dos servían 613.637 filas y 614.669 casos,
idénticos año por año, y las notas del registro decían «son el mismo dato, nunca
los sumes». MinDefensa recargó sus **23** datasets de criminalidad el
**21-oct-2026** —`rowsUpdatedAt` lo marca en los 23— y la duplicación se
deshizo: hoy son 682.898 casos en comercio contra 619.378 en residencias, sin un
solo año en que coincidan.

Nadie tocó una línea de código y la advertencia pasó de verdadera a falsa. Eso
es lo que hace la suite de contrato: la prueba que comprobaba que los dos
totales eran idénticos empezó a fallar. Y una nota del registro va al sobre de
**cada** consulta
vía `_avisos_dataset`, de modo que el servidor llevaba desde octubre diciéndole
al modelo que no sumara dos series distintas. Una advertencia caducada llega con
el mismo rango que la cifra, y es peor que ninguna.

**El que estaba mal era `HURTO A COMERCIO`.** No lo dice la fuente —la recarga
no viene con changelog— sino el crecimiento de cada serie entre el recuento del
18-ago-2026 y el del 05-nov-2026: los otros 22 datasets subieron menos del 4 %
(homicidio, +0,65 %; residencias, +0,77 %), lo que cabe en tres meses de
registros nuevos, y comercio subió **11 %**. Ninguna acumulación explica eso; sí
lo explica que la serie sea otra. Así que hasta octubre `HURTO A COMERCIO`
servía los hurtos a residencias, y **cualquier cifra de hurto a comercio
publicada antes del 21-oct-2026 es en realidad de residencias**.

**La trampa que queda viva es otra: la serie se rompe en 2017.** Comercio pasa
de 23.060 casos en 2016 a 60.311; residencias, de 24.191 a 46.550. Más que se
duplican las dos en un año, mientras el homicidio se queda plano (12.045 y
11.957) y los vehículos suben 6 %: el salto es de esos dos datasets, no del
registro. «Los hurtos a comercio se triplicaron desde 2016» mide la ruptura, no
el delito. Las notas nuevas lo advierten en cada consulta.

- El contrato que comprobaba la identidad ahora comprueba lo contrario **año por
  año**, no por totales: dos series podrían diferir en el total por filas nuevas
  y seguir siendo la misma.
- Hay contrato nuevo que vigila el salto de 2017 —y que el homicidio siga plano
  en esos años, que es lo que lo atribuye a los datasets y no a la fuente—. Si
  algún día se alisa, las notas sobran.
- `test_crimen.py` exige ahora que las dos notas lleven la fecha de la
  corrección y la ruptura, y que no digan «nunca los sumes».
- Los 23 totales de la tabla de `docs/fuentes.md` se recontaron el 05-nov-2026.
  Todos habían subido; la serie llega al 30-sep-2026. Las cifras citadas en
  prosa —homicidio, 345.195 filas y 345.917 víctimas; violencia intrafamiliar,
  675.813 y 1.651.032— se actualizaron con ellos, y donde el README y
  `docs/recetas.md` fijaban el corte en «finales de julio de 2026» ahora dicen
  que cambia con cada recarga: una fecha escrita a mano al lado de un
  `max(fecha_hecho)` que se consulta en vivo solo puede envejecer mal.

### Lo que sigue sin tener fuente abierta

Declarado en el *resource* `co://sin-fuente-abierta` y en el playbook, para que
la respuesta correcta sea decirlo y no buscar un sustituto que no lo es:

- **No hay población municipal total, así que no hay tasas por 100.000
  habitantes.** El DANE no publica las proyecciones por API: bajo su atribución
  en `datos.gov.co` hay exactamente dos datasets, los dos de DIVIPOLA, y el
  resto son republicaciones de alcaldías sueltas. Lo más cercano es la población
  de 5 a 16 años del MinEducación, que no sirve de denominador. Hay prueba de
  contrato que vigila si eso cambia.
- **No hay IPC, así que los montos siguen sin deflactar.** Ni el DANE ni el
  Banco de la República publican sus series por API REST abierta. `co_macro_
  convertir` da una segunda unidad verificable —dólares de la fecha del
  contrato— y la respuesta aclara que convertir no es deflactar.
- **No hay procesos judiciales, Registraduría, RUNT ni SIMIT.**

## [0.15.0] — 2026-10-28

Cuatro arreglos salidos de auditar el servidor con él mismo: tres se notan en
cada respuesta y el cuarto quita un desvío que se repetía.

### Corregido

**`detalle="resumen"` no resumía nada fuera del registro.** Sin campos curados,
el nivel solo cambiaba el tope de filas: dos filas del Universo de entidades del
DAFP llegaban con sus 24 columnas, un blob JSON de dirección, fax, correo,
teléfono y el nombre del representante legal. Unos 1.200 tokens, y datos
personales de alguien concreto arrastrados a la conversación por una pregunta
sobre el orden administrativo de la entidad.

Ahora, cuando el dataset no está en el registro y no se pidieron columnas, el
resumen es heurístico: fuera las columnas vacías en todas las filas, los blobs y
las de contacto o datos personales, y el sobre declara cuántas columnas quedaron
de cuántas. Con `seleccionar` explícito no se toca nada —quien pide columnas ya
eligió— y `detalle="completo"` sigue trayendo todo.

**El diagnóstico de la fuente llegaba ilegible.** Un 400 de Socrata se recortaba
en crudo a 300 caracteres, así que el modelo recibía `{"message":"Query
coordinator error: …` con las comillas escapadas, el SQL repetido dentro —que ya
conoce, lo acaba de escribir— y el corte justo donde empezaba la explicación.
Ahora se parsea el JSON, se tira el eco de la consulta y se conserva el código de
error, que es lo que dice qué arreglar.

**La frescura que publicaba el sobre no era la de los datos.** `updatedAt` del
catálogo es el **máximo** entre la fecha de los datos y la de la ficha, así que
un retoque de metadatos se presentaba como actualización. Verificado el
28-oct-2026: los indicadores de mortalidad del MinSalud (`4e4i-ua65`) decían
«actualizado 2026-09-19» con los datos parados desde **2022-08-02**; la Medición
del Desempeño Municipal del DNP, desde 2022-02-21; y hasta DIVIPOLA figuraba al
día con datos de enero de 2025. Ahora el sobre publica `data_updated_at`, y
`co_datos_describir_dataset` avisa cuando la ficha se tocó después que los datos.

La clave de caché del esquema lleva ahora **versión de forma** (`esquema/v2`). El
esquema se guarda 24 h en disco, así que al añadirle un campo las entradas viejas
seguían sirviendo la forma anterior: el arreglo de la frescura no se notaba hasta
el día siguiente, y en la primera prueba contra la fuente viva salió la fecha
antigua. Hay que subirla cada vez que cambie la forma del diccionario.

**El pie mostraba la marca de tiempo entera donde iba una fecha.** Las fechas del
catálogo traen zona —`2026-08-17T09:22:03.000Z`— y esa `Z` rompía los cuatro
formatos de `fmt.fecha`, que devolvía el texto sin tocar.

**Un dominio categórico que no responde ya no tumba la respuesta.** Resolver un
término contra los valores reales de una columna cuesta un `distinct`, y el de
`tipo_de_contrato` —5,9 M filas— agotó los 90 s del cliente: la consulta entera
moría. Ahora esa enumeración lleva su propio plazo (`CO_TIMEOUT_DOMINIO`, 20 s) y
al vencer degrada a comparación de texto **diciéndolo**, porque entonces el
filtro puede casar valores vecinos y un cero ya no demuestra que el término no
exista. Afectaba también a filtros que ya existían: departamento y modalidad en
las búsquedas de SECOP, y departamento en criminalidad.

### Añadido

**`ordenar` en `co_datos_agregar`.** El orden era siempre la métrica
descendente, que para una serie es lo contrario de lo que se quiere: agrupada por
mes salía ordenada por el conteo y no había manera de pedirla cronológica. Puede
citar un alias de la primera etapa, y por eso no se valida contra el esquema,
donde el alias no existe.

**`nit_entidad` y `tipo` en `co_secop_agregar`.** La pregunta más frecuente
—cuánta prestación de servicios firmó esta entidad— obligaba a bajar a la
herramienta genérica y escribir el `$where` a mano. El NIT se busca en sus dos
formas y el tipo se resuelve contra los valores reales de la columna: si el
término no existe en la fuente, el cero viene explicado.

## [0.14.0] — 2026-10-08

Todo lo de esta versión salió del mismo sitio: un análisis de contratación por
nivel de gobierno en el que hubo que **salirse del servidor** y golpear la API
con scripts. Cada cosa que obligó a hacerlo es un arreglo aquí.

### Añadido

**Exportar una agregación entera.** `co_datos_exportar` acepta `agrupar_por`,
`metricas` y `teniendo`: escribe la tabla de grupos en disco en vez de las filas.
Era el hueco que forzaba el desvío. Una agregación con más grupos que `limite` no
se podía ni paginar ni volcar —pedirla en CSV no evita el presupuesto de tokens,
porque el recorte se aplica después—, así que una tabla de 2.000 organismos
contratantes había que reconstruirla a mano. Se pagina por las claves de grupo,
que es el único orden estable, y si el conteo previo de grupos falla se pagina
hasta agotar la fuente y la respuesta dice que la garantía es esa.

**`offset` en `co_datos_agregar`.** Los grupos ya se pueden paginar. El orden
lleva ahora las claves de grupo como desempate: dos grupos empatados en la
métrica salen en cualquier orden, y sin desempate la página 2 repite unos y se
salta otros —el mismo fallo que el adaptador ya evitaba en las consultas sin
agrupar. Con `offset`, el total deja de ser `len(filas)`: cuenta también lo que
quedó detrás.

**Expresiones en `agrupar_por`.** `date_trunc_ym(fecha_de_firma) as mes` o
`upper(nombre_entidad)` ya agrupan. Antes `agrupar_por` se partía por comas y se
contrastaba entero contra el esquema, así que la expresión se rechazaba como
«columna inexistente» y la única salida era `co_datos_serie`, que solo agrupa
fechas. La expresión va al `$group` tal cual y al `$select` con alias, porque el
nombre que Socrata le da a una expresión sin alias no es predecible; las columnas
citadas dentro de ella sí se validan.

**`core/nit.py`:** dígito de verificación con el algoritmo de la DIAN.

### Corregido

**Un NIT filtraba la mitad de la entidad.** En SECOP el mismo NIT está cargado
con y sin dígito de verificación: `899999061` y `8999990619` son Bogotá;
`899999034` y `8999990341`, el SENA. Son 92 parejas que tocan el 28,9 % de los
contratos de prestación de servicios de 2026. `nit_entidad = '899999061'` dejaba
fuera, en silencio, los organismos cargados con la otra forma. Ahora las
herramientas de SECOP buscan ambas y lo advierten, y `co_secop_resolver_entidad`
avisa cuando dos NIT de su propia tabla son el mismo número.

Las cédulas no se expanden nunca: a una de cada once cédulas de diez dígitos le
cuadra el dígito de verificación por azar, y plegarla a nueve traería los
contratos de otra persona. Solo se tocan los números que empiezan por 8 o 9.

**Las URL se cortaban a 70 caracteres.** `urlproceso` —el enlace de verificación
pública de un contrato, lo único que permite comprobar una cifra en la fuente—
salía truncado y por tanto inservible, y no solo en la tabla: el contenido
estructurado recibe el mismo valor ya formateado, así que el enlace se perdía
también para quien lo leyera por programa. `recorta()` deja pasar las URL
enteras.

**El tope de `limite` se aplicaba en silencio.** Pedir 40 filas con
`detalle="completo"` devolvía 20 y el sobre decía `truncado: false`, que es justo
lo contrario de lo que había pasado. Ahora lo advierte con las dos cifras y el
`offset` siguiente.

**Documentación con una afirmación falsa.** `docs/recetas.md` decía que agrupar
por `nit_entidad` da un «piso» del conteo de contratistas multi-entidad. No lo
da: funde organismos en un sentido, pero los NIT duplicados inflan en el otro.
El README gana además la trampa de `orden`/`rama`, que no son fiables para
filtrar por nivel de gobierno —el ITM, municipal, figura como nacional en sus
15.482 contratos de 2026— y remite al Universo de entidades del DAFP.

## [0.13.0] — 2026-08-29

### Corregido

**Una serie diaria terminaba en un desplome inventado.** Pedir la contratación
día a día devolvía 1.194 contratos el último día frente a los ~4.500 de un lunes
normal, y el servidor se limitaba a decir «los datos llegan hasta 2026-08-24».
No era una caída: era que la carga se había quedado a medias justo ahí.

El fallo era conceptual. `cerrado()` preguntaba si el **calendario** había
cerrado, y un día siempre cierra. Pero la pregunta que importa es si terminó la
**carga**, y eso no se puede demostrar nunca: el periodo donde cortan los datos
es exactamente donde la fuente dejó de publicar. Para años y meses la primera
pregunta implica la segunda; para días, no.

Ahora son tres estados con tres tonos:

| Estado | Cuándo | Qué dice |
|---|---|---|
| Incompleto | contiene el corte y el calendario no ha cerrado | `ATENCIÓN … INCOMPLETO` |
| Último cargado | contiene el corte con el calendario cerrado | «puede seguir recibiendo registros» |
| Cerrado | el corte queda antes | solo declara el alcance |

Y `comparables()` —lo que alimenta el máximo y el mínimo— excluye el último
periodo **en los dos primeros casos**. La asimetría lo decide: excluirlo cuesta
un punto que se recupera solo en la próxima actualización de la fuente;
incluirlo puede publicar un mínimo falso, y eso no se recupera.

## [0.12.0] — 2026-08-19

El error fundacional del proyecto —comparar un periodo a medias con periodos
cerrados— seguía vivo en tres sitios del propio módulo que existe para evitarlo.
Salió citando cifras para un artículo, no revisando código.

### Corregido

**El aviso del año base ofrecía como mínimo un año sin cerrar.**
`co_crimen_serie` calculaba el máximo y el mínimo sobre TODA la serie, incluido
el último periodo. Para homicidio anunciaba «Mínimo: 8.195», que es 2026 cortado
el 31 de julio; el mínimo real de los años cerrados es 11.957, de 2017. La
advertencia que existe para no elegir mal el año base estaba proponiendo el peor
año posible. Ahora los extremos se calculan solo sobre periodos cerrados y el
aviso declara cuál excluyó.

**`co_crimen_comparar` no avisaba en absoluto.** Comparar 2017 con 2026 devolvía
una caída del 31 % en homicidios, sin una sola advertencia, porque 2026 va hasta
julio. Es exactamente el error que motivó la herramienta, dentro de la función
de comparar. Ahora detecta si alguno de los dos años sigue abierto y lo dice
—agrupando por año, porque cada dataset de MinDefensa corta por su cuenta: el de
secuestro el 30 de julio y el de homicidio el 31—.

**Y la falsa alarma opuesta.** `co_crimen_serie` y `co_crimen_por_municipio`
afirmaban «el último año está incompleto» siempre que existiera fecha de corte,
aunque lo pedido terminara en un año cerrado: `serie(hasta=2025)` avisaba de una
incompletitud que no había. Una falsa alarma repetida enseña a ignorar el aviso,
y entonces no sirve el día que es verdad.

### Añadido

- **`domain/periodos.py`**, con la detección compartida. `analisis.py` tenía una
  versión propia y aproximada —daba por cerrado cualquier mes acabado en 28-31,
  y abril no tiene 31 días—; ahora se calcula con el calendario y la usan los
  dos módulos.

### Pruebas

- `tests/test_documentacion.py`: la documentación también se rompe en silencio.
  Una tabla con una fila de más columnas que su cabecera no da error, se
  renderiza torcida y nadie lo nota. Recorre los 9 documentos comprobando el
  cuadre de columnas y que ninguna tabla quede dentro de un ítem de lista.
- El fixture de criminalidad devolvía en la misma respuesta las filas de `serie`
  (alias `periodo`) y las de `comparar` (alias `a`), así que `serie` recibía tres
  filas sin clave `periodo`: su última fila quedaba vacía y **tapaba cualquier
  comprobación sobre el último año**. Ahora responde según el alias pedido y
  respeta el filtro de fechas.

## [0.11.0] — 2026-08-19

Cierra el patrón de las dos auditorías por el otro extremo: hasta ahora el error
era **detectable**; ahora es **inexpresable**.

### Cambiado

**El total del sobre lleva su procedencia.** `Sobre.total_coincidencias` era
un `int | None`, y un entero desnudo no puede distinguir «lo conté» de
«supuse». Por eso `len(filas)` se coló en seis herramientas: sintácticamente
es impecable. Ahora el campo es `total: Total`, y `Total` no se construye sin
decir cómo se supo:

| Constructor | Cuándo |
|---|---|
| `Total.contado(n)` | lo contó la fuente: `count(*)` o la subconsulta anidada |
| `Total.cupo_entero(filas, limite)` | devolvió menos de lo pedido: no había más |
| `Total.completo(n)` | la colección no sale de una consulta con `$limit` |
| `Total.desconocido()` | no consta, y se advierte |

La pieza que cierra el asunto es `cupo_entero`: es el constructor que se
usaría por descuido, exige el límite de la consulta y **decide él**. Si la
fuente lo llenó, devuelve desconocido en vez del número que alguien habría
escrito. Ya no hay forma de afirmar un total sin haberlo comprobado.

El keyword viejo desaparece a propósito: cualquier sitio que siguiera pasando
un entero falla al construirse, y `total_coincidencias` queda como propiedad
de **solo lectura**. Los 17 sitios se revisaron uno a uno para elegir el
constructor que describe la verdad de cada uno.

### Añadido

- **`origen_del_total` en el sobre.** Quien cite una cifra puede ver si se contó
  o si simplemente cupo, sin preguntar. Verificado contra la fuente viva:
  `co_secop_resolver_entidad` → 11 `contado`; `co_datos_agregar` por
  `tipodocproveedor` → 10 `cabia_entero`; `co_datos_describir_dataset` → 85
  `completo`.

## [0.10.0] — 2026-08-19

Dos auditorías seguidas encontraron el mismo patrón: los defectos de este
servidor no son de cálculo, son **respuestas que afirman más de lo que
comprobaron**. Esta versión no arregla otro caso; ataca las dos razones por las
que se repetía.

### Cambiado

- **El presupuesto de tokens se mide, ya no se estima.** 0.9.0 reservaba el
  coste del pie con aritmética, y la propia prueba lo pilló corto: recortar
  añade avisos, así que el aviso de recorte empujaba la respuesta por encima
  del presupuesto que ese recorte acababa de imponer. Ahora la función que se
  mide **es** la que se envía —cuerpo, pie, procedencia y avisos incluidos—, de
  modo que no queda reserva que pueda quedarse corta. Desaparece el cálculo y
  con él la clase de error.

### Añadido

- **`tests/test_invariantes.py`: lo que toda herramienta debe cumplir,
  comprobado en todas a la vez.** Con una fuente simulada que siempre llena el
  `$limit` y nunca deja contar los grupos, ninguna respuesta puede declarar
  `total == devueltos`: o el total consta, o sale desconocido y se advierte.

  Y lo que de verdad cierra el patrón: **la prueba falla mientras una
  herramienta nueva no esté clasificada** en `CASOS` o en `EXENTAS` —con su
  motivo escrito—. Las seis instancias del error no se escribieron a la vez, se
  fueron añadiendo una a una sin que nada preguntara. Ahora pregunta.

  Verificado retirando la llamada al helper en `co_crimen_por_municipio`, que
  es exactamente como se escribiría una herramienta nueva descuidada: la prueba
  falla y dice qué hacer.

## [0.9.0] — 2026-08-19

Segunda auditoría. La primera cosa que revisó fue el código de 0.8.0, y ahí
estaba el peor hallazgo.

### Corregido

- **El conteo de grupos podía tumbar respuestas que ya tenían sus datos.**
  `contar_grupos` solo capturaba errores de validación, así que un `ErrorTimeout`
  o un `ErrorFuenteCaida` suyo se propagaba y destruía la respuesta entera. El
  conteo es un extra: cambiar «un total equivocado» por «ninguna respuesta» es
  ir hacia atrás. Ahora degrada ante cualquier fallo y lleva **plazo propio**
  (`CO_TIMEOUT_CONTEO`, 25 s), porque medido en el peor caso —agregar por
  proveedor sin filtro— el conteo añade 16 s a una respuesta de 7 s, y sin tope
  una fuente lenta convierte un número de cortesía en el 80 % de la latencia.

- **La caché colgaba a quien esperaba si cancelaban al dueño de la petición.**
  `except Exception` no atrapa `CancelledError`: la cancelación se saltaba el
  bloque, el `finally` retiraba la clave y el futuro quedaba pendiente para
  siempre, de modo que todos los que esperaban en `asyncio.shield` colgaban sin
  error y sin fin. Estaba **dormido** porque nada cancelaba estas corrutinas —y
  el plazo del conteo, arriba, lo habría despertado el mismo día—. Además, al
  que espera ya no se le propaga una cancelación ajena, sino un error normal
  del que puede recuperarse.

- **El presupuesto de tokens ignoraba el pie de la respuesta.** Procedencia,
  URL reproducible y advertencias son parte de lo que se manda y no se
  descontaban: medido, `co_datos_consultar` con `limite=200` entregaba 6.196
  tokens contra un presupuesto de 6.000. Peor aún, **recortar añade avisos**,
  así que el propio aviso de recorte empujaba la respuesta por encima del
  presupuesto que ese recorte acababa de imponer. Ahora se reserva el pie y los
  dos avisos que solo existirán si se recorta. Medido después: −13, −30 y
  −4.333 tokens de margen en los tres casos más pesados.

### Revisado y descartado

Se comprobaron, y **no** son defectos: la superficie de inyección de
`arma_soql` (`donde`/`teniendo`/`luego` van crudos por diseño contra una API
pública de solo lectura, y `escapa()` cubre los literales); el recorrido de
rutas al exportar (`Path(nombre).name` + lista blanca + extensión forzada); el
crecimiento de la caché en disco (51 ficheros, 1,4 MB: solo van a disco los
metadatos, acotados por número de datasets); y la caducidad de la tabla curada
de alias (las 20 pruebas de contrato pasan contra la API viva, y CI las corre a
diario).

## [0.8.0] — 2026-08-19

### Corregido

**El conteo falso de 0.7.0 no era un bug: eran seis.** Arreglarlo en
`co_datos_agregar` dejó vivo el mismo `total_coincidencias = len(filas)` en
todas las demás. Medido contra la fuente viva, esto es lo que afirmaban antes
frente a lo que hay:

| Herramienta | Decía | Hay |
|---|---:|---:|
| `co_secop_agregar` (proveedor, 2026) | 5 de 5 | **525.759** |
| `co_datos_serie` (día, SECOP II) | 2.000 de 2.000 | **3.646** |
| `co_secop_perfil_proveedor` | 5 de 5 | **1.084** |
| `co_crimen_por_municipio` (homicidio 2025) | 5 de 5 | **820** |
| `co_secop_resolver_entidad` («MUNICIPIO DE SANTA») | 10 de 10 | **11** |

El más caro es `resolver_entidad`: es la herramienta de desambiguación, así
que ocultar una coincidencia y jurar que se vieron todas hace elegir el NIT
equivocado con confianza y contamina cada consulta posterior.

El arreglo no es parchear seis copias sino **`domain/agregacion.py`**, con la
única función `anota_total()` que ahora usan todas. La lógica vive en un sitio
y el error no puede volver a aparecer sitio por sitio.

- **`co_datos_serie` con `periodo="dia"` truncaba de verdad, no en teoría.** El
  tope de 2.000 periodos sobra para años y meses, pero SECOP II abarca 3.646
  días distintos: la serie diaria se cortaba por la mitad y se declaraba
  completa. `co_crimen_serie` tenía el mismo tope cableado en 400.

- **El validador de columnas rechazaba SoQL válido, y fallaba cerrado.**
  `_campos_citados` contrastaba cada palabra contra una lista cableada de ~60
  funciones y tomaba por columna todo lo que faltara, de modo que
  `nombre_entidad as entidad` se rechazaba —«columna inexistente: entidad»—
  igual que `caseless_eq(...)` o `date_diff_d(...)`, que son SoQL perfectamente
  válido en datos.gov.co y no estaban en la lista. Cada rechazo falso costaba
  además ~900 tokens listando el esquema entero.

  Las dos reglas de verdad no necesitan vocabulario: un identificador seguido de
  `(` es una función, y uno precedido de `as` es un alias. Ninguno es una
  columna, y **toda** función y **todo** alias lo cumplen, presentes y futuros.
  La lista baja de ~60 nombres a las 27 palabras sueltas del lenguaje, que sí
  son un conjunto cerrado.

### Cambiado

- `co_datos_consultar` lanzaba el conteo y la página **en serie**: dos viajes
  encadenados a la misma fuente, y en un dataset de millones de filas un
  `count(*)` no es gratis. Ahora van en `asyncio.gather`, como ya hacían otros
  siete sitios del repo, y la latencia es la del más lento en vez de la suma.

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
