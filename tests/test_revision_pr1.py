"""Regresiones de la revisión externa del PR 1.

Trece defectos, todos reales, en el código que 0.16.0 añadió. Vale la pena
agruparlos porque no son trece despistes sueltos: son cuatro patrones, y los
cuatro consisten en que una regla se escribió en un sitio y la vía de acceso
era otra.

1. **La política vivía en la herramienta, no en la fuente.** `co_datos_consultar`
   acepta cualquier `dataset_id`, así que pedir `iaeu-rcn6` devolvía el SIRI con
   nombre y cédula sin finalidad, y `co_datos_exportar` escribía el microdato de
   Saber 11 en disco. El motor de privacidad entero se eludía cambiando de
   herramienta.
2. **El enmascarado cubría las celdas y no el texto.** El documento seguía
   saliendo completo en el título del dossier, en los avisos y en la consulta
   reproducible del pie: la misma respuesta ocultaba la columna y escribía el
   número cuatro líneas más abajo.
3. **Decisiones por página donde el dato es por fila.** Una sola persona natural
   enmascaraba los NIT públicos de las sociedades que la acompañaban; una
   búsqueda por nombre se daba por jurídica sin mirar lo que había vuelto.
4. **Cifras que afirman más de lo que se midió.** `cupo_entero` sin `offset`
   publicaba la página corta como el total; el dossier anunciaba «3 matrículas»
   con `limite=3`; y `en_ranking` se tragaba el fallo de la fuente, de modo que
   un timeout se publicaba como «no figura».

Y tres de consulta mal escrita: el nombre completo buscado en columnas que solo
tienen un trozo cada una (falso cero), el rango de TRM que pierde el intervalo
vigente al empezar, y el `hasta` suelto que eludía la validación de filtro.
"""

import pytest

from colombia_datos_mcp.adapters import socrata
from colombia_datos_mcp.core.cache import Cache
from colombia_datos_mcp.core.envelope import Total
from colombia_datos_mcp.core.errors import ErrorPrivacidad, ErrorValidacion
from colombia_datos_mcp.domain import (catalogo, dossier, empresas, exportar,
                                       integridad, macro)

from .fixtures import CATALOGO
from .test_dominio import RedFalsa
from .test_fuentes_nuevas import RUES_JURIDICA, RUES_NATURAL

SIRI = integridad.SIRI.id
SABER11 = "kgxf-xxbe"

FILA_SIRI = {
    "numero_identificacion": "79123456", "calidad_persona": "SERVIDOR PÚBLICO",
    "entidad_sancionado": "ALCALDÍA DE MEDELLÍN", "cargo": "SECRETARIO",
    "sanciones": "SUSPENSIÓN", "tipo_inhabilidad": "GENERAL",
    "duracion_anos": "3", "fecha_efectos_juridicos": "2020-05-01",
    "autoridad": "PROCURADURÍA", "primer_nombre": "ANA",
    "primer_apellido": "PEREZ",
}


@pytest.fixture(autouse=True)
def entorno(monkeypatch, tmp_path):
    import colombia_datos_mcp.core.cache as mod
    fresca = Cache(dir_disco=tmp_path / "cache")
    monkeypatch.setattr(mod, "cache", fresca)
    monkeypatch.setattr(socrata, "cache", fresca)
    monkeypatch.delenv("CO_PRIVACIDAD", raising=False)
    monkeypatch.setenv("CO_EXPORT_DIR", str(tmp_path / "export"))
    import colombia_datos_mcp.domain.exportar as mod_exp
    monkeypatch.setattr(mod_exp, "DIR_EXPORT", tmp_path / "export")


# Las columnas que la allow-list tiene que reconocer. `valida_campos` las
# deriva del esquema vivo, así que una prueba de agregación sobre el SIRI no
# llega al motor de privacidad si el catálogo simulado no las declara.
COLUMNAS = {
    "iaeu-rcn6": ["numero_identificacion", "entidad_sancionado", "calidad_persona",
                  "cargo", "sanciones", "tipo_inhabilidad", "duracion_anos",
                  "fecha_efectos_juridicos", "autoridad", "primer_nombre",
                  "segundo_nombre", "primer_apellido", "segundo_apellido"],
    "kgxf-xxbe": ["estu_consecutivo", "punt_global", "cole_depto_ubicacion",
                  "periodo"],
}


