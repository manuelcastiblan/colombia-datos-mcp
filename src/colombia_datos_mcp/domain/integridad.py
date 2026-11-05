"""Antecedentes y sanciones: lo que el Estado publica contra un documento.

Es el módulo que más se parece a lo que venden las APIs comerciales de
«screening de contrapartes», y el que más necesita decir lo que **no** puede
hacer, porque aquí una respuesta vacía se lee como un certificado limpio y no
lo es.

Lo que hay, verificado el 05-nov-2026:

| Fuente | Filas | Para qué sirve de verdad |
|---|---|---|
| SIRI, Procuraduría (`iaeu-rcn6`) | 42.124 | Sanciones a servidores públicos y fuerza pública |
| SECOP I, multas (`4n4q-k399`) | 1.716 | La única con documento del contratista |
| SECOP II, multas (`it5q-hg94`) | 588 | Casi nada, y el 91 % son comentarios positivos |
| Contadores, JCC (`fs36-azrv`) | 1.451 | Revisores fiscales sancionados |
| Responsabilidad fiscal, CGR (`jr8e-e8tu`) | 60 | Nada: muestra residual, parada en 2022 |

**Cuatro cifras que cambian cómo se lee todo lo anterior.** En SIRI, de 42.124
sanciones solo **18 son a contratistas** y 8 a particulares: para verificar a
un proveedor del Estado, este dataset está vacío en la práctica. En SECOP II,
de 588 filas **533 son «Comentarios positivos»** y solo 145 están publicadas;
el dataset se llama «Multas y Sanciones» y es la tabla de retroalimentación de
proveedores. La de la Contraloría tiene **60 filas** y no es el Boletín de
Responsables Fiscales. Y SECOP I dejó de ser la plataforma vigente, así que sus
1.716 multas no incluyen nada reciente.

De ahí la regla del módulo: **no hay ninguna consulta aquí cuyo resultado vacío
signifique «sin antecedentes»**. Cada respuesta sin coincidencias lo dice con
las cifras, en vez de devolver una tabla en blanco que parece una absolución.
Los certificados los expiden la Procuraduría, la Contraloría y la Policía en
sus propios portales, con captcha y con responsabilidad jurídica detrás.
"""

from __future__ import annotations

from . import agregacion
from ..adapters import socrata
from ..core import format as fmt
from ..core import nit as nit_mod
from ..core import privacidad
from ..core.envelope import Fuente, Sobre, Total
from ..core.errors import ErrorValidacion
from ..registry import datasets as reg

_LIC = "CC BY-SA 4.0"

SIRI = reg.INTEGRIDAD["siri"]
SECOP1 = reg.INTEGRIDAD["sanciones_secop1"]
SECOP2 = reg.INTEGRIDAD["sanciones_secop2"]
CONTADORES = reg.INTEGRIDAD["sanciones_contadores"]
FISCAL = reg.INTEGRIDAD["responsabilidad_fiscal"]

_ATRIB = {
    SIRI.id: "Procuraduría General de la Nación",
    SECOP1.id: "Agencia Nacional de Contratación Pública - Colombia Compra Eficiente",
    SECOP2.id: "Agencia Nacional de Contratación Pública - Colombia Compra Eficiente",
    CONTADORES.id: "Unidad Administrativa Especial Junta Central de Contadores",
    FISCAL.id: "Contraloría General de la República",
}

NO_ES_CERTIFICADO = (
    "ESTO NO ES UN CERTIFICADO DE ANTECEDENTES. Son datasets abiertos, "
    "incompletos y con rezago; no encontrar filas NO equivale a estar limpio. "
    "Los certificados con validez los expiden la Procuraduría, la Contraloría y "
    "la Policía en sus portales."
)
SECOP2_INUTIL = (
    "SECOP II «Multas y Sanciones» (it5q-hg94) tiene 588 filas, de las que 533 "
    "son «Comentarios positivos» y solo 145 están publicadas. Aquí se filtran "
    "los negativos y publicados; es la tabla de retroalimentación de "
    "proveedores, no un registro de sanciones."
)
SIRI_CASI_SIN_CONTRATISTAS = (
    "SIRI sanciona sobre todo a servidores públicos: 26.091 miembros de la "
    "fuerza pública y 15.736 servidores, frente a 18 contratistas y 8 "
    "particulares. Para verificar a un proveedor, está vacío en la práctica."
)


