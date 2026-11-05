"""Las fuentes de 0.16.0: RUES, Supersociedades, sanciones, educación, macro.

Con red simulada. Lo que se comprueba aquí no es que las consultas devuelvan
filas —eso lo comprueba la suite de contrato contra la fuente viva— sino que
**el servidor escriba las consultas correctas** y que las trampas verificadas
el 05-nov-2026 estén absorbidas:

* el literal de persona jurídica del RUES lleva la `ó` acentuada;
* el documento se busca en `nit` **y** en `numero_identificacion`;
* el orden de un importe pasa por `replace`, no por un casteo directo;
* el concepto con tilde se pide con `like`, no con igualdad;
* la TRM se busca por rango de vigencia, no por igualdad de fecha;
* y ninguna consulta que identifique a una persona pasa sin finalidad.
"""

import pytest

from colombia_datos_mcp.adapters import socrata
from colombia_datos_mcp.core import privacidad
from colombia_datos_mcp.core.cache import Cache
from colombia_datos_mcp.core.errors import ErrorPrivacidad, ErrorValidacion
from colombia_datos_mcp.domain import (dossier, educacion, empresas, integridad,
                                       macro, territorio)

from .test_dominio import RedFalsa


@pytest.fixture(autouse=True)
def entorno(monkeypatch, tmp_path):
    import colombia_datos_mcp.core.cache as mod
    fresca = Cache(dir_disco=tmp_path / "cache")
    monkeypatch.setattr(mod, "cache", fresca)
    monkeypatch.setattr(socrata, "cache", fresca)
    monkeypatch.delenv("CO_PRIVACIDAD", raising=False)


# --------------------------------------------------------- la red simulada --
# Dominios categóricos con los literales reales de cada fuente, acentos
# incluidos: es sobre eso que se resuelven los términos del usuario.
DOMINIOS = {
    "estado_matricula": ["ACTIVA", "CANCELADA", "MATRÍCULA CANCELADA LEY 1429"],
    "camara_comercio": ["MEDELLIN PARA ANTIOQUIA", "BOGOTÁ"],
    "macrosector": ["COMERCIO", "MANUFACTURA", "SERVICIOS"],
    "departamento_domicilio": ["ANTIOQUIA", "BOGOTÁ D.C."],
    "entidad_sancionado": ["ALCALDÍA DE MEDELLÍN", "EJÉRCITO NACIONAL"],
    "cole_depto_ubicacion": ["ANTIOQUIA", "BOGOTÁ", "CHOCÓ"],
    "municipio": ["Medellín", "Quibdó"],
    "departamento": ["Antioquia", "Chocó"],
    "entidad": ["Medellín", "Cali"],
    "descripcion": ["CDT A 180 DÍAS", "AHORRO"],
}

RUES_JURIDICA = {
    "razon_social": "CONSTRUCTORA EJEMPLO S A S", "sigla": "CESAS",
    "nit": "900123456", "numero_identificacion": "900123456",
    "digito_verificacion": "1",
    "categoria_matricula": privacidad.RUES_JURIDICA,
    "organizacion_juridica": "SOCIEDAD POR ACCIONES SIMPLIFICADA",
    "estado_matricula": "ACTIVA", "camara_comercio": "MEDELLIN PARA ANTIOQUIA",
    "fecha_matricula": "20100315", "ultimo_ano_renovado": "2026",
    "cod_ciiu_act_econ_pri": "F4111",
}
RUES_NATURAL = {**RUES_JURIDICA,
                "razon_social": "PEREZ ANA", "primer_nombre": "ANA",
                "categoria_matricula": privacidad.RUES_NATURAL,
                "numero_identificacion": "1023456789", "nit": "1023456789"}


def _respuesta(filas_por_dataset, caidos=()):
    """Un `get_json` que reparte por id de dataset y simula caídas por fuente."""

    def manejador(url, params):
        for ds_id in caidos:
            if f"/{ds_id}." in url:
                raise socrata.CoDatosError("fuente simulada caída")
        seleccionar = params.get("$select", "") or ""
        if seleccionar.startswith("distinct "):
            campo = seleccionar.split(" ", 1)[1].strip()
            return [{campo: v} for v in DOMINIOS.get(campo, [])]
        if seleccionar.startswith("count(*)"):
            return [{"total": "7"}]
        if seleccionar.startswith("max("):
            alias = seleccionar.split(" as ")[-1].strip()
            return [{alias: "2025"}]
        for ds_id, filas in filas_por_dataset.items():
            if f"/{ds_id}." in url:
                return filas(params) if callable(filas) else filas
        return []

    return manejador