def _catalogo_de(url: str) -> dict:
    """El catálogo que la allow-list espera, sintetizado para el dataset pedido."""
    for ds_id, campos in COLUMNAS.items():
        if ds_id in url:
            return {"resultSetSize": 1, "results": [{"resource": {
                "id": ds_id, "name": ds_id, "description": "",
                "attribution": "", "updatedAt": "2026-10-21T00:00:00.000Z",
                "provenance": "official", "parent_fxf": [],
                "page_views": {"page_views_total": 1},
                "columns_field_name": list(campos),
                "columns_name": list(campos),
                "columns_datatype": ["Text"] * len(campos),
                "columns_description": [""] * len(campos),
            }, "metadata": {"domain": "www.datos.gov.co"}}]}
    return CATALOGO


def _instala(monkeypatch, filas_por_dataset, caidos=()):
    """Red simulada que reparte por id de dataset y sirve el catálogo."""

    def manejador(url, params):
        for ds_id in caidos:
            if f"/{ds_id}." in url:
                raise socrata.CoDatosError("fuente simulada caída")
        if "api/catalog/v1" in url:
            return _catalogo_de(str(params.get("ids") or params.get("q") or url))
        sel = params.get("$select", "") or ""
        if sel.startswith("distinct "):
            return []
        if sel.startswith("count(*)"):
            return [{"total": "42"}]
        for ds_id, filas in filas_por_dataset.items():
            if f"/{ds_id}." in url:
                return filas(params) if callable(filas) else filas
        return []

    class Red(RedFalsa):
        async def get_json(self, url, params=None, headers=None):
            self.llamadas.append((url, dict(params or {})))
            return manejador(url, dict(params or {}))

    red = Red({})
    monkeypatch.setattr(socrata, "_http", red)
    return red


def _consultas(red):
    return " || ".join(str(p) for _u, p in red.llamadas)


# ========================================= 1. la puerta está en la fuente ==
async def test_la_via_generica_no_entrega_el_siri_sin_finalidad(monkeypatch):
    """El agujero central: la política estaba en las herramientas
    especializadas, así que `co_datos_consultar` sobre el mismo dataset
    devolvía nombre y cédula sin pasar por nada."""
    _instala(monkeypatch, {SIRI: [FILA_SIRI]})
    with pytest.raises(ErrorPrivacidad) as e:
        await catalogo.consultar(SIRI, detalle="completo")
    assert "co_datos_agregar" in e.value.sugerencia


async def test_la_via_generica_entrega_el_siri_enmascarado_con_finalidad(monkeypatch):
    _instala(monkeypatch, {SIRI: [FILA_SIRI]})
    r = await catalogo.consultar(SIRI, detalle="completo", finalidad="periodismo")
    assert "79123456" not in r["texto"]
    assert "79••••56" in r["texto"]
    assert "periodismo de interés público" in r["texto"]


async def test_el_microdato_de_saber_no_sale_fila_a_fila_ni_con_finalidad(monkeypatch):
    """Saber 11 son 7.109.704 personas con estrato y escolaridad de los padres.
    No hay finalidad que abra la fila de un estudiante concreto."""
    _instala(monkeypatch, {SABER11: [{"estu_consecutivo": "SB1", "punt_global": "320"}]})
    for finalidad in (None, "investigacion"):
        with pytest.raises(ErrorPrivacidad) as e:
            await catalogo.consultar(SABER11, detalle="completo", finalidad=finalidad)
        assert "co_educacion_saber11" in e.value.sugerencia


async def test_un_conteo_sobre_microdato_sigue_permitido(monkeypatch):
    """La regla es «solo agregado», no «prohibido»: un conteo no devuelve
    personas, y bloquearlo sería ruido."""
    _instala(monkeypatch, {SABER11: [{"estu_consecutivo": "SB1"}]})
    r = await catalogo.consultar(SABER11, detalle="conteo")
    assert "42" in r["texto"]


