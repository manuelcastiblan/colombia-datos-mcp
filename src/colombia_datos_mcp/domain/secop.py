"""Herramientas de contratación pública (SECOP I, SECOP II, TVEC)."""

from __future__ import annotations

import asyncio
import re

from . import agregacion
from ..adapters import socrata
from ..core import format as fmt
from ..core.budget import Detalle
from ..core.envelope import Fuente, Sobre
from ..core.errors import ErrorNoEncontrado, ErrorValidacion
from ..registry import datasets as reg

_FUENTE_CCE = "Agencia Nacional de Contratación Pública - Colombia Compra Eficiente"


def _fuente(ds: reg.Dataset) -> Fuente:
    return Fuente(id=ds.id, nombre=ds.nombre, licencia="CC BY-SA 4.0", atribucion=_FUENTE_CCE)


def _filtro_texto(campo: str, valor: str) -> str:
    """Filtro para campos de TEXTO LIBRE (nombres de entidad o proveedor).

    Antes plegaba los acentos del término y comparaba con `like`, dando por
    hecho que la fuente los traía destruidos. Eso solo es cierto en los campos
    descriptivos; `nombre_entidad` es "GOBERNACIÓN DE BOLÍVAR//", así que el
    filtro plegado devolvía cero. Ver `core.texto`.
    """
    return socrata.filtro_texto_libre(campo, valor)


def _solo_digitos(valor: str) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def _numero(valor, etiqueta: str) -> float:
    """Umbral numérico tolerante: 1000000, "1.000.000" o "$1.000.000".

    Delega en `format.a_numero` a propósito. Antes había aquí una copia de la
    misma regla, las dos divergieron, y la de este módulo leía una suma
    agregada mil veces mayor de lo que era.
    """
    n = fmt.a_numero(valor)
    if n is None:
        raise ErrorValidacion(
            f"{etiqueta} debe ser un número; llegó {valor!r}.",
            "Escríbelo en dígitos, con o sin separadores: 1000000 o 1.000.000.",
        )
    return n


# Un contrato estatal colombiano por encima de un billón de pesos es, en la
# práctica, un error de digitación: son ~3.450 registros cuyos valores llegan a
# 10^20 y que dominan cualquier suma en la que caigan.
UMBRAL_ABSURDO = 1_000_000_000_000
UMBRAL_ABSURDO_SOQL = f"valor_del_contrato > {UMBRAL_ABSURDO}"


def _advierte_absurdos(sobre, absurdos, global_):
    """Dice qué parte del total viene de valores imposibles.

    Sin esto la herramienta presenta como cifra de contratación una suma que
    puede ser 99 % ruido, y nada en la respuesta permite sospecharlo.

    El porcentaje se calcula contra la suma de TODO el filtro, no contra los
    grupos mostrados: comparar el ruido global con una página daba cifras por
    encima del 100 %.
    """
    fila = (absurdos.get("filas") or [{}])[0]
    n = fmt.a_numero(fila.get("n")) or 0
    if not n:
        return
    ruido = fmt.a_numero(fila.get("v")) or 0
    total = fmt.a_numero((global_.get("filas") or [{}])[0].get("v")) or 0
    parte = f", el {ruido / total * 100:.1f} % de la suma del filtro" if total else ""
    sobre.advertir(
        f"ATENCIÓN: {fmt.numero(n)} contrato(s) del filtro superan el billón de "
        f"pesos{parte}. Son errores de digitación —hay contratos de un enfermero "
        f"por 9,97 billones— y arrastran la suma entera. Filtrar por estado NO "
        f"basta: aunque el 97 % están Cancelado o Borrador, los que quedan siguen "
        f"dominando el total. Usa valor_max para acotarlos, o suma valor_pagado, "
        f"que en los atípicos es cero."
    )


# Campos de dominio cerrado: se resuelven contra los valores canónicos de la
# fuente. Los demás van por texto libre.
CATEGORICOS = ("departamento", "modalidad")


