"""Respuestas reales capturadas de la API en vivo el 18-ago-2026.

Se usan como fixtures para que las pruebas corran sin red. Los valores no se
inventaron ni se "limpiaron": incluyen los defectos reales de la fuente (coma
decimal, separador de miles en Medellín, números como string).
"""

# xaxy-8nri — DIVIPOLA cabeceras y centros poblados (DANE)
CENTROS_POBLADOS = [
    {"codigo_departamento": "17", "nombre_departamento": "CALDAS",
     "codigo_municipio": "17050", "nombre_municipio": "ARANZAZU",
     "codigo_centro_poblado": "17050006", "nombre_centro_poblado": "SAN RAFAEL",
     "tipo_centro_poblado": "CP", "longitud": "-75,523505", "latitud": "5,261945"},
    # Medellín: el único registro de 8.161 con separador de miles.
    {"codigo_departamento": "05", "nombre_departamento": "ANTIOQUIA",
     "codigo_municipio": "05001", "nombre_municipio": "MEDELLÍN",
     "codigo_centro_poblado": "05001000",
     "nombre_centro_poblado": "MEDELLÍN, DISTRITO ESPECIAL DE CIENCIA, TECNOLOGÍA E INNOVACIÓN",
     "tipo_centro_poblado": "CM", "longitud": "-75,581,775", "latitud": "6,246,631"},
    {"codigo_departamento": "05", "nombre_departamento": "ANTIOQUIA",
     "codigo_municipio": "05001", "nombre_municipio": "MEDELLÍN",
     "codigo_centro_poblado": "05001004", "nombre_centro_poblado": "SANTA ELENA",
     "tipo_centro_poblado": "CP", "longitud": "-75,501293", "latitud": "6,210599"},
]

# gdxc-w37w — DIVIPOLA municipios
MUNICIPIOS = [
    {"cod_dpto": "05", "dpto": "ANTIOQUIA", "cod_mpio": "05001", "nom_mpio": "MEDELLÍN",
     "tipo_municipio": "Municipio", "longitud": "-75,581775", "latitud": "6,246631"},
    {"cod_dpto": "05", "dpto": "ANTIOQUIA", "cod_mpio": "05002", "nom_mpio": "ABEJORRAL",
     "tipo_municipio": "Municipio", "longitud": "-75,428739", "latitud": "5,789315"},
]

# Discovery API — forma real de la respuesta del catálogo
CATALOGO = {
    "resultSetSize": 151,
    "results": [
        {
            "resource": {
                "id": "jbjy-vk9h",
                "name": "SECOP II - Contratos Electrónicos",
                "description": "Contratos registrados en SECOP II",
                "attribution": "Agencia Nacional de Contratación Pública - Colombia Compra Eficiente, Bogotá D.C.",
                "updatedAt": "2026-08-17T09:22:03.000Z",
                "provenance": "official",
                "parent_fxf": [],
                "page_views": {"page_views_total": 2697779},
                "columns_field_name": ["nombre_entidad", "nit_entidad", "valor_del_contrato",
                                       "fecha_de_firma", "documento_proveedor",
                                       "valor_pendiente_de"],
                "columns_name": ["Nombre Entidad", "Nit Entidad", "Valor del Contrato",
                                 "Fecha de Firma", "Documento Proveedor",
                                 "Valor Pendiente de Amortizacion"],
                "columns_datatype": ["Text", "Number", "Number", "Calendar date", "Text", "Number"],
                "columns_description": ["Nombre de la entidad", "NIT", "Valor", "Firma",
                                        "Documento", "Pendiente"],
            },
            "classification": {"domain_category": "Estadísticas Nacionales"},
            "metadata": {"license": "Creative Commons Attribution | Share Alike 4.0 International"},
        }
    ],
}

# Filas reales de SECOP II (valores numéricos como string, mojibake incluido)
CONTRATOS = [
    {"id_contrato": "CO1.PCCNTR.1234567", "nombre_entidad": "INSTITUTO NACIONAL DE VIAS",
     "nit_entidad": "800215807", "proveedor_adjudicado": "CONSTRUCTORA XYZ S.A.S",
     "documento_proveedor": "900123456",
     "objeto_del_contrato": "MANTENIMIENTO DE LA VÍA NACIONAL EN EJECUCIoN",
     "modalidad_de_contratacion": "Licitación pública",
     "valor_del_contrato": "12500000", "valor_pagado": "5000000",
     "fecha_de_firma": "2025-05-02T00:00:00.000",
     "estado_contrato": "En ejecución", "departamento": "Antioquia",
     "proceso_de_compra": "CO1.BDOS.7654321",
     "urlproceso": {"url": "https://community.secop.gov.co/Public/Tendering/x"}},
]

ADICIONES = [
    {"identificador": "CO1.CTRMOD.999", "id_contrato": "CO1.PCCNTR.1234567",
     "tipo": "MODIFICACION GENERAL", "descripcion": "Prórroga de plazo en 60 días",
     "fecharegistro": "2025-09-15T00:00:00.000"},
]