async def test_exportar_filas_del_siri_a_disco_exige_finalidad(monkeypatch):
    """Un volcado a disco es la copia que sobrevive a la conversación."""
    _instala(monkeypatch, {SIRI: [FILA_SIRI]})
    with pytest.raises(ErrorPrivacidad):
        await exportar.exportar(SIRI, "siri", formato="csv")


async def test_exportar_microdato_esta_bloqueado_antes_de_pedir_paginas(monkeypatch):
    red = _instala(monkeypatch, {SABER11: [{"estu_consecutivo": "SB1"}]})
    with pytest.raises(ErrorPrivacidad):
        await exportar.exportar(SABER11, "saber", formato="csv")
    # No se descargó nada: la puerta se cierra antes de paginar, no antes de
    # escribir. Lo contrario dejaría los datos en memoria y en la caché.
    assert not [p for _u, p in red.llamadas if "$limit" in p and "$group" not in p]


async def test_agrupar_por_documento_no_es_agregar_una_poblacion(monkeypatch):
    """«Agregar nunca pide permiso» vale porque agregar pregunta por
    poblaciones. Agrupar por cédula devuelve una fila por persona."""
    _instala(monkeypatch, {SIRI: [{"numero_identificacion": "79123456", "total": "2"}]})
    with pytest.raises(ErrorPrivacidad):
        await catalogo.agregar(SIRI, "numero_identificacion")
    r = await catalogo.agregar(SIRI, "numero_identificacion",
                               finalidad="control_fiscal")
    assert "79123456" not in r["texto"] and "79••••56" in r["texto"]


async def test_agrupar_por_entidad_no_pide_nada(monkeypatch):
    """El camino barato sigue siendo el que no identifica a nadie."""
    _instala(monkeypatch, {SIRI: [{"entidad_sancionado": "ALCALDÍA", "total": "9"}]})
    r = await catalogo.agregar(SIRI, "entidad_sancionado")
    assert "ALCALDÍA" in r["texto"]


# ================================ 2. el texto también escribe el documento ==
async def test_la_consulta_publicada_no_lleva_la_cedula(monkeypatch):
    """El sobre publica la URL exacta, y en una consulta nominal el filtro ES
    el documento: enmascarar la celda y escribirlo en el pie no servía de nada."""
    _instala(monkeypatch, {SIRI: [FILA_SIRI]})
    r = await integridad.disciplinarias(documento="79123456",
                                        finalidad="investigacion")
    assert "79123456" not in r["texto"]
    assert "79••••56" in r["texto"]
    assert "no corre tal cual" in r["texto"]


async def test_la_ficha_de_una_persona_no_escribe_el_numero_en_ningun_sitio(monkeypatch):
    _instala(monkeypatch, {empresas.RUES.id: [RUES_NATURAL]})
    r = await empresas.ficha("1023456789", finalidad="debida_diligencia")
    assert "1023456789" not in r["texto"]


async def test_el_titulo_del_dossier_no_reescribe_la_cedula(monkeypatch):
    """`redacta_filas` no puede tocar el título: iba aparte y salía entero."""
    _instala(monkeypatch, {empresas.RUES.id: [RUES_NATURAL]})
    r = await dossier.de_documento("1023456789", finalidad="periodismo")
    assert "1023456789" not in r["texto"]
    assert "10••••••89" in r["texto"]


async def test_el_nit_de_una_sociedad_sigue_saliendo_entero(monkeypatch):
    """La máscara no se generaliza: un NIT es un dato mercantil público y
    ocultarlo dejaría la respuesta inútil para cruzar con SECOP."""
    _instala(monkeypatch, {empresas.RUES.id: [RUES_JURIDICA]})
    r = await dossier.de_documento("900123456")
    assert "900123456" in r["texto"]


# ======================================= 3. por fila, no por página entera ==
async def test_una_persona_en_la_pagina_no_tapa_los_nit_de_las_sociedades(monkeypatch):
    """La decisión por página era gruesa en los dos sentidos: una página
    mezclada es lo normal en el RUES, no el caso raro."""
    _instala(monkeypatch, {empresas.RUES.id: [RUES_JURIDICA, RUES_NATURAL]})
    r = await empresas.buscar(nombre="x", solo_juridicas=False,
                              finalidad="investigacion")
    assert "900123456" in r["texto"], "el NIT de la sociedad se perdió"
    assert "1023456789" not in r["texto"], "la cédula se publicó"
    assert "10••••••89" in r["texto"]


