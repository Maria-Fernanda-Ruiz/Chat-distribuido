
"""Envío al central con reintentos y cola de pendientes (Karen, #14).

Toma los mensajes pendientes de SQLite y los envía al central.
Los fallos temporales se reintentan con backoff exponencial y jitter,
sin límite de intentos (D10).
"""

from __future__ import annotations

import asyncio
import random
import time

import httpx

from chat.contexto import Contexto
from chat.eventos import Evento, registrar


INTERVALO_COLA_S = 0.2


def calcular_espera(intento: int, base_s: float, maximo_s: float) -> float:
    """Calcula el backoff exponencial con jitter entre el 50 % y el 100 %."""
    espera = base_s

    for _ in range(intento - 1):
        if espera >= maximo_s / 2:
            espera = maximo_s
            break
        espera *= 2

    espera = min(espera, maximo_s)
    return random.uniform(espera / 2, espera)


async def enviar_pendientes(ctx: Contexto) -> None:
    """Envía los pendientes en orden de Lamport mientras el central esté disponible."""
    while True:
        # Espera hasta que presencia indique que el central está disponible.
        await ctx.central_disponible.wait()

        pendientes = ctx.almacen.pendientes_listos(time.time())

        if not pendientes:
            await asyncio.sleep(INTERVALO_COLA_S)
            continue

        for pendiente in pendientes:
            # Si el central cae, se detiene el envío de la cola.
            if not ctx.central_disponible.is_set():
                break

            mensaje = pendiente.mensaje
            intento = pendiente.intentos + 1

            try:
                respuesta = await ctx.http.post(
                    "/messages",
                    json=mensaje.a_json(),
                )

            except httpx.HTTPError as error:
                await _reintentar(
                    ctx,
                    mensaje,
                    intento,
                    causa=type(error).__name__,
                )
                continue

            estado = respuesta.status_code

            if 200 <= estado < 300:
                ctx.almacen.quitar_pendiente(mensaje.id)

                registrar(
                    Evento.ENVIADO,
                    mensaje,
                    intento=intento,
                )

            elif 300 <= estado < 500:
                ctx.almacen.quitar_pendiente(mensaje.id)

                registrar(
                    Evento.RECHAZADO_4XX,
                    mensaje,
                    estado=estado,
                    ruta="/messages",
                )

            else:
                await _reintentar(
                    ctx,
                    mensaje,
                    intento,
                    causa=f"HTTP_{estado}",
                )


async def _reintentar(
    ctx: Contexto,
    mensaje,
    intento: int,
    *,
    causa: str,
) -> None:
    """Programa el siguiente intento conservando el mismo id del mensaje."""
    espera = calcular_espera(
        intento,
        ctx.config.backoff_base_s,
        ctx.config.backoff_max_s,
    )

    ctx.almacen.reprogramar_pendiente(
        mensaje.id,
        intentos=intento,
        proximo_intento=time.time() + espera,
    )

    registrar(
        Evento.REINTENTO,
        mensaje,
        intento=intento,
        espera_s=espera,
        causa=causa,
    )
