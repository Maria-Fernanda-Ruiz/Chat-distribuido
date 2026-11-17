"""Recepción en pull y recuperación de historial (#18 y D27; canvas CD-005).

Dos caminos, según `MODO_RECEPCION`:

- **pull** (por defecto): `recibir_por_pull` pide `GET /history?after_seq=<cursor>` cada
  `PULL_INTERVALO_S`. El cursor `seq` se guarda en SQLite en la misma transacción que
  cada mensaje, así que después de un reinicio o de una caída del central se sigue donde
  quedó, sin perder los mensajes concurrentes que llegan tarde con una marca menor. Esa
  es también la recuperación de historial: la primera vez el cursor vale 0 y llega todo.
- **push**: el central nos llama a `/fed/messages`, y lo anterior al registro se
  recupera con `GET /history?since=` como dice D16: `since=0` al arrancar
  (`recuperar_al_arrancar`) y el último `lamport` visto al volver el central
  (`recuperar_desde`, que llama el heartbeat).

En los dos, cada mensaje entra por la misma recepción que `/fed/messages`
(`federacion.reloj`), con su deduplicación por `id` y su ajuste del reloj.
"""

from __future__ import annotations

import asyncio

import httpx
from pydantic import ValidationError

from chat.contexto import Contexto
from chat.eventos import Evento, registrar
from chat.federacion.reloj import recibir_mensaje, registrar_recepcion
from chat.modelo import Mensaje
from chat.presencia.registro import espera_reintento

# Lo máximo que entrega el central por consulta (especificación v1.0.0).
LIMITE_PAGINA = 1000


class ConsultaFallida(Exception):
    """El central no respondió bien a GET /history; se intenta en el siguiente ciclo."""


async def pedir_historial(ctx: Contexto, parametros: dict[str, object]) -> list[dict]:
    """Una consulta a GET /history. Devuelve la lista de mensajes o lanza ConsultaFallida."""
    try:
        respuesta = await ctx.http.get("/history", params=parametros)
    except httpx.HTTPError as error:
        raise ConsultaFallida(type(error).__name__) from error
    estado = respuesta.status_code
    if 300 <= estado < 500:
        registrar(Evento.RECHAZADO_4XX, estado=estado, ruta="/history")
        raise ConsultaFallida(f"HTTP_{estado}")
    if estado >= 500 or estado < 200:
        raise ConsultaFallida(f"HTTP_{estado}")
    try:
        datos = respuesta.json()
    except ValueError as error:
        raise ConsultaFallida("JSON mal formado") from error
    if not isinstance(datos, list):
        raise ConsultaFallida("la respuesta no es una lista")
    return datos


def _como_mensaje(datos: object) -> Mensaje | None:
    try:
        return Mensaje.model_validate(datos)
    except ValidationError:
        return None


def procesar_pagina_pull(ctx: Contexto, pagina: list[dict]) -> tuple[int, int]:
    """Recibe cada mensaje y avanza el cursor en la misma transacción.
    Devuelve (nuevos, duplicados)."""
    nuevos = duplicados = 0
    for datos in pagina:
        seq = datos.get("seq") if isinstance(datos, dict) else None
        mensaje = _como_mensaje(datos)
        if not isinstance(seq, int) or isinstance(seq, bool):
            # Sin seq no se puede avanzar el cursor; el central siempre lo manda.
            continue
        with ctx.almacen.transaccion() as tx:
            reloj = recibir_mensaje(mensaje, tx) if mensaje is not None else None
            tx.avanzar_cursor_seq(seq)
        if mensaje is None:
            continue
        registrar_recepcion(mensaje, reloj, via="pull")
        if reloj is None:
            duplicados += 1
        else:
            nuevos += 1
    return nuevos, duplicados


async def recibir_por_pull(ctx: Contexto) -> None:
    """Tarea de fondo del modo pull: consulta al central por cursor mientras esté vivo."""
    if ctx.config.modo_recepcion != "pull":
        return
    recuperando, desde, nuevos, duplicados = True, ctx.almacen.leer_cursor_seq(), 0, 0
    while True:
        if not ctx.central_disponible.is_set():
            # Con el central caído no se insiste; el heartbeat avisa cuándo volvió.
            await ctx.central_disponible.wait()
            recuperando, desde, nuevos, duplicados = True, ctx.almacen.leer_cursor_seq(), 0, 0
        parametros = {
            "after_seq": ctx.almacen.leer_cursor_seq(),
            "server": ctx.config.grupo,
            "limit": LIMITE_PAGINA,
        }
        try:
            pagina = await pedir_historial(ctx, parametros)
        except ConsultaFallida:
            await asyncio.sleep(ctx.config.pull_intervalo_s)
            continue
        n, d = procesar_pagina_pull(ctx, pagina)
        nuevos, duplicados = nuevos + n, duplicados + d
        if len(pagina) >= LIMITE_PAGINA:
            continue  # página llena: lo que sigue se pide ya
        if recuperando:
            registrar(
                Evento.HISTORIAL_RECUPERADO,
                after_seq=desde,
                nuevos=nuevos,
                duplicados=duplicados,
                via="pull",
            )
            recuperando = False
        await asyncio.sleep(ctx.config.pull_intervalo_s)


async def recuperar_desde(ctx: Contexto, since: int) -> None:
    """Modo push: pide GET /history?since= (inclusivo) y recibe cada mensaje.
    Lanza ConsultaFallida si el central no responde."""
    nuevos = duplicados = 0
    desde = since
    while True:
        pagina = await pedir_historial(ctx, {"since": desde, "limit": LIMITE_PAGINA})
        for datos in pagina:
            mensaje = _como_mensaje(datos)
            if mensaje is None:
                continue
            with ctx.almacen.transaccion() as tx:
                reloj = recibir_mensaje(mensaje, tx)
            registrar_recepcion(mensaje, reloj, via="historial")
            if reloj is None:
                duplicados += 1
            else:
                nuevos += 1
        ultimo = _como_mensaje(pagina[-1]) if pagina else None
        # Página llena: la siguiente empieza en la última marca (since es inclusivo y los
        # repetidos se descartan). Si la marca no avanzó, se corta para no girar en falso.
        if len(pagina) < LIMITE_PAGINA or ultimo is None or ultimo.lamport <= desde:
            break
        desde = ultimo.lamport
    registrar(
        Evento.HISTORIAL_RECUPERADO,
        since=since,
        nuevos=nuevos,
        duplicados=duplicados,
        via="historial",
    )


async def recuperar_al_arrancar(ctx: Contexto) -> None:
    """Tarea de fondo del modo push: since=0 al arrancar (D16), con backoff hasta que el
    central responda. Termina cuando lo logra."""
    if ctx.config.modo_recepcion != "push":
        return
    intento = 1
    while True:
        try:
            await recuperar_desde(ctx, 0)
            return
        except ConsultaFallida:
            espera = espera_reintento(intento, ctx.config.backoff_base_s, ctx.config.backoff_max_s)
            intento += 1
            await asyncio.sleep(espera)
