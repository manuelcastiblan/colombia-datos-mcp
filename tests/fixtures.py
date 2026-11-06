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


# =========================================================================
# IGAC — `atlas/politicoadministrativo/MapServer`, capturado el 05-nov-2026.
#
# El servicio volvió a responder después de meses de HTTP 500, y estas son sus
# respuestas reales. Se guardan con sus defectos intactos porque son justamente
# los defectos los que explican por qué la geometría NO migró a esta fuente:
#
#   - de sus seis capas, NINGUNA es municipal;
#   - la capa departamental no usa los campos del MGN (`DeCodigo`/`DeNombre`
#     en vez de `DPTO_CCDGO`/`DPTO_CNMBR`);
#   - y sus «33» registros cuadran en total con los 33 departamentos de
#     DIVIPOLA pero NO son los mismos: sobra un área en litigio con código `00`
#     y falta Bogotá D.C. (`11`). La intersección son 32.
# =========================================================================

# Documento de servicio, recortado a lo que se mira: la lista de capas.
IGAC_SERVICIO = {
    "currentVersion": 11.3,
    "mapName": "División Político-Administrativa",
    "serviceDescription": (
        '<DIV STYLE="text-align:Left;font-size:12pt"><P><SPAN>Mapa de la '
        "división político-administrativa del país generado para el Atlas de "
        "Colombia Edición 2024.</SPAN></P></DIV>"
    ),
    "copyrightText": "IGAC",
    "layers": [
        {"id": 0, "name": "Transporte terrestre", "geometryType": "esriGeometryPolyline"},
        {"id": 1, "name": "Distrito", "geometryType": "esriGeometryPoint"},
        {"id": 2, "name": "Capital_de_la_Republica", "geometryType": "esriGeometryPoint"},
        {"id": 3, "name": "Capital departamental", "geometryType": "esriGeometryPolygon"},
        {"id": 4, "name": "Área metropolitana", "geometryType": "esriGeometryPolygon"},
        {"id": 5, "name": "Departamento", "geometryType": "esriGeometryPolygon"},
    ],
    "capabilities": "Map,Query,Data",
    "supportedQueryFormats": "JSON, geoJSON, PBF",
    "maxRecordCount": 2000,
    "singleFusedMapCache": True,
    "spatialReference": {"wkid": 102100, "latestWkid": 3857},
}

# Campos de la capa 5 (`Departamento`), tal como los declara el servicio.
IGAC_CAMPOS_DEPARTAMENTO = [
    {"name": "OBJECTID", "type": "esriFieldTypeOID"},
    {"name": "SHAPE", "type": "esriFieldTypeGeometry"},
    {"name": "DeCodigo", "type": "esriFieldTypeString", "length": 6},
    {"name": "DeNombre", "type": "esriFieldTypeString", "length": 100},
    {"name": "DeArea", "type": "esriFieldTypeDouble"},
    {"name": "DeNorma", "type": "esriFieldTypeString", "length": 250},
    {"name": "Nombre_altas", "type": "esriFieldTypeString", "length": 100},
    {"name": "SHAPE_Length", "type": "esriFieldTypeDouble"},
    {"name": "SHAPE_Area", "type": "esriFieldTypeDouble"},
]

# Los 33 `DeCodigo` de la capa, en el orden en que llegaron, en dos volcados
# distintos del mismo día y del siguiente. Es el defecto más caro del servicio
# y además viene por duplicado:
#
#   1. Cuenta 33 como DIVIPOLA, pero sobra el `00` del área en litigio y
#      **falta el `11` de Bogotá D.C.**
#   2. **El orden no es estable**: `52` salió en la posición 17 en un volcado y
#      de último en el otro. Sin `ORDER BY` propio, paginar con `resultOffset`
#      perdería y duplicaría rasgos aunque el servicio respondiera siempre.
IGAC_CODIGOS_DEPARTAMENTO = [
    "00", "05", "08", "13", "15", "17", "18", "19", "20", "23", "25", "27",
    "41", "44", "47", "50", "52", "54", "63", "66", "68", "70", "73", "76",
    "81", "85", "86", "88", "91", "94", "95", "97", "99",
]
IGAC_CODIGOS_DEPARTAMENTO_OTRO_VOLCADO = [
    "00", "05", "08", "13", "15", "17", "18", "19", "20", "23", "25", "27",
    "41", "44", "47", "50", "54", "63", "66", "68", "70", "73", "76",
    "81", "85", "86", "88", "91", "94", "95", "97", "99", "52",
]

