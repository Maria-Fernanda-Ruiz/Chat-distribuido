
"""Reloj de Lamport persistente (Karen, #12).

El reloj se almacena en SQLite y es compartido por las áreas
que necesitan ordenar los eventos del servidor.

Reglas:
- Al enviar: L = L + 1.
- Al recibir un mensaje nuevo: L = max(L, recibido) + 1.
- Al recibir un duplicado: el reloj no cambia.

Si ya existe una transacción abierta, siempre se pasa mediante tx.

`recibir_mensaje` y `registrar_recepcion` son la única recepción del servidor: las usan
POST /fed/messages (via=fed), el pull (via=pull) y la recuperación con since
(via=historial), así la deduplicación y el reloj se aplican igual en los tres caminos
(D27, canvas CD-005).
"""

from chat.almacen import Almacen, Transaccion
from chat.eventos import Evento, registrar
from chat.modelo import Mensaje


def tick(
    tx: Transaccion | None = None,
    *,
    almacen: Almacen | None = None,
) -> int:
    """Incrementa el reloj antes de enviar un mensaje y devuelve su valor."""

    if tx is not None:
        nuevo_valor = tx.leer_reloj() + 1
        tx.fijar_reloj(nuevo_valor)
        return nuevo_valor

    if almacen is None:
        raise ValueError(
            "Se necesita una transacción o un almacén para actualizar el reloj."
        )

    with almacen.transaccion() as transaccion:
        return tick(transaccion)


def recibir(
    valor: int,
    tx: Transaccion | None = None,
    *,
    almacen: Almacen | None = None,
) -> int:
    """Actualiza el reloj al recibir un mensaje nuevo."""

    if tx is not None:
        reloj_local = tx.leer_reloj()
        nuevo_valor = max(reloj_local, valor) + 1
        tx.fijar_reloj(nuevo_valor)
        return nuevo_valor

    if almacen is None:
        raise ValueError(
            "Se necesita una transacción o un almacén para actualizar el reloj."
        )

    with almacen.transaccion() as transaccion:
        return recibir(valor, transaccion)


def recibir_mensaje(mensaje: Mensaje, tx: Transaccion) -> int | None:
    """Guarda el mensaje si su `id` es nuevo y ajusta el reloj, dentro de `tx`.

    Devuelve el reloj después de recibirlo, o None si era un duplicado: en ese caso no se
    guarda nada ni se toca el reloj."""
    if not tx.guardar_mensaje_si_no_existe(mensaje):
        return None
    return recibir(mensaje.lamport, tx)


def registrar_recepcion(mensaje: Mensaje, reloj: int | None, via: str) -> None:
    """Deja en el log RECIBIDO o DUPLICADO_DESCARTADO. Se llama después de confirmar la
    transacción, para no registrar algo que terminó en rollback."""
    if reloj is None:
        registrar(Evento.DUPLICADO_DESCARTADO, mensaje, via=via)
    else:
        registrar(Evento.RECIBIDO, mensaje, via=via, reloj=reloj)
