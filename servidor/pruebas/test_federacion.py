
"""Pruebas de recepción de mensajes federados (#13)."""

import logging


def mensaje_ejemplo(**cambios):
    mensaje = {
        "id": "m1",
        "from": "ana@g1",
        "origin": "g1",
        "lamport": 7,
        "sent_at": "2026-11-15T12:00:00Z",
        "body": "Hola desde g1",
    }
    mensaje.update(cambios)
    return mensaje


def test_recibir_mensaje_nuevo_lo_guarda_y_actualiza_lamport(cliente, caplog):
    with caplog.at_level(logging.INFO, logger="chat.eventos"):
        respuesta = cliente.post("/fed/messages", json=mensaje_ejemplo())

    almacen = cliente.app.state.contexto.almacen

    assert respuesta.status_code == 200
    assert almacen.contar_mensajes() == 1
    assert almacen.leer_reloj() == 8

    (guardado,) = almacen.listar_historial()
    assert guardado.id == "m1"

    assert "RECIBIDO id=m1" in caplog.text


def test_recibir_mensaje_duplicado_no_lo_guarda_ni_actualiza_lamport(cliente, caplog):
    with caplog.at_level(logging.INFO, logger="chat.eventos"):
        cliente.post("/fed/messages", json=mensaje_ejemplo())

        respuesta = cliente.post(
            "/fed/messages",
            json=mensaje_ejemplo(lamport=20, body="Mensaje repetido"),
        )

    almacen = cliente.app.state.contexto.almacen

    assert respuesta.status_code == 200
    assert almacen.contar_mensajes() == 1
    assert almacen.leer_reloj() == 8

    (guardado,) = almacen.listar_historial()
    assert guardado.body == "Hola desde g1"

    assert "RECIBIDO id=m1" in caplog.text
    assert "DUPLICADO_DESCARTADO id=m1" in caplog.text


def test_recibir_mensaje_ignora_campos_desconocidos(cliente):
    datos = mensaje_ejemplo()
    datos["campo_extra"] = "este campo debe ignorarse"

    respuesta = cliente.post("/fed/messages", json=datos)

    assert respuesta.status_code == 200
    assert cliente.app.state.contexto.almacen.contar_mensajes() == 1


def test_recibir_mensaje_invalido_no_modifica_el_reloj(cliente):
    datos = mensaje_ejemplo()
    del datos["from"]

    respuesta = cliente.post("/fed/messages", json=datos)

    almacen = cliente.app.state.contexto.almacen

    assert respuesta.status_code == 422
    assert almacen.contar_mensajes() == 0
    assert almacen.leer_reloj() == 0