async def test_una_sancion_a_persona_natural_por_nombre_exige_finalidad(monkeypatch):
    """SECOP I contrata con personas naturales. Buscar por nombre se daba por
    jurídico sin mirar los documentos que volvían."""
    _instala(monkeypatch, {integridad.SECOP1.id: [
        {"nombre_contratista": "ANA PEREZ", "documento_contratista": "52123456",
         "nombre_entidad": "ALCALDÍA", "numero_de_resolucion": "R-1",
         "valor_sancion": "1000000", "fecha_de_publicacion": "2024-03-01"}]})
    with pytest.raises(ErrorPrivacidad):
        await integridad.sanciones_contratacion(nombre="ana perez")
    r = await integridad.sanciones_contratacion(nombre="ana perez",
                                                finalidad="control_fiscal")
    assert "52123456" not in r["texto"] and "52••••56" in r["texto"]


async def test_una_sancion_a_empresa_por_nombre_no_pide_nada(monkeypatch):
    """Y el caso común sigue sin fricción: exigir finalidad por buscar un
    nombre habría bloqueado la pregunta normal."""
    _instala(monkeypatch, {integridad.SECOP1.id: [
        {"nombre_contratista": "CONSTRUCTORA S A S",
         "documento_contratista": "900123456", "nombre_entidad": "INVÍAS",
         "numero_de_resolucion": "R-2", "valor_sancion": "500",
         "fecha_de_publicacion": "2024-01-01"}]})
    r = await integridad.sanciones_contratacion(nombre="constructora")
    assert "900123456" in r["texto"]


# ============================ 4. cifras que afirman más de lo que se midió ==
def test_cupo_entero_con_offset_no_confunde_la_pagina_con_el_total():
    """25 coincidencias, `offset=20`, `limite=20`: la página trae 5 y el total
    es 25, no 5. Y una página vacía con offset no autoriza a afirmar nada."""
    assert Total.cupo_entero([1] * 5, 20, offset=20).valor == 25
    assert Total.cupo_entero([1] * 5, 20, offset=0).valor == 5
    assert Total.cupo_entero([], 20, offset=20).valor is None
    assert Total.cupo_entero([], 20, offset=0).valor == 0
    assert Total.cupo_entero([1] * 20, 20, offset=20).valor is None


async def test_la_segunda_pagina_del_rues_declara_el_total_de_verdad(monkeypatch):
    _instala(monkeypatch, {empresas.RUES.id: [RUES_JURIDICA]})
    r = await empresas.buscar(nombre="x", limite=20, offset=20)
    assert r["estructurado"]["_meta"]["total_coincidencias"] == 21


async def test_el_dossier_no_anuncia_el_cupo_como_el_total(monkeypatch):
    """Con `limite=3`, tres matrículas son el tamaño de la muestra."""
    _instala(monkeypatch, {empresas.RUES.id: [RUES_JURIDICA] * 3})
    r = await dossier.de_documento("900123456")
    assert "3 o más matrículas" in r["texto"]


async def test_un_ranking_caido_no_se_publica_como_no_figura(monkeypatch):
    """`en_ranking` capturaba toda excepción y devolvía "", así que el dossier
    escribía «no figura»: una ausencia atribuida a una fuente que no se pudo
    consultar. Es el error que el servidor entero existe para no cometer."""
    _instala(monkeypatch, {empresas.RUES.id: [RUES_JURIDICA]},
             caidos=(empresas.MAS_GRANDES.id,))
    r = await dossier.de_documento("900123456")
    assert "no consultable" in r["texto"]
    assert "no figura" not in r["texto"]


async def test_la_ficha_tambien_dice_que_no_pudo_mirar_el_ranking(monkeypatch):
    _instala(monkeypatch, {empresas.RUES.id: [RUES_JURIDICA]},
             caidos=(empresas.MAS_GRANDES.id, empresas.ESTABLECIMIENTOS.id))
    r = await empresas.ficha("900123456")
    assert r["texto"].count("no consultable") == 2


