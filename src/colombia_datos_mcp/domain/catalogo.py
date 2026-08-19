"""Herramientas de catálogo nacional sobre datos.gov.co."""

from __future__ import annotations

import asyncio

from . import agregacion
from ..adapters import socrata
from ..core import format as fmt
from ..core.budget import Detalle
from ..core.envelope import Fuente, Sobre
from ..core.errors import ErrorNoEncontrado, ErrorValidacion
from ..registry import datasets as reg

AVISO_SIN_TOKEN = (
    "Sin SOCRATA_APP_TOKEN configurado: sujeto a throttling por IP. "
    "El servidor funciona igual, pero con token es más estable."
)


def _fuente_de(esq: dict | None, dataset_id: str) -> Fuente:
    if not esq:
        return Fuente(id=dataset_id)
    return Fuente(
        id=esq.get("id") or dataset_id,
        nombre=esq.get("nombre") or "",
        actualizado=fmt.fecha(esq.get("actualizado")),
        licencia=esq.get("licencia"),
        atribucion=esq.get("atribucion"),
    )


async def buscar_datasets(consulta=None, categoria=None, entidad=None, limite=20, offset=0):
    """Busca en el catálogo. Por defecto solo datasets oficiales."""
    atribucion = reg.ATRIBUCIONES.get(entidad, entidad) if entidad else None
    r = await socrata.buscar_datasets(
        consulta=consulta, categoria=categoria, atribucion=atribucion,
        limite=limite, offset=offset,
    )
    crudo = r["datos"]
    resultados = crudo.get("results") or []

    filas = []
    for item in resultados:
        rec = item.get("resource", {})
        clasif = item.get("classification", {}) or {}
        filas.append({
            "id": rec.get("id"),
            "nombre": fmt.recorta(rec.get("name"), 70),
            "entidad": fmt.recorta(rec.get("attribution"), 45),
            "categoría": clasif.get("domain_category") or "-",
            "actualizado": fmt.fecha(rec.get("updatedAt")),
            "vistas": fmt.numero((rec.get("page_views") or {}).get("page_views_total")),
        })

    sobre = Sobre(
        datos=filas,
        total_coincidencias=crudo.get("resultSetSize"),
        offset=offset,
        orden="relevancia",
        consulta=r["consulta"],
    )
    if entidad and atribucion != entidad:
        sobre.advertir(
            f"Se usó la cadena de atribución exacta «{atribucion}». "
            "El facet de Socrata solo funciona con el literal completo."
        )
    if not filas:
        sobre.advertir(
            "Cero resultados. Ojo: no es lo mismo que un fallo de la fuente. "
            "Prueba con menos palabras o sin filtro de entidad."
        )
    if socrata.sin_token():
        sobre.advertir(AVISO_SIN_TOKEN)
    return sobre.render(lambda f: fmt.tabla_markdown(f))


async def describir_dataset(dataset_id: str):
    """Esquema en vivo: campo técnico + nombre legible + tipo + descripción."""
    esq = await socrata.esquema(dataset_id)
    if not esq:
        raise ErrorNoEncontrado(
            f"No se encontró el dataset {dataset_id} en el catálogo.",
            "Los IDs de Socrata rotan. Búscalo por nombre con co_datos_buscar_datasets.",
        )

    filas = [
        {
            "campo": c["campo"],
            "nombre": fmt.recorta(c["nombre"], 45),
            "tipo": c["tipo"],
            "descripción": fmt.recorta(c["descripcion"], 70),
        }
        for c in esq["columnas"]
    ]
    sobre = Sobre(
        datos=filas,
        total_coincidencias=len(filas),
        detalle=Detalle.COMPLETO,
        orden="posición",
        fuente=_fuente_de(esq, dataset_id),
    )
    if esq.get("es_vista_derivada") or esq.get("provenance") == "community":
        sobre.advertir(
            "Este asset es una VISTA DERIVADA o comunitaria, no la fuente oficial. "
            "Busca el dataset original antes de citar cifras."
        )
    conocido = reg.por_id(dataset_id)
    if conocido:
        sobre.advertir(f"Unidad de análisis: {conocido.unidad}.")
        for n in conocido.notas:
            sobre.advertir(n)
    return sobre.render(lambda f: fmt.tabla_markdown(f))


