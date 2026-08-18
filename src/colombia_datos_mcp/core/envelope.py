"""El sobre (§4.2): metadatos honestos alrededor de cada respuesta.

`consulta` es no negociable: la URL exacta y reproducible que produjo el
resultado. Para uso periodístico o de control fiscal, una cifra sin su consulta
reproducible no sirve.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .budget import Detalle, PRESUPUESTO_POR_DEFECTO, ajusta_filas


@dataclass
class Fuente:
    id: str
    nombre: str = ""
    actualizado: str | None = None
    licencia: str | None = None
    atribucion: str | None = None

    def como_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in (None, "")}


@dataclass
class Sobre:
    datos: list[dict] = field(default_factory=list)
    total_coincidencias: int | None = None
    offset: int = 0
    orden: str | None = None
    detalle: Detalle = Detalle.RESUMEN
    consulta: str | None = None
    fuente: Fuente | None = None
    advertencias: list[str] = field(default_factory=list)
    truncado: bool = False

    # ---------------------------------------------------------------- meta --
    @property
    def devueltos(self) -> int:
        return len(self.datos)

    @property
    def siguiente_offset(self) -> int | None:
        """Honestidad de paginación (§6.3): nunca se anuncia un salto que
        deje filas sin ver. Se calcula sobre lo REALMENTE devuelto."""
        if self.total_coincidencias is None:
            return self.offset + self.devueltos if self.devueltos else None
        siguiente = self.offset + self.devueltos
        return siguiente if siguiente < self.total_coincidencias else None

    def meta(self) -> dict:
        m = {
            "total_coincidencias": self.total_coincidencias,
            "devueltos": self.devueltos,
            "offset": self.offset,
            "siguiente_offset": self.siguiente_offset,
            "orden": self.orden,
            "detalle": self.detalle.value,
            "truncado": self.truncado,
            "consulta": self.consulta,
        }
        if self.fuente:
            m["fuente"] = self.fuente.como_dict()
        if self.advertencias:
            m["advertencias"] = list(self.advertencias)
        return {k: v for k, v in m.items() if v is not None}

    def advertir(self, texto: str) -> None:
        if texto and texto not in self.advertencias:
            self.advertencias.append(texto)

    # ------------------------------------------------------------- render --
    def render(self, cuerpo, presupuesto: int = PRESUPUESTO_POR_DEFECTO) -> dict:
        """Aplica el presupuesto de tokens y produce content + structuredContent.

        `cuerpo` es una función filas -> markdown.
        """
        filas, texto, recortado = ajusta_filas(self.datos, cuerpo, presupuesto)
        if recortado:
            self.datos = filas
            self.truncado = True
            self.advertir(
                "Respuesta recortada por presupuesto de tokens. Refina con filtros, "
                "usa detalle='conteo' para contar sin traer filas, o pagina con "
                f"offset={self.siguiente_offset}."
            )
        if self.total_coincidencias is not None and self.devueltos < self.total_coincidencias:
            self.advertir(
                f"Viendo {self.devueltos} de {self.total_coincidencias} coincidencias. "
                "Cualquier conclusión cuantitativa debe usar una herramienta de agregación, "
                "no estas filas."
            )
        return {"texto": texto + "\n\n" + self._pie(), "estructurado": {"datos": self.datos, "_meta": self.meta()}}

    def _pie(self) -> str:
        lineas = []
        m = self.meta()
        resumen = [f"**{m['devueltos']} fila(s)**"]
        if self.total_coincidencias is not None:
            resumen.append(f"de **{self.total_coincidencias}** coincidencias")
        if self.orden:
            resumen.append(f"· orden: `{self.orden}`")
        lineas.append(" ".join(resumen))
        if self.fuente:
            f = self.fuente
            det = [f"Fuente: `{f.id}`"]
            if f.nombre:
                det.append(f.nombre)
            if f.actualizado:
                det.append(f"· actualizado {f.actualizado}")
            if f.licencia:
                det.append(f"· {f.licencia}")
            lineas.append(" ".join(det))
        if self.siguiente_offset is not None:
            lineas.append(f"Siguiente página: `offset={self.siguiente_offset}`")
        if self.consulta:
            lineas.append(f"Consulta reproducible: {self.consulta}")
        for a in self.advertencias:
            lineas.append(f"> {a}")
        return "\n\n".join(lineas)
