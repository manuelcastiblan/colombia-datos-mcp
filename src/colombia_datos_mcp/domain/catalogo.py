"""Herramientas de catálogo nacional sobre datos.gov.co."""

from __future__ import annotations

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

    total = await socrata.contar(dataset_id, donde=donde)
    if nivel is Detalle.CONTEO:
        sobre = Sobre(datos=[], total_coincidencias=total, detalle=nivel, fuente=fuente,
                      consulta=socrata.url_reproducible(
                          f"{socrata.BASE_DATOS}/resource/{dataset_id}.json",
                          {"$select": "count(*)", "$where": donde}))
        return sobre.render(lambda _f: f"**{fmt.numero(total)}** filas coinciden con el filtro.")

    limite = min(int(limite), 200 if nivel is Detalle.RESUMEN else 20)
    r = await socrata.consultar(dataset_id, seleccionar=seleccionar, donde=donde,
                                ordenar=ordenar, limite=limite, offset=offset)
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
                  donde=None, teniendo=None, limite=20, formato="tabla",
                  grafica=True):
    """Agregación del lado del servidor: 20 grupos en vez de 10.000 filas."""
    if not agrupar_por:
        raise ErrorValidacion(
            "agrupar_por es obligatorio.",
            "Para contar sin agrupar usa co_datos_consultar con detalle='conteo'.",
        )
    await socrata.valida_campos(dataset_id, [c.strip() for c in agrupar_por.split(",")])

    esq = await socrata.esquema(dataset_id)
    seleccionar = f"{agrupar_por}, {metricas}"
    orden = _orden_de_metrica(metricas, agrupar_por)
    r = await socrata.consultar(
        dataset_id, seleccionar=seleccionar, donde=donde, agrupar=agrupar_por,
        teniendo=teniendo, ordenar=orden, limite=limite,
    )
    filas = [{k: _formatea_valor(k, v) for k, v in f.items()} for f in r["filas"]]
    # La gráfica se calcula sobre los valores CRUDOS: los ya formateados llevan
    # separadores de miles y símbolo de moneda.
    alias = _alias_metrica(metricas)
    if grafica and formato == "tabla" and alias:
        dibujos = fmt.barras([f.get(alias) for f in r["filas"]])
        for fila, dibujo in zip(filas, dibujos):
            fila["gráfica"] = dibujo
    sobre = Sobre(datos=filas, total_coincidencias=len(filas), orden=orden,
                  consulta=r["consulta"], fuente=_fuente_de(esq, dataset_id))
    if not donde:
        sobre.advertir(
            "Agregación sin filtro: hace full scan y en datasets grandes puede agotar "
            "el tiempo. Si falla, añade un filtro de fecha o territorio."
        )
    return sobre.render(lambda f: fmt.tabla_markdown(f), formato=formato)


# ------------------------------------------------------------- auxiliares --
def _campos_citados(*expresiones):
    """Extrae identificadores plausibles de las expresiones SoQL del modelo."""
    import re
    # Toda palabra que falte aquí se toma por columna y produce un
    # [VALIDACION] falso: `distinct departamento` se rechazaba como si
    # `distinct` fuera un campo inexistente.
    reservadas = {
        "and", "or", "not", "is", "null", "between", "like", "in", "count", "sum",
        "avg", "min", "max", "as", "asc", "desc", "true", "false", "upper", "lower",
        "starts_with", "date_trunc_y", "date_trunc_ym", "date_trunc_ymd",
        "distinct", "case", "when", "then", "else", "end", "coalesce", "nullif",
        "abs", "round", "floor", "ceil", "length", "trim", "concat", "substring",
        "replace", "contains", "sqrt", "pow", "exp", "ln", "log", "signum",
        "stddev_pop", "stddev_samp", "var_pop", "var_samp", "median",
        "count_distinct", "date_extract_y", "date_extract_m", "date_extract_d",
        "date_extract_hh", "date_extract_mm", "date_extract_ss", "date_extract_dow",
        "date_extract_woy", "within_circle", "within_box", "within_polygon",
        "distance_in_meters", "simplify", "convex_hull", "extent", "num_points",
        "asin", "acos", "atan", "sin", "cos", "tan", "to_floating_timestamp",
        "limit", "offset", "order", "group", "having", "select", "where", "by",
    }
    encontrados = set()
    for e in expresiones:
        if not e:
            continue
        sin_literales = re.sub(r"'[^']*'", " ", str(e))
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", sin_literales):
            if token.lower() not in reservadas:
                encontrados.add(token)
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


def _formatea_valor(campo: str, valor):
    nombre = campo.lower()
    if isinstance(valor, dict):
        valor = valor.get("url") or valor.get("description") or str(valor)
    if fmt.es_monetario(nombre):
        return fmt.moneda(valor)
    if fmt.es_conteo(nombre):
        return fmt.numero(valor)
    if "fecha" in nombre:
        return fmt.fecha(valor)
    return fmt.recorta(valor, 70)
