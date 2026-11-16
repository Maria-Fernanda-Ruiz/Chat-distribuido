
"""Pruebas del envío al central y sus reintentos (issue #14)."""

import asyncio
import json
import time

import httpx

from chat.almacen import Almacen
from chat.contexto import Contexto
from chat.federacion.envio import calcular_espera, enviar_pendientes
from chat.modelo import Mensaje


def preparar_pendiente(tmp_path, config):
    """Crea un almacén con un mensaje propio en la cola de pendientes."""
    almacen = Almacen(tmp_path / "chat.db")
    almacen.inicializar()

    mensaje = Mensaje.nuevo(
        usuario="ana",
        grupo=config.grupo,
        lamport=1,
        body="Hola desde pruebas",
    )

    with almacen.transaccion() as tx:
        tx.guardar_mensaje_si_no_existe(mensaje)
        tx.encolar_pendiente(mensaje.id, time.time())

    return almacen, mensaje


def crear_contexto(config, almacen, handler):
    """Construye un contexto con un central HTTP simulado."""
    http = httpx.AsyncClient(
        base_url=config.url_central,
        transport=httpx.MockTransport(handler),
    )

    contexto = Contexto(config=config, almacen=almacen, http=http)
    contexto.central_disponible.set()

    return contexto


async def esperar_hasta(condicion, timeout=2):
    """Espera una condición sin bloquear el ciclo de eventos."""
    limite = asyncio.get_running_loop().time() + timeout

    while not condicion():
        if asyncio.get_running_loop().time() >= limite:
            raise TimeoutError("No se cumplió la condición esperada")
        await asyncio.sleep(0.01)


def test_calcular_espera_respeta_el_maximo():
    for intento in range(1, 10):
        espera = calcular_espera(intento, 1.0, 5.0)
        assert 0 < espera <= 5.0


def test_envio_exitoso_elimina_el_pendiente(tmp_path, config):
    almacen, mensaje = preparar_pendiente(tmp_path, config)
    mensajes_recibidos = []

    def handler(request):
        mensajes_recibidos.append(json.loads(request.content))
        return httpx.Response(200)

    contexto = crear_contexto(config, almacen, handler)

    async def ejecutar():
        tarea = asyncio.create_task(enviar_pendientes(contexto))
        try:
            await esperar_hasta(lambda: almacen.contar_pendientes() == 0)
        finally:
            tarea.cancel()
            await asyncio.gather(tarea, return_exceptions=True)
            await contexto.http.aclose()

    asyncio.run(ejecutar())

    assert almacen.contar_pendientes() == 0
    assert len(mensajes_recibidos) == 1
    assert mensajes_recibidos[0]["id"] == mensaje.id


def test_respuesta_4xx_rechaza_y_elimina_el_pendiente(tmp_path, config):
    almacen, mensaje = preparar_pendiente(tmp_path, config)
    mensajes_recibidos = []

    def handler(request):
        mensajes_recibidos.append(json.loads(request.content))
        return httpx.Response(400)

    contexto = crear_contexto(config, almacen, handler)

    async def ejecutar():
        tarea = asyncio.create_task(enviar_pendientes(contexto))
        try:
            await esperar_hasta(lambda: almacen.contar_pendientes() == 0)
        finally:
            tarea.cancel()
            await asyncio.gather(tarea, return_exceptions=True)
            await contexto.http.aclose()

    asyncio.run(ejecutar())

    assert almacen.contar_pendientes() == 0
    assert len(mensajes_recibidos) == 1
    assert mensajes_recibidos[0]["id"] == mensaje.id