def _instala(monkeypatch, filas_por_dataset, caidos=()):
    manejador = _respuesta(filas_por_dataset, caidos)

    class Red(RedFalsa):
        async def get_json(self, url, params=None, headers=None):
            self.llamadas.append((url, dict(params or {})))
            return manejador(url, dict(params or {}))

    red = Red({})
    monkeypatch.setattr(socrata, "_http", red)
    return red


def _consultas(red):
    return " || ".join(str(p) for _u, p in red.llamadas)


# ================================================================ empresas ==
async def test_solo_juridicas_filtra_con_la_o_acentuada_de_la_fuente(monkeypatch):
    """`SOCIEDAD O PERSONA JURIDICA` devuelve cero: el literal lleva `ó`."""
    red = _instala(monkeypatch, {empresas.RUES.id: [RUES_JURIDICA]})
    await empresas.buscar(nombre="constructora")
    donde = _consultas(red)
    assert "SOCIEDAD ó PERSONA JURIDICA PRINCIPAL ó ESAL" in donde


async def test_buscar_personas_naturales_sin_finalidad_se_bloquea(monkeypatch):
    _instala(monkeypatch, {empresas.RUES.id: [RUES_NATURAL]})
    with pytest.raises(ErrorPrivacidad) as e:
        await empresas.buscar(nombre="perez", solo_juridicas=False)
    assert "solo_juridicas=True" in e.value.sugerencia


async def test_buscar_personas_naturales_con_finalidad_pasa_y_enmascara(monkeypatch):
    _instala(monkeypatch, {empresas.RUES.id: [RUES_NATURAL]})
    r = await empresas.buscar(nombre="perez", solo_juridicas=False,
                              finalidad="investigacion")
    assert "1023456789" not in r["texto"]
    assert "10••••••89" in r["texto"]
    assert "investigación académica" in r["texto"]


async def test_el_documento_se_busca_en_las_dos_columnas(monkeypatch):
    """En 485.630 sociedades `nit` está vacío y el número solo está en
    `numero_identificacion`: buscar en una sola pierde en silencio."""
    red = _instala(monkeypatch, {empresas.RUES.id: [RUES_JURIDICA]})
    await empresas.buscar(documento="900123456")
    donde = _consultas(red)
    assert "nit in (" in donde and "numero_identificacion in (" in donde


async def test_el_nit_del_rues_va_entre_comillas(monkeypatch):
    """Es de tipo text: sin comillas Socrata responde type-mismatch."""
    red = _instala(monkeypatch, {empresas.RUES.id: [RUES_JURIDICA]})
    await empresas.buscar(documento="900123456")
    assert "'900123456'" in _consultas(red)


async def test_la_ficha_de_una_persona_natural_pide_finalidad(monkeypatch):
    """517.527 comerciantes a título personal figuran con clase de
    identificación NIT, así que la forma del número no basta: para un documento
    con forma de cédula manda lo que diga `categoria_matricula`."""
    _instala(monkeypatch, {empresas.RUES.id: [RUES_NATURAL]})
    with pytest.raises(ErrorPrivacidad):
        await empresas.ficha("1023456789")


async def test_una_matricula_mal_clasificada_no_bloquea_una_sociedad(monkeypatch):
    """El caso de Bancolombia: dos matrículas, y la de Cali clasificada como
    PERSONA NATURAL con la razón social del banco en la fila. Bloquear por ella
    dejaba la herramienta inútil para su caso central, así que se resuelve del
    lado de la sociedad **y se dice**."""
    _instala(monkeypatch, {empresas.RUES.id: [
        {**RUES_NATURAL, "razon_social": "BANCOLOMBIA S.A.",
         "nit": None, "numero_identificacion": "890903938"},
        {**RUES_JURIDICA, "razon_social": "BANCOLOMBIA S.A",
         "nit": "890903938", "numero_identificacion": "890903938"}]})
    r = await empresas.ficha("890903938")
    assert "BANCOLOMBIA" in r["texto"]
    assert "error de la fuente" in r["texto"]
    # Y el NIT de la sociedad no se enmascara: haría inútil el cruce con SECOP.
    assert "890903938" in r["texto"]