async def consultar(dataset_id, seleccionar=None, donde=None, ordenar=None,
                    limite=20, offset=0, detalle="resumen", formato="tabla"):
    """SoQL con allow-list de columnas derivada del esquema vivo."""
    nivel = Detalle(detalle)
    esq = await socrata.esquema(dataset_id)
    fuente = _fuente_de(esq, dataset_id)

    await socrata.valida_campos(dataset_id, _campos_citados(seleccionar, donde, ordenar))

    if nivel is Detalle.CONTEO:
        total = await socrata.contar(dataset_id, donde=donde)
        sobre = Sobre(datos=[], total_coincidencias=total, detalle=nivel, fuente=fuente,
                      consulta=socrata.url_reproducible(
                          f"{socrata.BASE_DATOS}/resource/{dataset_id}.json",
                          {"$select": "count(*)", "$where": donde}))
        return sobre.render(lambda _f: f"**{fmt.numero(total)}** filas coinciden con el filtro.")

    limite = min(int(limite), 200 if nivel is Detalle.RESUMEN else 20)
    # El conteo y la página iban encadenados sin motivo: dos viajes en serie a
    # la misma fuente, y en un dataset de millones de filas el `count(*)` no es
    # gratis. Ahora la latencia es la del más lento, no la suma de los dos.
    total, r = await asyncio.gather(
        socrata.contar(dataset_id, donde=donde),
        socrata.consultar(dataset_id, seleccionar=seleccionar, donde=donde,
                          ordenar=ordenar, limite=limite, offset=offset),
    )
    filas = r["filas"]
    if nivel is Detalle.RESUMEN:
        conocido = reg.por_id(dataset_id)
        columnas = list(conocido.campos_resumen) if conocido and conocido.campos_resumen else None
        filas = _proyecta(filas, columnas)

    sobre = Sobre(datos=filas, total_coincidencias=total, offset=offset,
                  orden=r.get("orden") or ordenar, detalle=nivel,
                  consulta=r["consulta"], fuente=fuente)
    if socrata.sin_token():
        sobre.advertir(AVISO_SIN_TOKEN)
    return sobre.render(lambda f: fmt.tabla_markdown(f), formato=formato)


async def agregar(dataset_id, agrupar_por, metricas="count(*) as total",
                  donde=None, teniendo=None, luego=None, limite=20,
                  formato="tabla", grafica=True):
    """Agregación del lado del servidor: 20 grupos en vez de 10.000 filas.

    `luego` encadena una segunda etapa sobre el resultado de la primera
    (operador `|>` de SoQL). Es la única forma de agregar SOBRE los grupos:
    «cuántas personas tienen más de un contrato» no es un `count(*)` con
    `having` —eso cuenta contratos por persona—, sino un `count(*)` sobre la
    tabla que ese `having` deja.
    """
    if not agrupar_por:
        raise ErrorValidacion(
            "agrupar_por es obligatorio.",
            "Para contar sin agrupar usa co_datos_consultar con detalle='conteo'.",
        )
    await socrata.valida_campos(dataset_id, [c.strip() for c in agrupar_por.split(",")])

    esq = await socrata.esquema(dataset_id)
    seleccionar = f"{agrupar_por}, {metricas}"
    if luego:
        # La segunda etapa solo ve los alias de la primera, así que ordenar por
        # la métrica interna sería un 400 seguro.
        alias_final = _alias_metrica(luego)
        orden = f"{alias_final} DESC" if alias_final else None
        consulta = socrata.arma_soql(seleccionar, donde=donde, agrupar=agrupar_por,
                                     teniendo=teniendo, luego=luego, ordenar=orden,
                                     limite=limite)
        r = await socrata.consultar_soql(dataset_id, consulta)
    else:
        orden = _orden_de_metrica(metricas, agrupar_por)
        r = await socrata.consultar(
            dataset_id, seleccionar=seleccionar, donde=donde, agrupar=agrupar_por,
            teniendo=teniendo, ordenar=orden, limite=limite,
        )
    claves = {c.strip().lower() for c in agrupar_por.split(",")}
    filas = [{k: _formatea_valor(k, v, es_metrica=k.lower() not in claves)
              for k, v in f.items()} for f in r["filas"]]
    # La gráfica se calcula sobre los valores CRUDOS: los ya formateados llevan
    # separadores de miles y símbolo de moneda.
    alias = _alias_metrica(luego or metricas)
    if grafica and formato == "tabla" and alias:
        dibujos = fmt.barras([f.get(alias) for f in r["filas"]])
        for fila, dibujo in zip(filas, dibujos):
            fila["gráfica"] = dibujo

    sobre = Sobre(datos=filas, orden=orden, consulta=r["consulta"],
                  fuente=_fuente_de(esq, dataset_id))
    # `contable=not luego`: contar las filas de una 2.ª etapa exigiría una 3.ª.
    await agregacion.anota_total(sobre, r["filas"], limite, dataset_id=dataset_id,
                                 seleccionar=seleccionar, agrupar=agrupar_por,
                                 donde=donde, teniendo=teniendo, contable=not luego)
    if not donde:
        sobre.advertir(
            "Agregación sin filtro: hace full scan y en datasets grandes puede agotar "
            "el tiempo. Si falla, añade un filtro de fecha o territorio."
        )
    return sobre.render(lambda f: fmt.tabla_markdown(f), formato=formato)


