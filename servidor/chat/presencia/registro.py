"""Registro en el central y renovación periódica (#16; canvas CD-005).

`POST /register` con `{"server", "mode"}`, más `url` si hay `URL_PUBLICA`, al arrancar
y cada `REGISTRO_INTERVALO_S`. Si el central no responde o responde `5xx`, se reintenta
con el backoff de D10 sin tumbar el servidor. Un `4xx` queda en el log y se vuelve a
intentar en la siguiente renovación. El registro no vence (especificación v1.0.0); la
renovación corrige sola una URL de túnel que cambió y le dice al panel que seguimos
vivos.
"""

from __future__ import annotations

import asyncio
import random

import httpx

from chat.contexto import Contexto
from chat.eventos import Evento, registrar

# Resultado de un intento: registrado, rechazado (4xx: no sirve reintentar ya) o fallo
# transitorio (red o 5xx: se reintenta con backoff).
REGISTRADO, RECHAZADO, FALLO = "registrado", "rechazado", "fallo"


def cuerpo_registro(ctx: Contexto) -> dict[str, str]:
    cuerpo = {"server": ctx.config.grupo, "mode": ctx.config.modo_recepcion}
    if ctx.config.url_publica:
        cuerpo["url"] = ctx.config.url_publica
    return cuerpo


async def registrar_una_vez(ctx: Contexto, intento: int = 1) -> str:
    """Un intento de registro. Deja el evento en el log y devuelve cómo terminó."""
    try:
        respuesta = await ctx.http.post("/register", json=cuerpo_registro(ctx))
    except httpx.HTTPError as error:
        _reintento(intento, type(error).__name__)
        return FALLO
    estado = respuesta.status_code
    if 200 <= estado < 300:
        registrar(
            Evento.REGISTRADO,
            url=ctx.config.url_publica or None,
            modo=ctx.config.modo_recepcion,
            nuevo=_campo_new(respuesta),
        )
        return REGISTRADO
    if 300 <= estado < 500:
        registrar(Evento.RECHAZADO_4XX, estado=estado, ruta="/register")
        return RECHAZADO
    _reintento(intento, f"HTTP_{estado}")
    return FALLO


async def mantener_registro(ctx: Contexto) -> None:
    """Tarea de fondo: registra al arrancar y renueva cada REGISTRO_INTERVALO_S."""
    intento = 1
    while True:
        resultado = await registrar_una_vez(ctx, intento)
        if resultado == FALLO:
            espera = espera_reintento(intento, ctx.config.backoff_base_s, ctx.config.backoff_max_s)
            intento += 1
            await asyncio.sleep(min(espera, ctx.config.registro_intervalo_s))
        else:
            intento = 1
            await asyncio.sleep(ctx.config.registro_intervalo_s)


def espera_reintento(intento: int, base_s: float, maximo_s: float) -> float:
    """El backoff de D10: base · 2ⁿ⁻¹ hasta el máximo, con jitter entre la mitad y el total."""
    espera = min(maximo_s, base_s * 2 ** min(intento - 1, 30))
    return random.uniform(espera / 2, espera)


def _reintento(intento: int, causa: str) -> None:
    registrar(Evento.REINTENTO, ruta="/register", intento=intento, causa=causa)


def _campo_new(respuesta: httpx.Response) -> object:
    try:
        datos = respuesta.json()
    except ValueError:
        return None
    return datos.get("new") if isinstance(datos, dict) else None
