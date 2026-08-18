"""Herramientas de contratación pública (SECOP I, SECOP II, TVEC)."""

from __future__ import annotations

import asyncio
import re

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
    """Los acentos vienen destruidos en origen: comparar sin acentos y en
    mayúsculas es lo único que funciona de forma fiable."""
    return f"upper({campo}) like '%{socrata.escapa(fmt.sin_acentos(valor))}%'"


def _solo_digitos(valor: str) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def _construye_where(ds: reg.Dataset, **filtros) -> str | None:
    c = ds.campos_clave
    partes = []
    if filtros.get("entidad") and c.get("entidad"):
        partes.append(_filtro_texto(c["entidad"], filtros["entidad"]))
    if filtros.get("nit_entidad") and c.get("nit_entidad"):
        nit = _solo_digitos(filtros["nit_entidad"])
        partes.append(f"{c['nit_entidad']} = '{nit}'")
    if filtros.get("proveedor") and c.get("proveedor"):
        partes.append(_filtro_texto(c["proveedor"], filtros["proveedor"]))
    if filtros.get("documento_proveedor") and c.get("doc_proveedor"):
        doc = _solo_digitos(filtros["documento_proveedor"])
        partes.append(f"{c['doc_proveedor']} = '{doc}'")
    if filtros.get("departamento") and c.get("departamento"):
        partes.append(_filtro_texto(c["departamento"], filtros["departamento"]))
    if filtros.get("modalidad") and c.get("modalidad"):
        partes.append(_filtro_texto(c["modalidad"], filtros["modalidad"]))
    if filtros.get("desde") and c.get("fecha"):
        partes.append(f"{c['fecha']} >= '{socrata.escapa(filtros['desde'])}'")
    if filtros.get("hasta") and c.get("fecha"):
        partes.append(f"{c['fecha']} <= '{socrata.escapa(filtros['hasta'])}'")
    if filtros.get("valor_min") and c.get("valor"):
        partes.append(f"{c['valor']} >= {float(filtros['valor_min'])}")
    return " AND ".join(partes) if partes else None


async def _buscar(clave: str, detalle="resumen", limite=20, offset=0, **filtros):
    ds = reg.SECOP[clave]
    nivel = Detalle(detalle)
    donde = _construye_where(ds, **filtros)

    total = await socrata.contar(ds.id, donde=donde)
    if nivel is Detalle.CONTEO:
        sobre = Sobre(datos=[], total_coincidencias=total, detalle=nivel, fuente=_fuente(ds),
                      consulta=socrata.url_reproducible(
                          f"{socrata.BASE_DATOS}/resource/{ds.id}.json",
                          {"$select": "count(*)", "$where": donde}))
        return sobre.render(lambda _f: f"**{fmt.numero(total)}** {ds.unidad}(s) coinciden.")

    orden = f"{ds.campos_clave.get('valor')} DESC" if ds.campos_clave.get("valor") else ":id"
    r = await socrata.consultar(ds.id, donde=donde, ordenar=orden,
                                limite=min(int(limite), 100), offset=offset)
    columnas = list(ds.campos_resumen) if nivel is Detalle.RESUMEN else None
    filas = _proyecta(r["filas"], columnas, ds)

    sobre = Sobre(datos=filas, total_coincidencias=total, offset=offset, orden=orden,
                  detalle=nivel, consulta=r["consulta"], fuente=_fuente(ds))
    sobre.advertir(f"Unidad de análisis: {ds.unidad}. No sumes filas de datasets distintos.")
    if not donde:
        sobre.advertir("Sin filtros: estás viendo los registros de mayor valor del dataset completo.")
    return sobre.render(lambda f: fmt.tabla_markdown(f))


def _proyecta(filas, columnas, ds):
    salida = []
    for f in filas:
        cols = columnas or list(f.keys())
        fila = {}
        for c in cols:
            if c not in f:
                continue
            fila[_etiqueta(c)] = _valor(c, f[c])
        salida.append(fila or {k: _valor(k, v) for k, v in f.items()})
    return salida


