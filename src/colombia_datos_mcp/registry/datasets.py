"""Conocimiento de dominio curado, versionado y testeado.

Todo lo de aquí fue verificado contra la API en vivo el 18-ago-2026. Los IDs
NO se resuelven solo desde aquí: el adaptador los valida contra el catálogo, y
esto es el respaldo. Los IDs de Socrata rotan (`6d52-qyqg` ya devuelve 403).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Dataset:
    id: str
    nombre: str
    unidad: str            # QUÉ cuenta una fila: crítico para no sumar peras con manzanas
    campos_clave: dict = field(default_factory=dict)
    campos_resumen: tuple = ()
    notas: tuple = ()


# ------------------------------------------------------------------ SECOP --
SECOP = {
    "contratos": Dataset(
        id="jbjy-vk9h",
        nombre="SECOP II - Contratos Electrónicos",
        unidad="un contrato",
        campos_clave={
            "id": "id_contrato",
            "entidad": "nombre_entidad",
            "nit_entidad": "nit_entidad",
            "proveedor": "proveedor_adjudicado",
            "doc_proveedor": "documento_proveedor",
            "departamento": "departamento",
            "modalidad": "modalidad_de_contratacion",
            "fecha": "fecha_de_firma",
            "valor": "valor_del_contrato",
            "proceso": "proceso_de_compra",
            "url": "urlproceso",
        },
        campos_resumen=(
            "id_contrato", "nombre_entidad", "proveedor_adjudicado",
            "objeto_del_contrato", "modalidad_de_contratacion",
            "valor_del_contrato", "fecha_de_firma", "estado_contrato",
            "departamento",
        ),
        notas=(
            "85 columnas, ~5,88 M filas.",
            "nit_entidad es de tipo number aquí y text en p6dx-8zbt: no unir por tipo.",
        ),
    ),
    "procesos": Dataset(
        id="p6dx-8zbt",
        nombre="SECOP II - Procesos de Contratación",
        unidad="un proceso de compra",
        campos_clave={
            "id": "id_del_proceso",
            "entidad": "entidad",
            "nit_entidad": "nit_entidad",
            "departamento": "departamento_entidad",
            "modalidad": "modalidad_de_contratacion",
            "valor": "precio_base",
            "fecha": "fecha_de_publicacion_del",
        },
        campos_resumen=(
            "id_del_proceso", "entidad", "nombre_del_procedimiento",
            "modalidad_de_contratacion", "precio_base", "fase",
            "departamento_entidad",
        ),
        notas=("~9,02 M filas.",),
    ),
    "adiciones": Dataset(
        id="cb9c-h8sn",
        nombre="SECOP II - Adiciones (modificaciones contractuales)",
        unidad="una modificación contractual",
        campos_clave={"id": "identificador", "contrato": "id_contrato", "fecha": "fecharegistro"},
        campos_resumen=("identificador", "id_contrato", "tipo", "descripcion", "fecharegistro"),
        notas=(
            "26,1 M filas para ~5,9 M contratos: el join es 1:N pesado.",
            "Se llaman 'Adiciones', no 'modificaciones': buscar 'modificaciones' da 0 resultados.",
        ),
    ),
    "proveedores": Dataset(
        id="qmzu-gj57",
        nombre="SECOP II - Proveedores Registrados",
        unidad="un proveedor",
        campos_clave={"doc": "documento_proveedor"},
        campos_resumen=("nombre_proveedor", "documento_proveedor", "tipo_documento", "estado"),
    ),
    "integrado": Dataset(
        id="rpmr-utcd",
        nombre="SECOP Integrado (I + II, solo adjudicados)",
        unidad="un contrato adjudicado",
        campos_clave={
            "entidad": "nombre_de_la_entidad",
            "nit_entidad": "nit_de_la_entidad",
            "valor": "valor_contrato",
            "fecha": "fecha_de_firma_del_contrato",
            "origen": "origen",
        },
        campos_resumen=(
            "numero_del_contrato", "nombre_de_la_entidad", "nom_raz_social_contratista",
            "objeto_del_proceso", "valor_contrato", "fecha_de_firma_del_contrato", "origen",
        ),
        notas=("La vista más simple para análisis cruzado SECOP I + II.",),
    ),
    "secop1": Dataset(
        id="f789-7hwg",
        nombre="SECOP I - Procesos de Compra Pública",
        unidad="un proceso",
        campos_clave={"entidad": "nombre_de_la_entidad", "nit_entidad": "nit_de_la_entidad"},
        campos_resumen=("numero_de_proceso", "nombre_de_la_entidad", "objeto_a_contratar", "cuantia_proceso"),
    ),
    "paa": Dataset(
        id="9sue-ezhx",
        nombre="SECOP II - Plan Anual de Adquisiciones (detalle)",
        unidad="una línea del PAA",
        campos_clave={"entidad": "nombre_entidad", "nit_entidad": "nit_entidad", "anio": "annio"},
        campos_resumen=("nombre_entidad", "annio", "descripcion", "modalidad", "valor_total_esperado"),
        notas=("Las columnas de fecha son text, NO calendar_date: no se filtran con between.",),
    ),
    "tvec": Dataset(
        id="rgxm-mmea",
        nombre="Tienda Virtual del Estado Colombiano - Consolidado",
        unidad="una orden de compra",
        campos_clave={"id": "identificador_de_la_orden", "entidad": "entidad", "valor": "total"},
        campos_resumen=("identificador_de_la_orden", "entidad", "proveedor", "total", "fecha", "estado"),
    ),
}

# Joins verificados. Sin esto el modelo no acierta los fieldName truncados.
JOINS = (
    ("p6dx-8zbt.id_del_proceso", "jbjy-vk9h.proceso_de_compra"),
    ("jbjy-vk9h.id_contrato", "cb9c-h8sn.id_contrato"),
    ("rgxm-mmea.identificador_de_la_orden", "usqp-5nsn.orden"),
    ("hgi6-6wh3.id_procedimiento", "p6dx-8zbt.id_del_proceso"),
)

# --------------------------------------------------------------- DIVIPOLA --
DIVIPOLA_MUNICIPIOS = Dataset(
    id="gdxc-w37w",
    nombre="DIVIPOLA - Códigos municipios",
    unidad="una entidad territorial",
    campos_clave={"cod": "cod_mpio", "nombre": "nom_mpio", "dpto": "dpto", "tipo": "tipo_municipio"},
    campos_resumen=("cod_dpto", "dpto", "cod_mpio", "nom_mpio", "tipo_municipio"),
    notas=(
        "1.122 filas: 1.103 municipios + 18 áreas no municipalizadas + 1 isla.",
        "Atribuido a la Gobernación de Guainía: es una republicación de DIVIPOLA.",
        "longitud/latitud son text con coma decimal.",
    ),
)

DIVIPOLA_CENTROS = Dataset(
    id="xaxy-8nri",
    nombre="DIVIPOLA - Códigos cabeceras - Centros poblados",
    unidad="un centro poblado",
    campos_clave={
        "cod_mpio": "codigo_municipio",
        "cod_cp": "codigo_centro_poblado",
        "nombre": "nombre_centro_poblado",
        "tipo": "tipo_centro_poblado",
    },
    campos_resumen=(
        "codigo_departamento", "nombre_departamento", "codigo_municipio",
        "nombre_municipio", "codigo_centro_poblado", "nombre_centro_poblado",
        "tipo_centro_poblado",
    ),
    notas=(
        "8.161 filas: 1.104 cabeceras municipales (CM) + 7.057 centros poblados (CP).",
        "Atribución DANE. CC BY-SA 4.0, corte 30-dic-2024.",
        "Exactamente un registro (Medellín) trae separador de miles en la coordenada.",
    ),
)

DIVIPOLA_DEPARTAMENTOS = Dataset(
    id="vcjz-niiq",
    nombre="DIVIPOLA - Códigos departamentos",
    unidad="un departamento",
    campos_clave={},
    campos_resumen=(),
)

# Cadenas de atribución exactas. El facet solo funciona con el literal: buscar
# `attribution=DANE` devuelve 0, y el portal escribe "Estadísticas" en plural,
# que no es el nombre real de la entidad.
ATRIBUCIONES = {
    "DANE": "Departamento Administrativo Nacional de Estadísticas - DANE, Bogotá D.C.",
    "CCE": "Agencia Nacional de Contratación Pública - Colombia Compra Eficiente, Bogotá D.C.",
    "MinDefensa": "Ministerio de Defensa Nacional - MinDefensa, Bogotá D.C.",
    "Fiscalía": "Fiscalía General de la Nación, Bogotá D.C.",
    "MinTIC": "Ministerio de Tecnologías de la Información y las Comunicaciones - MinTIC, Bogotá D.C.",
}

# Los nombres en SECOP no son los coloquiales.
# Alias coloquial -> fragmento que SÍ aparece en `nombre_entidad` de
# jbjy-vk9h (SECOP II - Contratos). Verificado contra la fuente el 18-ago-2026:
# la suite de contrato lo revalida a diario, porque un alias caduco convierte
# una búsqueda válida en cero filas.
#
# Ojo con la tentación de escribir el nombre "correcto" de la entidad: varias
# se registran con su sigla y nada más. INVIAS y UNGRD figuran literalmente
# así, y expandirlas a su razón social daba cero.
ALIAS_ENTIDADES = {
    "DANE": "DEPARTAMENTO ADMINISTRATIVO NACIONAL DE ESTADISTICA",
    "IGAC": "INSTITUTO GEOGRAFICO AGUSTIN CODAZZI",
    "ICBF": "INSTITUTO COLOMBIANO DE BIENESTAR FAMILIAR",
    "SENA": "SERVICIO NACIONAL DE APRENDIZAJE",
    "INVIAS": "INVIAS",
    "DIAN": "DIRECCION DE IMPUESTOS Y ADUANAS NACIONALES",
    "ANLA": "AUTORIDAD NACIONAL DE LICENCIAS AMBIENTALES",
    "UNGRD": "UNGRD",
}

# RTVC no está en el dataset de contratos con ningún nombre: solo aparece en
# rpmr-utcd (SECOP Integrado), como "RADIO TELEVISION NACIONAL DE COLOMBIA."
# —con punto final— y como "RTVC - RADIO TELEVISIÓN NACIONAL DE COLOMBIA".
# Ponerlo como alias de contratos garantizaba cero, así que se documenta aquí.
SOLO_EN_INTEGRADO = {"RTVC": "RADIO TELEVISION NACIONAL DE COLOMBIA."}



# ---------------------------------------------------------------- crimen --
# Los 23 datasets de MinDefensa que cuentan DELITOS, verificados contra la API
# el 18-ago-2026. De los 37 que comparten esquema se excluyen a propósito los
# operativos —incautaciones, erradicación, minas intervenidas—: ahí `cantidad`
# son hectáreas o kilos, no casos, y mezclarlos con homicidios produce sumas
# sin significado.
CRIMEN = {
    'abigeato': Dataset(
        id='p88b-5ac7',
        nombre='ABIGEATO',
        unidad='una cabeza de ganado hurtada',
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad"},
        notas=(
            'La unidad son cabezas de ganado hurtadas, no casos.',
        ),
    ),
    'afectacion_fuerza_publica': Dataset(
        id='8rpn-wpty',
        nombre='AFECTACION FUERZA PUBLICA',
        unidad='un miembro de la fuerza pública afectado',
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad"},
        notas=(
            'La serie empieza en 2010.',
        ),
    ),
    'delitos_ambientales': Dataset(
        id='9zck-qfvc',
        nombre='DELITOS AMBIENTALES',
        unidad='un delito ambiental',
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad"},
    ),
    'delitos_informaticos': Dataset(
        id='4v6r-wu98',
        nombre='DELITOS INFORMATICOS',
        unidad='un delito informático',
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad"},
        notas=(
            'La serie empieza en 2006: la categoría no existía antes. Un porcentaje contra 2003 mide la creación de la categoría.',
        ),
    ),
    'delitos_sexuales': Dataset(
        id='bz43-8ahq',
        nombre='DELITOS SEXUALES',
        unidad='una víctima de delito sexual',
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad"},
        notas=(
            'Muy sensible a la propensión a denunciar.',
        ),
    ),
    'extorsion': Dataset(
        id='q2ib-t9am',
        nombre='EXTORSION',
        unidad='un caso de extorsión',
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad"},
    ),
    'homicidio': Dataset(
        id='m8fd-ahd9',
        nombre='HOMICIDIO',
        unidad='una víctima de homicidio',
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad"},
        notas=(
            'El indicador menos sensible al subregistro: un muerto es difícil de no registrar. 2017 fue el mínimo de la serie, con 11.957 víctimas.',
        ),
    ),
    'homicidio_transito': Dataset(
        id='uav5-b85g',
        nombre='HOMICIDIO TRANSITO',
        unidad='una víctima en accidente de tránsito',
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad"},
    ),
    'hurto_comercio': Dataset(
        id='7i2x-h5vp',
        nombre='HURTO COMERCIO',
        unidad='un hurto a comercio',
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad"},
        notas=(
            '«HURTO A COMERCIO» y «HURTO A RESIDENCIAS» son el MISMO dato: cifras idénticas año por año. Uno de los dos títulos está mal en la fuente. Nunca los sumes: duplicarías la cifra.',
        ),
    ),
    'hurto_financieras': Dataset(
        id='i7h7-wmjc',
        nombre='HURTO FINANCIERAS',
        unidad='un hurto a entidad financiera',
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad"},
    ),
    'hurto_personas': Dataset(
        id='4rxi-8m8d',
        nombre='HURTO PERSONAS',
        unidad='un hurto a persona',
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad"},
    ),
    'hurto_residencias': Dataset(
        id='7mn7-vzqp',
        nombre='HURTO RESIDENCIAS',
        unidad='un hurto a residencia',
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad"},
        notas=(
            'Idéntico a «HURTO A COMERCIO» (7i2x-h5vp), año por año. Uno de los dos títulos está mal en la fuente. No los sumes.',
        ),
    ),
    'hurto_vehiculos': Dataset(
        id='csb4-y6v2',
        nombre='HURTO VEHICULOS',
        unidad='un hurto de vehículo',
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad"},
    ),
    'invasion_tierras': Dataset(
        id='kvjj-d2ay',
        nombre='INVASION TIERRAS',
        unidad='un caso de invasión de tierras',
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad"},
    ),
    'lesiones': Dataset(
        id='jr6v-i33g',
        nombre='LESIONES',
        unidad='una víctima de lesiones personales',
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad"},
    ),
    'lesiones_transito': Dataset(
        id='ntej-qq7v',
        nombre='LESIONES TRANSITO',
        unidad='una víctima lesionada en accidente',
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad"},
    ),
    'pirateria_terrestre': Dataset(
        id='sutf-7dyz',
        nombre='PIRATERIA TERRESTRE',
        unidad='un caso de piratería terrestre',
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad"},
    ),
    'secuestro': Dataset(
        id='d7zw-hpf4',
        nombre='SECUESTRO',
        unidad='una víctima de secuestro',
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad"},
    ),
    'terrorismo': Dataset(
        id='yi5j-5fe9',
        nombre='TERRORISMO',
        unidad='un hecho terrorista',
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad"},
    ),
    'trata_personas': Dataset(
        id='95c7-mm6s',
        nombre='TRATA PERSONAS',
        unidad='una víctima de trata',
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad"},
    ),
    'violencia_intrafamiliar': Dataset(
        id='gepp-dxcs',
        nombre='VIOLENCIA INTRAFAMILIAR',
        unidad='un caso de violencia intrafamiliar',
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad"},
        notas=(
            'Muy sensible a la propensión a denunciar: el alza desde 2003 mide sobre todo cuánto se denuncia hoy.',
        ),
    ),
    'voladura_oleoductos': Dataset(
        id='ec2r-4byk',
        nombre='VOLADURA OLEODUCTOS',
        unidad='una voladura de oleoducto',
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad"},
    ),
    'voladura_puentes': Dataset(
        id='m98b-cdys',
        nombre='VOLADURA PUENTES',
        unidad='una voladura de puente o vía',
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad"},
    ),
}

LICENCIA_POR_DEFECTO = "CC BY-SA 4.0 (verificar por dataset)"


def por_id(dataset_id: str) -> Dataset | None:
    for d in list(SECOP.values()) + [
        DIVIPOLA_MUNICIPIOS, DIVIPOLA_CENTROS, DIVIPOLA_DEPARTAMENTOS
    ]:
        if d.id == dataset_id:
            return d
    return None
