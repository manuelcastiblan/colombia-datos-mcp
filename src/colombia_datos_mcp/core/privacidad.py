"""Motor de privacidad (§11): el guardarraíl que estaba definido y no existía.

`ErrorPrivacidad` llevaba meses en `core/errors.py` sin que ningún camino de
código lo lanzara, porque hasta ahora ninguna fuente del servidor traía
personas. Las que se añaden en 0.16.0 sí:

* **RUES** (`c82u-588k`): de sus 9.436.330 filas, **6.962.889 son
  `PERSONA NATURAL`** —comerciantes matriculados— con primer nombre, apellidos
  y número de cédula. Solo 2.473.441 son sociedades o ESAL.
* **SIRI** (`iaeu-rcn6`): 42.124 sanciones disciplinarias con nombre completo,
  cédula, cargo y la sanción impuesta. 26.091 son a miembros de la fuerza
  pública y 15.736 a servidores públicos.
* **Saber 11** (`kgxf-xxbe`): 7.109.704 registros **individuales** con género,
  fecha de nacimiento, estrato de la vivienda y escolaridad de los padres.

Son datos abiertos, publicados por el Estado bajo licencia CC. Eso los hace
legales de consultar; no los hace inocuos de volcar en una conversación. La
versión 0.15.0 ya había tenido que arreglar un caso menor del mismo problema
—dos filas del Universo de entidades del DAFP llegaban con el nombre y el
teléfono de un representante legal porque alguien preguntó por el orden
administrativo de la entidad— y se arregló con una heurística de columnas. Con
RUES y SIRI eso no basta: ahí el dato personal no es ruido que se cuele, es
exactamente lo que la fila contiene.

LAS TRES REGLAS

1. **Agregar nunca pide permiso.** Cuántas sanciones hay por departamento,
   cuántas sociedades se matricularon por año, el promedio de Saber 11 por
   municipio: son preguntas sobre poblaciones, no sobre personas, y no pasan
   por aquí. Que el camino barato sea también el que no identifica a nadie es
   deliberado.
2. **Identificar a una persona natural exige declarar para qué.** No es un
   trámite: `finalidad` viaja al sobre y queda en la respuesta, así que la
   consulta es auditable por quien la lea después. El modelo no puede
   inventarse una finalidad que el usuario no haya dado, porque el texto de
   error le dice justo eso.
3. **Quién puede relajar la política es el operador, no el modelo.**
   `CO_PRIVACIDAD` es variable de entorno. Ninguna herramienta recibe un
   parámetro que la afloje, de modo que ningún prompt puede pedirlo.

LO QUE NO HACE

No anonimiza: enmascarar un documento no impide reidentificar a alguien cuyo
nombre, cargo y municipio van en la misma fila. Sirve para que el número no
quede escrito en un historial de conversación, que es un riesgo distinto y
real. Quien necesite el documento completo tiene la fuente, citada en el sobre.
"""

from __future__ import annotations

import os

from .errors import ErrorPrivacidad, ErrorValidacion

# ----------------------------------------------------------------- política --
ESTRICTA = "estricta"
PERMISIVA = "permisiva"


def politica() -> str:
    """Se lee en cada llamada, no al importar: así una prueba puede cambiarla.

    Cualquier valor distinto de `permisiva` es `estricta`. Un error de
    escritura en la variable de entorno tiene que fallar hacia el lado que
    protege, no hacia el que expone.
    """
    valor = (os.environ.get("CO_PRIVACIDAD") or "").strip().lower()
    return PERMISIVA if valor == PERMISIVA else ESTRICTA


# --------------------------------------------------------------- finalidad --
# Las cuatro finalidades legítimas para las que este servidor se escribió. No
# es una lista de cortesía: `otra` no está, porque una finalidad que no se
# puede nombrar no se puede auditar.
FINALIDADES = {
    "investigacion": "investigación académica o social",
    "periodismo": "periodismo de interés público",
    "control_fiscal": "control fiscal o veeduría ciudadana",
    "debida_diligencia": "debida diligencia sobre una contraparte propia",
}

_ALIAS_FINALIDAD = {
    "investigación": "investigacion", "academico": "investigacion",
    "académico": "investigacion", "research": "investigacion",
    "periodistico": "periodismo", "periodístico": "periodismo",
    "prensa": "periodismo", "veeduria": "control_fiscal",
    "veeduría": "control_fiscal", "control fiscal": "control_fiscal",
    "fiscalizacion": "control_fiscal", "due_diligence": "debida_diligencia",
    "debida diligencia": "debida_diligencia", "kyc": "debida_diligencia",
}


