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
    "grupos": Dataset(
        id="ceth-n4bn",
        nombre="SECOP II - Grupos de Proveedores",
        unidad="un socio dentro de un consorcio o unión temporal",
        campos_clave={"grupo": "codigo_grupo", "nombre_grupo": "nombre_grupo",
                      "nit_grupo": "nit_grupo", "socio": "nit_participante",
                      "nombre_socio": "nombre_participante",
                      "participacion": "participacion",
                      "lider": "es_lider_del_grupo",
                      "representante": "nombre_representante_legal_grupo"},
        campos_resumen=(
            "codigo_grupo", "nombre_grupo", "nombre_participante",
            "nit_participante", "participacion", "es_lider_del_grupo",
            "nombre_representante_legal_grupo", "fecha_creaci_n_grupo",
            "minucipio",
        ),
        notas=(
            "675.436 filas. Responde quién está detrás de un consorcio, que es "
            "justo lo que el registro mercantil no sabe: los consorcios y las "
            "uniones temporales no se matriculan.",
            "La ÚNICA llave fiable es `codigo_grupo`, que es el "
            "`codigo_proveedor` de hgi6-6wh3. El `nit_grupo` casi siempre vale "
            "«No Definido» y el nombre NO identifica: en un solo municipio "
            "había once grupos distintos llamados «CONSORCIO PUENTE GUADUAS», "
            "con socios diferentes.",
            "`participacion` es el porcentaje del socio y permite repartir el "
            "valor de un contrato entre quienes están detrás. Es una "
            "atribución contable, no un flujo de caja.",
            "El municipio viene en `minucipio`, con la errata en el nombre de "
            "la columna.",
        ),
    ),
    "proponentes": Dataset(
        id="hgi6-6wh3",
        nombre="SECOP II - Proponentes por Proceso",
        unidad="un oferente en un proceso",
        campos_clave={"proceso": "id_procedimiento",
                      "entidad": "entidad_compradora", "nit_entidad": "nit_entidad",
                      "proveedor": "proveedor", "nit_proveedor": "nit_proveedor",
                      "codigo_proveedor": "codigo_proveedor"},
        campos_resumen=(
            "id_procedimiento", "nombre_procedimiento", "entidad_compradora",
            "proveedor", "nit_proveedor", "codigo_proveedor",
            "fecha_publicaci_n",
        ),
        notas=(
            "2.379.104 filas. Es la lista de QUIÉN OFERTÓ, no solo de quién "
            "ganó: con ella se ve si dos ofertas rivales comparten socio.",
            "Solo existe para los procesos competitivos. En un municipio con "
            "1.157 procesos había oferentes publicados de 208: de la "
            "contratación directa no hay nada que mirar aquí.",
            "`codigo_proveedor` es la llave hacia ceth-n4bn cuando el oferente "
            "es un consorcio.",
        ),
    ),
    "ejecucion": Dataset(
        id="mfmm-jqmq",
        nombre="SECOP II - Ejecución Contratos (plan de entregables)",
        unidad="una línea del plan de ejecución de un contrato",
        campos_clave={"contrato": "identificadorcontrato", "plan": "nombreplan",
                      "tipo": "tipoejecucion", "planeada": "cantidad_planeada",
                      "recibida": "cantidadrecibida",
                      "avance": "porcentaje_de_avance_real",
                      "esperado": "porcentajedeavanceesperado",
                      "entrega_real": "fechadeentregareal"},
        campos_resumen=(
            "identificadorcontrato", "nombreplan", "tipoejecucion",
            "descripci_n", "unidad", "cantidad_planeada", "cantidadrecibida",
            "cantidadporrecibir", "porcentaje_de_avance_real",
            "porcentajedeavanceesperado", "fechadeentregaesperada",
            "fechadeentregareal",
        ),
        notas=(
            "Es el único sitio de SECOP II donde está QUÉ SE RECIBIÓ, y para "
            "obra municipal está vacío: cero filas para los 953 contratos de "
            "un municipio, una sola fila en los 218 contratos de obra de ese "
            "municipio y sus cuatro vecinos desde 2022, cero en las 16 obras "
            "de la Gobernación de Cundinamarca y cero en seis de Medellín.",
            "7.723.427 filas en todo el país, concentradas en entidades "
            "nacionales. Un cero aquí NO significa que la obra no se entregó: "
            "significa que la entidad no usa el módulo.",
            "La llave es `identificadorcontrato` = `id_contrato` de "
            "jbjy-vk9h, mismo formato CO1.PCCNTR.*",
            "`condiciones_de_entrega`, que vive en el contrato mismo, es el "
            "otro campo de entrega y suele venir «No Definido».",
        ),
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
# -------------------------------------------------------------- fiscalía --
# El SPOA: la otra mitad del delito. La Policía cuenta denuncias; la Fiscalía
# cuenta qué pasó con ellas, y además cubre los delitos contra la
# administración pública, que MinDefensa no publica. Verificado el 19-nov-2026.
FISCALIA = {
    "procesos": Dataset(
        id="dbdv-iihs",
        nombre="Fiscalía - Procesos (SPOA)",
        unidad="un delito dentro de una noticia criminal, NO un proceso",
        campos_clave={"proceso": "proceso_anonimizado", "delito": "delito",
                      "titulo": "titulo_delito", "capitulo": "capitulo_delito",
                      "municipio": "cod_dane_hecho",
                      "nombre_municipio": "municipio_hecho",
                      "departamento": "departamento_hecho", "anio": "a_o_hecho",
                      "etapa": "etapa", "estado": "estado"},
        campos_resumen=(
            "a_o_hecho", "departamento_hecho", "municipio_hecho", "delito",
            "titulo_delito", "etapa", "estado", "tipo_noticia",
            "dir_hecho_rural_urbana", "seccional",
        ),
        notas=(
            "23.783.687 filas desde 2010, solo Ley 906. Lo anterior (Ley 600) "
            "no está.",
            "Una fila NO es un proceso: un proceso con varios delitos trae una "
            "fila por delito. En Guaduas son 16.204 filas y 15.665 procesos "
            "distintos. Para contar procesos, count(distinct "
            "proceso_anonimizado).",
            "Los nombres van en Title Case y SIN tilde: «Guaduas», "
            "«Cundinamarca», «Delitos Contra La Administracion De Publica» "
            "(con la errata de la fuente). El LIKE de Socrata distingue "
            "mayúsculas: '%ADMINISTRACI%' devuelve 0 y '%Administraci%' "
            "devuelve 582 en ese municipio. Filtrar por `cod_dane_hecho`.",
            "Agrupar por `municipio_hecho` expira; por `cod_dane_hecho` no.",
            "`etapa` y `estado` son el valor de HOY, no el del momento del "
            "hecho: una serie por año del hecho mezcla procesos que llevan "
            "quince años con los de este mes.",
            "Todas las columnas son text, las fechas incluidas: no hay "
            "`fecha_hecho`, sino `a_o_hecho`, `mes_hecho` y `trimestre_hecho` "
            "por separado.",
            "Es la única fuente abierta con delitos contra la administración "
            "pública por municipio: peculado, cohecho, contrato sin "
            "cumplimiento de requisitos legales, interés indebido.",
            "No identifica a nadie: `proceso_anonimizado` es un SHA-256 y no "
            "hay columnas de persona. Las personas están en los otros dos "
            "datasets de la familia, que son microdato.",
        ),
    ),
    "procesados": Dataset(
        id="piva-db2c",
        nombre="Fiscalía - Procesados (SPOA)",
        unidad="un procesado vinculado a un delito",
        campos_clave={"procesado": "id_procesado_anonimizado",
                      "proceso": "proceso_anonimizado", "delito": "delito",
                      "municipio": "cod_dane_hecho_origen",
                      "anio": "a_o_hecho_origen", "etapa": "etapa",
                      "sentencia": "tipo_sentencia"},
        notas=(
            "33.013.953 filas. MICRODATO: la fila es una PERSONA, con sexo, "
            "grupo etario, etnia, pueblo indígena, nivel educativo, "
            "discapacidad, orientación sexual e identidad de género, más el "
            "municipio y el delito. Solo se agrega.",
            "Una misma persona aparece varias veces, una por delito y por "
            "proceso: `id_procesado_anonimizado` no es una persona, es un "
            "registro de vinculación.",
        ),
    ),
    "victimas": Dataset(
        id="hr73-zqjf",
        nombre="Fiscalía - Víctimas (SPOA)",
        unidad="una víctima vinculada a un delito",
        campos_clave={"victima": "id_victima_anonimizado",
                      "proceso": "proceso_anonimizado", "delito": "delito",
                      "municipio": "cod_dane_hecho_origen",
                      "anio": "a_o_hecho_origen", "etapa": "etapa"},
        notas=(
            "17.988.620 filas. MICRODATO por la misma razón que procesados, y "
            "más sensible: incluye víctimas de delitos sexuales y "
            "caracterización de feminicidio. Solo se agrega.",
            "`victima_nna` marca a los menores de edad.",
        ),
    ),
}


# -------------------------------------------------------------- regalías --
# Dos sistemas que hablan del mismo dinero: el DNP mira el PROYECTO —y es la
# única fuente abierta con avance FÍSICO de obra— y el MinHacienda mira la
# plata. Verificado el 19-nov-2026.
REGALIAS = {
    "proyectos": Dataset(
        id="mzgh-shtp",
        nombre="DNP - Proyectos del Sistema General de Regalías",
        unidad="un proyecto aprobado por un OCAD",
        campos_clave={"bpin": "codigobpin", "entidad": "entidadejecutora",
                      "departamento": "departamento", "estado": "estado",
                      "valor": "valortotal", "fisica": "ejecucionfisica",
                      "financiera": "ejecucionfinanciera",
                      "interventor": "interventor"},
        campos_resumen=(
            "codigobpin", "nombre", "entidadejecutora", "departamento",
            "sector", "estado", "valortotal", "ejecucionfisica",
            "ejecucionfinanciera", "interventor", "nomocad",
        ),
        notas=(
            "35.010 proyectos. Es la ÚNICA fuente abierta con porcentaje de "
            "ejecución física de obra: SECOP II no lo tiene (ver mfmm-jqmq).",
            "El porcentaje lo reporta la entidad ejecutora, que a menudo "
            "figura como su propio `interventor`. Los terminados suelen "
            "declarar 100 % exacto, sin decimales.",
            "`ejecucionfisica` viene VACÍA en proyectos en ejecución: la "
            "ausencia no es cero y no se puede promediar como si lo fuera.",
            "No tiene municipio: `entidadejecutora` es texto («MUNICIPIO DE "
            "GUADUAS») y `codejecutor` no es DIVIPOLA.",
        ),
    ),
    "proyectos_contratos": Dataset(
        id="uwns-mbwd",
        nombre="DNP - Contratos de los proyectos de inversión",
        unidad="una fila de contrato asociada a un proyecto BPIN",
        campos_clave={"bpin": "bpin", "contrato": "referenciacontrato",
                      "proveedor": "proveedor", "doc": "documentoproveedor",
                      "valor": "valorcontrato", "tipo": "tipoproyecto",
                      "estado": "estadocontrato"},
        campos_resumen=(
            "bpin", "nombreproyecto", "tipoproyecto", "referenciacontrato",
            "objetodelcontrato", "proveedor", "valorcontrato",
            "estadocontrato", "vigenciacontrato",
        ),
        notas=(
            "1.637.804 filas. Es el puente entre un proyecto BPIN y los "
            "contratos que lo ejecutaron, SECOP I incluido: el `urlproceso` "
            "apunta a contratos.gov.co cuando el contrato es viejo.",
            "Un contrato puede venir PARTIDO en varias filas —el valor base y "
            "sus adiciones por separado—, así que sumar `valorcontrato` por "
            "BPIN infla. El valor real se confirma en SECOP.",
            "`valorcontrato` es TEXT, no número: ordenar por él ordena "
            "alfabéticamente.",
            "`estadoproyecto` aquí y `estado` en mzgh-shtp se contradicen: hay "
            "proyectos «Terminado» en uno y «EN EJECUCIÓN» en el otro. Citar "
            "los dos.",
        ),
    ),
    "ejecucion_financiera": Dataset(
        id="br9a-gygu",
        nombre="MinHacienda - Ejecución financiera de regalías",
        unidad="un proyecto dentro de un fondo y un bienio",
        campos_clave={"bpin": "codigobpin", "entidad": "nombreentidad",
                      "municipio": "codigodaneentidad", "fondo": "nombrefondo",
                      "vigencia": "vigencia", "pagado": "apropiacionpagada",
                      "porcentaje": "porcentajeejecutadopresu"},
        campos_resumen=(
            "vigencia", "nombrefondo", "nombredepartamento", "nombreentidad",
            "codigobpin", "nombreproyecto", "recursosaprobadosasignadosspgr",
            "apropiacioncdp", "apropiacionrp", "apropiacionpagada",
            "porcentajeejecutadopresu",
        ),
        notas=(
            "22.675 filas. Lleva `codigobpin`: es la vía para cruzar el dinero "
            "del MinHacienda con el avance físico del DNP.",
            "`vigencia` es un BIENIO («Vigencia 2025 - 2026»), no un año. "
            "Agrupar por vigencia no da una serie anual.",
            "`codigodaneentidad` es DIVIPOLA de cinco dígitos en texto, y vale "
            "«00000» cuando la entidad es «OTROS».",
        ),
    ),
    "ejecucion_presupuestal": Dataset(
        id="g4qj-2p2e",
        nombre="MinHacienda - Ejecución presupuestal de regalías",
        unidad="un fondo en una entidad y un bienio",
        campos_clave={"entidad": "nombreentidad",
                      "municipio": "codigodaneentidad", "fondo": "nombrefondo",
                      "vigencia": "vigencia",
                      "presupuesto": "presupuestosgrinversion",
                      "proyectos": "numeroproyectosaprobados"},
        notas=(
            "5.335 filas. No baja a proyecto: es el presupuesto por fondo y "
            "entidad. Para proyecto, br9a-gygu.",
        ),
    ),
    "caja": Dataset(
        id="e624-d9uy",
        nombre="MinHacienda - Situación de caja para regalías",
        unidad="un fondo en una entidad y un bienio",
        campos_clave={"entidad": "nombreentidad",
                      "municipio": "codigodaneentidad", "fondo": "nombrefondo",
                      "vigencia": "vigencia", "recaudo": "valorrecaudo",
                      "pagado": "totalpagado", "saldo": "saldocaja"},
        notas=(
            "5.284 filas. `saldocaja` es plata girada y no gastada: el "
            "indicador de regalías que se quedan quietas.",
        ),
    ),
    "ingresos": Dataset(
        id="xb6a-jh3a",
        nombre="MinHacienda - Ingresos corrientes para regalías",
        unidad="un fondo en una entidad y un mes del bienio",
        campos_clave={"entidad": "nombreentidad",
                      "municipio": "codigodaneentidad", "fondo": "nombrefondo",
                      "vigencia": "vigencia", "mes": "numeromesbienio",
                      "acumulado": "pbcacumuladomes"},
        notas=(
            "4.046 filas. Los valores son ACUMULADOS del bienio: la diferencia "
            "entre dos meses es el flujo; el valor del mes, no.",
        ),
    ),
}


# --------------------------------------------------------------- forense --
# Medicina Legal. TODO es microdato individual: la fila es una víctima, con
# etnia, orientación sexual, discapacidad, municipio y hora del hecho. Se
# registra para AGREGAR; `core.privacidad.MICRODATO` cierra la puerta a las
# filas por cualquier vía. Verificado el 19-nov-2026.
FORENSE = {
    "homicidios": Dataset(
        id="vtub-3de2",
        nombre="Medicina Legal - Presuntos homicidios (cifras definitivas)",
        unidad="una víctima de homicidio",
        campos_clave={"anio": "a_o_del_hecho",
                      "municipio": "codigo_dane_municipio",
                      "departamento": "codigo_dane_departamento",
                      "sexo": "sexo_de_la_victima",
                      "edad": "grupo_de_edad_quinquenal",
                      "mecanismo": "mecanismo_causal_de_la_lesion_fatal",
                      "agresor": "presunto_agresor_detallado"},
        notas=(
            "125.284 filas, 2015 a 2024, cifras definitivas.",
            "Es el conteo FORENSE, no el policial: no coincide con el "
            "HOMICIDIO de MinDefensa, y la diferencia entre los dos es un dato "
            "en sí mismo. No son intercambiables ni sumables.",
        ),
    ),
    "suicidios": Dataset(
        id="f75u-mirk",
        nombre="Medicina Legal - Presuntos suicidios (cifras definitivas)",
        unidad="una víctima de suicidio",
        campos_clave={"anio": "a_o_del_hecho",
                      "municipio": "codigo_dane_municipio",
                      "sexo": "sexo_de_la_victima",
                      "edad": "grupo_de_edad_quinquenal",
                      "razon": "razon_del_suicidio"},
        notas=("26.558 filas, 2015 a 2024.",),
    ),
    "desaparecidos": Dataset(
        id="8hqm-7fdt",
        nombre="Medicina Legal - Desaparecidos (histórico)",
        unidad="una persona reportada como desaparecida",
        campos_clave={"anio": "a_o_de_la_desaparicion",
                      "municipio": "codigo_dane_municipio",
                      "estado": "estado_de_la_desaparicion",
                      "clasificacion": "clasificacion_de_la_desaparicion",
                      "sexo": "sexo_del_desaparecido"},
        notas=(
            "212.803 filas.",
            "`estado_de_la_desaparicion` distingue a quien sigue desaparecido "
            "de quien apareció, vivo o muerto: contar filas sin filtrarlo "
            "cuenta las dos cosas juntas.",
        ),
    ),
    "violencia_intrafamiliar": Dataset(
        id="ers2-kerr",
        nombre="Medicina Legal - Violencia intrafamiliar (cifras definitivas)",
        unidad="una víctima atendida por violencia intrafamiliar",
        campos_clave={"anio": "a_o_del_hecho",
                      "municipio": "codigo_dane_municipio",
                      "sexo": "sexo_de_la_victima",
                      "agresor": "presunto_agresor_detallado",
                      "contexto": "contexto_del_hecho"},
        notas=(
            "236.840 filas, 2015 a 2024.",
            "Cuenta exámenes médico-legales, no denuncias: una víctima que no "
            "pasó por el instituto no está.",
        ),
    ),
    "violencia_pareja": Dataset(
        id="9fs6-37ea",
        nombre="Medicina Legal - Lesiones por violencia de pareja (histórico)",
        unidad="una víctima atendida por violencia de pareja",
        campos_clave={"anio": "a_o_del_hecho",
                      "municipio": "codigo_dane_municipio",
                      "sexo": "sexo_de_la_victima",
                      "agresor": "presunto_agresor_detallado"},
        notas=(
            "438.786 filas.",
            "Se solapa con violencia intrafamiliar: son dos cortes del mismo "
            "sistema, no dos poblaciones. Sumarlos duplica.",
        ),
    ),
    "delito_sexual": Dataset(
        id="hyqu-diue",
        nombre="Medicina Legal - Exámenes por presunto delito sexual",
        unidad="un examen médico-legal por presunto delito sexual",
        campos_clave={"anio": "a_o_del_hecho",
                      "municipio": "codigo_dane_municipio",
                      "sexo": "sexo_de_la_victima",
                      "edad": "grupo_de_edad_quinquenal",
                      "agresor": "presunto_agresor_detallado"},
        notas=(
            "233.352 filas, 2015 a 2024.",
            "El más sensible de la familia: la mayoría de las víctimas son "
            "menores de edad y la fila trae municipio, día y hora.",
        ),
    ),
    "transporte": Dataset(
        id="s65h-7665",
        nombre="Medicina Legal - Muertes por eventos de transporte",
        unidad="una víctima fatal de un evento de transporte",
        campos_clave={"anio": "a_o_del_hecho",
                      "municipio": "codigo_dane_municipio",
                      "sexo": "sexo_de_la_victima",
                      "condicion": "condicion_de_la_victima_at",
                      "vehiculo": "medio_de_desplazamiento_o_transporte"},
        notas=("73.403 filas, 2015 a 2024.",),
    ),
    "accidentales": Dataset(
        id="irg9-q5fx",
        nombre="Medicina Legal - Muertes accidentales (histórico)",
        unidad="una víctima de muerte accidental",
        campos_clave={"anio": "a_o_del_hecho",
                      "municipio": "codigo_dane_municipio",
                      "sexo": "sexo_de_la_victima",
                      "mecanismo": "mecanismo_causal_de_la_lesion_fatal"},
        notas=("33.254 filas.",),
    ),
    "lesiones_accidentales": Dataset(
        id="6cjn-eevd",
        nombre="Medicina Legal - Lesiones accidentales (cifras definitivas)",
        unidad="una persona atendida por lesión accidental",
        campos_clave={"anio": "a_o_del_hecho",
                      "municipio": "codigo_dane_municipio",
                      "sexo": "sexo_de_la_victima",
                      "mecanismo": "mecanismo_causal_de_la_lesion_no_fatal"},
        notas=("27.621 filas, 2015 a 2024.",),
    ),
    "fatales_preliminar": Dataset(
        id="2kpj-cktv",
        nombre="Medicina Legal - Lesiones fatales de causa externa (preliminar)",
        unidad="una víctima fatal de causa externa",
        campos_clave={"anio": "a_o_del_hecho",
                      "municipio": "codigo_dane_municipio",
                      "manera": "manera_de_muerte",
                      "sexo": "sexo_de_la_victima"},
        notas=(
            "49.474 filas. PRELIMINAR, del año en curso: la cifra cambia. No "
            "se mezcla con las definitivas.",
            "Agrupa homicidio, suicidio, transporte y accidente en una sola "
            "tabla: `manera_de_muerte` es la columna que los separa.",
        ),
    ),
    "no_fatales_preliminar": Dataset(
        id="79dd-d24f",
        nombre="Medicina Legal - Lesiones no fatales de causa externa (preliminar)",
        unidad="una persona atendida por lesión no fatal de causa externa",
        campos_clave={"anio": "a_o_del_hecho",
                      "municipio": "codigo_dane_municipio",
                      "contexto": "contexto_de_violencia",
                      "sexo": "sexo_de_la_victima"},
        notas=(
            "290.281 filas. PRELIMINAR, del año en curso. No se mezcla con las "
            "definitivas.",
        ),
    ),
}


# ------------------------------------------------------------ operativos --
# Los 14 datasets de MinDefensa que se habían dejado fuera de CRIMEN, más
# cinco de esquema propio. Entran en su PROPIA familia, no en CRIMEN, porque
# su `cantidad` no son casos: son hectáreas, kilos, galones o unidades. La
# separación es justo lo que impide sumarlos con homicidios. Verificado el
# 19-nov-2026; la unidad de cada uno está medida y va en sus notas.
OPERATIVOS = {
    "erradicacion": Dataset(
        id="p72f-qcvk",
        nombre="MinDefensa - ERRADICACIÓN",
        unidad="hectáreas de cultivo ilícito erradicadas",
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad",
                      "cultivo": "tipo_de_cultivo", "unidad_medida": "unidad"},
        notas=(
            "146.232 filas, y la columna `unidad` vale HECTAREA en todas.",
            "La `cantidad` son hectáreas: NO se suma con ningún dataset de "
            "CRIMEN, donde la cantidad son casos o personas.",
        ),
    ),
    "aspersion": Dataset(
        id="uvrw-m4tm",
        nombre="MinDefensa - ASPERSIÓN",
        unidad="hectáreas asperjadas",
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad",
                      "unidad_medida": "unidad"},
        notas=("9.889 filas, `unidad` = HECTAREA en todas.",),
    ),
    "incautacion_cocaina": Dataset(
        id="26zg-9p9r",
        nombre="MinDefensa - INCAUTACIONES DE COCAÍNA",
        unidad="kilogramos de cocaína incautados",
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad",
                      "unidad_medida": "unidad"},
        notas=(
            "156.187 filas.",
            "La columna `unidad` está ROTA: en vez de KILOGRAMO trae números "
            "—0.002, 0.003, 0.005— que son cantidades. Los cinco valores más "
            "frecuentes son todos numéricos. La unidad real es el kilogramo, "
            "pero el campo no sirve para comprobarlo.",
        ),
    ),
    "incautacion_base_coca": Dataset(
        id="nxbk-nikm",
        nombre="MinDefensa - INCAUTACIONES DE BASE DE COCA",
        unidad="kilogramos de base de coca incautados",
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad",
                      "unidad_medida": "unidad"},
        notas=("177.570 filas, `unidad` = KILOGRAMO en todas.",),
    ),
    "incautacion_basuco": Dataset(
        id="3cjd-phaj",
        nombre="MinDefensa - INCAUTACIONES DE BASUCO",
        unidad="kilogramos de basuco incautados",
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad",
                      "unidad_medida": "unidad"},
        notas=("237.611 filas, `unidad` = KILOGRAMO en todas.",),
    ),
    "incautacion_marihuana": Dataset(
        id="g228-vp9d",
        nombre="MinDefensa - INCAUTACIONES DE MARIHUANA",
        unidad="kilogramos de marihuana incautados",
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad",
                      "unidad_medida": "unidad"},
        notas=("495.622 filas, `unidad` = KILOGRAMO en todas.",),
    ),
    "incautacion_heroina": Dataset(
        id="iat2-gskt",
        nombre="MinDefensa - INCAUTACIÓN DE HEROÍNA",
        unidad="kilogramos de heroína incautados",
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad",
                      "unidad_medida": "unidad"},
        notas=("11.018 filas, `unidad` = KILOGRAMO en todas.",),
    ),
    "insumos_liquidos": Dataset(
        id="k2wp-tdv7",
        nombre="MinDefensa - INCAUTACIONES DE INSUMOS LÍQUIDOS",
        unidad="galones de insumo líquido incautados",
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad",
                      "unidad_medida": "unidad"},
        notas=(
            "62.048 filas. La unidad NO es homogénea: 61.970 filas dicen GALON "
            "y 78 dicen UNIDAD. Sumar la columna mezcla galones con bultos.",
        ),
    ),
    "insumos_solidos": Dataset(
        id="n997-hhiv",
        nombre="MinDefensa - INSUMOS SÓLIDOS",
        unidad="kilogramos de insumo sólido incautados",
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad",
                      "unidad_medida": "unidad"},
        notas=(
            "68.579 filas. La unidad viene con dos grafías: KILOGRAMO en "
            "66.724 y kILOGRAMO —con la ka minúscula— en 1.855. Agrupar por "
            "`unidad` devuelve dos grupos que son el mismo.",
        ),
    ),
    "destruccion_infraestructura_droga": Dataset(
        id="s29y-2xjd",
        nombre="MinDefensa - DESTRUCCIÓN DE INFRAESTRUCTURA DE DROGAS",
        unidad="una instalación de producción destruida",
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad",
                      "unidad_medida": "unidad_de_medida"},
        notas=("38.314 filas, `unidad_de_medida` = UNIDAD en todas.",),
    ),
    "maquinaria_mineria": Dataset(
        id="dxs6-mdeg",
        nombre="MinDefensa - MAQUINARIA DE EXPLOTACIÓN ILÍCITA",
        unidad="una máquina incautada o destruida",
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad",
                      "clase": "clase_de_bien",
                      "unidad_medida": "unidad_de_medida"},
        notas=(
            "8.012 filas, `unidad_de_medida` = UNIDAD en todas. `clase_de_bien` "
            "dice qué máquina es.",
        ),
    ),
    "minas_intervenidas": Dataset(
        id="gr35-i7pm",
        nombre="MinDefensa - MINAS INTERVENIDAS",
        unidad="una mina intervenida",
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad",
                      "clase": "clase_de_bien",
                      "unidad_medida": "unidad_de_medida"},
        notas=(
            "16.774 filas, y `unidad_de_medida` está VACÍA en todas: el campo "
            "existe y no dice nada.",
        ),
    ),
    "capturas_mineria_ilegal": Dataset(
        id="3wcs-8xp9",
        nombre="MinDefensa - CAPTURAS POR MINERÍA ILEGAL",
        unidad="una persona capturada por minería ilegal",
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad",
                      "unidad_medida": "unidad_de_medida"},
        notas=("6.220 filas.",),
    ),
    "gestion_del_riesgo": Dataset(
        id="fr5q-rz2x",
        nombre="MinDefensa - GESTIÓN DEL RIESGO",
        unidad="una actuación de gestión del riesgo",
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad",
                      "proceso": "proceso_de_gestion_del_riesgo"},
        notas=(
            "103.359 filas. No es un delito ni un decomiso: son actuaciones de "
            "la fuerza pública ante emergencias.",
        ),
    ),
    "masacres": Dataset(
        id="u8eq-92tb",
        nombre="MinDefensa - MASACRES",
        unidad="una masacre, con sus víctimas en otra columna",
        campos_clave={"fecha": "fecha_hecho", "municipio": "cod_muni",
                      "departamento": "departamento", "casos": "casos",
                      "victimas": "victimas", "zona": "zona"},
        notas=(
            "456 filas, y es el único de la familia con DOS medidas: `casos` "
            "cuenta masacres y `victimas` cuenta personas. Sumar la columna "
            "equivocada cambia la cifra por cuatro o más.",
            "No tiene columna `cantidad`.",
        ),
    ),
    "desmovilizacion": Dataset(
        id="3pur-d5ez",
        nombre="MinDefensa - DESMOVILIZACIÓN INDIVIDUAL",
        unidad="una persona desmovilizada",
        campos_clave={"fecha": "fecha", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad",
                      "grupo": "grupo"},
        notas=(
            "5.284 filas. La fecha se llama `fecha`, no `fecha_hecho`, al "
            "revés que el resto de MinDefensa.",
            "`grupo` es el grupo armado del que viene la persona.",
        ),
    ),
    "desvinculacion_menores": Dataset(
        id="ajsa-ebuq",
        nombre="MinDefensa - DESVINCULACIÓN (MENORES DE EDAD)",
        unidad="un menor de edad desvinculado de un grupo armado",
        campos_clave={"fecha": "fecha", "municipio": "cod_muni",
                      "departamento": "departamento", "cantidad": "cantidad",
                      "grupo": "grupo"},
        notas=("6.831 filas. La fecha se llama `fecha`.",),
    ),
    "sometimiento": Dataset(
        id="xg7g-dzk4",
        nombre="MinDefensa - SOMETIMIENTO INDIVIDUAL A LA JUSTICIA",
        unidad="una persona sometida a la justicia",
        campos_clave={"fecha": "fecha", "municipio": "cod_muni",
                      "departamento": "departamento", "grupo": "grupo"},
        notas=(
            "2.705 filas, y NO tiene columna `cantidad`: una fila es una "
            "persona y se cuenta con count(*).",
        ),
    ),
    "capturas": Dataset(
        id="3jdh-nmwu",
        nombre="Policía Nacional - Reporte de capturas",
        unidad="capturas de un mismo perfil en un municipio y una fecha",
        campos_clave={"fecha": "fecha_hecho", "municipio": "codigo_dane",
                      "departamento": "departamento", "cantidad": "cantidad",
                      "conducta": "descripcion_conducta_captura",
                      "genero": "genero", "edad": "grupo_etario"},
        notas=(
            "3.746.786 filas. Es de la Policía, no de MinDefensa: el municipio "
            "va en `codigo_dane` y no en `cod_muni`.",
            "Mide la respuesta del Estado, no el delito: una captura no es una "
            "condena ni un caso. No se suma con CRIMEN.",
        ),
    ),
}