def _fuente(ds: reg.Dataset) -> Fuente:
    return Fuente(id=ds.id, nombre=ds.nombre, licencia=_LIC,
                  atribucion=_ATRIB.get(ds.id))


def _literales(documento: str) -> str:
    d = nit_mod.solo_digitos(documento)
    if not d:
        raise ErrorValidacion(
            f"Documento sin dígitos: {documento!r}.",
            "Pasa la cédula o el NIT sin dígito de verificación, solo números.")
    return ", ".join(f"'{socrata.escapa(f)}'" for f in nit_mod.equivalentes(d))


# -------------------------------------------------------------- screening --
def _contratista_juridico(fila: dict) -> bool:
    """¿La fila es de una empresa? Se mira el documento que trae, no la consulta.

    Una fila sin dígitos en el documento —todas las de SECOP II, que no lo
    publica— cuenta como jurídica porque no hay nada que enmascarar:
    enmascararla convertiría «(SECOP II no lo publica)» en una cadena vacía.
    """
    d = str(fila.get("documento") or "")
    if not any(c.isdigit() for c in d):
        return True
    return privacidad.es_persona_juridica(d)


def _clave_fecha(fila: dict) -> str:
    """La fecha de una fila ya formateada, como cadena ordenable.

    `fmt.fecha` devuelve dd-mm-aaaa, que ordenado alfabéticamente no es
    cronológico: hay que darle la vuelta a los trozos. Sin fecha va al final.
    """
    valor = str(fila.get("fecha") or "")
    trozos = valor.replace("/", "-").split("-")
    if len(trozos) == 3 and len(trozos[0]) == 2:
        return f"{trozos[2]}-{trozos[1]}-{trozos[0]}"
    return valor


