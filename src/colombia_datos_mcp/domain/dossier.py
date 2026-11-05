"""Un documento, todas las fuentes: la vista por entidad en vez de por dataset.

El servidor estaba organizado por dataset, que es como están los datos, no como
están las preguntas. «Qué publica el Estado sobre este NIT» obligaba a cinco
llamadas y a saber de antemano en qué dataset mirar. Esto las hace de una vez y,
sobre todo, **enumera lo que miró**: el valor de un dossier no está en lo que
encuentra —muchas veces casi nada— sino en que el alcance de la búsqueda quede
escrito junto al resultado, de modo que un cero se pueda interpretar.

Cada bloque falla por su cuenta. Si Supersociedades no responde, el dossier sale
con el resto y lo dice en esa línea, porque con seis backends el fallo parcial
es el caso normal y no hay razón para que tumbe la respuesta entera.

La regla de privacidad no cambia aquí: si el documento es de una persona
natural, el dossier entero pide finalidad antes de devolver nada. Cruzar cinco
fuentes sobre una persona es más invasivo que consultar una, no menos, así que
la puerta es la misma y está igual de cerrada.
"""

from __future__ import annotations

import asyncio

from ..adapters import socrata
from ..core import format as fmt
from ..core import nit as nit_mod
from ..core import privacidad
from ..core.envelope import Fuente, Sobre, Total
from ..core.errors import ErrorValidacion
from ..registry import datasets as reg
from . import empresas, integridad

CONTRATOS = reg.SECOP["contratos"]
INTEGRADO = reg.SECOP["integrado"]


def _literales_texto(documento: str) -> str:
    return ", ".join(f"'{socrata.escapa(f)}'"
                     for f in nit_mod.equivalentes(nit_mod.solo_digitos(documento)))


def _literales_numero(documento: str) -> str:
    return ", ".join(nit_mod.equivalentes(nit_mod.solo_digitos(documento)))


async def _seguro(corrutina, etiqueta: str):
    """Ejecuta un bloque del dossier sin dejar que su fallo tumbe los demás.

    Devuelve `(resultado, None)` o `(None, motivo)`. El motivo va a la tabla:
    «no consultable» es información distinta de «sin coincidencias», y
    confundirlas es justo lo que hace que un dossier engañe.
    """
    try:
        return await corrutina, None
    except Exception as e:                                    # noqa: BLE001
        return None, f"no consultable ({type(e).__name__})"


