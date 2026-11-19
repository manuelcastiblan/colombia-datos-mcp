"""La documentación también se rompe, y en silencio.

Una tabla markdown con una fila de más columnas que su cabecera no da error:
se renderiza torcida y nadie lo nota hasta que alguien la lee. Pasó con la fila
que documenta `luego` en `co_datos_agregar`, donde el operador `|>` iba dentro
de una celda: **una barra vertical parte la fila aunque vaya entre acentos
graves**, porque los backticks no protegen del parser de tablas. Justo la fila
que documentaba la novedad era la que salía mal.

Estas pruebas no juzgan el contenido, solo que se pueda leer.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
DOCUMENTOS = sorted(
    [RAIZ / "README.md", RAIZ / "CONTRIBUTING.md", RAIZ / "CHANGELOG.md"]
    + list((RAIZ / "docs").glob("*.md"))
)

# Una línea de separación: |---|---:|:---:|
SEPARACION = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$")


def _celdas(linea: str) -> int:
    """Cuenta celdas respetando el escape `\\|`, que es la forma correcta de
    meter una barra vertical dentro de una."""
    s = re.sub(r"\\\|", "\x00", linea.strip())
    s = s.removeprefix("|").removesuffix("|")
    return len(s.split("|"))


def _tablas(lineas: list[str]):
    """Devuelve (nº de línea de la cabecera, indentación, [líneas de la tabla])."""
    i = 0
    while i < len(lineas):
        if (i + 1 < len(lineas) and "|" in lineas[i]
                and SEPARACION.match(lineas[i + 1]) and "-" in lineas[i + 1]):
            j = i + 1
            while j < len(lineas) and "|" in lineas[j]:
                j += 1
            yield i, len(lineas[i]) - len(lineas[i].lstrip()), lineas[i:j]
            i = j
        else:
            i += 1


def _ids(p: Path) -> str:
    return str(p.relative_to(RAIZ)).replace("\\", "/")


@pytest.mark.parametrize("documento", DOCUMENTOS, ids=_ids)
def test_las_filas_tienen_las_columnas_de_su_cabecera(documento: Path):
    lineas = documento.read_text(encoding="utf-8").splitlines()
    fallos = []
    for inicio, _indent, tabla in _tablas(lineas):
        esperadas = _celdas(tabla[0])
        for k, fila in enumerate(tabla[1:], start=1):
            if _celdas(fila) != esperadas:
                fallos.append(
                    f"  línea {inicio + k + 1}: {_celdas(fila)} columnas, "
                    f"la cabecera tiene {esperadas}\n    {fila.strip()[:90]}"
                )
    assert not fallos, (
        f"Tablas rotas en {_ids(documento)}:\n" + "\n".join(fallos)
        + "\n  Si la celda necesita una barra vertical, escápala como \\|; "
        "los acentos graves NO bastan."
    )


@pytest.mark.parametrize("documento", DOCUMENTOS, ids=_ids)
def test_ninguna_tabla_va_dentro_de_una_lista(documento: Path):
    """Una tabla indentada dentro de un ítem de lista no la pintan muchos
    renderizadores. Se saca a nivel de bloque; el ítem pasa a párrafo con
    entradilla en negrita, que se lee igual y se ve en todas partes."""
    lineas = documento.read_text(encoding="utf-8").splitlines()
    indentadas = [inicio + 1 for inicio, indent, _ in _tablas(lineas) if indent >= 2]
    assert not indentadas, (
        f"Tablas indentadas en {_ids(documento)}, líneas {indentadas}: "
        "sácalas del ítem de lista o conviértelas en texto."
    )


def test_hay_documentos_que_revisar():
    """Si un renombrado deja la lista vacía, las dos pruebas de arriba pasarían
    sin comprobar nada."""
    assert len(DOCUMENTOS) >= 8, f"solo se encontraron {len(DOCUMENTOS)} documentos"


# ------------------------------------------------------------- mermaid ---
# Un diagrama roto tampoco da error: GitHub pinta una caja gris con el texto
# del fallo y el documento sigue "funcionando". Esto no lo renderiza —para eso
# hace falta un navegador— pero sí detecta lo que lo rompe en la práctica:
# una comilla sin cerrar dentro de una etiqueta y un corchete desparejado.
TIPOS = ("flowchart", "graph", "sequenceDiagram", "classDiagram", "stateDiagram",
         "erDiagram", "journey", "gantt", "pie", "mindmap", "timeline")
MERMAID = re.compile(r"```mermaid\n(.*?)```", re.S)


@pytest.mark.parametrize("documento", DOCUMENTOS, ids=_ids)
def test_los_diagramas_mermaid_estan_bien_formados(documento: Path):
    texto = documento.read_text(encoding="utf-8")
    fallos = []
    for bloque in MERMAID.finditer(texto):
        linea0 = texto[:bloque.start()].count("\n") + 1
        cuerpo = bloque.group(1)
        primera = next((l.strip() for l in cuerpo.splitlines() if l.strip()), "")
        if not primera.startswith(TIPOS):
            fallos.append(f"  línea {linea0}: empieza por {primera[:40]!r}, "
                          "que no es un tipo de diagrama conocido")
        for k, linea in enumerate(cuerpo.splitlines(), start=1):
            if linea.count('"') % 2:
                fallos.append(f"  línea {linea0 + k}: comilla sin cerrar\n    {linea.strip()[:80]}")
            for abre, cierra in (("[", "]"), ("{", "}"), ("(", ")")):
                if linea.count(abre) != linea.count(cierra):
                    fallos.append(f"  línea {linea0 + k}: {abre}{cierra} desparejado"
                                  f"\n    {linea.strip()[:80]}")
    assert not fallos, f"Diagramas rotos en {_ids(documento)}:\n" + "\n".join(fallos)


def test_hay_diagramas_que_revisar():
    """Si alguien los borra o cambia la valla, la prueba de arriba pasaría
    sin mirar nada. Son seis repartidos en cuatro documentos."""
    total = sum(len(MERMAID.findall(d.read_text(encoding="utf-8"))) for d in DOCUMENTOS)
    assert total >= 6, f"solo se encontraron {total} diagramas"
