"""Desempeño municipal del DNP.

Una sola fuente y tres advertencias, porque es de las que más fácil se cita mal.

* **Es formato largo**: 22.020 filas son 1.101 municipios × 4 indicadores × 5
  años. Una fila es *un valor de un indicador*, no un municipio.
* **La serie va de 2016 a 2020 y se paró ahí.** La ficha del dataset dice que
  se actualizó el 21-feb-2022, y eso es la ficha: el último año con datos es
  2020. El MDM se sigue publicando cada año, así que citar esto como «el
  desempeño municipal» sin la fecha es citar algo de hace un lustro.
* **No es TerriData.** El catálogo completo de indicadores territoriales del
  DNP no tiene API pública; esto son los cuatro agregados del MDM.
"""

from __future__ import annotations

from ..adapters import socrata
from ..core import format as fmt
from ..core.envelope import Fuente, Sobre, Total
from ..core.errors import ErrorValidacion
from ..registry import datasets as reg

MDM = reg.TERRITORIO["mdm"]
_LIC = "CC BY-SA 4.0"
_ATRIB = "Departamento Nacional de Planeación - DNP"

# Los cuatro indicadores que publica el dataset, con su literal exacto.
INDICADORES = {
    "mdm": "MDM",
    "gestion": "Componente de gestión",
    "resultados": "Componente de resultados",
    "dotaciones": "Grupo de dotaciones iniciales",
}


async def desempeno(municipio: str | None = None, departamento: str | None = None,
                    anio: int = 0, indicador: str = "mdm", limite: int = 25,
                    formato: str = "tabla", grafica: bool = True):
    """Ranking o ficha del Índice de Desempeño Municipal.

    `indicador="dotaciones"` no es una puntuación sino el grupo de comparación:
    el MDM solo se compara **dentro** del mismo grupo de dotaciones iniciales,
    porque un municipio con hospital y universidad no parte de donde parte uno
    sin acueducto. Ordenar el MDM nacional de mayor a menor ignora eso.
    """
    clave = str(indicador or "mdm").strip().lower()
    if clave not in INDICADORES:
        raise ErrorValidacion(
            f"Indicador desconocido: {indicador!r}.",
            "Válidos: " + ", ".join(f"{k} ({v})" for k, v in INDICADORES.items()))
    literal = INDICADORES[clave]

    avisos, partes = [], [f"indicador = '{socrata.escapa(literal)}'"]
    if not anio:
        anio = await _ultimo_anio()
        avisos.append(
            f"Año no indicado: se usa {anio}, el último con datos. La fuente no "
            "tiene años posteriores aunque su ficha diga que se actualizó en 2022.")
    partes.append(f"anio = '{int(anio)}'")
    if municipio:
        cat = await socrata.filtro_categorico(MDM.id, "entidad", municipio)
        if cat.filtro is None:
            return _sin(f"«{municipio}» no aparece como municipio en el MDM")
        partes.append(cat.filtro)
    if departamento:
        cat = await socrata.filtro_categorico(MDM.id, "departamento", departamento)
        if cat.filtro is None:
            return _sin(f"«{departamento}» no aparece como departamento en el MDM")
        partes.append(cat.filtro)
    donde = " AND ".join(partes)

    tope = min(int(limite), 100)
    r = await socrata.consultar(
        MDM.id,
        seleccionar="anio, codigo_entidad, entidad, departamento, dato, etiqueta",
        donde=donde, ordenar="dato::number DESC", limite=tope)

    crudos = [fmt.a_numero(f.get("dato")) or 0 for f in r["filas"]]
    filas = [{"año": f.get("anio"),
              "cod_mpio": f.get("codigo_entidad"),
              "municipio": fmt.limpia_texto(f.get("entidad")),
              "departamento": fmt.limpia_texto(f.get("departamento")),
              clave: _redondea(f.get("dato")),
              "etiqueta": fmt.limpia_texto(f.get("etiqueta"))}
             for f in r["filas"]]
    if grafica and formato == "tabla" and filas:
        for fila, barra in zip(filas, fmt.barras(crudos)):
            fila["gráfica"] = barra

    sobre = Sobre(datos=filas, orden="dato DESC", consulta=r["consulta"],
                  fuente=Fuente(id=MDM.id, nombre=MDM.nombre, licencia=_LIC,
                                atribucion=_ATRIB))
    sobre.total = Total.cupo_entero(r["filas"], tope)
    if not sobre.total.consta:
        sobre.total = Total.contado(await socrata.contar(MDM.id, donde=donde))
    for a in avisos:
        sobre.advertir(a)
    sobre.advertir(
        "El MDM se compara DENTRO del mismo grupo de dotaciones iniciales, no "
        "entre todos los municipios: un ranking nacional mezcla municipios que "
        "no parten del mismo sitio. Pide indicador='dotaciones' para ver el "
        "grupo de cada uno.")
    sobre.advertir(
        "`codigo_entidad` es la clave DIVIPOLA, de 5 dígitos y con ceros a la "
        "izquierda: cruza con criminalidad, educación y geometría por código.")
    for n in MDM.notas:
        sobre.advertir(n)
    return sobre.render(lambda f: fmt.tabla_markdown(f), formato=formato)


def _redondea(valor) -> str:
    n = fmt.a_numero(valor)
    return f"{n:.2f}" if n is not None else ""


def _sin(mensaje: str):
    sobre = Sobre(datos=[], total=Total.completo(0),
                  fuente=Fuente(id=MDM.id, nombre=MDM.nombre, licencia=_LIC,
                                atribucion=_ATRIB))
    sobre.advertir(f"{mensaje}. No es un fallo de la fuente.")
    return sobre.render(lambda _f: "_Sin coincidencias._")


async def _ultimo_anio() -> int:
    r = await socrata.consultar(MDM.id, seleccionar="max(anio) as a", limite=1)
    filas = r["filas"]
    valor = fmt.a_numero(filas[0].get("a")) if filas else None
    return int(valor) if valor else 2020
