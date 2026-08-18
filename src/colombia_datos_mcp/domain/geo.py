"""DIVIPOLA: la clave de join universal del servidor (ADR-03)."""

from __future__ import annotations

from ..adapters import socrata
from ..core import format as fmt
from ..core import texto
from ..core.budget import Detalle
from ..core.coords import normaliza_par
from ..core.envelope import Fuente, Sobre
from ..core.errors import ErrorValidacion
from ..registry import datasets as reg

_LIC = "CC BY-SA 4.0"


async def divipola(consulta=None, codigo=None, nivel="municipio",
                   con_coordenadas=True, limite=25, offset=0, formato="tabla"):
    """Resuelve nombre <-> código DIVIPOLA, con coordenadas.

    Los códigos son TEXTO con ceros a la izquierda (`05`, `08`). Tratarlos como
    enteros rompe el join con todo lo demás.
    """
    if nivel not in ("departamento", "municipio", "centro_poblado"):
        raise ErrorValidacion(
            "nivel debe ser 'departamento', 'municipio' o 'centro_poblado'.",
            "Usa 'municipio' para el código DIVIPOLA de 5 dígitos.",
        )
    if nivel == "centro_poblado":
        return await _centros(consulta, codigo, con_coordenadas, limite, offset, formato)
    return await _municipios(consulta, codigo, nivel, con_coordenadas, limite, offset, formato)


def _sin_coincidencias(ds, consulta, campo, offset):
    """Cero honesto: el término no existe en la fuente, y se dice.

    Devolver esto sin consultar evita el peor resultado posible, que es una
    tabla vacía indistinguible de "la fuente no tiene datos".
    """
    sobre = Sobre(datos=[], total_coincidencias=0, offset=offset,
                  fuente=Fuente(id=ds.id, nombre=ds.nombre, licencia=_LIC))
    sobre.advertir(
        f"«{consulta}» no corresponde a ningún valor de `{campo}` en DIVIPOLA. "
        "La fuente responde bien; revisa la grafía o busca por código."
    )
    return sobre.render(lambda _f: "_Sin coincidencias._")


async def _municipios(consulta, codigo, nivel, con_coordenadas, limite, offset,
                      formato="tabla"):
    ds = reg.DIVIPOLA_MUNICIPIOS
    partes = []
    if codigo:
        c = str(codigo).strip()
        campo = "cod_dpto" if nivel == "departamento" or len(c) <= 2 else "cod_mpio"
        partes.append(f"{campo} = '{socrata.escapa(c)}'")
    avisos = []
    if consulta:
        campo = "dpto" if nivel == "departamento" else "nom_mpio"
        filtro, valores, truncado = await socrata.filtro_categorico(ds.id, campo, consulta)
        if filtro is None:
            return _sin_coincidencias(ds, consulta, campo, offset)
        if truncado:
            avisos.append(f"«{consulta}» casa con más de {texto.MAX_VALORES_EN} nombres; "
                          "se usaron los primeros. Afina el término.")
        partes.append(filtro)
    donde = " AND ".join(partes) if partes else None

    total = await socrata.contar(ds.id, donde=donde)
    r = await socrata.consultar(ds.id, donde=donde, ordenar="cod_mpio",
                                limite=min(int(limite), 200), offset=offset)

    filas, sin_coord = [], 0
    for f in r["filas"]:
        fila = {
            "cod_dpto": f.get("cod_dpto"),
            "departamento": fmt.limpia_texto(f.get("dpto")),
            "cod_mpio": f.get("cod_mpio"),
            "municipio": fmt.limpia_texto(f.get("nom_mpio")),
            "tipo": fmt.limpia_texto(f.get("tipo_municipio")),
        }
        if con_coordenadas:
            par = normaliza_par(f)
            if par:
                fila["lon"], fila["lat"] = round(par[0], 6), round(par[1], 6)
            else:
                fila["lon"] = fila["lat"] = None
                sin_coord += 1
        filas.append(fila)

    sobre = Sobre(datos=filas, total_coincidencias=total, offset=offset, orden="cod_mpio",
                  consulta=r["consulta"],
                  fuente=Fuente(id=ds.id, nombre=ds.nombre, licencia=_LIC,
                                atribucion="DIVIPOLA (republicación); origen DANE"))
    for a in avisos:
        sobre.advertir(a)
    sobre.advertir(
        "Los códigos DIVIPOLA son texto con ceros a la izquierda: consérvalos como string."
    )
    if sin_coord:
        sobre.advertir(f"{sin_coord} registro(s) sin coordenada utilizable en la fuente.")
    if not filas:
        sobre.advertir("Sin coincidencias. La fuente responde bien; revisa el nombre o el código.")
    return sobre.render(lambda f: fmt.tabla_markdown(f), formato=formato)