# ===================================== y tres de consulta mal construida ==
async def test_el_nombre_completo_se_parte_en_terminos(monkeypatch):
    """SIRI guarda el nombre en cuatro columnas y ninguna tiene el completo:
    buscar «ANA PEREZ» dentro de cada una devolvía cero con la persona dentro.
    Un cero falso es el peor fallo posible en una consulta de antecedentes."""
    red = _instala(monkeypatch, {SIRI: [FILA_SIRI]})
    await integridad.disciplinarias(nombre="ANA PEREZ", finalidad="periodismo")
    donde = _consultas(red)
    # Cada término contra las cuatro columnas, y los términos entre sí con AND.
    assert donde.count("primer_nombre") >= 2
    assert ") AND (" in donde


async def test_un_nombre_de_un_solo_termino_se_comporta_igual_que_antes(monkeypatch):
    red = _instala(monkeypatch, {SIRI: [FILA_SIRI]})
    await integridad.disciplinarias(nombre="PEREZ", finalidad="periodismo")
    assert ") AND (" not in _consultas(red)


async def test_las_sanciones_de_las_dos_plataformas_salen_en_orden(monkeypatch):
    """Cada fuente venía ordenada por su cuenta y luego se concatenaban, así
    que el sobre anunciaba `fecha DESC` y entregaba SECOP I primero."""
    _instala(monkeypatch, {
        integridad.SECOP1.id: [
            {"nombre_contratista": "EMPRESA A", "documento_contratista": "900111111",
             "nombre_entidad": "E1", "numero_de_resolucion": "R-1",
             "valor_sancion": "1", "fecha_de_publicacion": "2012-01-01"}],
        integridad.SECOP2.id: [
            {"nombre_proveedor_objeto_de": "EMPRESA A", "nombre_entidad_creadora": "E2",
             "numero_de_acto": "A-9", "valor": "2", "fecha_evento": "2024-06-01",
             "tipo_de_sancion": "MULTA"}],
    })
    r = await integridad.sanciones_contratacion(nombre="empresa a")
    assert r["texto"].index("A-9") < r["texto"].index("R-1")


async def test_el_rango_de_trm_no_pierde_la_tasa_vigente_al_empezar(monkeypatch):
    """La TRM del 21 de enero de 2024 es la certificada el 19, vigente hasta el
    22. `vigenciadesde >= desde` la descartaba, y entonces `fecha=` y
    `desde=/hasta=` daban respuestas distintas para el mismo día."""
    red = _instala(monkeypatch, {macro.TRM.id: [
        {"vigenciadesde": "2024-01-19T00:00:00", "vigenciahasta": "2024-01-22T00:00:00",
         "valor": "3928.00", "unidad": "COP"}]})
    await macro.trm(desde="2024-01-21", hasta="2024-01-21")
    donde = _consultas(red)
    assert "vigenciahasta >= '2024-01-21" in donde
    assert "vigenciadesde >= " not in donde


async def test_el_nit_del_ranking_sale_como_entero(monkeypatch):
    """La fuente lo sirve como `899999068.00`; encadenado a la ficha,
    `solo_digitos` lo convertía en 89999906800 y consultaba otro documento."""
    _instala(monkeypatch, {empresas.MAS_GRANDES.id: [
        {"raz_n_social": "ECOPETROL S.A.", "nit": "899999068.00",
         "macrosector": "MINERO", "departamento_domicilio": "BOGOTÁ D.C.",
         "ingresos_operacionales": "$ 1,000", "total_activos": "$ 2,000",
         "total_patrimonio": "$ 3,000", "ganancia_p_rdida": "$ 4,000"}]})
    r = await empresas.ranking(anio=2025, grafica=False)
    assert "899999068" in r["texto"] and "899999068.00" not in r["texto"]


async def test_hasta_por_si_solo_no_cuela_una_agregacion_de_dos_millones(monkeypatch):
    """`hasta` producía filtro, así que pasaba la validación; pero un límite
    superior posterior al último reporte no descarta ninguna fila."""
    _instala(monkeypatch, {macro.TASAS.id: []})
    with pytest.raises(ErrorValidacion) as e:
        await macro.tasas(hasta="2030-01-01")
    assert "no acota nada" in e.value.sugerencia