async def screening(documento: str, finalidad: str | None = None,
                    limite: int = 10, formato: str = "tabla"):
    """Busca un documento en las cinco fuentes de sanciones, de una vez.

    Devuelve una fila por fuente con cuántas coincidencias hay y el detalle de
    las que se encontraron. El valor no está en las coincidencias —casi siempre
    serán cero— sino en que la tabla enumera **qué se miró**, de modo que el
    alcance de la respuesta queda escrito junto a ella.
    """
    juridica = privacidad.es_persona_juridica(documento)
    if not juridica:
        finalidad = privacidad.exige_finalidad(
            finalidad,
            que=("Buscar antecedentes del documento "
                 f"{privacidad.etiqueta_documento(documento)}"),
            alternativa="co_integridad_panorama, que agrega SIRI por entidad, "
                        "departamento o tipo de sanción sin identificar a nadie",
        )
    literales = _literales(documento)

    # (dataset, columna del documento, filtro extra, qué columnas mostrar)
    rastreos = (
        (SIRI, "numero_identificacion", None,
         ("calidad_persona", "entidad_sancionado", "cargo", "sanciones",
          "tipo_inhabilidad", "duracion_anos", "fecha_efectos_juridicos")),
        (SECOP1, "documento_contratista", None,
         ("nombre_contratista", "nombre_entidad", "numero_de_resolucion",
          "valor_sancion", "fecha_de_publicacion")),
        (CONTADORES, "c_dula", None,
         ("contador", "tipo", "resoluci_n", "fecha_resoluci_n", "meses")),
        (FISCAL, "n_mero_de_identificaci_n", None,
         ("raz_n_social_de_la_entidad", "tipo_de_sanci_n_multa",
          "monto_de_la_multa_o_sanci", "fecha_de_resoluci_n_que")),
    )

    resumen, detalles, consultas, trozos = [], [], [], []
    tope = min(int(limite), 50)
    for ds, campo, extra, columnas in rastreos:
        donde = f"{campo} in ({literales})"
        if ds is FISCAL:
            # Aquí el documento es de tipo number, no text: las comillas dan
            # type-mismatch en vez de cero filas.
            donde = f"{campo} in ({', '.join(nit_mod.equivalentes(nit_mod.solo_digitos(documento)))})"
        if extra:
            donde = f"{donde} AND {extra}"
        try:
            r = await socrata.consultar(
                ds.id, seleccionar=", ".join((campo,) + columnas), donde=donde,
                limite=tope)
            filas = r["filas"]
            consultas.append(r["consulta"])
            trozos.append((len(filas), tope))
            estado = (f"{len(filas)} o más" if len(filas) >= tope
                      else str(len(filas)))
        except Exception as e:                      # una fuente caída no tumba las otras
            filas, estado = [], f"no consultable ({type(e).__name__})"
        resumen.append({"fuente": ds.nombre, "id": ds.id, "coincidencias": estado})
        for f in filas:
            detalle = {"fuente": ds.nombre.split(" - ")[0]}
            detalle.update({k: fmt.limpia_texto(v) if isinstance(v, str) else v
                            for k, v in f.items() if k != campo})
            detalles.append(detalle)

    # SECOP II va aparte: no tiene columna de documento, así que no se puede
    # cruzar por número. Decirlo es más útil que omitir la fuente.
    resumen.append({"fuente": SECOP2.nombre, "id": SECOP2.id,
                    "coincidencias": "no cruzable por documento"})

    detalles = privacidad.redacta_filas(detalles, persona_juridica=juridica)
    # Las cinco filas de resumen son una colección cerrada; los detalles vienen
    # con `$limit` por fuente. Lo que no consta es cuántos detalles hay, así que
    # el total se declara desconocido en vez de sumar lo que llegó.
    # `mostrar_conteo=False` porque la respuesta son DOS tablas en una: cinco
    # filas de resumen, una por fuente, más los detalles. Contarlas juntas daba
    # «5 fila(s) de 0 coincidencias», que es verdad por separado y absurdo
    # leído seguido. El `Total` se conserva para poder avisar si alguna fuente
    # llenó su límite, que es lo único que de verdad hace falta declarar aquí.
    consulta = " · ".join(consultas)
    if not juridica:
        consulta = privacidad.redacta_consulta(consulta, documento)
    sobre = Sobre(datos=resumen + detalles, total=Total.union(trozos),
                  mostrar_conteo=False, consulta=consulta,
                  fuente=Fuente(id="screening", nombre="Cinco fuentes de sanciones",
                                licencia=_LIC))
    if not juridica:
        sobre.advertir(privacidad.AVISO_CONSULTA_REDACTADA)
    if not sobre.total.consta:
        sobre.advertir(
            f"Alguna fuente devolvió el máximo de {tope} coincidencias, así que "
            "hay más de las mostradas: el total es desconocido. Sube `limite` o "
            "ve a la herramienta de esa fuente.")
    sobre.advertir(NO_ES_CERTIFICADO)
    sobre.advertir(SIRI_CASI_SIN_CONTRATISTAS)
    sobre.advertir(
        "SECOP II no publica el documento del contratista en su tabla de "
        "sanciones: `as_codigo_proveedor_objeto` es un código interno de la "
        "plataforma. Esa fuente solo se puede mirar por nombre, con "
        "co_integridad_sanciones_contratacion."
    )
    sobre.advertir(
        "La Responsabilidad Fiscal de la Contraloría tiene 60 filas y está "
        "parada desde el 23-mar-2022: su cero no informa de nada."
    )
    if not juridica:
        privacidad.avisa(sobre, finalidad=finalidad)

    def cuerpo(filas):
        res = [f for f in filas if "coincidencias" in f]
        det = [f for f in filas if "coincidencias" not in f]
        texto = "**Fuentes consultadas**\n\n" + fmt.tabla_markdown(res)
        if det:
            texto += "\n\n**Coincidencias**\n\n" + fmt.tabla_markdown(det)
        else:
            texto += ("\n\n_Sin coincidencias en ninguna de las fuentes "
                      "cruzables por documento._")
        return texto

    return sobre.render(cuerpo, formato=formato)


