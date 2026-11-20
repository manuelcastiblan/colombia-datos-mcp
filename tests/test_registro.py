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
    assert len(reg.todos()) >= 100, f"el registro tiene {len(reg.todos())} datasets"
    assert len(reg.FAMILIAS) >= 14


# ------------------------------------------------- cadenas de atribución ---
# El facet de Socrata exige el literal exacto, y una entidad puede publicar
# bajo varios. El DANE usa tres: mientras el registro conoció una sola,
# `entidad="DANE"` devolvía 2 de sus 6 datasets anunciando «2 de 2».
def test_cada_atribucion_es_una_cadena_o_varias_pero_nunca_vacia():
    malas = []
    for sigla, valor in reg.ATRIBUCIONES.items():
        literales = (valor,) if isinstance(valor, str) else tuple(valor)
        if not literales or any(not isinstance(l, str) or not l.strip()
                                for l in literales):
            malas.append(sigla)
        if len(set(literales)) != len(literales):
            malas.append(f"{sigla} (repetida)")
    assert not malas, f"atribuciones mal formadas: {malas}"


def test_literales_atribucion_devuelve_siempre_una_tupla():
    # una sola cadena o varias, el tipo que sale es el mismo
    for sigla in reg.ATRIBUCIONES:
        assert isinstance(reg.literales_atribucion(sigla), tuple)
    assert reg.literales_atribucion("DNP") == (reg.ATRIBUCIONES["DNP"],)
    assert len(reg.literales_atribucion("DANE")) == 3
    assert len(reg.literales_atribucion("CCE")) == 4
    # lo que no está en la tabla se devuelve tal cual: que falle el facet y lo
    # diga el sobre es mejor que adivinar una cadena por quien pregunta
    assert reg.literales_atribucion("NoExiste") == ("NoExiste",)


# ------------------------------------------------------------- joins ---
# Estuvo declarado `p6dx-8zbt.id_del_proceso = jbjy-vk9h.proceso_de_compra`,
# que cruza CO1.REQ.* contra CO1.BDOS.*: cero filas siempre, sin error. Un
# join equivocado no se cae, devuelve vacío, y el vacío parece un hallazgo.
def _partes(ref: str) -> tuple[str, str]:
    did, _, campo = ref.partition(".")
    return did, campo


def test_todo_join_apunta_a_un_dataset_del_registro():
    conocidos = {d.id for d in reg.todos()}
    huerfanos = []
    for a, b in reg.JOINS:
        for ref in (a, b):
            did, campo = _partes(ref)
            if did not in conocidos:
                huerfanos.append(ref)
            if not campo:
                huerfanos.append(f"{ref} (sin campo)")
    assert not huerfanos, f"joins que apuntan fuera del registro: {huerfanos}"


def test_ningun_join_declarado_esta_tambien_en_los_falsos():
    """`JOINS_FALSOS` existe para que nadie reintente un cruce ya descartado.
    Si un par aparece en las dos listas, una de las dos miente."""
    declarados = {tuple(sorted((a, b))) for a, b in reg.JOINS}
    falsos = {tuple(sorted((a, b))) for a, b, _ in reg.JOINS_FALSOS}
    choque = declarados & falsos
    assert not choque, f"pares en JOINS y en JOINS_FALSOS a la vez: {choque}"


def test_cada_join_falso_explica_por_que():
    sin_motivo = [(a, b) for a, b, motivo in reg.JOINS_FALSOS if len(motivo.strip()) < 20]
    assert not sin_motivo, f"joins falsos sin explicación: {sin_motivo}"


def test_el_join_de_proceso_usa_el_portafolio_y_no_el_procedimiento():
    """La corrección concreta, clavada: CO1.BDOS.* vive en `id_del_portafolio`."""
    pares = {(a, b) for a, b in reg.JOINS}
    assert ("p6dx-8zbt.id_del_portafolio", "jbjy-vk9h.proceso_de_compra") in pares
    assert ("p6dx-8zbt.id_del_proceso", "jbjy-vk9h.proceso_de_compra") not in pares


def test_la_familia_agro_comparte_la_llave_entre_sus_tres_tablas():
    """Producción, área y rendimiento solo se cruzan si las tres traen la
    misma terna. Si una cambia de nombre de campo, el cruce se rompe callado."""
    llaves = {k: tuple(sorted(d.campos_clave)) for k, d in reg.AGRO.items()}
    assert len(set(llaves.values())) == 1, llaves
    assert set(reg.AGRO["arroz_produccion"].campos_clave) >= {"ano", "semestre", "sistema"}
