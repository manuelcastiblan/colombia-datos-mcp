"""Lo que toda agregación debe declarar sobre sí misma.

Existe porque el mismo error apareció cinco veces: `total_coincidencias =
len(filas)` sobre un resultado que ya venía recortado por `$limit`, de modo
que una tabla de 10 grupos afirmaba «10 de 10» habiendo 11, o 2.881. No es un
error de más, sino de **parecer completo justo cuando no se está**, que es lo
único que el sobre existe para impedir.

Cada sitio lo arreglaba por su cuenta o no lo arreglaba. Ahora hay uno solo.
"""

from __future__ import annotations

from ..adapters import socrata
from ..core.envelope import Sobre

# El aviso por defecto del sobre manda a agregar; dentro de una agregación ese
# consejo no aplica, porque los grupos ocultos no se recuperan agregando otra
# vez sino ampliando la ventana.
AVISO_PARCIAL = ("Los grupos no mostrados NO están en esta tabla: cualquier suma "
                 "sobre estas filas es parcial. Sube `limite` o afina `donde`.")


async def anota_total(
    sobre: Sobre,
    filas: list,
    limite: int,
    *,
    dataset_id: str,
    seleccionar: str,
    agrupar: str,
    donde: str | None = None,
    teniendo: str | None = None,
    contable: bool = True,
) -> None:
    """Pone en el sobre cuántos grupos hay **de verdad**.

    Tres casos, en orden de coste:

    1. La fuente devolvió menos filas que el límite: no hay más, así que el
       total es exacto y no cuesta una sola petición.
    2. Llenó el límite: hay que contar los grupos aparte, y eso solo se puede
       anidando (`count(*)` sobre una consulta agrupada da el tamaño de cada
       grupo, no cuántos hay).
    3. La fuente no admite anidar, o la consulta ya venía anidada y contarla
       exigiría una tercera etapa: el total se declara **desconocido**. Un
       total ignorado se advierte; uno inventado contamina lo que toque.
    """
    sobre.aviso_parcial = AVISO_PARCIAL
    if len(filas) < limite:
        sobre.total_coincidencias = len(filas)
        return
    sobre.total_coincidencias = (
        await socrata.contar_grupos(dataset_id, seleccionar, agrupar,
                                    donde=donde, teniendo=teniendo)
        if contable else None
    )
    if sobre.total_coincidencias is None:
        sobre.advertir(
            f"Total de grupos desconocido: no se pudieron contar. Puede haber "
            f"más de los {len(filas)} mostrados; no los tomes por todos."
        )
