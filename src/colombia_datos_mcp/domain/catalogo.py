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
                    limite=20, offset=0, detalle="resumen"):
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
                  orden=ordenar or "orden natural de la fuente", detalle=nivel,
                  consulta=r["consulta"], fuente=fuente)
    if socrata.sin_token():
        sobre.advertir(AVISO_SIN_TOKEN)
    return sobre.render(lambda f: fmt.tabla_markdown(f))


async def agregar(dataset_id, agrupar_por, metricas="count(*) as total",
                  donde=None, teniendo=None, limite=20):
    """Agregación del lado del servidor: 20 grupos en vez de 10.000 filas."""
    if not agrupar_por:
        raise ErrorValidacion(
            "agrupar_por es obligatorio.",
            "Para contar sin agrupar usa co_datos_consultar con detalle='conteo'.",
        )
    await socrata.valida_campos(dataset_id, [c.strip() for c in agrupar_por.split(",")])

    esq = await socrata.esquema(dataset_id)
    seleccionar = f"{agrupar_por}, {metricas}"
    r = await socrata.consultar(
        dataset_id, seleccionar=seleccionar, donde=donde, agrupar=agrupar_por,
        teniendo=teniendo, ordenar="total DESC", limite=limite,
    )
    filas = [{k: _formatea_valor(k, v) for k, v in f.items()} for f in r["filas"]]
    sobre = Sobre(datos=filas, total_coincidencias=len(filas), orden="total DESC",
                  consulta=r["consulta"], fuente=_fuente_de(esq, dataset_id))
    if not donde:
        sobre.advertir(
            "Agregación sin filtro: hace full scan y en datasets grandes puede agotar "
            "el tiempo. Si falla, añade un filtro de fecha o territorio."
        )
    return sobre.render(lambda f: fmt.tabla_markdown(f))


# ------------------------------------------------------------- auxiliares --
def _campos_citados(*expresiones):
    """Extrae identificadores plausibles de las expresiones SoQL del modelo."""
    import re
    reservadas = {
        "and", "or", "not", "is", "null", "between", "like", "in", "count", "sum",
        "avg", "min", "max", "as", "asc", "desc", "true", "false", "upper", "lower",
        "starts_with", "date_trunc_y", "date_trunc_ym", "date_trunc_ymd",
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


def _proyecta(filas, columnas):
    if not columnas:
        return filas
    proyectadas = []
    for f in filas:
        fila = {}
        for c in columnas:
            if c in f:
                fila[c] = _formatea_valor(c, f[c])
        proyectadas.append(fila or f)
    return proyectadas


def _formatea_valor(campo: str, valor):
    nombre = campo.lower()
    if isinstance(valor, dict):
        valor = valor.get("url") or valor.get("description") or str(valor)
    if any(p in nombre for p in ("valor", "precio", "total", "cuantia", "saldo")):
        return fmt.moneda(valor)
    if "fecha" in nombre:
        return fmt.fecha(valor)
    return fmt.recorta(valor, 70)