async def test_la_ficha_declara_el_total_de_matriculas_sin_inventarlo(monkeypatch):
    """Diez es un tope, no una colección cerrada."""
    _instala(monkeypatch, {empresas.RUES.id: [RUES_JURIDICA] * 10})
    r = await empresas.ficha("900123456")
    meta = r["estructurado"]["_meta"]
    assert meta["total_coincidencias"] == 7          # lo contó la fuente simulada
    assert meta["origen_del_total"] == "contado"


async def test_sin_matricula_no_se_concluye_que_no_existe(monkeypatch):
    _instala(monkeypatch, {empresas.RUES.id: []})
    r = await empresas.ficha("900123456")
    assert "entidad pública" in r["texto"]
    assert "co_secop_perfil_proveedor" in r["texto"]


def test_las_fechas_del_rues_son_yyyymmdd_en_texto():
    assert empresas.fecha_rues("19841122") == "1984-11-22"
    assert empresas.fecha_rues("20100315") == "2010-03-15"
    assert empresas.fecha_rues("") == ""
    assert empresas.fecha_rues("1984") == "1984"      # no se inventa lo que falta


async def test_el_orden_de_un_importe_limpia_el_signo_antes_de_castear(monkeypatch):
    """`ingresos_operacionales::number` falla: el valor es «$ 100.59»."""
    red = _instala(monkeypatch, {empresas.MAS_GRANDES.id: [
        {"raz_n_social": "ECOPETROL S.A.", "nit": "899999068.00",
         "macrosector": "MINERO", "departamento_domicilio": "BOGOTÁ D.C.",
         "ingresos_operacionales": "$ 100.59", "total_activos": "$ 198.11",
         "total_patrimonio": "$ 90.00", "ganancia_p_rdida": "$ 9.03"}]})
    r = await empresas.ranking(anio=2025)
    # El `$order` real lleva el `replace`; la etiqueta del sobre es la legible,
    # y la URL reproducible del pie deja comprobar cuál se aplicó de verdad.
    donde = _consultas(red)
    assert "replace(replace(ingresos_operacionales, '$ ', ''), ',', '')::number" in donde
    assert r["estructurado"]["_meta"]["orden"] == "ingresos_operacionales DESC"


async def test_el_ranking_declara_que_los_importes_son_billones(monkeypatch):
    _instala(monkeypatch, {empresas.MAS_GRANDES.id: [
        {"raz_n_social": "X", "nit": "1", "ingresos_operacionales": "$ 1.00"}]})
    r = await empresas.ranking(anio=2025)
    assert "BILLONES" in r["texto"]
    assert "Superfinanciera" in r["texto"]      # los bancos no están aquí


async def test_sin_anio_el_ranking_toma_el_ultimo_y_lo_dice(monkeypatch):
    """Son 10.000 por año: sin fijarlo cada empresa sale cinco veces."""
    red = _instala(monkeypatch, {empresas.MAS_GRANDES.id: [
        {"raz_n_social": "X", "nit": "1", "ingresos_operacionales": "$ 1.00"}]})
    r = await empresas.ranking()
    assert "se usa 2025" in r["texto"]
    assert "a_o_de_corte = 2025" in _consultas(red)


async def test_el_concepto_con_tilde_se_pide_con_like(monkeypatch):
    """El byte guardado es U+FFFD: la igualdad devuelve 0 habiendo 627.932."""
    red = _instala(monkeypatch, {
        empresas.EEFF_SITUACION.id: [
            {"fecha_corte": "2023-12-31T00:00:00.000",
             "concepto": "Total de activos", "valor": "1889713"}],
        empresas.EEFF_RESULTADOS.id: []})
    await empresas.estados_financieros("830010665")
    donde = _consultas(red)
    assert "concepto like 'Ganancia (p_rdida)'" in donde
    assert "'Ganancia (pérdida)'" not in donde


