"""Cliente HTTP con autolímite, backoff y circuit breaker por host (§6.2).

Ninguna fuente colombiana publica sus cuotas. El límite existe, simplemente no
se conoce, así que el servidor se autolimita a ciegas y de forma conservadora.

Con cinco backends, el fallo parcial es el caso normal: si el IGAC cae, SECOP
sigue funcionando.
"""

from __future__ import annotations

import asyncio
import os
import random
import time

import httpx

from .errors import (
    ErrorConfig,
    ErrorFuenteCaida,
    ErrorLimiteTasa,
    ErrorNoEncontrado,
    ErrorTimeout,
    ErrorValidacion,
)

USER_AGENT = os.environ.get(
    "CO_USER_AGENT",
    "colombia-datos-mcp/0.1 (+https://github.com/mcastiblanco/colombia-datos-mcp)",
)

REQ_POR_SEGUNDO = float(os.environ.get("CO_REQ_POR_SEGUNDO", "5"))
MAX_REINTENTOS = int(os.environ.get("CO_MAX_REINTENTOS", "4"))

# Reintentables. 202 es el "Request Processing" de Socrata para queries lentas.
REINTENTABLES = {202, 408, 429, 500, 502, 503, 504}

TIMEOUTS = {"arcgis": 30.0, "socrata": 90.0, "defecto": 45.0}


class _Cubeta:
    """Token bucket por host. Perfiles de tolerancia distintos por backend."""

    def __init__(self, tasa: float):
        self.tasa = tasa
        self.tokens = tasa
        self.marca = time.monotonic()
        self._lock = asyncio.Lock()

    async def esperar(self) -> None:
        async with self._lock:
            ahora = time.monotonic()
            self.tokens = min(self.tasa, self.tokens + (ahora - self.marca) * self.tasa)
            self.marca = ahora
            if self.tokens < 1:
                espera = (1 - self.tokens) / self.tasa
                await asyncio.sleep(espera)
                self.tokens = 0
                self.marca = time.monotonic()
            else:
                self.tokens -= 1


class _Breaker:
    """Circuit breaker por host: 5 fallos seguidos abren el circuito 60 s."""

    def __init__(self, umbral: int = 5, descanso: float = 60.0):
        self.umbral, self.descanso = umbral, descanso
        self.fallos = 0
        self.abierto_hasta = 0.0

    @property
    def abierto(self) -> bool:
        return time.monotonic() < self.abierto_hasta

    def exito(self) -> None:
        self.fallos = 0
        self.abierto_hasta = 0.0

    def fallo(self) -> None:
        self.fallos += 1
        if self.fallos >= self.umbral:
            self.abierto_hasta = time.monotonic() + self.descanso


class ClienteHTTP:
    def __init__(self, perfil: str = "defecto"):
        self._perfil = perfil
        self._cubetas: dict[str, _Cubeta] = {}
        self._breakers: dict[str, _Breaker] = {}
        self._cliente: httpx.AsyncClient | None = None

    async def _asegura_cliente(self) -> httpx.AsyncClient:
        if self._cliente is None or self._cliente.is_closed:
            self._cliente = httpx.AsyncClient(
                timeout=httpx.Timeout(TIMEOUTS.get(self._perfil, TIMEOUTS["defecto"])),
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            )
        return self._cliente

    async def cerrar(self) -> None:
        if self._cliente and not self._cliente.is_closed:
            await self._cliente.aclose()

    def _host(self, url: str) -> str:
        return httpx.URL(url).host or "desconocido"

    async def get_json(self, url: str, params: dict | None = None, headers: dict | None = None):
        host = self._host(url)
        breaker = self._breakers.setdefault(host, _Breaker())
        if breaker.abierto:
            raise ErrorFuenteCaida(
                f"El backend {host} está temporalmente fuera de servicio.",
                "Otras fuentes del servidor siguen disponibles; reintenta en un minuto.",
                host=host,
            )
        cubeta = self._cubetas.setdefault(host, _Cubeta(REQ_POR_SEGUNDO))
        cliente = await self._asegura_cliente()

        ultimo = None
        for intento in range(MAX_REINTENTOS):
            await cubeta.esperar()
            try:
                r = await cliente.get(url, params=params, headers=headers)
            except httpx.TimeoutException as exc:
                ultimo = ErrorTimeout(
                    f"Tiempo agotado consultando {host}.",
                    "Reduce el rango de fechas o añade filtros; las agregaciones sin "
                    "filtro hacen full scan y suelen exceder el tiempo.",
                )
            except httpx.HTTPError as exc:
                ultimo = ErrorFuenteCaida(f"Error de red contra {host}: {exc}", "Reintenta más tarde.")
            else:
                if r.status_code == 200:
                    breaker.exito()
                    try:
                        return r.json()
                    except ValueError:
                        raise ErrorFuenteCaida(
                            f"{host} devolvió una respuesta que no es JSON.",
                            "Puede ser una página de bloqueo (WAF) o un error HTML.",
                        )
                ultimo = self._error_de(r, host)
                # 4xx no reintentables: reintentar solo amplifica el problema.
                if r.status_code not in REINTENTABLES:
                    breaker.exito()
                    raise ultimo
            espera = (2 ** intento) * 0.5 + random.uniform(0, 0.4)
            await asyncio.sleep(espera)

        breaker.fallo()
        raise ultimo or ErrorFuenteCaida(f"No se pudo consultar {host}.", "Reintenta más tarde.")

    def _error_de(self, r: httpx.Response, host: str):
        codigo = r.status_code
        cuerpo = (r.text or "")[:300]
        if codigo == 400:
            return ErrorValidacion(
                f"Consulta rechazada por {host}: {cuerpo}",
                "Revisa los nombres de columna con la herramienta de esquema antes de filtrar.",
            )
        if codigo == 403:
            if os.environ.get("SOCRATA_APP_TOKEN"):
                return ErrorConfig(
                    f"{host} devolvió 403 con token configurado: el SOCRATA_APP_TOKEN es inválido.",
                    "Verifica el token o quítalo: el servidor funciona sin él.",
                )
            return ErrorNoEncontrado(
                f"{host} devolvió 403: recurso privado, retirado, o es una vista federada.",
                "Algunos datasets 'federated_href' parecen tablas pero no lo son; "
                "búscalos en el portal de origen.",
            )
        if codigo == 404:
            return ErrorNoEncontrado(
                f"No existe el recurso en {host}.",
                "Los IDs de dataset rotan. Búscalo por nombre en el catálogo.",
            )
        if codigo == 429:
            return ErrorLimiteTasa(
                f"{host} está limitando la tasa de peticiones.",
                "Configura SOCRATA_APP_TOKEN para tener cuota propia.",
            )
        return ErrorFuenteCaida(f"{host} devolvió HTTP {codigo}: {cuerpo}", "Reintenta más tarde.")
