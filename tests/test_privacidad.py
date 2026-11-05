"""El motor de privacidad y el total de las respuestas compuestas.

Las dos piezas que 0.16.0 añadió al núcleo. Se prueban juntas porque las dos
existen por el mismo motivo: hacer **inexpresable** una afirmación que nadie
comprobó. `Total` impedía decir «esto es todo» sin saberlo; `privacidad`
impide devolver una persona identificada sin que conste para qué.
"""

import pytest

from colombia_datos_mcp.core import privacidad
from colombia_datos_mcp.core.envelope import Sobre, Total
from colombia_datos_mcp.core.errors import ErrorPrivacidad, ErrorValidacion


@pytest.fixture(autouse=True)
def politica_estricta(monkeypatch):
    """La política por defecto, explícita: ninguna prueba hereda el entorno."""
    monkeypatch.delenv("CO_PRIVACIDAD", raising=False)


# ----------------------------------------------------------- la política --
def test_la_politica_por_defecto_es_estricta():
    assert privacidad.politica() == privacidad.ESTRICTA


def test_un_valor_mal_escrito_cae_del_lado_que_protege(monkeypatch):
    """`permisva` no es `permisiva`, y un error de dedo del operador no puede
    abrir el servidor: cualquier valor desconocido es estricta."""
    for valor in ("permisva", "PERMISIV", "si", "1", "true", ""):
        monkeypatch.setenv("CO_PRIVACIDAD", valor)
        assert privacidad.politica() == privacidad.ESTRICTA, valor


def test_permisiva_solo_con_el_literal_exacto(monkeypatch):
    monkeypatch.setenv("CO_PRIVACIDAD", "permisiva")
    assert privacidad.politica() == privacidad.PERMISIVA
    monkeypatch.setenv("CO_PRIVACIDAD", "  PERMISIVA  ")
    assert privacidad.politica() == privacidad.PERMISIVA


# ---------------------------------------------------------- la finalidad --
@pytest.mark.parametrize("entrada,esperado", [
    ("investigacion", "investigacion"),
    ("investigación", "investigacion"),
    ("Académico", "investigacion"),
    ("periodismo", "periodismo"),
    ("prensa", "periodismo"),
    ("control fiscal", "control_fiscal"),
    ("veeduría", "control_fiscal"),
    ("debida diligencia", "debida_diligencia"),
    ("KYC", "debida_diligencia"),
])
def test_los_alias_de_finalidad_se_normalizan(entrada, esperado):
    assert privacidad.normaliza_finalidad(entrada) == esperado


def test_una_finalidad_inventada_se_rechaza_listando_las_validas():
    with pytest.raises(ErrorValidacion) as e:
        privacidad.normaliza_finalidad("porque me apetece")
    assert "investigacion" in e.value.sugerencia
    assert e.value.codigo == "VALIDACION"


def test_sin_finalidad_se_bloquea_y_el_error_nombra_la_alternativa():
    """Un bloqueo que no dice qué hacer en su lugar entrena al modelo a
    reintentar con otras palabras hasta colarse."""
    with pytest.raises(ErrorPrivacidad) as e:
        privacidad.exige_finalidad(None, que="La ficha de X",
                                   alternativa="co_integridad_panorama")
    assert e.value.codigo == "PRIVACIDAD"
    assert "co_integridad_panorama" in e.value.sugerencia
    assert "no la supongas" in e.value.mensaje.lower()


def test_la_politica_permisiva_no_bloquea_pero_lo_declara(monkeypatch):
    monkeypatch.setenv("CO_PRIVACIDAD", "permisiva")
    assert privacidad.exige_finalidad(None, que="X", alternativa="Y") == "no_declarada"


def test_ninguna_herramienta_puede_aflojar_la_politica():
    """La política se lee del entorno, nunca de un argumento. Es lo que impide
    que un prompt pida que se desactive."""
    import inspect
    firma = inspect.signature(privacidad.exige_finalidad)
    assert "politica" not in firma.parameters
    assert set(firma.parameters) == {"finalidad", "que", "alternativa"}


