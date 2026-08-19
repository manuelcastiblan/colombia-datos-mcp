"""Caché en dos niveles (§6.1). Los ocho servidores auditados tienen cero.

L1: memoria con TTL corto, para consultas repetidas dentro de una sesión.
L2: disco (JSON) con TTL largo, para esquemas y directorios de servicios.
Más deduplicación de peticiones idénticas en vuelo.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from pathlib import Path

TTL_DATOS = int(os.environ.get("CO_TTL_DATOS", "900"))        # 15 min
TTL_METADATOS = int(os.environ.get("CO_TTL_METADATOS", "86400"))  # 24 h

DIR_CACHE = Path(
    os.environ.get("CO_CACHE_DIR", Path.home() / ".cache" / "colombia-datos-mcp")
)


def _clave(*partes) -> str:
    crudo = "|".join(str(p) for p in partes)
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()[:32]


class Cache:
    def __init__(self, dir_disco: Path = DIR_CACHE, max_memoria: int = 512):
        self._mem: dict[str, tuple[float, object]] = {}
        self._max_memoria = max_memoria
        self._dir = Path(dir_disco)
        self._en_vuelo: dict[str, asyncio.Future] = {}

    # ------------------------------------------------------------------ L1 --
    def obtener_memoria(self, clave: str):
        entrada = self._mem.get(clave)
        if not entrada:
            return None
        expira, valor = entrada
        if expira < time.time():
            self._mem.pop(clave, None)
            return None
        return valor

    def guardar_memoria(self, clave: str, valor, ttl: int = TTL_DATOS) -> None:
        if len(self._mem) >= self._max_memoria:
            # Descarta lo más próximo a expirar; suficiente y sin dependencias.
            viejo = min(self._mem.items(), key=lambda kv: kv[1][0])[0]
            self._mem.pop(viejo, None)
        self._mem[clave] = (time.time() + ttl, valor)

    # ------------------------------------------------------------------ L2 --
    def _ruta(self, clave: str) -> Path:
        return self._dir / f"{clave}.json"

    def obtener_disco(self, clave: str):
        ruta = self._ruta(clave)
        try:
            if not ruta.exists():
                return None
            with ruta.open(encoding="utf-8") as fh:
                envuelto = json.load(fh)
            if envuelto.get("expira", 0) < time.time():
                ruta.unlink(missing_ok=True)
                return None
            return envuelto.get("valor")
        except (OSError, ValueError):
            return None

    def guardar_disco(self, clave: str, valor, ttl: int = TTL_METADATOS) -> None:
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            tmp = self._ruta(clave).with_suffix(".tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump({"expira": time.time() + ttl, "valor": valor}, fh)
            tmp.replace(self._ruta(clave))
        except (OSError, TypeError):
            pass  # la caché es best-effort, nunca load-bearing

    # ------------------------------------------------------------ combinado --
    async def obtener_o_calcular(self, partes, calcular, ttl=TTL_DATOS, en_disco=False):
        """Devuelve el valor cacheado o lo calcula, deduplicando en vuelo."""
        clave = _clave(*partes)

        valor = self.obtener_memoria(clave)
        if valor is not None:
            return valor
        if en_disco:
            valor = self.obtener_disco(clave)
            if valor is not None:
                self.guardar_memoria(clave, valor, ttl)
                return valor

        pendiente = self._en_vuelo.get(clave)
        if pendiente is not None:
            return await asyncio.shield(pendiente)

        futuro = asyncio.get_running_loop().create_future()
        self._en_vuelo[clave] = futuro
        try:
            valor = await calcular()
            self.guardar_memoria(clave, valor, ttl)
            if en_disco:
                self.guardar_disco(clave, valor, ttl)
            if not futuro.done():
                futuro.set_result(valor)
            return valor
        except BaseException as exc:
            # `BaseException` y no `Exception`: `CancelledError` hereda de la
            # primera, así que una cancelación del dueño se saltaba este bloque,
            # el `finally` retiraba la clave y el futuro quedaba pendiente PARA
            # SIEMPRE. Todo el que esperase en `shield` colgaba sin remedio y
            # sin error. Estaba dormido porque nada cancelaba estas corrutinas;
            # basta un `wait_for` en cualquier llamante para despertarlo.
            if not futuro.done():
                # Y no se propaga la cancelación tal cual: al que espera no lo
                # ha cancelado nadie, así que recibe un error normal —del que
                # puede recuperarse— en vez de morir por una cancelación ajena.
                futuro.set_exception(
                    RuntimeError("La petición compartida se canceló antes de terminar.")
                    if isinstance(exc, asyncio.CancelledError) else exc
                )
                # Si nadie llegó a esperar este futuro, asyncio escupiría
                # "Future exception was never retrieved" al recolectarlo, y ese
                # ruido en stderr contamina el transporte stdio del servidor.
                # Consumir la excepción la marca como recuperada.
                futuro.add_done_callback(lambda f: f.exception())
            raise
        finally:
            self._en_vuelo.pop(clave, None)


cache = Cache()
