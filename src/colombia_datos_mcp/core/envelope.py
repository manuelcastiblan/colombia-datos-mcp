"""El sobre (§4.2): metadatos honestos alrededor de cada respuesta.

`consulta` es no negociable: la URL exacta y reproducible que produjo el
resultado. Para uso periodístico o de control fiscal, una cifra sin su consulta
reproducible no sirve.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import format as fmt
from .budget import Detalle, PRESUPUESTO_POR_DEFECTO, ajusta_filas


# Los dos avisos que dependen de cuánto se recorte. Van aquí para que el texto
# medido y el texto enviado sean literalmente el mismo objeto.
PLANTILLA_RECORTE = (
    "Respuesta recortada por presupuesto de tokens. Refina con filtros, usa "
    "detalle='conteo' para contar sin traer filas, o pagina con offset={offset}."
)
PLANTILLA_PARCIAL = "Viendo {devueltos} de {total} coincidencias. {detalle}"


@dataclass(frozen=True)
class Total:
    """Cuántas coincidencias hay **y cómo se supo**.

    El defecto más repetido de este servidor fue escribir `len(filas)` donde
    iba un total. Sintácticamente es un entero impecable; semánticamente es una
    afirmación que nadie comprobó, y apareció en seis herramientas por separado.

    Un entero desnudo no puede distinguir «lo conté» de «supuse». Este tipo sí,
    y el constructor que se usaría por descuido —`cupo_entero`— exige el límite
    de la consulta y **decide él**: si la fuente lo llenó, devuelve desconocido
    en vez del número que alguien habría puesto. No hay forma de afirmar un
    total sin haberlo comprobado, así que el error deja de ser detectable para
    ser inexpresable.
    """

    valor: int | None
    origen: str

    @property
    def consta(self) -> bool:
        return self.valor is not None

    @classmethod
    def contado(cls, n: int) -> "Total":
        """La fuente lo contó: `count(*)`, o la subconsulta anidada de grupos."""
        return cls(int(n), "contado")

    @classmethod
    def cupo_entero(cls, filas, limite: int) -> "Total":
        """El total cuando la respuesta cabía entera.

        Si la fuente devolvió MENOS de lo que se le pidió, no hay más y
        `len(filas)` sí es el total, exacto y sin coste. Si llenó el límite, no
        consta: eso es justo lo que se afirmaba a la ligera.
        """
        return (cls(len(filas), "cabia_entero") if len(filas) < limite
                else cls(None, "desconocido"))

    @classmethod
    def completo(cls, n: int) -> "Total":
        """La colección ES completa por construcción, no por haber cabido: las
        columnas de un esquema, un contrato concreto, una lista fija de
        datasets, un resultado vacío. No hay consulta con `$limit` detrás."""
        return cls(int(n), "completo")

    @classmethod
    def desconocido(cls) -> "Total":
        return cls(None, "desconocido")


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
    # Se llama `total`, y no `total_coincidencias`, a propósito: así cualquier
    # sitio que siguiera pasando un entero desnudo falla al construirse en vez
    # de colarse. `total_coincidencias` sigue existiendo como propiedad de solo
    # lectura —y como campo del sobre en la respuesta—, pero ya no se asigna.
    total: Total | None = None
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
    def total_coincidencias(self) -> int | None:
        """Solo lectura. Para fijarlo hay que construir un `Total` y decir de
        dónde salió; asignar aquí un entero da AttributeError, que es el
        objetivo."""
        return self.total.valor if self.total else None

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
            # Cómo se supo ese total: `contado` por la fuente, `cabia_entero`
            # porque no había más que ver, o `completo` porque la colección no
            # sale de una consulta con `$limit`. Quien cite la cifra puede ver
            # de dónde vino sin preguntar.
            "origen_del_total": self.total.origen if self.total and self.total.consta else None,
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

        todas = list(self.datos)
        base = list(self.advertencias)

        def respuesta(filas):
            """El texto REAL que se enviaría con ese recorte: cuerpo, pie,
            procedencia y avisos incluidos.

            Antes se medía solo el cuerpo y se estimaba el resto, con dos
            fallos encadenados: el pie no se descontaba —200 filas se pasaban
            196 tokens— y, al reservarlo, recortar AÑADE avisos, así que el
            propio aviso de recorte empujaba la respuesta por encima del
            presupuesto que ese recorte acababa de imponer. Midiendo lo que se
            manda, en vez de una parte y un cálculo, el problema no existe: no
            hay reserva que se pueda quedar corta.
            """
            self.datos = filas
            self.advertencias = list(base)
            self.truncado = len(filas) < len(todas)
            if self.truncado:
                self.advertir(PLANTILLA_RECORTE.format(offset=self.siguiente_offset))
            if (self.mostrar_conteo and self.total_coincidencias is not None
                    and self.devueltos < self.total_coincidencias):
                self.advertir(PLANTILLA_PARCIAL.format(
                    devueltos=self.devueltos, total=self.total_coincidencias,
                    detalle=self.aviso_parcial))
            return cuerpo(filas) + "\n\n" + self._pie()

        # `ajusta_filas` deja siempre el estado en la selección que devuelve,
        # así que `self.datos` y las advertencias quedan coherentes con `texto`.
        _filas, texto, _recortado = ajusta_filas(todas, respuesta, presupuesto)
        return {"texto": texto,
                "estructurado": {"datos": self.datos, "_meta": self.meta()}}

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