# Los 33 de DIVIPOLA (`vcjz-niiq`), para contrastar sin red.
DIVIPOLA_CODIGOS_DEPARTAMENTO = [
    "05", "08", "11", "13", "15", "17", "18", "19", "20", "23", "25", "27",
    "41", "44", "47", "50", "52", "54", "63", "66", "68", "70", "73", "76",
    "81", "85", "86", "88", "91", "94", "95", "97", "99",
]

# Los tres primeros rasgos del volcado `f=geojson&outSR=4326`, que acertó 2 de 5
# intentos (y 1 de 3 al recapturarlo al día siguiente, con valores idénticos).
#
# Las `properties` van literales. La geometría va recortada a sus primeros
# vértices reales —el original trae 983, 29.674 y 6.385 vértices, 33 MB para los
# 33 departamentos— porque lo que se prueba aquí son los nombres de campo, no el
# contorno. Los vértices que quedan son los que devolvió el servicio.
IGAC_DEPARTAMENTOS = {
    "type": "FeatureCollection",
    "features": [
        # Primer registro de la capa, y no es un departamento.
        {"type": "Feature",
         "properties": {"DeCodigo": "00",
                        "DeNombre": "Area en Litigio Cauca - Huila",
                        "DeArea": 342.09908699027653},
         "geometry": {"type": "Polygon", "coordinates": [[
             [-76.34464774420762, 2.4031266221305567],
             [-76.34923382518622, 2.4031577969895426],
             [-76.35170765984215, 2.403149551845668],
             [-76.3535726142098, 2.403026130752219],
             [-76.34464774420762, 2.4031266221305567]]]}},
        # Nombre en Title Case, no en mayúsculas como el MGN y DIVIPOLA.
        {"type": "Feature",
         "properties": {"DeCodigo": "05", "DeNombre": "Antioquia",
                        "DeArea": 62786.02050706712},
         "geometry": {"type": "Polygon", "coordinates": [[
             [-76.41356110796086, 8.747655763561786],
             [-76.41443349833366, 8.747988706073032],
             [-76.4151373185597, 8.748669295744243],
             [-76.41601217035623, 8.749174831917815],
             [-76.41356110796086, 8.747655763561786]]]}},
        {"type": "Feature",
         "properties": {"DeCodigo": "08", "DeNombre": "Atlántico",
                        "DeArea": 3313.3844614584987},
         "geometry": {"type": "Polygon", "coordinates": [[
             [-74.84946230668928, 11.097782466605283],
             [-74.8495412848869, 11.098023049290342],
             [-74.84962177732494, 11.09826154180014],
             [-74.84970379528724, 11.098497991088445],
             [-74.84946230668928, 11.097782466605283]]]}},
    ],
}

# El error, literal, con el que murieron las consultas en frío. Llega dentro de
# un cuerpo JSON con HTTP 200 cuando se pide `f=json`, y como HTTP 503 de verdad
# cuando se pide `f=geojson`: la forma del fallo depende del formato.
IGAC_ERROR_TIMEOUT = {
    "error": {
        "code": 503,
        "message": "Error handling service request :Wait timeout for the request exceeded.",
        "details": [],
    }
}

# Y el del FeatureServer, que tampoco existe: HTTP 200, error en el cuerpo. Ojo,
# el mismo endpoint devuelve a veces el de arriba —el timeout, a los 60 s— en vez
# de este: cuando está cargado ni llega a mirar si la extensión existe. Lo único
# estable es el 200 con un `error` dentro.
IGAC_ERROR_SIN_FEATURESERVER = {
    "error": {
        "code": 500,
        "message": ("Error handling service request :Server object extension "
                    "'featureserver' not found."),
        "details": [],
    }
}