async def test_los_estados_financieros_fijan_periodo_actual(monkeypatch):
    """«Periodo Anterior» es el comparativo del mismo radicado: duplicaría cada
    año si no se excluyera."""
    red = _instala(monkeypatch, {empresas.EEFF_SITUACION.id: [],
                                 empresas.EEFF_RESULTADOS.id: []})
    await empresas.estados_financieros("830010665")
    assert "periodo = 'Periodo Actual'" in _consultas(red)


async def test_sin_estados_financieros_se_explica_que_los_bancos_no_reportan(
        monkeypatch):
    _instala(monkeypatch, {empresas.EEFF_SITUACION.id: [],
                           empresas.EEFF_RESULTADOS.id: []})
    r = await empresas.estados_financieros("890903938")
    assert "Bancolombia" in r["texto"]
    assert "Superfinanciera" in r["texto"]


# ============================================================== integridad ==
async def test_el_panorama_no_pide_finalidad(monkeypatch):
    """Es la alternativa que el motor ofrece al bloquear: tiene que existir."""
    _instala(monkeypatch, {integridad.SIRI.id: [
        {"grupo": "SERVIDOR PÚBLICO", "sanciones": "15736"}]})
    r = await integridad.panorama(agrupar_por="calidad")
    assert "SERVIDOR PÚBLICO" in r["texto"]
    assert "finalidad" not in r["texto"].lower()


async def test_el_screening_de_una_cedula_sin_finalidad_se_bloquea(monkeypatch):
    _instala(monkeypatch, {})
    with pytest.raises(ErrorPrivacidad) as e:
        await integridad.screening("1023456789")
    assert "co_integridad_panorama" in e.value.sugerencia


async def test_el_screening_de_un_nit_no_pide_finalidad(monkeypatch):
    _instala(monkeypatch, {})
    r = await integridad.screening("900123456")
    assert "Fuentes consultadas" in r["texto"]


async def test_el_screening_enumera_lo_que_miro_aunque_no_encuentre_nada(
        monkeypatch):
    """El valor del screening no está en lo que encuentra sino en que el
    alcance quede escrito: un cero sin alcance no se puede interpretar."""
    _instala(monkeypatch, {})
    r = await integridad.screening("900123456")
    for ds in (integridad.SIRI, integridad.SECOP1, integridad.CONTADORES,
               integridad.FISCAL, integridad.SECOP2):
        assert ds.id in r["texto"]
    assert "NO ES UN CERTIFICADO" in r["texto"]


async def test_una_fuente_caida_no_tumba_el_screening(monkeypatch):
    """Con seis backends el fallo parcial es el caso normal."""
    _instala(monkeypatch, {}, caidos=(integridad.SIRI.id,))
    r = await integridad.screening("900123456")
    assert "no consultable" in r["texto"]
    assert integridad.SECOP1.id in r["texto"]       # las demás siguen


async def test_el_screening_dice_que_secop2_no_es_cruzable_por_documento(
        monkeypatch):
    _instala(monkeypatch, {})
    r = await integridad.screening("900123456")
    assert "no cruzable por documento" in r["texto"]


async def test_las_disciplinarias_siempre_piden_finalidad(monkeypatch):
    _instala(monkeypatch, {integridad.SIRI.id: []})
    with pytest.raises(ErrorPrivacidad):
        await integridad.disciplinarias(documento="1023456789")


async def test_buscar_por_nombre_en_siri_advierte_de_los_homonimos(monkeypatch):
    red = _instala(monkeypatch, {integridad.SIRI.id: []})
    r = await integridad.disciplinarias(nombre="perez", finalidad="periodismo")
    assert "homónimos" in r["texto"]
    # Cuatro columnas y ninguna con el nombre completo.
    donde = _consultas(red)
    for campo in ("primer_nombre", "segundo_nombre", "primer_apellido",
                  "segundo_apellido"):
        assert campo in donde


async def test_cero_en_siri_no_es_un_certificado_limpio(monkeypatch):
    _instala(monkeypatch, {integridad.SIRI.id: []})
    r = await integridad.disciplinarias(documento="1023456789",
                                        finalidad="control_fiscal")
    assert "NO" in r["texto"] and "certificado" in r["texto"]


