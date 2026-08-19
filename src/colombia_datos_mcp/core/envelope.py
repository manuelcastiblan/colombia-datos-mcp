"""El sobre (§4.2): metadatos honestos alrededor de cada respuesta.

`consulta` es no negociable: la URL exacta y reproducible que produjo el
resultado. Para uso periodístico o de control fiscal, una cifra sin su consulta
reproducible no sirve.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import format as fmt
from .budget import Detalle, PRESUPUESTO_POR_DEFECTO, ajusta_filas, estima_tokens


# Los dos avisos que se añaden DESPUÉS de recortar. Son constantes para poder
# reservar su coste antes de decidir cuántas filas caben, sin duplicar el texto.
PLANTILLA_RECORTE = (
    "Respuesta recortada por presupuesto de tokens. Refina con filtros, usa "
    "detalle='conteo' para contar sin traer filas, o pagina con offset={offset}."
)
PLANTILLA_PARCIAL = "Viendo {devueltos} de {total} coincidencias. {detalle}"


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
    # Hay respuestas donde «N fila(s)» no significa nada —exportar a disco
    # devuelve una ruta, no filas— y anunciarlo confunde más que informa.
    mostrar_conteo: bool = True
    # Qué añadir cuando se ve menos de lo que hay. El texto por defecto manda a
    # agregar, pero en una respuesta YA agregada ese consejo no aplica: los
    # grupos ocultos no se recuperan agregando otra vez, sino subiendo el
    # límite o afinando el filtro.
    aviso_parcial: str = ("Cualquier conclusión cuantitativa debe usar una herramienta "
                          "de agregación, no estas filas.")

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
            "siguiente_offset": self.siguiente_offset if self.mostrar_conteo else None,
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
    def render(self, cuerpo, presupuesto: int = PRESUPUESTO_POR_DEFECTO,
               formato: str = "tabla") -> dict:
        """Aplica el presupuesto de tokens y produce content + structuredContent.

        `cuerpo` es una función filas -> markdown. Con `formato` distinto de
        "tabla" se ignora y las filas se serializan a CSV o JSON dentro de un
        bloque cercado: así el pie del sobre no contamina lo que se copia, pero
        la respuesta sigue trayendo su procedencia y sus advertencias.
        """
        if formato in ("csv", "json"):
            serializa = fmt.cuerpo_por_formato(formato)

            def cuerpo(filas, _serializa=serializa, _f=formato):
                return f"```{_f}\n{_serializa(filas)}\n```"

        # El pie —procedencia, URL reproducible y advertencias— es parte de la
        # respuesta y no se descontaba: una tabla de 200 filas se pasaba 196
        # tokens, y el exceso crece con cada advertencia y con lo larga que sea
        # la URL (las de plegado de acentos rondan los 700 caracteres).
        #
        # Y no basta con reservar el pie actual: recortar AÑADE avisos, así que
        # hay que reservar también los que solo existirán si se recorta. Si no,
        # el propio aviso de recorte empuja la respuesta por encima del
        # presupuesto que ese recorte acababa de imponer.
        reserva = estima_tokens(
            self._pie()
            + PLANTILLA_RECORTE.format(offset=self.siguiente_offset)
            + PLANTILLA_PARCIAL.format(devueltos=self.devueltos,
                                       total=self.total_coincidencias,
                                       detalle=self.aviso_parcial)
        )
        disponible = max(presupuesto - reserva, presupuesto // 4)
        filas, texto, recortado = ajusta_filas(self.datos, cuerpo, disponible)
        if recortado:
            self.datos = filas
            self.truncado = True
            self.advertir(PLANTILLA_RECORTE.format(offset=self.siguiente_offset))
        if (self.mostrar_conteo and self.total_coincidencias is not None
                and self.devueltos < self.total_coincidencias):
            self.advertir(PLANTILLA_PARCIAL.format(
                devueltos=self.devueltos, total=self.total_coincidencias,
                detalle=self.aviso_parcial))
        return {"texto": texto + "\n\n" + self._pie(), "estructurado": {"datos": self.datos, "_meta": self.meta()}}

    def _pie(self) -> str:
        lineas = []
        m = self.meta()
        if self.mostrar_conteo:
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
        if self.mostrar_conteo and self.siguiente_offset is not None:
            lineas.append(f"Siguiente página: `offset={self.siguiente_offset}`")
        if self.consulta:
            lineas.append(f"Consulta reproducible: {self.consulta}")
        for a in self.advertencias:
            lineas.append(f"> {a}")
        return "\n\n".join(lineas)