# ------------------------------------------------------ el identificador --
@pytest.mark.parametrize("documento,clase", [
    ("899999068", "nit"),          # Ecopetrol
    ("8999990681", "nit"),         # con dígito de verificación
    ("890903938", "nit"),          # Bancolombia
    ("79123456", "cedula"),
    ("1023456789", "cedula"),
    ("52123456", "cedula"),
    ("12345", "indeterminado"),    # demasiado corto
    ("123456789012", "indeterminado"),
    ("", "indeterminado"),
    (None, "indeterminado"),
])
def test_clase_de_documento(documento, clase):
    assert privacidad.clase_documento(documento) == clase


def test_lo_indeterminado_cuenta_como_persona():
    """Equivocarse hacia «es una empresa» expone a alguien; equivocarse hacia
    «es una persona» solo pide una finalidad de más."""
    assert not privacidad.es_persona_juridica("12345")
    assert not privacidad.es_persona_juridica("")


# -------------------------------------------------------- el enmascarado --
@pytest.mark.parametrize("documento,esperado", [
    ("1023456789", "10••••••89"),
    ("79123456", "79••••56"),
    ("890903938", "89•••••38"),
    ("1.023.456.789", "10••••••89"),   # tolera separadores
    ("12345", "•••••"),                 # menos de seis: entero
    ("", ""),
])
def test_enmascara_conserva_longitud_y_extremos(documento, esperado):
    assert privacidad.enmascara(documento) == esperado


def test_el_enmascarado_distingue_a_dos_personas_sin_escribir_el_numero():
    """Conservar extremos y longitud deja comprobar que dos filas hablan de la
    misma persona, que es para lo que sirve en una tabla."""
    a, b = privacidad.enmascara("1023456789"), privacidad.enmascara("1023456789")
    c = privacidad.enmascara("1098765432")
    assert a == b and a != c


# -------------------------------------------------- las columnas afectadas --
@pytest.mark.parametrize("campo", [
    "numero_identificacion", "num_identificacion_representante_legal",
    "documento_contratista", "c_dula", "cedula", "nit",
    "n_mero_de_identificaci_n",
])
def test_se_reconocen_las_columnas_de_documento(campo):
    assert privacidad.es_columna_documento(campo)


@pytest.mark.parametrize("campo", [
    "tipo_identificacion", "nombre_tipo_identificacion", "clase_identificacion",
    "codigo_clase_identificacion", "digito_verificacion", "nit_entidad",
    "nit_de_la_entidad", "codigo_entidad", "razon_social", "municipio",
])
def test_no_se_enmascara_lo_que_no_es_un_documento_de_persona(campo):
    """`nit_entidad` es el de un organismo público y `clase_identificacion` es
    una categoría: enmascararlos rompería los cruces sin proteger a nadie."""
    assert not privacidad.es_columna_documento(campo)


# ---------------------------------------------------------- la redacción --
FILA_PERSONA = {"primer_nombre": "ANA", "numero_identificacion": "1023456789",
                "cargo": "ALCALDE", "sanciones": "DESTITUCION"}


def test_redacta_las_filas_de_personas():
    [salida] = privacidad.redacta_filas([FILA_PERSONA])
    assert salida["numero_identificacion"] == "10••••••89"
    assert salida["primer_nombre"] == "ANA"      # el nombre no se toca
    assert salida["cargo"] == "ALCALDE"


def test_no_redacta_el_nit_de_una_sociedad():
    """El NIT de una empresa es información mercantil pública, y enmascararlo
    dejaría la respuesta inútil para cruzarla con SECOP."""
    fila = {"razon_social": "ECOPETROL S.A.", "nit": "899999068"}
    [salida] = privacidad.redacta_filas([fila], persona_juridica=True)
    assert salida["nit"] == "899999068"


def test_la_politica_permisiva_no_redacta(monkeypatch):
    monkeypatch.setenv("CO_PRIVACIDAD", "permisiva")
    [salida] = privacidad.redacta_filas([FILA_PERSONA])
    assert salida["numero_identificacion"] == "1023456789"


def test_redactar_no_pierde_ni_inventa_columnas():
    [salida] = privacidad.redacta_filas([FILA_PERSONA])
    assert set(salida) == set(FILA_PERSONA)