async def test_secop2_se_filtra_a_negativos_publicados(monkeypatch):
    """533 de 588 filas son «Comentarios positivos» y solo 145 están
    publicadas: sin filtrar, el conteo se multiplica por cuatro."""
    red = _instala(monkeypatch, {integridad.SECOP1.id: [],
                                 integridad.SECOP2.id: []})
    await integridad.sanciones_contratacion(nombre="constructora")
    donde = _consultas(red)
    assert "tipo = 'Comentarios negativos'" in donde
    assert "estado = 'Publicado por el administrador de la plataforma'" in donde


async def test_sin_nombre_no_se_mira_secop2_y_se_avisa(monkeypatch):
    _instala(monkeypatch, {integridad.SECOP1.id: []})
    r = await integridad.sanciones_contratacion(documento="900123456")
    assert "Sin `nombre` no se miró SECOP II" in r["texto"]


# =============================================================== educación ==
async def test_saber11_promedia_casteando_porque_el_puntaje_es_texto(monkeypatch):
    red = _instala(monkeypatch, {educacion.SABER11.id: [
        {"cole_depto_ubicacion": "BOGOTÁ", "estudiantes": "152584",
         "promedio": "270.2560163582026949"}]})
    r = await educacion.saber11(periodo="20224")
    donde = _consultas(red)
    assert "avg(punt_global::number)" in donde
    assert "270.3" in r["texto"]


async def test_saber11_excluye_los_grupos_diminutos(monkeypatch):
    """Un promedio sobre tres personas no es comparable, y además se acerca a
    identificar a quien lo compone."""
    red = _instala(monkeypatch, {educacion.SABER11.id: []})
    await educacion.saber11(periodo="20224", agrupar_por="colegio")
    assert "count(*) >= 20" in _consultas(red)


async def test_saber11_declara_que_solo_sale_agregado(monkeypatch):
    _instala(monkeypatch, {educacion.SABER11.id: []})
    r = await educacion.saber11(periodo="20224")
    assert privacidad.AVISO_SOLO_AGREGADO in r["texto"]


async def test_saber11_sin_periodo_toma_la_aplicacion_masiva(monkeypatch):
    """`max(periodo)` daría a veces la de marzo, con quince mil estudiantes,
    presentada como «el último año»: es un error de población, no de fecha."""
    def periodos(params):
        if params.get("$group") == "periodo":
            return [{"periodo": "20231", "n": "15000"},
                    {"periodo": "20224", "n": "1065888"}]
        return [{"cole_depto_ubicacion": "BOGOTÁ", "estudiantes": "10",
                 "promedio": "250"}]
    _instala(monkeypatch, {educacion.SABER11.id: periodos})
    r = await educacion.saber11()
    assert "20224" in r["texto"]
    assert "se usa 20224" in r["texto"]


async def test_saber11_advierte_que_el_ranking_no_mide_calidad(monkeypatch):
    _instala(monkeypatch, {educacion.SABER11.id: []})
    r = await educacion.saber11(periodo="20224", agrupar_por="colegio")
    assert "estrato" in r["texto"]


async def test_la_poblacion_del_men_no_sirve_de_denominador(monkeypatch):
    """Es la pregunta que se hace sola, y la respuesta correcta es que no."""
    _instala(monkeypatch, {educacion.MEN.id: [
        {"a_o": "2023", "c_digo_municipio": "05001", "municipio": "Medellín",
         "departamento": "Antioquia", "poblaci_n_5_16": "377562",
         "cobertura_neta": "95.94", "cobertura_bruta": "107.16"}]})
    r = await educacion.indicadores(anio=2023)
    assert "5 a 16 años" in r["texto"]
    assert "criminalidad" in r["texto"]


async def test_la_cobertura_bruta_por_encima_de_cien_se_explica(monkeypatch):
    _instala(monkeypatch, {educacion.MEN.id: []})
    r = await educacion.indicadores(anio=2023)
    assert "107,16" in r["texto"] or "107.16" in r["texto"]


