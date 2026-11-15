
"""Reloj de Lamport persistente (Karen, #12).

El reloj se almacena en SQLite y es compartido por las áreas
que necesitan ordenar los eventos del servidor.

Reglas:
- Al enviar: L = L + 1.
- Al recibir un mensaje nuevo: L = max(L, recibido) + 1.
- Al recibir un duplicado: el reloj no cambia.

Si ya existe una transacción abierta, siempre se pasa mediante tx.
"""

from chat.almacen import Almacen, Transaccion


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