async def de_documento(documento: str, finalidad: str | None = None,
                       formato: str = "tabla"):
    """Ficha cruzada de un NIT o una cédula en las fuentes del servidor."""
    d = nit_mod.solo_digitos(documento)
    if not d:
        raise ErrorValidacion(
            f"Documento sin dígitos: {documento!r}.",
            "Pasa el NIT sin dígito de verificación, o la cédula, solo números.")

    juridica = privacidad.es_persona_juridica(d)
    if not juridica:
        finalidad = privacidad.exige_finalidad(
            finalidad,
            que=f"El dossier cruzado del documento {documento}",
            alternativa="co_secop_perfil_proveedor, que da los agregados de "
                        "contratación sin cruzar fuentes de antecedentes",
        )

    texto, numero = _literales_texto(d), _literales_numero(d)
    bloques, consultas = [], []

    # ------------------------------------------------- 1. registro mercantil
    rues, motivo = await _seguro(socrata.consultar(
        empresas.RUES.id,
        seleccionar="razon_social, nit, numero_identificacion, categoria_matricula, "
                    "organizacion_juridica, estado_matricula, camara_comercio, "
                    "fecha_matricula",
        donde=f"(nit in ({texto}) OR numero_identificacion in ({texto}))",
        ordenar="fecha_matricula DESC", limite=3), "RUES")
    nombre_rues, es_natural_rues, aviso_clasificacion = "", False, None
    if motivo:
        bloques.append(("Registro mercantil", "RUES · c82u-588k", motivo))
    elif rues["filas"]:
        consultas.append(rues["consulta"])
        m = rues["filas"][0]
        nombre_rues = fmt.limpia_texto(m.get("razon_social"))
        es_natural_rues, aviso_clasificacion = privacidad.resuelve_persona(
            d, [f.get("categoria_matricula") for f in rues["filas"]])
        bloques.append((
            "Registro mercantil", "RUES · c82u-588k",
            f"{nombre_rues} · {fmt.limpia_texto(m.get('organizacion_juridica'))} · "
            f"matrícula {fmt.limpia_texto(m.get('estado_matricula'))} en "
            f"{fmt.limpia_texto(m.get('camara_comercio'))} desde "
            f"{empresas.fecha_rues(m.get('fecha_matricula'))}"
            + (f" · {len(rues['filas'])} matrículas" if len(rues["filas"]) > 1 else "")))
    else:
        consultas.append(rues["consulta"])
        bloques.append((
            "Registro mercantil", "RUES · c82u-588k",
            "sin matrícula — puede ser una entidad pública, que no se matricula "
            "en cámara de comercio"))

    # El RUES corrige la conjetura por la forma del número en los dos
    # sentidos: atrapa a los 517.527 comerciantes a título personal con clase
    # NIT, y `resuelve_persona` evita que una fila mal clasificada —la de
    # Bancolombia en Cali— bloquee la ficha de una sociedad.
    if es_natural_rues and juridica:
        finalidad = privacidad.exige_finalidad(
            finalidad,
            que=f"El documento {documento} está matriculado como PERSONA NATURAL "
                "en el RUES, así que el dossier",
            alternativa="co_secop_perfil_proveedor para la contratación sola")
        juridica = False

    # --------------------------------------------------------- 2. contratación
    cont, motivo = await _seguro(socrata.consultar(
        CONTRATOS.id,
        seleccionar="count(*) as contratos, sum(valor_del_contrato) as valor, "
                    "min(fecha_de_firma) as primero, max(fecha_de_firma) as ultimo",
        donde=f"documento_proveedor in ({texto})", limite=1), "SECOP")
    if motivo:
        bloques.append(("Contratación estatal", f"SECOP II · {CONTRATOS.id}", motivo))
    else:
        consultas.append(cont["consulta"])
        f = cont["filas"][0] if cont["filas"] else {}
        n = fmt.a_numero(f.get("contratos")) or 0
        bloques.append((
            "Contratación estatal", f"SECOP II · {CONTRATOS.id}",
            (f"{fmt.numero(n)} contratos · {fmt.moneda(f.get('valor'))} · de "
             f"{fmt.fecha(f.get('primero'))} a {fmt.fecha(f.get('ultimo'))}")
            if n else "sin contratos en SECOP II (puede tener en SECOP I)"))

    # ---------------------------------------------------- 3. estados financieros
    eeff, motivo = await _seguro(socrata.consultar(
        empresas.EEFF_SITUACION.id,
        seleccionar="fecha_corte, valor",
        donde=(f"nit in ({numero}) AND periodo = 'Periodo Actual' "
               "AND concepto = 'Total de activos'"),
        ordenar="fecha_corte DESC", limite=1), "Supersociedades")
    if motivo:
        bloques.append(("Estados financieros",
                        f"Supersociedades · {empresas.EEFF_SITUACION.id}", motivo))
    elif eeff["filas"]:
        consultas.append(eeff["consulta"])
        f = eeff["filas"][0]
        bloques.append((
            "Estados financieros", f"Supersociedades · {empresas.EEFF_SITUACION.id}",
            f"último corte {fmt.fecha(f.get('fecha_corte'))} · total de activos "
            f"{fmt.numero(f.get('valor'))} (escala no declarada por la fuente)"))
    else:
        bloques.append((
            "Estados financieros", f"Supersociedades · {empresas.EEFF_SITUACION.id}",
            "no reporta — los bancos y aseguradoras reportan a la Superfinanciera"))

    # ------------------------------------------------------------- 4. ranking
    grandes, motivo = await _seguro(empresas.en_ranking(d), "ranking")
    bloques.append(("10.000 más grandes", f"Supersociedades · {empresas.MAS_GRANDES.id}",
                    motivo or (grandes or "no figura")))

    # ------------------------------------------------- 5. sanciones y antecedentes
    rastreos = (
        ("Multas de contratación", integridad.SECOP1,
         f"documento_contratista in ({texto})"),
        ("Antecedentes disciplinarios", integridad.SIRI,
         f"numero_identificacion in ({texto})"),
        ("Sanciones a contadores", integridad.CONTADORES, f"c_dula in ({texto})"),
        ("Responsabilidad fiscal", integridad.FISCAL,
         f"n_mero_de_identificaci_n in ({numero})"),
    )
    conteos = await asyncio.gather(
        *(_seguro(socrata.contar(ds.id, donde=donde), ds.id)
          for _etiqueta, ds, donde in rastreos))
    for (etiqueta, ds, _donde), (n, motivo) in zip(rastreos, conteos):
        if motivo:
            hallazgo = motivo
        elif n:
            hallazgo = f"**{fmt.numero(n)} registro(s)** — mira el detalle con co_integridad_screening"
        else:
            hallazgo = "0 registros"
        bloques.append((etiqueta, f"{ds.nombre.split(' - ')[0]} · {ds.id}", hallazgo))

    filas = [{"ámbito": a, "fuente": f, "hallazgo": h} for a, f, h in bloques]
    filas = privacidad.redacta_filas(filas, persona_juridica=juridica)

    titulo = (f"**Documento {d}**"
              + (f" — {nombre_rues}" if nombre_rues else "")
              + (f" · DV {nit_mod.digito_verificacion(d)}" if juridica and len(d) == 9 else ""))

    sobre = Sobre(datos=filas, total=Total.completo(len(filas)),
                  mostrar_conteo=False, consulta=" · ".join(consultas),
                  fuente=Fuente(id="dossier",
                                nombre="RUES + SECOP + Supersociedades + 4 fuentes de sanciones",
                                licencia="CC BY-SA 4.0 (verificar por dataset)"))
    sobre.advertir(integridad.NO_ES_CERTIFICADO)
    if aviso_clasificacion:
        sobre.advertir(aviso_clasificacion)
    sobre.advertir(
        "Las nueve líneas son TODO lo que este servidor sabe mirar. No incluye "
        "procesos judiciales, Registraduría, RUNT, SIMIT ni el Boletín de "
        "Deudores Morosos: esas fuentes solo se consultan por formulario web "
        "con captcha y no tienen API abierta.")
    sobre.advertir(
        "El cruce es por número de documento en sus dos formas (con y sin "
        "dígito de verificación). Una empresa que opere con otro NIT, o un "
        "contratista registrado con un número mal digitado, no aparece.")
    if not juridica:
        privacidad.avisa(sobre, finalidad=finalidad)
    return sobre.render(lambda f: titulo + "\n\n" + fmt.tabla_markdown(f),
                        formato=formato)
