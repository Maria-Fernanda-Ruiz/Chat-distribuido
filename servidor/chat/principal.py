
"""Arma la aplicación: incluye las rutas de cada área y lanza las tareas de fondo.

El ciclo de vida sigue el análisis (sección 12). Al arrancar se abre SQLite, se crea el
contexto, se lanzan las tareas de fondo y la API empieza a responder. Al parar se cancelan las tareas
y el proceso termina enseguida: lo pendiente queda guardado y se retoma al volver.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from chat.almacen import Almacen
from chat.api_local import rutas as rutas_api_local
from chat.configuracion import Configuracion
from chat.contexto import Contexto
from chat.eventos import Evento, registrar
from chat.federacion import envio, rutas as rutas_federacion
from chat.presencia import rutas as rutas_presencia

TareaDeFondo = Callable[[Contexto], Awaitable[None]]

# Cada área agrega aquí su tarea cuando la implementa. Una tarea es una función
# `async def tarea(ctx: Contexto) -> None` que normalmente corre en un ciclo hasta que la
# cancelan al parar el servidor.
TAREAS_DE_FONDO: list[TareaDeFondo] = [
    # registro.mantener_registro,        # presencia, #16
    # historial.recuperar_al_arrancar,   # presencia, #18
    # heartbeat.vigilar_central,         # presencia, #17
    envio.enviar_pendientes,             # federación, #14
]

# Si una tarea falla de forma inesperada, se reinicia después de esta espera (Norms).
ESPERA_REINICIO_TAREA_S = 1.0

_log = logging.getLogger("chat")


def crear_app(
    config: Configuracion,
    almacen: Almacen | None = None,
    tareas: Sequence[TareaDeFondo] | None = None,
) -> FastAPI:
    """Crea la aplicación. Las pruebas pueden pasar su propio almacén y reemplazar
    TAREAS_DE_FONDO con `tareas`."""
    almacen = almacen if almacen is not None else Almacen(config.ruta_bd)
    tareas_a_lanzar = list(TAREAS_DE_FONDO if tareas is None else tareas)

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
        almacen.inicializar()
        async with httpx.AsyncClient(
            base_url=config.url_central, timeout=config.http_timeout_s
        ) as http:
            contexto = Contexto(config=config, almacen=almacen, http=http)
            # Se arranca suponiendo que el central está vivo (análisis, sección 8).
            contexto.central_disponible.set()
            app.state.contexto = contexto
            registrar(
                Evento.ARRANQUE,
                reloj=almacen.leer_reloj(),
                mensajes=almacen.contar_mensajes(),
                pendientes=almacen.contar_pendientes(),
                central=config.url_central,
            )
            corriendo = [
                asyncio.create_task(_vigilar(tarea, contexto), name=tarea.__name__)
                for tarea in tareas_a_lanzar
            ]
            try:
                yield
            finally:
                for tarea in corriendo:
                    tarea.cancel()
                await asyncio.gather(*corriendo, return_exceptions=True)
                registrar(Evento.PARADA, pendientes=almacen.contar_pendientes())

    app = FastAPI(title=f"Chat distribuido · {config.grupo}", lifespan=ciclo_de_vida)
    app.include_router(rutas_api_local.router)
    app.include_router(rutas_federacion.router)
    app.include_router(rutas_presencia.router)
    return app


async def _vigilar(tarea: TareaDeFondo, contexto: Contexto) -> None:
    """Corre una tarea de fondo y la reinicia si falla, para que nunca muera en silencio."""
    while True:
        try:
            await tarea(contexto)
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            _log.exception(
                "La tarea de fondo %s falló; se reinicia en %g s",
                tarea.__name__,
                ESPERA_REINICIO_TAREA_S,
            )
            await asyncio.sleep(ESPERA_REINICIO_TAREA_S)
