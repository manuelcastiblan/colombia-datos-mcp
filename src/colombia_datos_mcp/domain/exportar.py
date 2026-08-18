"""Exportación a disco: la única operación del servidor que ESCRIBE.

Todo lo demás es de solo lectura. Aquí hay tres decisiones deliberadas:

* **El destino no es un parámetro libre.** Se recibe un nombre de archivo, no
  una ruta, y se escribe siempre bajo `CO_EXPORT_DIR`. Un modelo que compone la
  ruta a partir del texto del usuario no debe poder escribir en `~/.ssh`.
* **Se pagina hasta el final**, no hasta donde llegue una página. Exportar existe
  precisamente para saltarse el presupuesto de tokens, así que el límite es de
  filas, no de tamaño de respuesta.
* **El recorte se anuncia.** Si se alcanza `max_filas` antes que el total, el
  fichero queda incompleto y la respuesta lo dice con las dos cifras.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from ..adapters import socrata
from ..core import format as fmt
from ..core.envelope import Fuente, Sobre
from ..core.errors import ErrorValidacion

DIR_EXPORT = Path(
    os.environ.get("CO_EXPORT_DIR", Path.home() / "colombia-datos-export")
)

# Tamaño de página al descargar. Socrata acepta más, pero páginas gigantes
# alargan el timeout y un fallo obliga a repetir todo el tramo.
PAGINA = 1000
MAX_FILAS_TOPE = 200_000

EXTENSIONES = {"csv": ".csv", "json": ".json", "parquet": ".parquet"}


def _nombre_seguro(nombre: str, formato: str) -> str:
    """Reduce el nombre a un fichero plano, sin rutas ni sorpresas."""
    base = Path(str(nombre or "").strip()).name          # descarta directorios
    base = re.sub(r"[^\w.\- ]", "_", base, flags=re.UNICODE).strip(" .")
    base = re.sub(r"\s+", "_", base)
    if not base:
        raise ErrorValidacion(
            "nombre_archivo vacío o no utilizable.",
            "Dale un nombre simple, sin carpetas: 'contratos_anla'.",
        )
    esperada = EXTENSIONES[formato]
    if not base.lower().endswith(esperada):
        base = Path(base).stem + esperada
    return base


def _escribe(ruta: Path, filas: list[dict], formato: str) -> None:
    if formato == "json":
        ruta.write_text(fmt.json_texto(filas), encoding="utf-8")
        return
    if formato == "parquet":
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            raise ErrorValidacion(
                "El formato parquet necesita pyarrow, que no está instalado.",
                "Instala `pyarrow` o exporta en csv, que no requiere nada.",
            ) from None
        columnas = fmt.columnas_union(filas)
        tabla = pa.table({c: [f.get(c) for f in filas] for c in columnas})
        pq.write_table(tabla, ruta)
        return
    # CSV con BOM: sin él, Excel en Windows destroza los acentos al abrirlo.
    ruta.write_text("﻿" + fmt.csv_texto(filas), encoding="utf-8")


async def exportar(dataset_id: str, nombre_archivo: str, donde=None, seleccionar=None,
                   ordenar=None, formato: str = "csv", max_filas: int = 50_000):
    """Descarga un dataset filtrado y lo guarda. Devuelve la ruta y el conteo."""
    if formato not in EXTENSIONES:
        raise ErrorValidacion(
            f"formato debe ser uno de: {', '.join(EXTENSIONES)}.",
            "csv es el que no necesita dependencias extra.",
        )
    max_filas = max(1, min(int(max_filas), MAX_FILAS_TOPE))
    nombre = _nombre_seguro(nombre_archivo, formato)

    await socrata.valida_campos(dataset_id, _identificadores(seleccionar, donde, ordenar))
    total = await socrata.contar(dataset_id, donde=donde)

    filas: list[dict] = []
    while len(filas) < min(total, max_filas):
        pagina = await socrata.consultar(
            dataset_id, seleccionar=seleccionar, donde=donde, ordenar=ordenar,
            limite=min(PAGINA, max_filas - len(filas)), offset=len(filas),
        )
        nuevas = pagina["filas"]
        if not nuevas:
            break            # la fuente se quedó sin filas antes que el conteo
        filas.extend(nuevas)

    # Sin `total_coincidencias`: el sobre diría "0 fila(s) de N" y añadiría el
    # aviso de "estás viendo una parte", que aquí es justo lo contrario de lo
    # que pasó. Las cifras van en el cuerpo, que es donde se leen.
    sobre = Sobre(datos=[], orden=ordenar, fuente=Fuente(id=dataset_id),
                  mostrar_conteo=False)
    if not filas:
        sobre.advertir(
            "Cero filas: no se escribió ningún fichero. No es un fallo de la "
            "fuente, es que el filtro no encontró nada."
        )
        return sobre.render(lambda _f: "_Sin filas que exportar._")

    try:
        DIR_EXPORT.mkdir(parents=True, exist_ok=True)
        ruta = DIR_EXPORT / nombre
        _escribe(ruta, filas, formato)
    except OSError as exc:
        raise ErrorValidacion(
            f"No se pudo escribir {nombre}: {exc}",
            f"Comprueba permisos sobre {DIR_EXPORT}, o cambia CO_EXPORT_DIR.",
        ) from None

    tam = ruta.stat().st_size
    # El estructurado lleva la ficha del fichero, no filas: así un cliente puede
    # encadenar la exportación con lo que venga después sin parsear la prosa.
    sobre.datos = [{
        "ruta": str(ruta), "filas": len(filas), "bytes": tam,
        "formato": formato, "completo": len(filas) >= total,
        "total_coincidencias": total,
    }]
    cuerpo = (
        f"Exportadas **{fmt.numero(len(filas))}** fila(s) a `{ruta}` "
        f"({fmt.numero(tam)} bytes, {formato})."
    )
    if len(filas) < total:
        sobre.advertir(
            f"El fichero tiene {len(filas)} de {total} filas: se alcanzó "
            f"max_filas={max_filas}. NO es el conjunto completo."
        )
    else:
        sobre.advertir("El fichero contiene el conjunto completo del filtro.")
    if formato == "csv":
        sobre.advertir(
            "El CSV lleva BOM para que Excel respete los acentos. Si lo lees con "
            "pandas, usa encoding='utf-8-sig'."
        )
    return sobre.render(lambda _f: cuerpo)


def _identificadores(*expresiones):
    """Mismo criterio que en `catalogo`: valida columnas contra el esquema."""
    from .catalogo import _campos_citados

    return _campos_citados(*expresiones)