# ------------------------------------------------------------- auxiliares --
# Palabras que aparecen SUELTAS en SoQL. No incluye funciones: una función va
# siempre seguida de `(`, y eso se detecta en vez de enumerarse.
_PALABRAS_SOQL = {
    "and", "or", "not", "is", "null", "between", "like", "in", "as", "asc", "desc",
    "true", "false", "distinct", "case", "when", "then", "else", "end", "by",
    "select", "where", "group", "having", "order", "limit", "offset",
}


def _campos_citados(*expresiones):
    """Identificadores que tienen que existir en el esquema.

    Antes se contrastaban contra una lista cableada de ~60 nombres de función y
    todo lo que faltara se tomaba por columna, así que el validador **fallaba
    cerrado** sobre SoQL perfectamente válido: `char_length(x)` se rechazaba
    porque la función no estaba en la lista, y `x as entidad` porque el alias
    tampoco. Cada rechazo falso costaba además ~900 tokens listando el esquema.

    Las dos reglas de verdad no necesitan vocabulario:

    * un identificador seguido de `(` es una **función**;
    * un identificador precedido de `as` es un **alias** que se está declarando.

    Ninguno de los dos es una columna, y toda función y todo alias los cumplen,
    presentes y futuros. Lo que queda por enumerar son solo las palabras sueltas
    del lenguaje, que sí son un conjunto cerrado.
    """
    import re
    encontrados = set()
    for e in expresiones:
        if not e:
            continue
        sin_literales = re.sub(r"'[^']*'", " ", str(e))
        previo = ""
        for m in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\s*(\()?", sin_literales):
            token, es_funcion = m.group(1), bool(m.group(2))
            bajo = token.lower()
            if not (es_funcion or bajo in _PALABRAS_SOQL or previo == "as"):
                encontrados.add(token)
            previo = bajo
    return encontrados


def _alias_metrica(metricas: str) -> str | None:
    """Primer alias declarado en `metricas`, que es la columna de la métrica."""
    import re
    alias = re.findall("(?:^|[ ,(])as +([A-Za-z_][A-Za-z0-9_]*)", str(metricas or ""), re.I)
    return alias[0] if alias else None


def _orden_de_metrica(metricas: str, agrupar_por: str) -> str:
    """Ordena por el alias real de la métrica, no por uno cableado.

    `ordenar="total DESC"` estaba fijo mientras `metricas` era libre: pedir
    `sum(valor_del_contrato) as valor` producía un 400 de Socrata
    («No such column: total») en una herramienta cuyo único fin es agregar.
    """
    alias = _alias_metrica(metricas)
    return f"{alias} DESC" if alias else agrupar_por.split(",")[0].strip()


def _proyecta(filas, columnas):
    """Igual que en `domain.secop`: las columnas se toman de TODAS las filas.

    Socrata omite los campos nulos, así que fiarse de la primera fila pierde en
    silencio los datos de las siguientes.
    """
    if not columnas or not filas:
        return filas
    presentes = [c for c in columnas if any(c in f for f in filas)]
    proyectadas = []
    for f in filas:
        fila = {c: _formatea_valor(c, f[c]) if c in f else "" for c in presentes}
        proyectadas.append(fila or f)
    return proyectadas


def _formatea_valor(campo: str, valor, es_metrica: bool = False):
    nombre = campo.lower()
    if isinstance(valor, dict):
        valor = valor.get("url") or valor.get("description") or str(valor)
    if fmt.es_identificador(nombre):
        return fmt.recorta(valor, 70)
    if fmt.es_monetario(nombre):
        return fmt.moneda(valor)
    if fmt.es_conteo(nombre):
        return fmt.numero(valor)
    if "fecha" in nombre:
        return fmt.fecha(valor)
    # En una agregación, toda columna que no sea clave de grupo es una métrica.
    # El alias lo elige quien consulta —`personas`, `entidades`, `municipios`—
    # y ningún vocabulario cerrado va a adivinarlo: mejor la regla estructural.
    if es_metrica and fmt.es_entero(valor):
        return fmt.numero(valor)
    return fmt.recorta(valor, 70)