async def _construye_where(ds: reg.Dataset, **filtros):
    """Construye el `$where`.

    Devuelve `(donde, avisos, imposible)`. `imposible` es True cuando un
    término categórico no corresponde a ningún valor real de la fuente: en ese
    caso el llamador devuelve cero SIN consultar y lo dice, porque un cero
    silencioso es indistinguible de "no hay datos".
    """
    c = ds.campos_clave
    partes, avisos = [], []

    for clave in CATEGORICOS:
        if not filtros.get(clave) or not c.get(clave):
            continue
        campo = c[clave]
        filtro, valores, truncado = await socrata.filtro_categorico(ds.id, campo, filtros[clave])
        if filtro is None:
            avisos.append(
                f"«{filtros[clave]}» no corresponde a ningún valor de `{campo}` en la "
                "fuente, así que no hay nada que devolver. No es un fallo de la fuente."
            )
            return None, avisos, True
        if len(valores) > 1:
            muestra = ", ".join(valores[:8]) + ("…" if len(valores) > 8 else "")
            avisos.append(f"«{filtros[clave]}» resolvió a {len(valores)} valor(es): {muestra}")
        if truncado:
            avisos.append(
                f"El término «{filtros[clave]}» casa con demasiados valores de `{campo}`; "
                "se usaron los primeros. Afina el término."
            )
        partes.append(filtro)

    if filtros.get("entidad") and c.get("entidad"):
        partes.append(_filtro_texto(c["entidad"], filtros["entidad"]))
    if filtros.get("nit_entidad") and c.get("nit_entidad"):
        partes.append(f"{c['nit_entidad']} = '{_solo_digitos(filtros['nit_entidad'])}'")
    if filtros.get("proveedor") and c.get("proveedor"):
        partes.append(_filtro_texto(c["proveedor"], filtros["proveedor"]))
    if filtros.get("documento_proveedor") and c.get("doc_proveedor"):
        partes.append(f"{c['doc_proveedor']} = '{_solo_digitos(filtros['documento_proveedor'])}'")
    if filtros.get("desde") and c.get("fecha"):
        partes.append(f"{c['fecha']} >= '{socrata.escapa(filtros['desde'])}'")
    if filtros.get("hasta") and c.get("fecha"):
        partes.append(f"{c['fecha']} <= '{socrata.escapa(filtros['hasta'])}'")
    if filtros.get("valor_min") and c.get("valor"):
        partes.append(f"{c['valor']} >= {_numero(filtros['valor_min'], 'valor_min')}")
    if filtros.get("valor_max") and c.get("valor"):
        partes.append(f"{c['valor']} <= {_numero(filtros['valor_max'], 'valor_max')}")

    return (" AND ".join(partes) if partes else None), avisos, False


async def _buscar(clave: str, detalle="resumen", limite=20, offset=0,
                  formato="tabla", **filtros):
    ds = reg.SECOP[clave]
    nivel = Detalle(detalle)
    donde, avisos, imposible = await _construye_where(ds, **filtros)

    if imposible:
        # El término no existe en la fuente: cero es la respuesta correcta, y
        # se dice por qué en vez de gastar una consulta que devolvería cero.
        sobre = Sobre(datos=[], total_coincidencias=0, detalle=nivel, fuente=_fuente(ds))
        for a in avisos:
            sobre.advertir(a)
        return sobre.render(lambda _f: "_Sin coincidencias._")

    total = await socrata.contar(ds.id, donde=donde)
    if nivel is Detalle.CONTEO:
        sobre = Sobre(datos=[], total_coincidencias=total, detalle=nivel, fuente=_fuente(ds),
                      consulta=socrata.url_reproducible(
                          f"{socrata.BASE_DATOS}/resource/{ds.id}.json",
                          {"$select": "count(*)", "$where": donde}))
        for a in avisos:
            sobre.advertir(a)
        return sobre.render(lambda _f: f"**{fmt.numero(total)}** {ds.unidad}(s) coinciden.")

    orden = f"{ds.campos_clave.get('valor')} DESC" if ds.campos_clave.get("valor") else ":id"
    r = await socrata.consultar(ds.id, donde=donde, ordenar=orden,
                                limite=min(int(limite), 100), offset=offset)
    columnas = list(ds.campos_resumen) if nivel is Detalle.RESUMEN else None
    filas = _proyecta(r["filas"], columnas, ds)

    sobre = Sobre(datos=filas, total_coincidencias=total, offset=offset, orden=orden,
                  detalle=nivel, consulta=r["consulta"], fuente=_fuente(ds))
    for a in avisos:
        sobre.advertir(a)
    sobre.advertir(f"Unidad de análisis: {ds.unidad}. No sumes filas de datasets distintos.")
    if not donde:
        sobre.advertir("Sin filtros: estás viendo los registros de mayor valor del dataset completo.")
    return sobre.render(lambda f: fmt.tabla_markdown(f), formato=formato)


