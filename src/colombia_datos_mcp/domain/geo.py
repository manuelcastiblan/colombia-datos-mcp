"""DIVIPOLA: la clave de join universal del servidor (ADR-03)."""

from __future__ import annotations

import json

from ..adapters import geometria, socrata
from ..core import format as fmt
from ..core import texto
from ..core.budget import Detalle
from ..core.coords import normaliza_par
from ..core.envelope import Fuente, Sobre, Total
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
    sobre = Sobre(datos=[], total=Total.completo(0), offset=offset,
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

    sobre = Sobre(datos=filas, total=Total.contado(total), offset=offset, orden="cod_mpio",
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

    sobre = Sobre(datos=filas, total=Total.contado(total), offset=offset,
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
    # `datos` va recortado pero el total es el de TODAS las discrepancias
    # halladas: este sitio ya lo hacia bien y fue el modelo del resto.
    sobre = Sobre(datos=discrepancias[:limite], total=Total.completo(len(discrepancias)),
                  orden="delta DESC", detalle=Detalle.RESUMEN, consulta=cab["consulta"],
                  fuente=Fuente(id="gdxc-w37w + xaxy-8nri", nombre="Cotejo DIVIPOLA", licencia=_LIC))
    sobre.advertir(
        "Una discrepancia grande no implica que una fuente esté mal: las áreas no "
        "municipalizadas y los municipios con cabecera trasladada aparecen aquí legítimamente."
    )
    return sobre.render(lambda f: encabezado + "\n\n" + fmt.tabla_markdown(f))


# -------------------------------------------------------------- límites ----
MAX_FEATURES = 200


async def limites(nivel: str = "municipio", codigo: str | None = None,
                  departamento: str | None = None, guardar: str | None = None):
    """Devuelve los límites como GeoJSON, filtrados por código o departamento.

    La geometría va en el contenido estructurado, no en el markdown: un polígono
    no se lee en una tabla, y meterlo en el texto se comería el presupuesto de
    tokens entero. El cuerpo trae el resumen de qué salió y con qué extensión.
    """
    if nivel not in ("municipio", "departamento"):
        raise ErrorValidacion(
            "nivel debe ser 'municipio' o 'departamento'.",
            "El detalle disponible es municipal; 'departamento' los agrupa.",
        )
    datos = await geometria.cargar()
    C = geometria.CAMPOS
    rasgos = datos["features"]
    avisos = []

    if codigo:
        c = str(codigo).strip()
        rasgos = [f for f in rasgos
                  if (f["properties"][C["codigo"]] == c if len(c) > 2
                      else f["properties"][C["cod_dpto"]] == c)]
    if departamento:
        objetivo = texto.plegar(departamento)
        casan = [f for f in rasgos
                 if objetivo in texto.plegar(f["properties"][C["departamento"]])]
        if not casan:
            sobre = Sobre(datos=[], mostrar_conteo=False,
                          fuente=Fuente(id="MGN 2018", nombre="Límites municipales",
                                        licencia=_LIC,
                                        atribucion=geometria.PROCEDENCIA))
            sobre.advertir(
                f"«{departamento}» no corresponde a ningún departamento de la "
                "geometría. No es un fallo de la fuente."
            )
            return sobre.render(lambda _f: "_Sin coincidencias._")
        rasgos = casan

    if nivel == "departamento":
        rasgos = _agrupa_por_departamento(rasgos, C)
        avisos.append(
            "Cada departamento es un MultiPolygon con los polígonos de sus "
            "municipios: las aristas internas siguen ahí. Relleno se ve igual, "
            "pero si trazas el borde aparecerán las divisiones municipales."
        )

    if len(rasgos) > MAX_FEATURES and not guardar:
        raise ErrorValidacion(
            f"El filtro devuelve {len(rasgos)} geometrías, más de {MAX_FEATURES}.",
            "Acota con `codigo` o `departamento`, o usa `guardar` para "
            "escribirlas en disco en vez de traerlas en la respuesta.",
        )

    coleccion = {"type": "FeatureCollection", "features": rasgos}
    filas = []
    for f in rasgos[:60]:
        pr = f["properties"]
        x0, y0, x1, y1 = geometria.bbox(f["geometry"])
        filas.append({
            "codigo": pr.get(C["codigo"]) or pr.get(C["cod_dpto"]),
            "nombre": fmt.limpia_texto(pr.get(C["municipio"])
                                       or pr.get(C["departamento"])),
            "departamento": fmt.limpia_texto(pr.get(C["departamento"])),
            "lon": f"{x0:.2f} a {x1:.2f}",
            "lat": f"{y0:.2f} a {y1:.2f}",
        })

    sobre = Sobre(datos=[], total=Total.completo(len(rasgos)), mostrar_conteo=False,
                  fuente=Fuente(id="MGN 2018", nombre="Límites municipales del DANE",
                                licencia=_LIC, atribucion=geometria.PROCEDENCIA))
    cuerpo = [f"**{len(rasgos)}** geometría(s) de nivel {nivel}.", ""]
    if filas:
        cuerpo.append(fmt.tabla_markdown(filas))
        if len(rasgos) > len(filas):
            cuerpo.append("")
            cuerpo.append(f"_Se listan {len(filas)} de {len(rasgos)}; el GeoJSON "
                          "completo va en el contenido estructurado._")

    if guardar:
        from .exportar import DIR_EXPORT, _nombre_seguro
        nombre = _nombre_seguro(guardar, "json")[:-5] + ".geojson"
        try:
            DIR_EXPORT.mkdir(parents=True, exist_ok=True)
            ruta = DIR_EXPORT / nombre
            ruta.write_text(json.dumps(coleccion, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            raise ErrorValidacion(
                f"No se pudo escribir {nombre}: {exc}",
                f"Comprueba permisos sobre {DIR_EXPORT}.",
            ) from None
        cuerpo.append("")
        cuerpo.append(f"Guardado en `{ruta}` "
                      f"({fmt.numero(ruta.stat().st_size)} bytes).")
        sobre.datos = [{"ruta": str(ruta), "geometrias": len(rasgos), "nivel": nivel}]
    else:
        sobre.datos = [coleccion]

    for a in avisos:
        sobre.advertir(a)
    sobre.advertir(
        f"Procedencia: {geometria.PROCEDENCIA}. Es un corte de 2018, así que los "
        "municipios creados después no están — por eso falta Nuevo Belén de "
        "Bajirá."
    )
    sobre.advertir(
        "El código es la clave DIVIPOLA: une por código con cualquier otra "
        "fuente del servidor, sin pasar por el nombre."
    )
    sobre.advertir(
        "GEOMETRÍA MUY SIMPLIFICADA: mediana de 10 vértices por municipio y el "
        "48 % tiene menos de 10. Sirve para colorear un mapa nacional, NO para "
        "medir áreas ni para decidir si un punto cae dentro cerca de un límite."
    )
    return sobre.render(lambda _f: "\n".join(cuerpo))


def _agrupa_por_departamento(rasgos, C):
    """Un MultiPolygon por departamento.

    No es una disolución real —fusionar los polígonos y borrar las aristas
    internas necesitaría una librería de geometría—, pero para recortar,
    rellenar o encuadrar es equivalente. El sobre lo advierte.
    """
    por_dpto: dict[str, dict] = {}
    for f in rasgos:
        pr = f["properties"]
        cod = pr[C["cod_dpto"]]
        d = por_dpto.setdefault(cod, {
            "type": "Feature",
            "properties": {C["cod_dpto"]: cod,
                           C["departamento"]: pr[C["departamento"]],
                           "municipios": 0},
            "geometry": {"type": "MultiPolygon", "coordinates": []},
        })
        d["properties"]["municipios"] += 1
        g = f["geometry"]
        if g["type"] == "Polygon":
            d["geometry"]["coordinates"].append(g["coordinates"])
        else:
            d["geometry"]["coordinates"].extend(g["coordinates"])
    return sorted(por_dpto.values(), key=lambda f: f["properties"][C["cod_dpto"]])