async def _centros(consulta, codigo, con_coordenadas, limite, offset, formato="tabla"):
    ds = reg.DIVIPOLA_CENTROS
    partes = []
    if codigo:
        c = str(codigo).strip()
        campo = "codigo_centro_poblado" if len(c) > 5 else "codigo_municipio"
        partes.append(f"{campo} = '{socrata.escapa(c)}'")
    if consulta:
        filtro, _valores, _trunc = await socrata.filtro_categorico(
            ds.id, "nombre_centro_poblado", consulta)
        if filtro is None:
            return _sin_coincidencias(ds, consulta, "nombre_centro_poblado", offset)
        partes.append(filtro)
    donde = " AND ".join(partes) if partes else None

    total = await socrata.contar(ds.id, donde=donde)
    r = await socrata.consultar(ds.id, donde=donde, ordenar="codigo_centro_poblado",
                                limite=min(int(limite), 200), offset=offset)

    filas, sin_coord = [], 0
    for f in r["filas"]:
        fila = {
            "cod_mpio": f.get("codigo_municipio"),
            "municipio": fmt.limpia_texto(f.get("nombre_municipio")),
            "cod_cp": f.get("codigo_centro_poblado"),
            "centro poblado": fmt.limpia_texto(f.get("nombre_centro_poblado")),
            "tipo": f.get("tipo_centro_poblado"),
        }
        if con_coordenadas:
            par = normaliza_par(f)
            if par:
                fila["lon"], fila["lat"] = round(par[0], 6), round(par[1], 6)
            else:
                fila["lon"] = fila["lat"] = None
                sin_coord += 1
        filas.append(fila)

    sobre = Sobre(datos=filas, total_coincidencias=total, offset=offset,
                  orden="codigo_centro_poblado", consulta=r["consulta"],
                  fuente=Fuente(id=ds.id, nombre=ds.nombre, licencia=_LIC, atribucion="DANE"))
    sobre.advertir("CM = cabecera municipal, CP = centro poblado.")
    if sin_coord:
        sobre.advertir(f"{sin_coord} registro(s) sin coordenada utilizable en la fuente.")
    return sobre.render(lambda f: fmt.tabla_markdown(f), formato=formato)


async def cotejar_coordenadas(limite=15):
    """Chequeo cruzado entre las dos fuentes de coordenadas.

    La cabecera municipal de xaxy-8nri debería coincidir con el punto del
    municipio en gdxc-w37w. Las discrepancias son un hallazgo sobre la calidad
    del dato oficial, no un error del servidor.
    """
    muni = await socrata.consultar(reg.DIVIPOLA_MUNICIPIOS.id, limite=5000, ordenar="cod_mpio")
    cab = await socrata.consultar(reg.DIVIPOLA_CENTROS.id,
                                  donde="tipo_centro_poblado = 'CM'",
                                  limite=5000, ordenar="codigo_municipio")

    indice = {}
    for f in muni["filas"]:
        par = normaliza_par(f)
        if par:
            indice[f.get("cod_mpio")] = par

    discrepancias, sin_par = [], 0
    for f in cab["filas"]:
        par = normaliza_par(f)
        base = indice.get(f.get("codigo_municipio"))
        if not par or not base:
            sin_par += 1
            continue
        delta = max(abs(base[0] - par[0]), abs(base[1] - par[1]))
        if delta > 0.01:  # ~1,1 km
            discrepancias.append({
                "cod_mpio": f.get("codigo_municipio"),
                "municipio": fmt.limpia_texto(f.get("nombre_municipio")),
                "delta_grados": round(delta, 4),
                "km_aprox": round(delta * 111, 1),
            })
    discrepancias.sort(key=lambda d: -d["delta_grados"])

    encabezado = (
        f"Municipios cotejados: **{len(indice)}** · cabeceras: **{len(cab['filas'])}** · "
        f"discrepancias > ~1 km: **{len(discrepancias)}** · sin pareja: {sin_par}"
    )
    sobre = Sobre(datos=discrepancias[:limite], total_coincidencias=len(discrepancias),
                  orden="delta DESC", detalle=Detalle.RESUMEN, consulta=cab["consulta"],
                  fuente=Fuente(id="gdxc-w37w + xaxy-8nri", nombre="Cotejo DIVIPOLA", licencia=_LIC))
    sobre.advertir(
        "Una discrepancia grande no implica que una fuente esté mal: las áreas no "
        "municipalizadas y los municipios con cabecera trasladada aparecen aquí legítimamente."
    )
    return sobre.render(lambda f: encabezado + "\n\n" + fmt.tabla_markdown(f))