def test_los_vacios_se_quedan_vacios():
    """Enmascarar una celda vacía produciría un documento que no existe."""
    [salida] = privacidad.redacta_filas([{"numero_identificacion": None}])
    assert salida["numero_identificacion"] is None


# ------------------------------------------------------------- los avisos --
def test_el_sobre_declara_la_finalidad_para_que_sea_auditable():
    sobre = Sobre(datos=[FILA_PERSONA])
    privacidad.avisa(sobre, finalidad="investigacion")
    unidos = " ".join(sobre.advertencias)
    assert "investigación académica" in unidos
    assert "auditable" in unidos
    assert "Ley 1581" in unidos


def test_sin_finalidad_declarada_el_sobre_dice_que_fue_el_operador(monkeypatch):
    monkeypatch.setenv("CO_PRIVACIDAD", "permisiva")
    sobre = Sobre(datos=[])
    privacidad.avisa(sobre, finalidad="no_declarada")
    assert any("CO_PRIVACIDAD=permisiva" in a for a in sobre.advertencias)


# ------------------------------------------------- Total.union (§ sobre) --
def test_union_es_exacta_si_ninguna_consulta_lleno_su_limite():
    total = Total.union([(3, 50), (7, 50)])
    assert total.valor == 10
    assert total.origen == "cabia_entero"


def test_union_no_consta_si_alguna_lleno_su_limite():
    """Es el error que apareció en cuatro herramientas de 0.16.0: cada consulta
    por separado parecía caber, y la que se pasó quedaba escondida en la suma."""
    total = Total.union([(3, 50), (50, 50)])
    assert total.valor is None
    assert not total.consta


def test_union_sin_trozos_es_una_coleccion_vacia_y_completa():
    total = Total.union([])
    assert total.valor == 0 and total.origen == "completo"


def test_union_no_se_puede_confundir_con_un_entero():
    """El mismo blindaje que `cupo_entero`: el sobre no acepta un int donde va
    un `Total`, así que la afirmación sin comprobar no se puede escribir."""
    sobre = Sobre(datos=[{"a": 1}])
    with pytest.raises(AttributeError):
        sobre.total_coincidencias = 99


# ------------------------------------------- las dos señales que discrepan --
def test_la_fuente_manda_cuando_el_numero_parece_una_cedula():
    """Es el caso que la forma del número no ve: 517.527 comerciantes a título
    personal figuran con clase de identificación NIT."""
    natural, aviso = privacidad.resuelve_persona(
        "1023456789", [privacidad.RUES_NATURAL])
    assert natural is True
    assert aviso is None


def test_sin_matriculas_naturales_no_hay_nada_que_decidir():
    natural, aviso = privacidad.resuelve_persona(
        "900123456", [privacidad.RUES_JURIDICA, privacidad.RUES_JURIDICA])
    assert natural is False and aviso is None


def test_una_fila_mal_clasificada_no_bloquea_la_ficha_de_una_sociedad():
    """El caso real: el NIT de Bancolombia tiene dos matrículas y la de Cali
    está clasificada como PERSONA NATURAL, con la razón social del banco en la
    fila. Bloquear por ella dejaba la herramienta inútil para su caso central.
    """
    natural, aviso = privacidad.resuelve_persona(
        "890903938", [privacidad.RUES_NATURAL, privacidad.RUES_JURIDICA])
    assert natural is False
    assert aviso and "error de la fuente" in aviso
    assert "Bancolombia" in aviso


def test_la_discrepancia_no_se_resuelve_en_silencio():
    """Resolver el conflicto sin decirlo escondería un dato sobre el dato."""
    _natural, aviso = privacidad.resuelve_persona(
        "890903938", [privacidad.RUES_NATURAL])
    assert aviso is not None
    assert "1 de las 1" in aviso


def test_un_nit_de_diez_digitos_tambien_se_reconoce_como_empresa():
    natural, aviso = privacidad.resuelve_persona(
        "8909039388", [privacidad.RUES_NATURAL])
    assert natural is False and aviso is not None