# ------------------------------------------------------------- conflicto --
# Unidad para las Víctimas. Son cifras YA agregadas: no hay microdato.
# Verificado el 19-nov-2026.
CONFLICTO = {
    "victimas_municipio": Dataset(
        id="ykxr-xynr",
        nombre="UARIV - Cifras de víctimas, municipal",
        unidad="un cruce de municipio, sexo, etnia, discapacidad y ciclo vital",
        campos_clave={"municipio": "cod_ciudad_muni",
                      "nombre_municipio": "ciudad_municipio",
                      "departamento": "cod_estado_depto", "sexo": "sexo",
                      "etnia": "etnia", "ocurrencia": "per_ocu",
                      "declaracion": "per_decla", "ubicacion": "per_ubic",
                      "eventos": "eventos"},
        campos_resumen=(
            "fecha_corte", "estado_depto", "ciudad_municipio", "sexo", "etnia",
            "discapacidad", "ciclo_vital", "per_ocu", "per_decla", "per_ubic",
            "eventos",
        ),
        notas=(
            "8.538.627 filas.",
            "HAY CUATRO CONTEOS DE PERSONA Y NO SON INTERCAMBIABLES: `per_ocu` "
            "es dónde ocurrió el hecho, `per_decla` dónde se declaró, "
            "`per_ubic` dónde vive hoy la víctima y `per_sa` los sujetos de "
            "atención. Elegir el equivocado cambia el mapa entero.",
            "`eventos` cuenta hechos, no personas.",
            "Trae varias `fecha_corte` apiladas: sin filtrarla se suman cortes "
            "distintos del mismo universo. Aquí el formato es aaaa/mm/dd.",
        ),
    ),
    "victimas_hecho_municipio": Dataset(
        id="9qih-4vkc",
        nombre="UARIV - Cifras de víctimas por hecho, municipal",
        unidad="un cruce de municipio, hecho victimizante y caracterización",
        campos_clave={"municipio": "cod_ciudad_muni",
                      "nombre_municipio": "ciudad_municipio", "hecho": "hecho",
                      "sexo": "sexo", "etnia": "etnia",
                      "ocurrencia": "per_ocu", "eventos": "eventos"},
        campos_resumen=(
            "fecha_corte", "estado_depto", "ciudad_municipio", "hecho", "sexo",
            "etnia", "discapacidad", "ciclo_vital", "per_ocu", "per_decla",
            "eventos",
        ),
        notas=(
            "11.566.909 filas. Mismo aviso de los cuatro conteos que "
            "ykxr-xynr, y además: una víctima con dos hechos aparece en los "
            "dos, así que sumar por `hecho` no da el total de víctimas.",
            "La `fecha_corte` aquí viene dd/mm/aaaa y en ykxr-xynr aaaa/mm/dd: "
            "dos formatos en la misma familia.",
            "Y como es TEXT, max(fecha_corte) MIENTE: devuelve 31/12/2025 "
            "cuando el corte más reciente es 31/10/2026, porque ordena "
            "alfabéticamente.",
        ),
    ),
}