def normaliza_finalidad(finalidad: str | None) -> str | None:
    if not finalidad:
        return None
    clave = str(finalidad).strip().lower().replace("-", "_")
    clave = _ALIAS_FINALIDAD.get(clave, clave.replace(" ", "_"))
    if clave in FINALIDADES:
        return clave
    raise ErrorValidacion(
        f"Finalidad no reconocida: {finalidad!r}.",
        "Válidas: " + ", ".join(f"{k} ({v})" for k, v in FINALIDADES.items()),
    )


def exige_finalidad(finalidad: str | None, *, que: str, alternativa: str) -> str:
    """Puerta de entrada a cualquier consulta que identifique a una persona.

    `alternativa` es obligatorio a propósito: un bloqueo que no dice qué hacer
    en su lugar entrena al modelo a reintentar con otras palabras. Aquí el
    mensaje nombra la herramienta agregada que responde la misma pregunta sin
    identificar a nadie.
    """
    normal = normaliza_finalidad(finalidad)
    if normal:
        return normal
    if politica() == PERMISIVA:
        return "no_declarada"
    raise ErrorPrivacidad(
        f"{que} identifica a una persona natural, así que hay que declarar "
        "`finalidad`. No la supongas: pregúntasela a quien te lo pidió.",
        f"Declara una de {', '.join(sorted(FINALIDADES))}, o responde sin "
        f"identificar a nadie con {alternativa}.",
    )


# ------------------------------------------------------------ clasificación --
def _digitos(valor) -> str:
    return "".join(c for c in str(valor or "") if c.isdigit())


def clase_documento(documento) -> str:
    """`nit`, `cedula` o `indeterminado`.

    Los NIT de empresas y entidades empiezan por 8 o 9 y tienen nueve dígitos
    (más el de verificación). Una cédula colombiana vigente va de seis a diez
    dígitos y no empieza por 8 ni 9 salvo en el rango alto de extranjería, que
    es justo donde la regla se rompe: por eso existe `indeterminado` en vez de
    forzar una respuesta.

    `indeterminado` cuenta como persona natural en todo este módulo. Equivocarse
    hacia «es una empresa» expone a alguien; equivocarse hacia «es una persona»
    solo pide una finalidad de más.
    """
    d = _digitos(documento)
    if not d:
        return "indeterminado"
    if d[0] in "89" and len(d) in (9, 10):
        return "nit"
    if 6 <= len(d) <= 10:
        return "cedula"
    return "indeterminado"


def es_persona_juridica(documento) -> bool:
    return clase_documento(documento) == "nit"


# ------------------------------------------------------------- enmascarado --
# El literal exacto de RUES, con la `ó` acentuada que trae la fuente. Buscar
# "SOCIEDAD O PERSONA JURIDICA" devuelve cero filas.
RUES_JURIDICA = "SOCIEDAD ó PERSONA JURIDICA PRINCIPAL ó ESAL"
RUES_NATURAL = "PERSONA NATURAL"

# Fragmentos de nombre de columna que contienen un número de documento. Se
# comparan en minúsculas y sin acentos sobre el nombre técnico del campo.
_COLUMNAS_DOCUMENTO = (
    "numero_identificacion", "num_identificacion", "documento", "cedula",
    "c_dula", "nit", "identificacion", "identificaci_n",
)
# Columnas que no se enmascaran aunque casen con lo anterior: son códigos de
# entidad pública o del sistema, no documentos de personas.
_NO_SON_DOCUMENTO = (
    "tipo_identificacion", "tipo_de_identificacion", "clase_identificacion",
    "nombre_tipo_identificacion", "codigo_clase_identificacion",
    "digito_verificacion", "nit_entidad", "nit_de_la_entidad",
    "codigo_entidad", "cod_entidad",
)


def es_columna_documento(campo: str) -> bool:
    c = str(campo or "").lower()
    if any(p in c for p in _NO_SON_DOCUMENTO):
        return False
    return any(p in c for p in _COLUMNAS_DOCUMENTO)


def enmascara(documento) -> str:
    """Deja los dos primeros dígitos y los dos últimos.

    `1.023.456.789` sale como `10••••••89`. Conserva la longitud —que es
    información útil: distingue una cédula antigua de una moderna— y deja
    comprobar que dos filas hablan de la misma persona, sin escribir el número.
    Con menos de seis dígitos no hay nada que ocultar de forma útil, así que se
    enmascara entero.
    """
    d = _digitos(documento)
    if not d:
        return ""
    if len(d) < 6:
        return "•" * len(d)
    return d[:2] + "•" * (len(d) - 4) + d[-2:]