def _proyecta(filas, columnas, ds):
    """Proyecta a las columnas curadas conservando SU orden.

    Se emiten las columnas que aparecen en alguna fila, no solo las de la
    primera: Socrata omite los campos nulos, así que un contrato en borrador
    sin `fecha_de_firma` a la cabeza borraba la fecha de todas las demás.
    Las que no aparecen en ninguna fila se omiten, para no añadir ruido.
    """
    if not filas:
        return []
    cols = list(columnas) if columnas else fmt.columnas_union(filas)
    presentes = [c for c in cols if any(c in f for f in filas)]
    salida = []
    for f in filas:
        fila = {_etiqueta(c): _valor(c, f[c]) if c in f else "" for c in presentes}
        salida.append(fila or {k: _valor(k, v) for k, v in f.items()})
    return salida


def _etiqueta(campo: str) -> str:
    return campo.replace("_", " ").strip()


def _valor(campo: str, valor):
    n = campo.lower()
    if isinstance(valor, dict):
        valor = valor.get("url") or str(valor)
    if fmt.es_monetario(n):
        return fmt.moneda(valor)
    if fmt.es_conteo(n):
        return fmt.numero(valor)
    if "fecha" in n:
        return fmt.fecha(valor)
    if "objeto" in n or "descripcion" in n or "procedimiento" in n:
        return fmt.recorta(valor, 80)
    return fmt.recorta(valor, 55)


# ------------------------------------------------------------ públicas ----
async def buscar_contratos(entidad=None, nit_entidad=None, proveedor=None,
                           documento_proveedor=None, departamento=None, modalidad=None,
                           desde=None, hasta=None, valor_min=None, valor_max=None,
                           detalle="resumen", limite=20, offset=0, formato="tabla"):
    return await _buscar("contratos", detalle=detalle, limite=limite, offset=offset,
                         formato=formato, valor_max=valor_max,
                         entidad=entidad, nit_entidad=nit_entidad, proveedor=proveedor,
                         documento_proveedor=documento_proveedor, departamento=departamento,
                         modalidad=modalidad, desde=desde, hasta=hasta, valor_min=valor_min)


async def buscar_procesos(entidad=None, nit_entidad=None, departamento=None, modalidad=None,
                          desde=None, hasta=None, detalle="resumen", limite=20, offset=0,
                          formato="tabla"):
    return await _buscar("procesos", detalle=detalle, limite=limite, offset=offset,
                         formato=formato,
                         entidad=entidad, nit_entidad=nit_entidad, departamento=departamento,
                         modalidad=modalidad, desde=desde, hasta=hasta)