# ---------------------------------------------------------- disciplinarias --
async def disciplinarias(documento: str | None = None, nombre: str | None = None,
                         entidad: str | None = None, finalidad: str | None = None,
                         limite: int = 20, offset: int = 0, formato: str = "tabla"):
    """Sanciones del SIRI por documento, por nombre o por entidad sancionadora.

    Buscar por `entidad` sin documento ni nombre no identifica a nadie en
    particular, pero devuelve filas que sí traen personas: también pasa por el
    motor de privacidad. Para una lectura sin personas está `panorama`.
    """
    if not (documento or nombre or entidad):
        raise ErrorValidacion(
            "Hace falta `documento`, `nombre` o `entidad`.",
            "Para ver el reparto de sanciones sin identificar a nadie usa "
            "co_integridad_panorama.")
    finalidad = privacidad.exige_finalidad(
        finalidad,
        que="Consultar sanciones disciplinarias del SIRI",
        alternativa="co_integridad_panorama, que agrupa las 42.124 sanciones "
                    "por entidad, departamento, sanción o calidad de la persona",
    )

    partes, avisos = [], []
    if documento:
        partes.append(f"numero_identificacion in ({_literales(documento)})")
    if nombre:
        # Cuatro columnas separadas y ninguna con el nombre completo. Buscar la
        # cadena entera en cada columna era un falso cero garantizado: con
        # nombre="ANA PEREZ", ninguna columna contiene "ANA PEREZ" —una tiene
        # "ANA" y otra "PEREZ"—, así que la persona estaba en SIRI y la
        # respuesta decía que no. Un cero falso es el peor fallo posible aquí.
        #
        # Se parte en términos: CADA término tiene que aparecer en ALGUNA de
        # las cuatro columnas. Un término suelto se comporta como antes.
        campos = ("primer_nombre", "segundo_nombre", "primer_apellido",
                  "segundo_apellido")
        terminos = [t for t in str(nombre).split() if t.strip()]
        por_termino = []
        for termino in terminos:
            trozos = [socrata.filtro_texto_libre(c, termino) for c in campos]
            trozos = [t for t in trozos if t]
            if trozos:
                por_termino.append("(" + " OR ".join(trozos) + ")")
        if por_termino:
            partes.append("(" + " AND ".join(por_termino) + ")")
        avisos.append(
            "SIRI guarda el nombre en cuatro columnas y ninguna tiene el nombre "
            f"completo, así que {'cada término se busca' if len(terminos) > 1 else 'el término se busca'} "
            "en las cuatro: un apellido común devuelve homónimos. Sin el "
            "documento no hay forma de distinguirlos, y confundir a dos "
            "personas aquí es grave."
        )
    if entidad:
        cat = await socrata.filtro_categorico(SIRI.id, "entidad_sancionado", entidad)
        if cat.filtro is None:
            sobre = Sobre(datos=[], total=Total.completo(0), fuente=_fuente(SIRI))
            sobre.advertir(
                f"«{entidad}» no aparece como entidad del sancionado en SIRI. No "
                "es un fallo de la fuente.")
            return sobre.render(lambda _f: "_Sin coincidencias._")
        partes.append(cat.filtro)

    donde = " AND ".join(partes)
    tope = min(int(limite), 100)
    r = await socrata.consultar(
        SIRI.id, seleccionar=", ".join(SIRI.campos_resumen), donde=donde,
        ordenar="fecha_efectos_juridicos DESC", limite=tope, offset=offset)

    filas = [{"documento": f.get("numero_identificacion"),
              "calidad": fmt.limpia_texto(f.get("calidad_persona")),
              "entidad": fmt.limpia_texto(f.get("entidad_sancionado")),
              "cargo": fmt.limpia_texto(f.get("cargo")),
              "sanción": fmt.limpia_texto(f.get("sanciones")),
              "inhabilidad": fmt.limpia_texto(f.get("tipo_inhabilidad")),
              "años": f.get("duracion_anos"),
              "efectos": fmt.fecha(f.get("fecha_efectos_juridicos")),
              "autoridad": fmt.limpia_texto(f.get("autoridad"))}
             for f in r["filas"]]
    filas = privacidad.redacta_filas(filas)

    # SIRI es nominal por definición: toda fila es una persona, así que el
    # documento no viaja nunca en la consulta publicada.
    sobre = Sobre(datos=filas, offset=offset, orden="fecha_efectos_juridicos DESC",
                  consulta=privacidad.redacta_consulta(r["consulta"], documento or ""),
                  fuente=_fuente(SIRI))
    if documento:
        sobre.advertir(privacidad.AVISO_CONSULTA_REDACTADA)
    sobre.total = Total.cupo_entero(r["filas"], tope, offset=offset)
    if not sobre.total.consta:
        sobre.total = Total.contado(await socrata.contar(SIRI.id, donde=donde))
    if not filas:
        sobre.advertir(
            "Sin coincidencias en SIRI. El dataset tiene 42.124 sanciones y es "
            "una extracción, no el registro vivo de la Procuraduría: esto NO "
            "es un certificado de antecedentes limpio.")
    for a in avisos:
        sobre.advertir(a)
    sobre.advertir(NO_ES_CERTIFICADO)
    sobre.advertir(SIRI_CASI_SIN_CONTRATISTAS)
    sobre.advertir(
        "Las fechas y las duraciones son de tipo text en esta fuente, así que "
        "el orden cronológico es alfabético sobre la cadena: para rangos usa "
        "co_datos_consultar y compruébalo.")
    privacidad.avisa(sobre, finalidad=finalidad)
    return sobre.render(lambda f: fmt.tabla_markdown(f), formato=formato)


