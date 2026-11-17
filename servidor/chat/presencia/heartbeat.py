"""Heartbeat al central y estado vivo o caído (#17; análisis, sección 8; canvas CD-005).

- `GET /health` cada `HEARTBEAT_INTERVALO_S`; cualquier `2xx` cuenta como vivo.
- Tras `HEARTBEAT_FALLOS_PARA_CAIDO` fallos seguidos: `CENTRAL_CAIDO` y
  `ctx.central_disponible.clear()`. El envío de pendientes y el pull lo esperan, así que
  se pausan.
- Con el primer `2xx` después de estar caído: `CENTRAL_VOLVIO` y, en este orden, se
  renueva el registro, en push se recupera el historial con `since` = último `lamport`
  visto (D16), se adelantan los pendientes y se pone `ctx.central_disponible`. En pull no
  hace falta recuperar aparte: el cursor sigue donde quedó (D27).
"""

from __future__ import annotations

import asyncio
import time

import httpx

from chat.contexto import Contexto
from chat.eventos import Evento, registrar
from chat.presencia import historial, registro


async def central_responde(ctx: Contexto) -> bool:
    try:
        respuesta = await ctx.http.get("/health")
    except httpx.HTTPError:
        return False
    return 200 <= respuesta.status_code < 300


async def al_volver(ctx: Contexto) -> None:
    """Lo que se hace cuando el central vuelve, antes de reanudar el envío y el pull."""
    await registro.registrar_una_vez(ctx)
    if ctx.config.modo_recepcion == "push":
        try:
            await historial.recuperar_desde(ctx, ctx.almacen.ultimo_lamport_visto())
        except historial.ConsultaFallida:
            # El central acaba de responder al heartbeat; si justo ahora falla, lo que
            # falte llega por /fed/messages desde nuestro cursor en el central.
            pass
    ctx.almacen.adelantar_pendientes(time.time())


async def vigilar_central(ctx: Contexto) -> None:
    """Tarea de fondo: cuenta fallos seguidos y cambia el estado del central."""
    fallos = 0
    # Si la tarea se reinició con el central marcado caído (por un fallo en al_volver),
    # se sigue tratando como caído; si no, el primer 2xx nunca volvería a poner el evento.
    caido_desde: float | None = None if ctx.central_disponible.is_set() else time.monotonic()
    while True:
        if await central_responde(ctx):
            fallos = 0
            if caido_desde is not None:
                registrar(Evento.CENTRAL_VOLVIO, caido_s=time.monotonic() - caido_desde)
                caido_desde = None
                await al_volver(ctx)
                ctx.central_disponible.set()
        else:
            fallos += 1
            if caido_desde is None and fallos >= ctx.config.heartbeat_fallos_para_caido:
                caido_desde = time.monotonic()
                ctx.central_disponible.clear()
                registrar(Evento.CENTRAL_CAIDO, fallos=fallos)
        await asyncio.sleep(ctx.config.heartbeat_intervalo_s)