async def detalle_contrato(id_contrato: str):
    """Vista compuesta: una llamada del modelo = un hecho completo."""
    contratos = reg.SECOP["contratos"]
    adiciones = reg.SECOP["adiciones"]
    id_limpio = socrata.escapa(id_contrato.strip())

    base, adics = await asyncio.gather(
        socrata.consultar(contratos.id, donde=f"id_contrato = '{id_limpio}'", limite=1),
        socrata.consultar(adiciones.id, donde=f"id_contrato = '{id_limpio}'",
                          ordenar="fecharegistro DESC", limite=25),
        return_exceptions=True,
    )
    if isinstance(base, Exception):
        raise base
    if not base["filas"]:
        raise ErrorNoEncontrado(
            f"No existe el contrato {id_contrato}.",
            "El identificador de SECOP II tiene la forma CO1.PCCNTR.<n>. "
            "Búscalo con co_secop_buscar_contratos.",
        )

    c = base["filas"][0]
    lineas = ["## Contrato " + fmt.limpia_texto(c.get("id_contrato")), ""]
    for etiqueta, campo in [
        ("Entidad", "nombre_entidad"), ("NIT entidad", "nit_entidad"),
        ("Departamento", "departamento"), ("Proveedor", "proveedor_adjudicado"),
        ("Documento proveedor", "documento_proveedor"),
        ("Modalidad", "modalidad_de_contratacion"), ("Estado", "estado_contrato"),
        ("Objeto", "objeto_del_contrato"),
        ("Valor", "valor_del_contrato"), ("Valor pagado", "valor_pagado"),
        ("Fecha de firma", "fecha_de_firma"),
        ("Inicio", "fecha_de_inicio_del_contrato"), ("Fin", "fecha_de_fin_del_contrato"),
        ("Proceso de compra", "proceso_de_compra"),
    ]:
        if campo in c:
            lineas.append(f"- **{etiqueta}:** {_valor(campo, c[campo])}")

    url = c.get("urlproceso")
    if isinstance(url, dict):
        url = url.get("url")
    if url:
        lineas.append(f"- **Verificación pública:** {url}")

    filas_ad = []
    if not isinstance(adics, Exception):
        filas_ad = [
            {"tipo": fmt.recorta(a.get("tipo"), 30),
             "fecha": fmt.fecha(a.get("fecharegistro")),
             "descripción": fmt.recorta(a.get("descripcion"), 90)}
            for a in adics["filas"]
        ]
    if filas_ad:
        lineas += ["", f"### Modificaciones registradas ({len(filas_ad)})", "",
                   fmt.tabla_markdown(filas_ad)]
    elif isinstance(adics, Exception):
        lineas += ["", "_No se pudieron consultar las adiciones: la fuente falló. "
                       "No significa que el contrato no tenga modificaciones._"]
    else:
        lineas += ["", "_Sin modificaciones registradas en SECOP II._"]

    cuerpo = "\n".join(lineas)
    sobre = Sobre(datos=[c], total_coincidencias=1, detalle=Detalle.COMPLETO,
                  consulta=base["consulta"], fuente=_fuente(contratos))
    return sobre.render(lambda _f: cuerpo)


async def perfil_proveedor(documento: str, limite=20):
    """Totales agregados por proveedor, no volcado de filas."""
    doc = _solo_digitos(documento)
    if not doc:
        raise ErrorValidacion(
            "El documento debe contener dígitos (cédula o NIT sin dígito de verificación).",
            "Ejemplo: 900123456",
        )
    contratos = reg.SECOP["contratos"]
    donde = f"documento_proveedor = '{doc}'"

    tope = min(int(limite), 50)
    SELECT_TOP = "nombre_entidad, count(*) as total, sum(valor_del_contrato) as valor"
    total, resumen, top = await asyncio.gather(
        socrata.contar(contratos.id, donde=donde),
        socrata.consultar(contratos.id,
                          seleccionar="count(*) as total, sum(valor_del_contrato) as valor",
                          donde=donde, limite=1),
        socrata.consultar(contratos.id, seleccionar=SELECT_TOP, donde=donde,
                          agrupar="nombre_entidad", ordenar="valor DESC", limite=tope),
    )
    if total == 0:
        sobre = Sobre(datos=[], total_coincidencias=0, fuente=_fuente(contratos),
                      consulta=top["consulta"])
        sobre.advertir(
            "Cero contratos para ese documento en SECOP II. No es un fallo de la fuente: "
            "puede ser un proveedor solo presente en SECOP I, o un documento mal digitado."
        )
        return sobre.render(lambda _f: "_Sin contratos registrados._")

    agregado = resumen["filas"][0] if resumen["filas"] else {}
    filas = [
        {"entidad contratante": fmt.recorta(f.get("nombre_entidad"), 55),
         "contratos": fmt.numero(f.get("total")),
         "valor total": fmt.moneda(f.get("valor"))}
        for f in top["filas"]
    ]
    encabezado = (
        f"**Documento {doc}** · {fmt.numero(total)} contratos en SECOP II · "
        f"valor total {fmt.moneda(agregado.get('valor'))}"
    )
    sobre = Sobre(datos=filas, orden="valor DESC", consulta=top["consulta"],
                  fuente=_fuente(contratos))
    await agregacion.anota_total(sobre, top["filas"], tope, dataset_id=contratos.id,
                                 seleccionar=SELECT_TOP, agrupar="nombre_entidad",
                                 donde=donde)
    sobre.advertir(
        "Solo SECOP II. Para contratación anterior a la plataforma consulta también "
        "rpmr-utcd (SECOP Integrado)."
    )
    return sobre.render(lambda f: encabezado + "\n\n" + fmt.tabla_markdown(f))


