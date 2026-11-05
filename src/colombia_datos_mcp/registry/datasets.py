"""Conocimiento de dominio curado, versionado y testeado.

Todo lo de aquí fue verificado contra la API en vivo el 18-ago-2026. Los IDs
NO se resuelven solo desde aquí: el adaptador los valida contra el catálogo, y
esto es el respaldo. Los IDs de Socrata rotan (`6d52-qyqg` ya devuelve 403).

La familia de criminalidad se recontó el 5-nov-2026, después de que MinDefensa
recargara sus 23 datasets el 21-oct-2026. Esa recarga deshizo la duplicación
entre «HURTO A COMERCIO» y «HURTO A RESIDENCIAS», así que la nota que decía que
eran el mismo dato pasó de ser verdadera a ser falsa sin que cambiara una línea
de código: una nota del registro es una afirmación con fecha de caducidad, y por
eso cada una que importa tiene contrato que la vigila.
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
    "Confecámaras": "Confecámaras, Bogotá D.C.",
    "Supersociedades": "Superintendencia de Sociedades SuperSociedades, Bogotá D.C.",
    "Superfinanciera": "Superintendencia Financiera de Colombia - SUPERFINANCIERA, Bogotá D.C.",
    "Procuraduría": "Procuraduría General de la Nación, Bogotá D.C.",
    "Contraloría": "Contraloría General de la República, Bogotá D.C.",
    "ICFES": "Instituto Colombiano para la Evaluación de la Educación - ICFES, Bogotá D.C.",
    "MinEducación": "Ministerio de Educación Nacional MinEducación, Bogotá, D.C",
    "DNP": "Departamento Nacional de Planeación DNP, Bogotá D.C",
    "JCC": "Unidad Administrativa Especial Junta Central de Contadores - JCC, Bogotá D.C.",
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
            'Hasta la recarga del 21-oct-2026 este dataset servía cifras idénticas a «HURTO A RESIDENCIAS» y el registro advertía de no sumarlos. La fuente lo corrigió: ya no coinciden en ningún año —682.898 casos aquí, 619.378 allá— y sumarlos es legítimo. Lo que no lo es: un análisis hecho con descargas anteriores a esa fecha.',
            'La serie se rompe en 2017: 23.060 casos en 2016 contra 60.311 en 2017, con el homicidio plano en los mismos años (12.045 y 11.957). El salto es de este dataset, no del registro, así que una comparación que cruce 2017 mide la ruptura y no el fenómeno.',
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
            'Hasta la recarga del 21-oct-2026 «HURTO A COMERCIO» (7i2x-h5vp) servía esta misma serie y el registro advertía de no sumarlos. Ya no coinciden en ningún año —619.378 casos aquí, 682.898 allá— y sumarlos es legítimo. Una descarga anterior a esa fecha trae el dato duplicado.',
            'La serie se rompe en 2017: 24.191 casos en 2016 contra 46.550 en 2017, con el homicidio plano. Una comparación que cruce 2017 mide la ruptura y no el fenómeno.',
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

# -------------------------------------------------------------- empresas --
# Verificado contra la API en vivo el 05-nov-2026. Son las fuentes del registro
# mercantil y societario: lo que Croma vende como «verificación de empresas»
# está publicado como dataset abierto en datos.gov.co, sin credenciales.
EMPRESAS = {
    "rues": Dataset(
        id="c82u-588k",
        nombre="RUES - Personas Naturales, Personas Jurídicas y ESAL",
        unidad="una matrícula mercantil",
        campos_clave={
            "nit": "nit",
            "doc": "numero_identificacion",
            "nombre": "razon_social",
            "estado": "estado_matricula",
            "categoria": "categoria_matricula",
            "camara": "camara_comercio",
            "ciiu": "cod_ciiu_act_econ_pri",
        },
        campos_resumen=(
            "razon_social", "sigla", "nit", "digito_verificacion",
            "categoria_matricula", "organizacion_juridica", "estado_matricula",
            "camara_comercio", "fecha_matricula", "ultimo_ano_renovado",
            "cod_ciiu_act_econ_pri",
        ),
        notas=(
            "9.436.330 filas. 6.962.889 son PERSONA NATURAL y 2.473.441 son "
            "sociedad o ESAL: la mayoría del dataset son personas, no empresas.",
            "Una fila es una MATRÍCULA, no una empresa: 5.091.481 están "
            "CANCELADAS. Contar filas no cuenta empresas vivas.",
            "`nit` es de tipo text: hay que filtrar con comillas (nit='890903938'). "
            "Pasarlo como número da error de tipo en Socrata.",
            "Las fechas son text en formato YYYYMMDD (19841122), no "
            "calendar_date: `between` no funciona y hay que comparar cadenas.",
            "El literal de persona jurídica trae la ó acentuada: "
            "'SOCIEDAD ó PERSONA JURIDICA PRINCIPAL ó ESAL'.",
        ),
    ),
    "establecimientos": Dataset(
        id="nb3d-v3n7",
        nombre="RUES - Establecimientos, Agencias y Sucursales",
        unidad="un establecimiento de comercio",
        campos_clave={"nit_dueno": "nit_propietario", "nombre": "razon_social",
                      "estado": "estado_matricula"},
        campos_resumen=(
            "razon_social", "tipo_propietario", "nit_propietario",
            "estado_matricula", "camara_comercio", "fecha_matricula",
            "cod_ciiu_act_econ_pri",
        ),
        notas=(
            "6.391.836 filas. Son los puntos de venta, no las sociedades: una "
            "sociedad puede tener decenas y cada uno cuenta como fila.",
        ),
    ),
    "eeff_situacion": Dataset(
        id="pfdp-zks5",
        nombre="Supersociedades - Estados Financieros NIIF · Situación Financiera",
        unidad="una línea de un estado financiero (formato largo XBRL)",
        campos_clave={"nit": "nit", "concepto": "concepto", "valor": "valor",
                      "fecha": "fecha_corte", "periodo": "periodo"},
        campos_resumen=("nit", "fecha_corte", "periodo", "concepto", "valor"),
        notas=(
            "19.638.408 filas: una por concepto, empresa y corte. El balance de "
            "UNA empresa son cientos de filas, no una.",
            "`periodo` vale casi siempre 'Periodo Actual' o 'Periodo Anterior', "
            "etiquetas RELATIVAS al radicado. El año real está en `fecha_corte`.",
            "`valor` es de tipo text, no number: hay que castearlo para sumar o "
            "comparar.",
            "Los nombres de `concepto` traen mojibake de origen.",
        ),
    ),
    "eeff_resultados": Dataset(
        id="prwj-nzxa",
        nombre="Supersociedades - Estados Financieros NIIF · Resultado Integral",
        unidad="una línea de un estado de resultados (formato largo XBRL)",
        campos_clave={"nit": "nit", "concepto": "concepto", "valor": "valor",
                      "fecha": "fecha_corte", "periodo": "periodo"},
        campos_resumen=("nit", "fecha_corte", "periodo", "concepto", "valor"),
        notas=("8.091.357 filas. Mismas trampas que pfdp-zks5.",),
    ),
    "mas_grandes": Dataset(
        id="6cat-2gcs",
        nombre="Supersociedades - 10.000 Empresas más Grandes del País",
        unidad="una empresa en un año de corte",
        campos_clave={"nit": "nit", "nombre": "raz_n_social",
                      "anio": "a_o_de_corte", "activos": "total_activos",
                      "ingresos": "ingresos_operacionales"},
        campos_resumen=(
            "raz_n_social", "nit", "a_o_de_corte", "macrosector",
            "ingresos_operacionales", "total_activos", "total_patrimonio",
            "ganancia_p_rdida", "ciudad_domicilio", "departamento_domicilio",
        ),
        notas=(
            "50.000 filas, no 10.000: son 10.000 empresas por año, de 2021 a "
            "2025. Sin filtrar `a_o_de_corte` cada empresa sale cinco veces.",
            "Los importes son text: total_activos, ingresos_operacionales y "
            "ganancia_p_rdida hay que castearlos.",
            "Es un ranking por ingresos operacionales reportados a "
            "Supersociedades: no incluye quien no reporta ahí (bancos, por "
            "ejemplo, reportan a Superfinanciera).",
        ),
    ),
}

# ------------------------------------------------------------- integridad --
# «Screening de contrapartes» en términos de Croma. Verificado el 05-nov-2026.
INTEGRIDAD = {
    "siri": Dataset(
        id="iaeu-rcn6",
        nombre="Procuraduría - Antecedentes de SIRI",
        unidad="una sanción disciplinaria a una persona",
        campos_clave={"doc": "numero_identificacion", "sancion": "sanciones",
                      "calidad": "calidad_persona", "entidad": "entidad_sancionado",
                      "fecha": "fecha_efectos_juridicos"},
        campos_resumen=(
            "numero_identificacion", "calidad_persona", "entidad_sancionado",
            "cargo", "sanciones", "tipo_inhabilidad", "duracion_anos",
            "fecha_efectos_juridicos", "autoridad",
        ),
        notas=(
            "42.124 filas con NOMBRE y CÉDULA de personas identificadas: pasa "
            "por el motor de privacidad.",
            "26.091 son a miembros de la fuerza pública y 15.736 a servidores "
            "públicos. Solo 18 son a CONTRATISTA y 8 a PARTICULAR: para "
            "verificar un contratista del Estado este dataset está casi vacío.",
            "No es el certificado de antecedentes. Ausencia de filas aquí NO "
            "equivale a un certificado limpio de la Procuraduría.",
            "Todas las columnas son text, incluidas las fechas y las duraciones.",
        ),
    ),
    "sanciones_secop2": Dataset(
        id="it5q-hg94",
        nombre="SECOP II - Multas y Sanciones",
        unidad="un comentario sobre un proveedor (positivo o negativo)",
        campos_clave={"proveedor": "nombre_proveedor_objeto_de",
                      "contrato": "id_contrato", "proceso": "id_proceso",
                      "valor": "valor", "fecha": "fecha_evento",
                      "tipo": "tipo_de_sancion", "estado": "estado"},
        campos_resumen=(
            "nombre_proveedor_objeto_de", "nombre_entidad_creadora", "tipo",
            "tipo_de_sancion", "valor", "valor_pagado", "fecha_evento",
            "numero_de_acto", "estado",
        ),
        notas=(
            "El título engaña: de sus 588 filas, 533 son 'Comentarios "
            "positivos' y solo 55 'Comentarios negativos'. Es la tabla de "
            "retroalimentación de proveedores, no un registro de sanciones.",
            "Solo 145 filas están 'Publicado por el administrador de la "
            "plataforma'. Las otras 443 están a la espera de aprobación (379), "
            "rechazadas (33) o en borrador (31): contarlas todas como sanciones "
            "multiplica la cifra por cuatro.",
            "`as_codigo_proveedor_objeto` es un código interno de SECOP, NO el "
            "NIT: no sirve para cruzar con el RUES ni con los contratos.",
            "588 filas para ~5,9 M de contratos. No es una base de sanciones "
            "utilizable; se expone para poder decirlo con datos.",
        ),
    ),
    "sanciones_secop1": Dataset(
        id="4n4q-k399",
        nombre="SECOP I - Multas y Sanciones",
        unidad="una sanción a un contratista",
        campos_clave={"doc": "documento_contratista",
                      "contratista": "nombre_contratista",
                      "entidad": "nombre_entidad", "nit_entidad": "nit_entidad",
                      "valor": "valor_sancion", "fecha": "fecha_de_publicacion"},
        campos_resumen=(
            "nombre_contratista", "documento_contratista", "nombre_entidad",
            "numero_de_contrato", "numero_de_resolucion", "valor_sancion",
            "fecha_de_publicacion", "fecha_de_firmeza", "municipio",
        ),
        notas=(
            "1.716 filas, y es la ÚNICA de las dos de contratación que trae el "
            "documento del contratista: es la que sirve para cruzar.",
            "SECOP I dejó de ser la plataforma vigente: las sanciones recientes "
            "no están aquí. Ausencia de filas no es ausencia de sanciones.",
        ),
    ),
    "sanciones_contadores": Dataset(
        id="fs36-azrv",
        nombre="Junta Central de Contadores - Registro de Sanciones",
        unidad="una sanción a un contador público",
        campos_clave={"doc": "c_dula", "nombre": "contador", "tipo": "tipo",
                      "fecha": "fecha_resoluci_n"},
        campos_resumen=("contador", "c_dula", "tipo", "resoluci_n",
                        "fecha_resoluci_n", "fecha_inicio", "fecha_fin", "meses"),
        notas=(
            "1.451 filas con nombre y cédula: pasa por el motor de privacidad.",
            "Importa para contratación pública porque el revisor fiscal "
            "sancionado firma estados financieros de proponentes.",
        ),
    ),
    "responsabilidad_fiscal": Dataset(
        id="jr8e-e8tu",
        nombre="Contraloría - Responsabilidad Fiscal",
        unidad="una sanción o multa fiscal",
        campos_clave={"doc": "n_mero_de_identificaci_n",
                      "nombre": "raz_n_social_de_la_entidad",
                      "tipo": "tipo_de_sanci_n_multa"},
        campos_resumen=("raz_n_social_de_la_entidad", "n_mero_de_identificaci_n",
                        "tipo_de_sanci_n_multa", "monto_de_la_multa_o_sanci",
                        "fecha_de_resoluci_n_que", "tema_clasificaci_n_o_motivo"),
        notas=(
            "60 filas y sin actualizar desde el 23-mar-2022. NO es el Boletín "
            "de Responsables Fiscales: es una muestra residual. Buscar aquí y "
            "no encontrar nada no dice nada.",
        ),
    ),
}

# -------------------------------------------------------------- educación --
EDUCACION = {
    "saber11": Dataset(
        id="kgxf-xxbe",
        nombre="ICFES - Resultados únicos Saber 11",
        unidad="un estudiante en una aplicación del examen",
        campos_clave={"periodo": "periodo", "global": "punt_global",
                      "colegio": "cole_nombre_establecimiento",
                      "cod_colegio": "cole_cod_dane_establecimiento",
                      "municipio": "cole_mcpio_ubicacion",
                      "cod_municipio": "cole_cod_mcpio_ubicacion",
                      "departamento": "cole_depto_ubicacion"},
        campos_resumen=(),
        notas=(
            "7.109.704 filas de MICRODATO INDIVIDUAL: género, fecha de "
            "nacimiento, estrato de la vivienda y escolaridad de los padres. "
            "Este servidor solo lo expone agregado.",
            "Los puntajes son de tipo text, incluido punt_global: hay que "
            "castearlos para promediar.",
            "`periodo` es AÑO+SEMESTRE pegados (20224). Los periodos acabados "
            "en 4 son la aplicación masiva de octubre (~1,1 M de estudiantes) y "
            "los acabados en 1 son la minoritaria de marzo (~15 mil): "
            "promediarlos juntos mezcla dos poblaciones distintas.",
            "Sin actualizar desde el 23-ago-2023: la serie termina en 2022-4.",
        ),
    ),
    "saber_pro": Dataset(
        id="u37r-hjmu",
        nombre="ICFES - Resultados únicos Saber Pro",
        unidad="un estudiante universitario en una aplicación",
        campos_clave={"periodo": "periodo"},
        notas=("Microdato individual. Mismas reglas que Saber 11.",),
    ),
    "saber_tyt": Dataset(
        id="iwgf-bkfk",
        nombre="ICFES - Resultados únicos Saber TyT",
        unidad="un estudiante técnico o tecnológico en una aplicación",
        campos_clave={"periodo": "periodo"},
        notas=("Microdato individual. Mismas reglas que Saber 11.",),
    ),
    "men_municipio": Dataset(
        id="nudc-7mev",
        nombre="MinEducación - Estadísticas en educación por municipio",
        unidad="un municipio en un año",
        campos_clave={"anio": "a_o", "cod_municipio": "c_digo_municipio",
                      "municipio": "municipio", "departamento": "departamento",
                      "poblacion": "poblaci_n_5_16"},
        campos_resumen=(
            "a_o", "c_digo_municipio", "municipio", "departamento",
            "poblaci_n_5_16", "cobertura_neta", "cobertura_bruta",
            "deserci_n", "aprobaci_n", "reprobaci_n", "repitencia",
            "tama_o_promedio_de_grupo",
        ),
        notas=(
            "15.707 filas: ~1.100 municipios por año. Es la única fuente del "
            "servidor con POBLACIÓN municipal, y es solo la de 5 a 16 años: no "
            "sirve de denominador para tasas de criminalidad.",
            "Los nombres de campo llevan la tilde comida por el slug: `a_o`, "
            "`deserci_n`, `poblaci_n_5_16`, `c_digo_municipio`.",
            "Los indicadores son porcentajes, y vienen como text pese a estar "
            "declarados Number.",
            "La cobertura bruta pasa de 100 % con normalidad: cuenta "
            "matriculados de cualquier edad sobre la población del rango "
            "teórico. Medellín 2023 estaba en 107,16 %.",
        ),
    ),
    "men_departamento": Dataset(
        id="ji8i-4anb",
        nombre="MinEducación - Estadísticas en educación por departamento",
        unidad="un departamento en un año",
        campos_clave={"anio": "a_o", "departamento": "departamento"},
        notas=("Agregado departamental del mismo tablero que nudc-7mev.",),
    ),
}

# ------------------------------------------------------------- territorio --
TERRITORIO = {
    "mdm": Dataset(
        id="nkjx-rsq7",
        nombre="DNP - Medición del Desempeño Municipal",
        unidad="un valor de un indicador para un municipio en un año",
        campos_clave={"cod_municipio": "codigo_entidad", "entidad": "entidad",
                      "indicador": "indicador", "dato": "dato", "anio": "anio",
                      "departamento": "departamento"},
        campos_resumen=("anio", "codigo_entidad", "entidad", "departamento",
                        "indicador", "dato", "etiqueta"),
        notas=(
            "22.020 filas: formato largo, 4 indicadores × 5.505 observaciones.",
            "Los indicadores son MDM, Componente de gestión, Componente de "
            "resultados y Grupo de dotaciones iniciales. No es TerriData: el "
            "catálogo completo de TerriData no tiene API pública.",
            "Sin actualizar desde el 21-feb-2022, aunque la ficha diga otra "
            "cosa. El MDM se publica cada año; estas cifras no son las últimas.",
            "`dato` es text y usa el separador decimal de la fuente.",
        ),
    ),
}

# ------------------------------------------------------------------ macro --
MACRO = {
    "trm": Dataset(
        id="32sa-8pi3",
        nombre="Superfinanciera - Tasa de Cambio Representativa del Mercado (TRM)",
        unidad="una TRM vigente para un rango de fechas",
        campos_clave={"valor": "valor", "desde": "vigenciadesde",
                      "hasta": "vigenciahasta"},
        campos_resumen=("vigenciadesde", "vigenciahasta", "valor", "unidad"),
        notas=(
            "8.381 filas. Una fila puede cubrir VARIOS días: la TRM de un "
            "viernes rige sábado y domingo, y `vigenciahasta` lo dice. Para la "
            "TRM de una fecha hay que buscar el rango que la contiene, no la "
            "igualdad con `vigenciadesde`.",
            "Es la TRM que certifica la Superfinanciera, no una tasa de mercado "
            "intradía.",
        ),
    ),
    "tasas_captacion": Dataset(
        id="axk9-g2nh",
        nombre="Superfinanciera - Tasas de interés de captación y mercado monetario",
        unidad="una tasa reportada por una entidad en un corte",
        campos_clave={"fecha": "fechacorte", "entidad": "nombreentidad",
                      "tasa": "tasa", "monto": "monto",
                      "descripcion": "descripcion"},
        campos_resumen=("fechacorte", "nombreentidad", "descripcion", "tasa",
                        "monto", "nombre_unidad_de_captura"),
        notas=(
            "2.102.178 filas. Una fila es lo que UNA entidad reportó, no una "
            "tasa de mercado: promediar sin ponderar por `monto` da una cifra "
            "que no es la del sistema.",
        ),
    ),
}

# Lo que el servidor NO puede ofrecer y conviene que conste, porque la pregunta
# se hace sola al ver el resto. Verificado el 05-nov-2026.
SIN_FUENTE_ABIERTA = {
    "poblacion_municipal": (
        "El DANE no publica las proyecciones de población municipal como API. "
        "En datos.gov.co solo hay republicaciones de alcaldías sueltas "
        "(Chiquinquirá, Sabaneta, Manizales) y bajo la atribución del DANE hay "
        "exactamente dos datasets, los dos de DIVIPOLA. Sin denominador no hay "
        "tasas por 100.000 habitantes: lo más cercano es la población de 5 a 16 "
        "años del MinEducación (nudc-7mev), que no sirve para eso."
    ),
    "ipc": (
        "El IPC del DANE y las series del Banco de la República no están en "
        "datos.gov.co ni tienen API REST pública documentada. Sin IPC no hay "
        "deflactor, así que los montos de SECOP siguen siendo nominales. Lo que "
        "sí hay es la TRM (32sa-8pi3), que permite convertir a dólares de la "
        "fecha del contrato."
    ),
    "rama_judicial": (
        "Los procesos judiciales, la Registraduría, el RUNT y el SIMIT solo se "
        "consultan por formulario web con captcha, no por API abierta. No "
        "entran en un servidor que se define como «sin credenciales»."
    ),
}

LICENCIA_POR_DEFECTO = "CC BY-SA 4.0 (verificar por dataset)"


# Todas las familias en un sitio. `por_id` recorría solo SECOP y DIVIPOLA, así
# que al añadir cinco familias más los campos curados de las nuevas no se
# aplicaban: `detalle="resumen"` caía en la heurística y devolvía las 36
# columnas del RUES, nombre del representante legal incluido.
FAMILIAS = {
    "secop": SECOP, "crimen": CRIMEN, "empresas": EMPRESAS,
    "integridad": INTEGRIDAD, "educacion": EDUCACION, "territorio": TERRITORIO,
    "macro": MACRO,
}


def todos() -> list[Dataset]:
    sueltos = [DIVIPOLA_MUNICIPIOS, DIVIPOLA_CENTROS, DIVIPOLA_DEPARTAMENTOS]
    return [d for familia in FAMILIAS.values() for d in familia.values()] + sueltos


def por_id(dataset_id: str) -> Dataset | None:
    for d in todos():
        if d.id == dataset_id:
            return d
    return None


def familia_de(dataset_id: str) -> str | None:
    """A qué familia pertenece un dataset. Lo usa el motor de privacidad para
    saber si una respuesta puede traer personas identificadas."""
    for nombre, familia in FAMILIAS.items():
        if any(d.id == dataset_id for d in familia.values()):
            return nombre
    return None
