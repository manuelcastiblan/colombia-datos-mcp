"""Comparación de texto contra fuentes que conservan los acentos.

Las cifras que se afirman aquí salen de medir las tres estrategias contra los
1.122 municipios reales de DIVIPOLA antes de elegir. Se dejan como prueba para
que un cambio de estrategia tenga que volver a justificarse.
"""

from colombia_datos_mcp.adapters import socrata
from colombia_datos_mcp.core import texto

# Valores canónicos tal como los devuelve la fuente, con sus acentos.
DEPARTAMENTOS = ["Atlántico", "Antioquia", "Distrito Capital de Bogotá",
                 "Bolívar", "Nariño", "Chocó", "Valle del Cauca"]
MUNICIPIOS = ["MEDELLÍN", "ABEJORRAL", "ITAGÜÍ", "SAN ANDRÉS DE CUERQUÍA",
              "EL PEÑÓN", "ANDES", "LOS ANDES"]


def test_plegar_quita_acentos_y_normaliza():
    assert texto.plegar("Bogotá D.C.") == "BOGOTA D.C."
    assert texto.plegar("Itagüí") == "ITAGUI"
    assert texto.plegar("El Peñón") == "EL PENON"
    assert texto.plegar(None) == ""


def test_resuelve_el_termino_sin_acentos_contra_el_valor_acentuado():
    # El defecto original: la fuente trae "Atlántico" y el filtro buscaba
    # "ATLANTICO", así que devolvía cero en silencio.
    assert texto.coincidencias("atlantico", DEPARTAMENTOS) == ["Atlántico"]
    assert texto.coincidencias("bogota", DEPARTAMENTOS) == ["Distrito Capital de Bogotá"]
    assert texto.coincidencias("choco", DEPARTAMENTOS) == ["Chocó"]


def test_resuelve_tambien_si_el_usuario_escribe_el_acento():
    assert texto.coincidencias("Atlántico", DEPARTAMENTOS) == ["Atlántico"]
    # …incluso mal puesto: "Antioquía" no existe, pero pliega igual.
    assert texto.coincidencias("Antioquía", DEPARTAMENTOS) == ["Antioquia"]


def test_encuentra_los_municipios_con_dos_tildes():
    # Estos son los que fallaban con cualquier estrategia de comodines.
    for nombre in ("itagui", "san andres de cuerquia", "el penon"):
        assert texto.coincidencias(nombre, MUNICIPIOS), nombre


def test_la_subcadena_sigue_siendo_subcadena():
    # "ANDES" ⊂ "LOS ANDES" es semántica correcta de búsqueda, no ruido.
    assert texto.coincidencias("andes", MUNICIPIOS) == ["ANDES", "LOS ANDES"]


def test_termino_inexistente_no_inventa_coincidencias():
    assert texto.coincidencias("narnia", DEPARTAMENTOS) == []
    assert texto.coincidencias("", DEPARTAMENTOS) == []


# ------------------------------------------------------- texto libre ------
def test_sanea_like_pliega_y_quita_comodines():
    assert texto.sanea_like("Gobernación") == "GOBERNACION"
    # Un `%` escrito por el usuario ensancharía la búsqueda sin que la pida.
    assert "%" not in texto.sanea_like("100% nacional")


def test_el_plegado_de_texto_libre_ocurre_en_el_servidor():
    filtro = socrata.filtro_texto_libre("nombre_entidad", "gobernacion")
    # SoQL sí soporta replace(): plegar la COLUMNA es exacto, mientras que
    # plegar solo el término se dejaba fuera las filas con tilde.
    assert filtro.startswith("replace(")
    assert "'Ó', 'O'" in filtro and "'Ñ', 'N'" in filtro
    assert filtro.endswith("like '%GOBERNACION%'")


def test_texto_libre_escapa_las_comillas():
    assert "O''BRIEN" in socrata.filtro_texto_libre("proveedor_adjudicado", "O'Brien")


def test_filtro_en_usa_los_literales_exactos_y_escapa():
    assert socrata.filtro_en("departamento", ["Atlántico"]) ==         "departamento in ('Atlántico')"
    assert "O''Brien" in socrata.filtro_en("proveedor_adjudicado", ["O'Brien"])