def test_respuesta_5xx_programa_reintento_y_conserva_id(tmp_path, config):
    almacen, mensaje = preparar_pendiente(tmp_path, config)
    mensajes_recibidos = []

    def handler(request):
        mensajes_recibidos.append(json.loads(request.content))
        return httpx.Response(500)

    contexto = crear_contexto(config, almacen, handler)

    async def ejecutar():
        tarea = asyncio.create_task(enviar_pendientes(contexto))
        try:
            await esperar_hasta(
                lambda: (
                    almacen.contar_pendientes() == 1
                    and almacen.pendientes_listos(time.time() + 1000)[0].intentos == 1
                )
            )
        finally:
            tarea.cancel()
            await asyncio.gather(tarea, return_exceptions=True)
            await contexto.http.aclose()

    asyncio.run(ejecutar())

    pendientes = almacen.pendientes_listos(time.time() + 1000)

    assert len(pendientes) == 1
    assert pendientes[0].mensaje.id == mensaje.id
    assert pendientes[0].intentos == 1
    assert len(mensajes_recibidos) == 1
    assert mensajes_recibidos[0]["id"] == mensaje.id


def test_error_de_conexion_programa_reintento(tmp_path, config):
    almacen, mensaje = preparar_pendiente(tmp_path, config)

    def handler(request):
        raise httpx.ConnectError("Central no disponible", request=request)

    contexto = crear_contexto(config, almacen, handler)

    async def ejecutar():
        tarea = asyncio.create_task(enviar_pendientes(contexto))
        try:
            await esperar_hasta(
                lambda: (
                    almacen.contar_pendientes() == 1
                    and almacen.pendientes_listos(time.time() + 1000)[0].intentos == 1
                )
            )
        finally:
            tarea.cancel()
            await asyncio.gather(tarea, return_exceptions=True)
            await contexto.http.aclose()

    asyncio.run(ejecutar())

    pendientes = almacen.pendientes_listos(time.time() + 1000)

    assert len(pendientes) == 1
    assert pendientes[0].mensaje.id == mensaje.id
    assert pendientes[0].intentos == 1


def test_central_caido_no_intenta_enviar(tmp_path, config):
    almacen, _ = preparar_pendiente(tmp_path, config)
    solicitudes = []

    def handler(request):
        solicitudes.append(request)
        return httpx.Response(200)

    contexto = crear_contexto(config, almacen, handler)
    contexto.central_disponible.clear()

    async def ejecutar():
        tarea = asyncio.create_task(enviar_pendientes(contexto))
        try:
            await asyncio.sleep(0.05)
        finally:
            tarea.cancel()
            await asyncio.gather(tarea, return_exceptions=True)
            await contexto.http.aclose()

    asyncio.run(ejecutar())

    assert solicitudes == []
    assert almacen.contar_pendientes() == 1
def test_envia_pendientes_en_orden_de_lamport(tmp_path, config):
    almacen = Almacen(tmp_path / "chat.db")
    almacen.inicializar()

    mensajes = []

    for lamport in (3, 1, 2):
        mensaje = Mensaje.nuevo(
            usuario="ana",
            grupo=config.grupo,
            lamport=lamport,
            body=f"Mensaje {lamport}",
        )

        with almacen.transaccion() as tx:
            tx.guardar_mensaje_si_no_existe(mensaje)
            tx.encolar_pendiente(mensaje.id, time.time())

        mensajes.append(mensaje)

    mensajes_recibidos = []

    def handler(request):
        mensajes_recibidos.append(json.loads(request.content))
        return httpx.Response(200)

    contexto = crear_contexto(config, almacen, handler)

    async def ejecutar():
        tarea = asyncio.create_task(enviar_pendientes(contexto))
        try:
            await esperar_hasta(lambda: almacen.contar_pendientes() == 0)
        finally:
            tarea.cancel()
            await asyncio.gather(tarea, return_exceptions=True)
            await contexto.http.aclose()

    asyncio.run(ejecutar())

    assert almacen.contar_pendientes() == 0
    assert [mensaje["lamport"] for mensaje in mensajes_recibidos] == [1, 2, 3]
    assert [mensaje["id"] for mensaje in mensajes_recibidos] == [
        mensajes[1].id,
        mensajes[2].id,
        mensajes[0].id,
    ]