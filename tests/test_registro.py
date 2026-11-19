"""Invariantes del registro de fuentes. Sin red.

El registro pasó de 52 a 97 datasets de una vez, y un registro grande falla de
formas aburridas: un ID pegado dos veces, una familia que nadie enlaza en
`FAMILIAS` —y entonces `por_id` no la ve y `detalle="resumen"` devuelve las 40
columnas crudas—, o una fuente de personas que entra sin pasar por el motor de
privacidad porque se añadió con prisa.

Ninguna de estas pruebas toca la API. Lo que sí depende de la fuente viva está
en `test_contrato.py`.
"""

from __future__ import annotations

import collections

from colombia_datos_mcp.core import privacidad
from colombia_datos_mcp.registry import datasets as reg

# Familias cuyas filas describen a una PERSONA con cuasi-identidades: sexo,
# grupo etario, etnia, discapacidad, orientación sexual y municipio del hecho.
# Sin nombre ni cédula, pero en un municipio pequeño eso es alguien.
FAMILIAS_DE_MICRODATO = ("forense",)


def test_ningun_id_esta_dos_veces():
    """Dos entradas con el mismo ID no dan error: `por_id` devuelve la primera
    y la segunda queda muerta, con sus notas y sus campos curados."""
    cuenta = collections.Counter(d.id for d in reg.todos())
    repetidos = {i: n for i, n in cuenta.items() if n > 1}
    assert not repetidos, f"IDs repetidos en el registro: {repetidos}"


def test_toda_familia_esta_enlazada_en_familias():
    """Una familia que existe como dict pero no está en `FAMILIAS` es
    invisible para `por_id`, `familia_de` y el motor de privacidad. Ya pasó
    una vez: al abrir cinco familias, sus campos curados no se aplicaban."""
    sueltas = []
    for nombre, valor in vars(reg).items():
        if nombre.isupper() and isinstance(valor, dict) and valor:
            if all(isinstance(v, reg.Dataset) for v in valor.values()):
                if valor not in reg.FAMILIAS.values():
                    sueltas.append(nombre)
    assert not sueltas, f"familias fuera de FAMILIAS: {sueltas}"


def test_cada_dataset_declara_que_cuenta_una_fila():
    """`unidad` es lo que impide sumar hectáreas con homicidios. Una cadena
    vacía o un «registro» genérico no sirven."""
    flojos = [f"{fam}.{clave}={ds.id}"
              for fam, familia in reg.FAMILIAS.items()
              for clave, ds in familia.items()
              if not ds.unidad or len(ds.unidad) < 9]
    assert not flojos, f"sin unidad de análisis declarada: {flojos}"


def test_familia_de_responde_para_todos():
    sin_familia = [d.id for familia in reg.FAMILIAS.values() for d in familia.values()
                   if reg.familia_de(d.id) is None]
    assert not sin_familia, f"sin familia: {sin_familia}"


def test_por_id_encuentra_lo_que_todos_enumera():
    perdidos = [d.id for d in reg.todos() if reg.por_id(d.id) is None]
    assert not perdidos, f"`todos()` los lista pero `por_id` no los encuentra: {perdidos}"


def test_el_microdato_declarado_existe_en_el_registro():
    """Un ID mal escrito en `MICRODATO` es una puerta abierta silenciosa: la
    política se aplicaría a un dataset que no existe."""
    conocidos = {d.id for d in reg.todos()}
    fantasmas = sorted(privacidad.MICRODATO - conocidos)
    assert not fantasmas, f"en MICRODATO y no en el registro: {fantasmas}"


def test_las_fuentes_personales_declaradas_existen():
    conocidos = {d.id for d in reg.todos()}
    fantasmas = sorted(privacidad.PERSONALES - conocidos)
    assert not fantasmas, f"en PERSONALES y no en el registro: {fantasmas}"


def test_toda_la_familia_forense_es_microdato():
    """La regla que protege a la familia de sí misma: si alguien añade mañana
    otro dataset de Medicina Legal y olvida el motor de privacidad, esto
    falla. La fila es una víctima con etnia, orientación sexual, discapacidad
    y municipio; no se devuelve fila a fila."""
    fuera = []
    for fam in FAMILIAS_DE_MICRODATO:
        for clave, ds in reg.FAMILIAS[fam].items():
            if ds.id not in privacidad.MICRODATO:
                fuera.append(f"{fam}.{clave}={ds.id}")
    assert not fuera, f"microdato de personas sin puerta de privacidad: {fuera}"


def test_las_personas_de_la_fiscalia_son_microdato():
    """`procesos` no identifica a nadie y se consulta libre; `procesados` y
    `victimas` son una fila por persona y solo se agregan."""
    assert reg.FISCALIA["procesos"].id not in privacidad.MICRODATO
    assert reg.FISCALIA["procesados"].id in privacidad.MICRODATO
    assert reg.FISCALIA["victimas"].id in privacidad.MICRODATO


def test_los_operativos_no_se_mezclan_con_crimen():
    """Están separados a propósito: en CRIMEN la `cantidad` son casos o
    personas y en OPERATIVOS son hectáreas, kilos o galones. Si alguien
    moviera uno de sitio, un `co_crimen_comparar` empezaría a sumar kilos."""
    ids_crimen = {d.id for d in reg.CRIMEN.values()}
    ids_operativos = {d.id for d in reg.OPERATIVOS.values()}
    assert not (ids_crimen & ids_operativos), "un dataset está en las dos familias"
    medidas = {clave: ds.unidad for clave, ds in reg.OPERATIVOS.items()}
    assert any("hect" in u for u in medidas.values())
    assert any("kilogramo" in u for u in medidas.values())


def test_las_notas_que_dan_una_cifra_la_dan_entera():
    """Una nota a medio escribir —«filas.» sin número— es peor que no tenerla:
    parece medida y no lo está."""
    rotas = [f"{ds.id}: {n[:40]}"
             for d in reg.todos() for ds in [d] for n in ds.notas
             if n.strip().startswith("filas") or "@@" in n]
    assert not rotas, f"notas con el número sin rellenar: {rotas}"


def test_el_registro_no_encogio_sin_querer():
    """Un `git merge` desafortunado sobre un fichero de 1.700 líneas puede
    borrar una familia entera sin que nada más falle."""
    assert len(reg.todos()) >= 97, f"el registro tiene {len(reg.todos())} datasets"
    assert len(reg.FAMILIAS) >= 13