def resuelve_persona(documento, categorias) -> tuple[bool, str | None]:
    """¿Las matrículas del RUES son de una persona natural? Y si las señales
    discrepan, el aviso que hay que poner en el sobre.

    Hay **dos** señales y ninguna es infalible:

    * `categoria_matricula` de la fuente, que es la buena: atrapa a los
      517.527 comerciantes a título personal que figuran con clase de
      identificación `NIT` y que la forma del número daría por empresas.
    * La forma del documento, que atrapa el error contrario. Y existe: el NIT
      de **Bancolombia** (890903938) tiene dos matrículas en el RUES, la de
      Medellín como sociedad y **la de Cali clasificada como `PERSONA
      NATURAL`**, con la razón social del banco escrita en la fila. Es un error
      de la fuente, no un caso límite.

    La primera versión bloqueaba en cuanto UNA matrícula dijera persona
    natural, por quedarse del lado que protege. El efecto real fue dejar la
    herramienta inútil para su caso central: pedir la ficha de uno de los
    bancos más grandes del país devolvía `[PRIVACIDAD]`.

    La regla que queda: manda la fuente, **salvo** que el documento tenga forma
    inequívoca de NIT de empresa —nueve dígitos empezando por 8 o 9, un rango
    al que la numeración de cédulas no llegó nunca—. Cuando discrepan no se
    resuelve en silencio: la fila se conserva y el sobre dice que la fuente la
    tiene mal clasificada, porque eso es información sobre el dato.
    """
    naturales = sum(1 for c in categorias if str(c or "") == RUES_NATURAL)
    if not naturales:
        return False, None
    if not es_persona_juridica(documento):
        return True, None
    total = len(list(categorias))
    return False, (
        f"{naturales} de las {total} matrículas de este documento están "
        f"clasificadas como «{RUES_NATURAL}» en el RUES, pese a que el número "
        "es un NIT de empresa. Es un error de la fuente —el NIT de Bancolombia "
        "aparece así en la cámara de Cali— y se trata como persona jurídica. "
        "Si de verdad fuera una persona, pide la ficha con `finalidad`."
    )


def redacta_filas(filas: list[dict], *, persona_juridica: bool = False) -> list[dict]:
    """Enmascara los documentos de las filas que son de personas naturales.

    Con `persona_juridica=True` no se toca nada: el NIT de una sociedad es
    información mercantil pública y enmascararlo haría la respuesta inútil para
    cruzarla con SECOP, que es justo para lo que sirve.

    Respeta `CO_PRIVACIDAD=permisiva` porque esa decisión es del operador.
    """
    if persona_juridica or politica() == PERMISIVA:
        return filas
    if not filas:
        return filas
    campos = {c for f in filas for c in f if es_columna_documento(c)}
    if not campos:
        return filas
    return [{k: (enmascara(v) if k in campos and v not in (None, "") else v)
             for k, v in f.items()} for f in filas]


# ---------------------------------------------------------------- avisos --
AVISO_ENMASCARADO = (
    "Los números de documento van enmascarados (dos primeros y dos últimos "
    "dígitos). La fuente citada arriba los trae completos; este servidor no los "
    "escribe en la conversación. Con CO_PRIVACIDAD=permisiva el operador puede "
    "cambiarlo; no es algo que se pida por parámetro."
)
AVISO_DATO_PERSONAL = (
    "Esta respuesta contiene datos personales de personas identificadas. Son "
    "datos abiertos publicados por el Estado, lo que los hace legales de "
    "consultar y no libres de cualquier uso: la Ley 1581 de 2012 pide finalidad "
    "legítima y no autoriza a recopilarlos, cruzarlos ni redifundirlos para "
    "otra cosa."
)
AVISO_SOLO_AGREGADO = (
    "Esta fuente es microdato individual, así que este servidor solo la expone "
    "agregada. No hay forma de pedir por aquí la fila de una persona concreta."
)


def avisa(sobre, *, finalidad: str | None = None, enmascarado: bool = True) -> None:
    """Pone en el sobre lo que haya que poner, según lo que se devolvió."""
    sobre.advertir(AVISO_DATO_PERSONAL)
    if enmascarado and politica() != PERMISIVA:
        sobre.advertir(AVISO_ENMASCARADO)
    if finalidad and finalidad in FINALIDADES:
        sobre.advertir(
            f"Finalidad declarada: {FINALIDADES[finalidad]}. Queda en esta "
            "respuesta para que sea auditable."
        )
    elif finalidad == "no_declarada":
        sobre.advertir(
            "Sin finalidad declarada: el operador puso CO_PRIVACIDAD=permisiva."
        )
