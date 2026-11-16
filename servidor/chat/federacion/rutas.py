"""Endpoints de federación que llama el central (Karen, #13).

Aquí se implementa POST /fed/messages (análisis, sección 4):

- Mensaje nuevo: se guarda y se actualiza el reloj Lamport en la misma
  transacción. Responde {"duplicate": false} y registra RECIBIDO.
- Mensaje duplicado: no se guarda de nuevo ni se modifica el reloj.
  Responde {"duplicate": true} y registra DUPLICADO_DESCARTADO.
- Los campos desconocidos se ignoran sin error.
- Los eventos indican via=fed para distinguir la recepción federada
  de la recepción mediante el historial.

Basado en el canvas CD-004 y los contratos de CD-002.
"""

from fastapi import APIRouter

from chat.contexto import ContextoDep
from chat.eventos import Evento, registrar
from chat.federacion.reloj import recibir
from chat.modelo import Mensaje

router = APIRouter(tags=["Federación (la llama el central)"])


@router.post("/fed/messages", status_code=200)
def recibir_mensaje(mensaje: Mensaje, ctx: ContextoDep) -> dict[str, bool]:
    """Recibe un mensaje federado, descarta duplicados y actualiza Lamport."""

    with ctx.almacen.transaccion() as tx:
        nuevo = tx.guardar_mensaje_si_no_existe(mensaje)

        if nuevo:
            recibir(mensaje.lamport, tx)

    if nuevo:
        registrar(
            Evento.RECIBIDO,
            mensaje,
            via="fed",
            reloj=ctx.almacen.leer_reloj(),
        )
    else:
        registrar(
            Evento.DUPLICADO_DESCARTADO,
            mensaje,
            via="fed",
        )

    return {"duplicate": not nuevo}
