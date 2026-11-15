
"""Endpoints de federación que llama el central (Karen, #13)."""

from fastapi import APIRouter

from chat.contexto import ContextoDep
from chat.eventos import Evento, registrar
from chat.federacion.reloj import recibir
from chat.modelo import Mensaje

router = APIRouter(tags=["Federación (la llama el central)"])


@router.post("/fed/messages", status_code=200)
def recibir_mensaje(mensaje: Mensaje, ctx: ContextoDep) -> None:
    """Recibe un mensaje federado, descarta duplicados y actualiza Lamport."""

    with ctx.almacen.transaccion() as tx:
        nuevo = tx.guardar_mensaje_si_no_existe(mensaje)

        if nuevo:
            recibir(mensaje.lamport, tx)

    if nuevo:
        registrar(Evento.RECIBIDO, mensaje)
    else:
        registrar(Evento.DUPLICADO_DESCARTADO, mensaje)