# --------------------------------------------------------------- panorama --
GRUPOS_PANORAMA = {
    "entidad": "entidad_sancionado",
    "departamento": "entidad_departamento",
    "sancion": "sanciones",
    "calidad": "calidad_persona",
    "autoridad": "autoridad",
    "inhabilidad": "tipo_inhabilidad",
    "cargo": "cargo",
}


async def panorama(agrupar_por: str = "calidad", limite: int = 20,
                   formato: str = "tabla", grafica: bool = True):
    """El reparto de las 42.124 sanciones del SIRI, sin una sola persona.

    Es la vía que el motor de privacidad ofrece como alternativa cuando bloquea
    una consulta nominal, y existe para que esa alternativa sea real: la
    pregunta «qué sanciona la Procuraduría y a quién» se responde aquí entera,
    sin pedir finalidad ni devolver un nombre.
    """
    campo = GRUPOS_PANORAMA.get(agrupar_por)
    if not campo:
        raise ErrorValidacion(
            f"Agrupación desconocida: {agrupar_por!r}.",
            "Válidas: " + ", ".join(sorted(GRUPOS_PANORAMA)))

    tope = min(int(limite), 100)
    SELECT = f"{campo} as grupo, count(*) as sanciones"
    r = await socrata.consultar(SIRI.id, seleccionar=SELECT, agrupar=campo,
                                ordenar="sanciones DESC", limite=tope)
    crudos = [fmt.a_numero(f.get("sanciones")) or 0 for f in r["filas"]]
    filas = [{agrupar_por: fmt.limpia_texto(f.get("grupo")) or "(sin dato)",
              "sanciones": fmt.numero(f.get("sanciones"))} for f in r["filas"]]
    if grafica and formato == "tabla" and filas:
        for fila, barra in zip(filas, fmt.barras(crudos)):
            fila["gráfica"] = barra

    sobre = Sobre(datos=filas, orden="sanciones DESC", consulta=r["consulta"],
                  fuente=_fuente(SIRI))
    await agregacion.anota_total(sobre, r["filas"], tope, dataset_id=SIRI.id,
                                 seleccionar=SELECT, agrupar=campo)
    sobre.advertir(
        "Una fila es una SANCIÓN, no una persona: una misma persona puede tener "
        "varias y aquí cuentan por separado.")
    sobre.advertir(
        "Son sanciones registradas en esta extracción del SIRI, con el rezago "
        "que eso implica. No es la estadística oficial de la Procuraduría.")
    return sobre.render(lambda f: fmt.tabla_markdown(f), formato=formato)