async def test_un_indicador_inventado_se_rechaza_listando_los_validos(monkeypatch):
    _instala(monkeypatch, {educacion.MEN.id: []})
    with pytest.raises(ErrorValidacion) as e:
        await educacion.indicadores(indicador="felicidad")
    assert "cobertura_neta" in e.value.sugerencia


# ============================================================== territorio ==
async def test_el_mdm_advierte_que_solo_se_compara_dentro_del_grupo(monkeypatch):
    _instala(monkeypatch, {territorio.MDM.id: [
        {"anio": "2020", "codigo_entidad": "76001", "entidad": "Cali",
         "departamento": "Valle del Cauca", "dato": "86.4462",
         "etiqueta": "Ciudades"}]})
    r = await territorio.desempeno(anio=2020)
    assert "dotaciones iniciales" in r["texto"]
    assert "ranking nacional" in r["texto"]


async def test_el_mdm_usa_el_literal_exacto_del_indicador(monkeypatch):
    red = _instala(monkeypatch, {territorio.MDM.id: []})
    await territorio.desempeno(anio=2020, indicador="gestion")
    assert "indicador = 'Componente de gestión'" in _consultas(red)


# =================================================================== macro ==
async def test_la_trm_se_busca_por_rango_de_vigencia(monkeypatch):
    """Un domingo no tiene TRM propia: rige la del viernes. Preguntar por
    igualdad de `vigenciadesde` devuelve cero habiendo tasa vigente."""
    red = _instala(monkeypatch, {macro.TRM.id: [
        {"valor": "3916.39", "unidad": "COP",
         "vigenciadesde": "2024-01-20T00:00:00.000",
         "vigenciahasta": "2024-01-22T00:00:00.000"}]})
    r = await macro.trm(fecha="2024-01-21")
    donde = _consultas(red)
    assert "vigenciadesde <=" in donde and "vigenciahasta >=" in donde
    assert "varios días" in r["texto"]


async def test_convertir_calcula_y_declara_que_no_es_deflactar(monkeypatch):
    _instala(monkeypatch, {macro.TRM.id: [
        {"valor": "4000", "unidad": "COP",
         "vigenciadesde": "2024-01-20T00:00:00.000",
         "vigenciahasta": "2024-01-20T00:00:00.000"}]})
    r = await macro.convertir(1_000_000_000, "2024-01-20")
    assert "250.000,00" in r["texto"]
    assert "NO es deflactar" in r["texto"]
    assert "IPC" in r["texto"]


async def test_convertir_al_reves(monkeypatch):
    _instala(monkeypatch, {macro.TRM.id: [
        {"valor": "4000", "unidad": "COP",
         "vigenciadesde": "2024-01-20T00:00:00.000",
         "vigenciahasta": "2024-01-20T00:00:00.000"}]})
    r = await macro.convertir(1000, "2024-01-20", hacia="cop")
    assert "4.000.000" in r["texto"]


@pytest.mark.parametrize("fecha", ["20-01-2024", "2024/01/20", "ayer", ""])
async def test_una_fecha_mal_escrita_se_rechaza_con_el_formato(monkeypatch, fecha):
    _instala(monkeypatch, {macro.TRM.id: []})
    with pytest.raises(ErrorValidacion) as e:
        await macro.convertir(100, fecha)
    assert "YYYY-MM-DD" in e.value.sugerencia


async def test_las_tasas_exigen_un_filtro(monkeypatch):
    """2,1 M de filas: sin filtro la agregación hace un recorrido completo."""
    _instala(monkeypatch, {macro.TASAS.id: []})
    with pytest.raises(ErrorValidacion) as e:
        await macro.tasas()
    assert "2.102.178" in e.value.sugerencia


async def test_las_tasas_declaran_que_el_promedio_no_esta_ponderado(monkeypatch):
    _instala(monkeypatch, {macro.TASAS.id: [
        {"descripcion": "CDT A 180 DÍAS", "reportes": "500",
         "tasa_promedio": "10.5", "monto_total": "1000000"}]})
    r = await macro.tasas(desde="2024-01-01")
    assert "PROMEDIO SIMPLE" in r["texto"]
    assert "ponder" in r["texto"]


