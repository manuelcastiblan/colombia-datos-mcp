"""Jerarquía de errores tipados.

Regla del diseño (§6.6): el modelo debe poder distinguir siempre "no hay
resultados" de "la fuente falló", y todo error trae una sugerencia accionable,
no decorativa.
"""

from __future__ import annotations


class CoDatosError(Exception):
    """Base. `codigo` es estable y documentado; `sugerencia` es accionable."""

    codigo = "ERROR"

    def __init__(self, mensaje: str, sugerencia: str = "", **contexto):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.sugerencia = sugerencia
        self.contexto = contexto

    def como_texto(self) -> str:
        partes = [f"[{self.codigo}] {self.mensaje}"]
        if self.sugerencia:
            partes.append(f"Sugerencia: {self.sugerencia}")
        if self.contexto:
            detalle = ", ".join(f"{k}={v}" for k, v in self.contexto.items())
            partes.append(f"Contexto: {detalle}")
        return "\n".join(partes)


class ErrorValidacion(CoDatosError):
    """Entrada inválida del modelo: columna inexistente, rango imposible."""

    codigo = "VALIDACION"


class ErrorNoEncontrado(CoDatosError):
    """El recurso no existe. Distinto de 'la consulta no devolvió filas'."""

    codigo = "NO_ENCONTRADO"


class ErrorLimiteTasa(CoDatosError):
    codigo = "LIMITE_TASA"


class ErrorFuenteCaida(CoDatosError):
    """El backend falló. Nunca se confunde con 'cero resultados'."""

    codigo = "FUENTE_CAIDA"


class ErrorTimeout(CoDatosError):
    codigo = "TIMEOUT"


class ErrorEsquemaCambiado(CoDatosError):
    """Deriva de esquema upstream: el Estado cambió el dato."""

    codigo = "ESQUEMA_CAMBIADO"


class ErrorFueraDeJurisdiccion(CoDatosError):
    """Guardarraíl de gestor catastral (§6.5)."""

    codigo = "FUERA_DE_JURISDICCION"


class ErrorConfig(CoDatosError):
    """Mala configuración del operador, p. ej. token inválido."""

    codigo = "CONFIG"


class ErrorPrivacidad(CoDatosError):
    """El motor de privacidad bloqueó la consulta (§11). No es un fallo."""

    codigo = "PRIVACIDAD"
