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
ALIAS_ENTIDADES = {
    "RTVC": "RADIO TELEVISION NACIONAL DE COLOMBIA.",
    "DANE": "DEPARTAMENTO ADMINISTRATIVO NACIONAL DE ESTADISTICA",
    "IGAC": "INSTITUTO GEOGRAFICO AGUSTIN CODAZZI",
    "ICBF": "INSTITUTO COLOMBIANO DE BIENESTAR FAMILIAR",
    "SENA": "SERVICIO NACIONAL DE APRENDIZAJE",
    "INVIAS": "INSTITUTO NACIONAL DE VIAS",
    "DIAN": "DIRECCION DE IMPUESTOS Y ADUANAS NACIONALES",
    "ANLA": "AUTORIDAD NACIONAL DE LICENCIAS AMBIENTALES",
    "UNGRD": "UNIDAD NACIONAL PARA LA GESTION DEL RIESGO DE DESASTRES",
}

LICENCIA_POR_DEFECTO = "CC BY-SA 4.0 (verificar por dataset)"


def por_id(dataset_id: str) -> Dataset | None:
    for d in list(SECOP.values()) + [
        DIVIPOLA_MUNICIPIOS, DIVIPOLA_CENTROS, DIVIPOLA_DEPARTAMENTOS
    ]:
        if d.id == dataset_id:
            return d
    return None