# ================================================================= dossier ==
async def test_el_dossier_de_un_nit_cruza_las_cinco_familias(monkeypatch):
    _instala(monkeypatch, {
        empresas.RUES.id: [RUES_JURIDICA],
        dossier.CONTRATOS.id: [{"contratos": "12", "valor": "5000000000",
                                "primero": "2020-01-01T00:00:00.000",
                                "ultimo": "2024-06-30T00:00:00.000"}],
        empresas.EEFF_SITUACION.id: [{"fecha_corte": "2023-12-31T00:00:00.000",
                                      "valor": "1889713"}],
        empresas.MAS_GRANDES.id: [],
    })
    r = await dossier.de_documento("900123456")
    texto = r["texto"]
    assert "CONSTRUCTORA EJEMPLO S A S" in texto
    for ambito in ("Registro mercantil", "Contratación estatal",
                   "Estados financieros", "10.000 más grandes",
                   "Antecedentes disciplinarios"):
        assert ambito in texto


async def test_el_dossier_pide_finalidad_si_el_rues_dice_persona_natural(
        monkeypatch):
    """Cruzar siete fuentes sobre una persona es más invasivo que consultar
    una, así que la puerta es la misma y está igual de cerrada.

    El documento tiene forma de NIT —nueve dígitos empezando por 9— y aun así
    se bloquea, porque todas sus matrículas dicen persona natural: es el caso
    inverso al de Bancolombia, donde solo una lo decía.
    """
    _instala(monkeypatch, {empresas.RUES.id: [
        {**RUES_NATURAL, "nit": None, "numero_identificacion": "1023456789"}]})
    with pytest.raises(ErrorPrivacidad) as e:
        await dossier.de_documento("1023456789")
    assert "finalidad" in e.value.mensaje


async def test_el_dossier_avisa_de_la_matricula_mal_clasificada(monkeypatch):
    _instala(monkeypatch, {empresas.RUES.id: [
        {**RUES_NATURAL, "razon_social": "BANCOLOMBIA S.A.",
         "nit": None, "numero_identificacion": "890903938"},
        {**RUES_JURIDICA, "nit": "890903938"}]})
    r = await dossier.de_documento("890903938")
    assert "error de la fuente" in r["texto"]


async def test_el_dossier_enumera_lo_que_no_sabe_mirar(monkeypatch):
    _instala(monkeypatch, {empresas.RUES.id: [RUES_JURIDICA]})
    r = await dossier.de_documento("900123456")
    assert "Registraduría" in r["texto"] and "captcha" in r["texto"]


async def test_un_bloque_caido_no_tumba_el_dossier(monkeypatch):
    _instala(monkeypatch, {empresas.RUES.id: [RUES_JURIDICA]},
             caidos=(dossier.CONTRATOS.id,))
    r = await dossier.de_documento("900123456")
    assert "no consultable" in r["texto"]
    assert "CONSTRUCTORA EJEMPLO S A S" in r["texto"]


# ------------------------------------------- regresiones de la prueba de humo --
async def test_la_ficha_no_repite_columnas_en_el_select(monkeypatch):
    """Una columna duplicada en el `$select` no es un aviso, es un 400.

    `campos_resumen` del RUES ya trae `categoria_matricula`, así que
    concatenarle las columnas extra la repetía y Socrata rechazaba la consulta
    entera con `query.soql.invalid`. Las pruebas con red simulada no lo veían
    —la red falsa no valida SoQL— y salió en la primera llamada real.
    """
    red = _instala(monkeypatch, {empresas.RUES.id: [RUES_JURIDICA]})
    await empresas.ficha("900123456")
    selects = [p["$select"] for _u, p in red.llamadas if "$select" in p]
    assert selects, "la ficha no pidió columnas"
    for select in selects:
        columnas = [c.strip() for c in select.split(",")]
        assert len(columnas) == len(set(columnas)), select


async def test_el_screening_no_cuenta_juntas_sus_dos_tablas(monkeypatch):
    """Son cinco filas de resumen más los detalles: «5 fila(s) de 0
    coincidencias» es verdad por separado y absurdo leído seguido."""
    _instala(monkeypatch, {})
    r = await integridad.screening("900123456")
    assert "fila(s)" not in r["texto"]
    assert r["estructurado"]["_meta"].get("siguiente_offset") is None