async def resolver_entidad(nombre: str, limite=10):
    """Nombre coloquial -> NIT y nombre canónico. La búsqueda difusa por nombre
    libre es la principal fuente de falsos negativos en SECOP."""
    if not nombre or len(nombre.strip()) < 3:
        raise ErrorValidacion("Da al menos 3 caracteres del nombre.", "Ejemplo: 'invias'")

    consulta = nombre.strip()
    alias = reg.ALIAS_ENTIDADES.get(consulta.upper())
    termino = alias or consulta

    contratos = reg.SECOP["contratos"]
    tope = min(int(limite), 30)
    SELECT = "nombre_entidad, nit_entidad, count(*) as total"
    AGRUPAR = "nombre_entidad, nit_entidad"

    async def _busca(t):
        return await socrata.consultar(
            contratos.id, seleccionar=SELECT, donde=_filtro_texto("nombre_entidad", t),
            agrupar=AGRUPAR, ordenar="total DESC", limite=tope,
        )

    r = await _busca(termino)
    # La tabla de alias se cura a mano y caduca: si el alias no encuentra nada,
    # se reintenta con lo que escribió el usuario antes de decir que no existe.
    # Varias entidades se registran con su sigla y nada más.
    alias_fallido = bool(alias) and not r["filas"]
    if alias_fallido:
        r = await _busca(consulta)
    filas = [
        {"nombre canónico": fmt.recorta(f.get("nombre_entidad"), 65),
         "NIT": f.get("nit_entidad"),
         "contratos": fmt.numero(f.get("total"))}
        for f in r["filas"]
    ]
    sobre = Sobre(datos=filas, orden="total DESC", consulta=r["consulta"],
                  fuente=_fuente(contratos))
    # Ocultar coincidencias aquí es lo más caro de todo el servidor: es la
    # herramienta de desambiguación, y elegir el NIT equivocado creyendo que
    # se vieron todos contamina cada consulta posterior.
    await agregacion.anota_total(
        sobre, r["filas"], tope, dataset_id=contratos.id, seleccionar=SELECT,
        agrupar=AGRUPAR,
        donde=_filtro_texto("nombre_entidad", consulta if alias_fallido else termino))
    if alias and not alias_fallido:
        sobre.advertir(f"«{consulta}» se resolvió por alias curado a «{alias}».")
    elif alias_fallido:
        sobre.advertir(
            f"El alias curado «{alias}» no encontró nada; se buscó «{consulta}» "
            "literalmente. El alias está caduco: repórtalo."
        )
    if consulta.upper() in reg.SOLO_EN_INTEGRADO:
        sobre.advertir(
            f"«{consulta}» no aparece en SECOP II - Contratos con ningún nombre. "
            f"En SECOP Integrado (rpmr-utcd) figura como "
            f"«{reg.SOLO_EN_INTEGRADO[consulta.upper()]}»."
        )
    if not filas:
        sobre.advertir(
            "Sin coincidencias. Los nombres en SECOP no son los coloquiales "
            "(RTVC se escribe 'RADIO TELEVISION NACIONAL DE COLOMBIA.', con punto final). "
            "Prueba con una palabra distintiva del nombre largo."
        )
    else:
        sobre.advertir("Usa el NIT en las demás herramientas: es mucho más preciso que el nombre.")
    return sobre.render(lambda f: fmt.tabla_markdown(f))