def _etiqueta(campo: str) -> str:
    return campo.replace("_", " ").strip()


def _valor(campo: str, valor):
    n = campo.lower()
    if isinstance(valor, dict):
        valor = valor.get("url") or str(valor)
    if any(p in n for p in ("valor", "precio", "total", "cuantia", "saldo")):
        return fmt.moneda(valor)
    if "fecha" in n:
        return fmt.fecha(valor)
    if "objeto" in n or "descripcion" in n or "procedimiento" in n:
        return fmt.recorta(valor, 80)
    return fmt.recorta(valor, 55)


# ------------------------------------------------------------ públicas ----
async def buscar_contratos(entidad=None, nit_entidad=None, proveedor=None,
                           documento_proveedor=None, departamento=None, modalidad=None,
                           desde=None, hasta=None, valor_min=None,
                           detalle="resumen", limite=20, offset=0):
    return await _buscar("contratos", detalle=detalle, limite=limite, offset=offset,
                         entidad=entidad, nit_entidad=nit_entidad, proveedor=proveedor,
                         documento_proveedor=documento_proveedor, departamento=departamento,
                         modalidad=modalidad, desde=desde, hasta=hasta, valor_min=valor_min)


async def buscar_procesos(entidad=None, nit_entidad=None, departamento=None, modalidad=None,
                          desde=None, hasta=None, detalle="resumen", limite=20, offset=0):
    return await _buscar("procesos", detalle=detalle, limite=limite, offset=offset,
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

    total, resumen, top = await asyncio.gather(
        socrata.contar(contratos.id, donde=donde),
        socrata.consultar(contratos.id,
                          seleccionar="count(*) as total, sum(valor_del_contrato) as valor",
                          donde=donde, limite=1),
        socrata.consultar(contratos.id,
                          seleccionar="nombre_entidad, count(*) as total, sum(valor_del_contrato) as valor",
                          donde=donde, agrupar="nombre_entidad", ordenar="valor DESC",
                          limite=min(int(limite), 50)),
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
    sobre = Sobre(datos=filas, total_coincidencias=len(filas), orden="valor DESC",
                  consulta=top["consulta"], fuente=_fuente(contratos))
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
    r = await socrata.consultar(
        contratos.id,
        seleccionar="nombre_entidad, nit_entidad, count(*) as total",
        donde=_filtro_texto("nombre_entidad", termino),
        agrupar="nombre_entidad, nit_entidad",
        ordenar="total DESC",
        limite=min(int(limite), 30),
    )
    filas = [
        {"nombre canónico": fmt.recorta(f.get("nombre_entidad"), 65),
         "NIT": f.get("nit_entidad"),
         "contratos": fmt.numero(f.get("total"))}
        for f in r["filas"]
    ]
    sobre = Sobre(datos=filas, total_coincidencias=len(filas), orden="total DESC",
                  consulta=r["consulta"], fuente=_fuente(contratos))
    if alias:
        sobre.advertir(f"«{consulta}» se resolvió por alias curado a «{alias}».")
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
                  desde=None, hasta=None, limite=20):
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
    orden = "valor DESC" if metrica == "valor" else "contratos DESC"
    r = await socrata.consultar(ds.id, seleccionar=seleccionar, donde=donde,
                                agrupar=campo, ordenar=orden, limite=min(int(limite), 50))
    filas = [
        {agrupar_por: fmt.recorta(f.get(campo), 55),
         "contratos": fmt.numero(f.get("contratos")),
         "valor total": fmt.moneda(f.get("valor"))}
        for f in r["filas"]
    ]
    sobre = Sobre(datos=filas, total_coincidencias=len(filas), orden=orden,
                  consulta=r["consulta"], fuente=_fuente(ds))
    sobre.advertir("Montos nominales sin deflactar: no compares valores entre años distintos sin ajustar.")
    if not donde:
        sobre.advertir("Agregación sobre el dataset completo (~5,9 M filas): puede agotar el tiempo.")
    return sobre.render(lambda f: fmt.tabla_markdown(f))