# ------------------------------------------------- sanciones contratación --
async def sanciones_contratacion(documento: str | None = None,
                                 nombre: str | None = None,
                                 finalidad: str | None = None,
                                 limite: int = 20, formato: str = "tabla"):
    """Multas y sanciones de SECOP I y II a contratistas del Estado.

    Las dos plataformas se consultan de forma distinta porque publican cosas
    distintas: SECOP I trae el documento del contratista y SECOP II no, solo el
    nombre y un código interno. Sin `nombre` la mitad de SECOP II es invisible.
    """
    if not (documento or nombre):
        raise ErrorValidacion(
            "Hace falta `documento` o `nombre` del contratista.",
            "Para el panorama de la contratación usa co_secop_agregar.")
    # Con `documento`, la forma del número decide antes de consultar.
    juridica = privacidad.es_persona_juridica(documento) if documento else True
    if documento and not juridica:
        finalidad = privacidad.exige_finalidad(
            finalidad,
            que=("Buscar sanciones de contratación de "
                 f"{privacidad.etiqueta_documento(documento)}"),
            alternativa="el nombre de la empresa, si lo que buscas es una "
                        "persona jurídica",
        )

    filas, consultas, avisos, trozos = [], [], [], []
    tope = min(int(limite), 50)

    # SECOP I: la única con documento.
    partes = []
    if documento:
        partes.append(f"documento_contratista in ({_literales(documento)})")
    if nombre:
        partes.append(socrata.filtro_texto_libre("nombre_contratista", nombre))
    r1 = await socrata.consultar(
        SECOP1.id, seleccionar=", ".join(SECOP1.campos_resumen),
        donde=" AND ".join(p for p in partes if p) or None,
        ordenar="fecha_de_publicacion DESC", limite=tope)
    consultas.append(r1["consulta"])
    trozos.append((len(r1["filas"]), tope))
    for f in r1["filas"]:
        filas.append({"plataforma": "SECOP I",
                      "contratista": fmt.limpia_texto(f.get("nombre_contratista")),
                      "documento": f.get("documento_contratista"),
                      "entidad": fmt.limpia_texto(f.get("nombre_entidad")),
                      "acto": fmt.limpia_texto(f.get("numero_de_resolucion")),
                      "valor": fmt.moneda(f.get("valor_sancion")),
                      "fecha": fmt.fecha(f.get("fecha_de_publicacion")),
                      "estado": "en firme" if f.get("fecha_de_firmeza") else "sin firmeza"})

    # SECOP II: solo por nombre, y solo lo negativo y publicado.
    if nombre:
        donde2 = (socrata.filtro_texto_libre("nombre_proveedor_objeto_de", nombre)
                  + " AND tipo = 'Comentarios negativos'"
                  + " AND estado = 'Publicado por el administrador de la plataforma'")
        r2 = await socrata.consultar(
            SECOP2.id, seleccionar=", ".join(SECOP2.campos_resumen), donde=donde2,
            ordenar="fecha_evento DESC", limite=tope)
        consultas.append(r2["consulta"])
        trozos.append((len(r2["filas"]), tope))
        for f in r2["filas"]:
            filas.append({"plataforma": "SECOP II",
                          "contratista": fmt.limpia_texto(f.get("nombre_proveedor_objeto_de")),
                          "documento": "(SECOP II no lo publica)",
                          "entidad": fmt.limpia_texto(f.get("nombre_entidad_creadora")),
                          "acto": fmt.limpia_texto(f.get("numero_de_acto")),
                          "valor": fmt.moneda(f.get("valor")),
                          "fecha": fmt.fecha(f.get("fecha_evento")),
                          "estado": fmt.limpia_texto(f.get("tipo_de_sancion"))})
        avisos.append(SECOP2_INUTIL)
    else:
        avisos.append(
            "Sin `nombre` no se miró SECOP II: esa fuente no publica el "
            "documento del contratista, solo el nombre. Pasa el nombre para "
            "incluirla.")

    # Cada plataforma venía ordenada por su propia fecha y luego se
    # concatenaban, así que el sobre anunciaba `fecha DESC` y entregaba todo
    # SECOP I primero: una sanción de 2024 en SECOP II salía debajo de una de
    # 2012. El orden se aplica a la lista mezclada, que es la que se lee.
    filas.sort(key=_clave_fecha, reverse=True)

    # Una búsqueda por nombre se daba por jurídica sin comprobar nada, y SECOP I
    # contrata con personas naturales: devolvía su cédula completa sin finalidad.
    # Pero exigirla por el hecho de buscar un nombre bloquearía el caso común
    # —el nombre de una empresa—, así que se decide con lo que la fuente
    # devolvió, igual que en `resuelve_persona`: si entre las filas hay algún
    # documento con forma de cédula, eso es una persona y hay que pedir permiso.
    hay_personas = any(not _contratista_juridico(f) for f in filas)
    if hay_personas:
        finalidad = privacidad.exige_finalidad(
            finalidad,
            que=(f"La búsqueda por «{nombre}» devuelve contratistas que son "
                 "personas naturales, con su documento, así que"),
            alternativa="co_secop_agregar para el panorama de la contratación, "
                        "que no identifica a nadie",
        )
        filas = privacidad.redacta_filas(filas, es_juridica=_contratista_juridico)
        avisos.append(privacidad.AVISO_CONSULTA_REDACTADA)
    elif not juridica:
        filas = privacidad.redacta_filas(filas)
        avisos.append(privacidad.AVISO_CONSULTA_REDACTADA)
    consulta = " · ".join(consultas)
    if hay_personas or not juridica:
        consulta = privacidad.redacta_consulta(consulta, documento or "")
    sobre = Sobre(datos=filas, total=Total.union(trozos),
                  orden="fecha DESC", consulta=consulta,
                  fuente=Fuente(id=f"{SECOP1.id} + {SECOP2.id}",
                                nombre="SECOP I + II · Multas y Sanciones",
                                licencia=_LIC, atribucion=_ATRIB[SECOP1.id]))
    if not filas:
        sobre.advertir(
            "Sin sanciones registradas. Las dos fuentes juntas tienen 1.716 + "
            "588 filas para ~5,9 M de contratos, así que un cero aquí dice muy "
            "poco: NO es constancia de no haber sido sancionado.")
    if not sobre.total.consta:
        sobre.advertir(
            f"Total desconocido: alguna de las dos plataformas devolvió el "
            f"máximo de {tope} filas, así que hay más sanciones de las "
            "mostradas. Sube `limite`.")
    for a in avisos:
        sobre.advertir(a)
    sobre.advertir(
        "SECOP I ya no es la plataforma vigente: sus 1.716 multas no recogen "
        "sanciones recientes.")
    sobre.advertir(NO_ES_CERTIFICADO)
    if not juridica:
        privacidad.avisa(sobre, finalidad=finalidad)
    return sobre.render(lambda f: fmt.tabla_markdown(f), formato=formato)