async def agregar(agrupar_por="departamento", metrica="valor", donde_entidad=None,
                  desde=None, hasta=None, limite=20, formato="tabla", grafica=True):
    """Agregación server-side sobre contratos de SECOP II."""
    campos = {
        "departamento": "departamento",
        "entidad": "nombre_entidad",
        "modalidad": "modalidad_de_contratacion",
        "proveedor": "proveedor_adjudicado",
        "sector": "sector",
        "tipo": "tipo_de_contrato",
        "estado": "estado_contrato",
    }
    if agrupar_por not in campos:
        raise ErrorValidacion(
            f"agrupar_por debe ser uno de: {', '.join(campos)}.",
            "Para otras dimensiones usa co_datos_agregar con el dataset jbjy-vk9h.",
        )
    ds = reg.SECOP["contratos"]
    campo = campos[agrupar_por]

    partes = []
    if donde_entidad:
        partes.append(_filtro_texto("nombre_entidad", donde_entidad))
    if desde:
        partes.append(f"fecha_de_firma >= '{socrata.escapa(desde)}'")
    if hasta:
        partes.append(f"fecha_de_firma <= '{socrata.escapa(hasta)}'")
    donde = " AND ".join(partes) if partes else None

    seleccionar = f"{campo}, count(*) as contratos, sum(valor_del_contrato) as valor"
    # SECOP contiene valores imposibles por error de digitación —contratos de
    # 10^20 pesos— y una suma los arrastra entera. Se cuentan aparte para poder
    # decir cuánto del total es basura en vez de presentar la cifra a secas.
    donde_absurdos = " AND ".join(
        [p for p in [donde, f"{UMBRAL_ABSURDO_SOQL}"] if p])
    orden = "valor DESC" if metrica == "valor" else "contratos DESC"
    tope = min(int(limite), 50)
    r, absurdos, global_ = await asyncio.gather(
        socrata.consultar(ds.id, seleccionar=seleccionar, donde=donde,
                          agrupar=campo, ordenar=orden, limite=tope),
        socrata.consultar(ds.id, seleccionar="count(*) as n, sum(valor_del_contrato) as v",
                          donde=donde_absurdos, limite=1),
        socrata.consultar(ds.id, seleccionar="sum(valor_del_contrato) as v",
                          donde=donde, limite=1),
    )
    filas = [
        {agrupar_por: fmt.recorta(f.get(campo), 55),
         "contratos": fmt.numero(f.get("contratos")),
         "valor total": fmt.moneda(f.get("valor"))}
        for f in r["filas"]
    ]
    # Barras sobre la métrica por la que se ordenó, con los valores crudos.
    if grafica and formato == "tabla":
        clave = "valor" if metrica == "valor" else "contratos"
        for fila, dibujo in zip(filas, fmt.barras([f.get(clave) for f in r["filas"]])):
            fila["gráfica"] = dibujo
    sobre = Sobre(datos=filas, orden=orden, consulta=r["consulta"], fuente=_fuente(ds))
    await agregacion.anota_total(sobre, r["filas"], tope, dataset_id=ds.id,
                                 seleccionar=seleccionar, agrupar=campo, donde=donde)
    _advierte_absurdos(sobre, absurdos, global_)
    sobre.advertir("Montos nominales sin deflactar: no compares valores entre años distintos sin ajustar.")
    if not donde:
        sobre.advertir("Agregación sobre el dataset completo (~5,9 M filas): puede agotar el tiempo.")
    return sobre.render(lambda f: fmt.tabla_markdown(f), formato=formato)