# ---------------------------------------------------------- penitenciario --
PENITENCIARIO = {
    "poblacion_intramural": Dataset(
        id="ux6v-gpit",
        nombre="INPEC - Población intramural por códigos DIVIPOLA",
        unidad="un establecimiento de reclusión en un mes",
        campos_clave={"anio": "anno", "mes": "mes",
                      "municipio": "codigo_municipio",
                      "departamento": "codigo_departamento",
                      "establecimiento": "nombre_establecimiento",
                      "capacidad": "capacidad", "poblacion": "poblacion",
                      "hacinamiento": "hacinamiento"},
        campos_resumen=(
            "anno", "mes", "nombre_regional", "nombre_establecimiento",
            "departamento", "municipio", "capacidad", "poblacion",
            "sobrepoblacion", "hacinamiento",
        ),
        notas=(
            "7.333 filas. Es una SERIE MENSUAL: sin filtrar `anno` y `mes` se "
            "suman todos los cortes y la población sale multiplicada por el "
            "número de meses.",
            "`hacinamiento` ya viene en porcentaje; no hay que calcularlo.",
            "El municipio es el del establecimiento, no el de origen de las "
            "personas presas.",
        ),
    ),
}


SIN_FUENTE_ABIERTA = {
    "poblacion_municipal": (
        "El DANE no publica las proyecciones de población municipal como API. "
        "En datos.gov.co solo hay republicaciones de alcaldías sueltas "
        "(Chiquinquirá, Sabaneta, Manizales) y bajo la atribución del DANE hay "
        "exactamente TRES datasets, los tres de DIVIPOLA —municipios, "
        "departamentos y centros poblados—, contados sobre el catálogo oficial "
        "entero el 19-nov-2026. Sin denominador no hay "
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
        "El EXPEDIENTE judicial —la consulta de procesos de la Rama—, la "
        "Registraduría, el RUNT y el SIMIT solo se consultan por formulario web "
        "con captcha, no por API abierta. No entran en un servidor que se "
        "define como «sin credenciales». Lo que sí hay en el registro es la "
        "etapa procesal agregada del SPOA de la Fiscalía (dbdv-iihs), que no "
        "es el expediente y no se puede cruzar por documento: viene "
        "anonimizada."
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
    "macro": MACRO, "fiscalia": FISCALIA, "regalias": REGALIAS,
    "forense": FORENSE, "operativos": OPERATIVOS, "conflicto": CONFLICTO,
    "penitenciario": PENITENCIARIO,
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
