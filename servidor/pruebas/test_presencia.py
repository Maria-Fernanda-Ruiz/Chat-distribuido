"""Pruebas de presencia y recepción en pull (#15–#18, D27; canvas CD-005).

El central se simula con httpx.MockTransport, con el comportamiento de la especificación
v1.0.0: /register responde {"server", "url", "mode", "new"}, /history devuelve una lista
con `seq` y /health responde 200 mientras el central está vivo.
"""

import asyncio
import dataclasses
import json
import logging
import time

import httpx
import pytest

from chat.almacen import Almacen
from chat.contexto import Contexto
from chat.federacion.reloj import tick
from chat.modelo import Mensaje
from chat.presencia import heartbeat, historial, registro


class CentralFalso:
    def __init__(self) -> None:
        self.registros: list[dict] = []
        self.codigos_registro: list[int] = []
        self.consultas: list[dict[str, str]] = []
        self.mensajes: list[dict] = []
        self.salud: int | str = 200

    def agregar(self, id: str, lamport: int, origin: str = "g1") -> dict:
        mensaje = {
            "id": id,
            "from": f"ana@{origin}",
            "origin": origin,
            "lamport": lamport,
            "sent_at": "2026-11-16T12:00:00Z",
            "body": "hola",
            "seq": len(self.mensajes) + 1,
        }
        self.mensajes.append(mensaje)
        return mensaje

    def __call__(self, request: httpx.Request) -> httpx.Response:
        ruta = request.url.path
        if ruta == "/register":
            cuerpo = json.loads(request.content)
            self.registros.append(cuerpo)
            codigo = self.codigos_registro.pop(0) if self.codigos_registro else 200
            return httpx.Response(
                codigo,
                json={
                    "server": cuerpo["server"],
                    "url": cuerpo.get("url"),
                    "mode": cuerpo.get("mode", "push"),
                    "new": len(self.registros) == 1,
                },
            )
        if ruta == "/health":
            if self.salud == "sin conexión":
                raise httpx.ConnectError("central caído", request=request)
            return httpx.Response(self.salud, json={"status": "ok", "spec_version": "1.0.0", "last_seq": 0})
        if ruta == "/history":
            parametros = dict(request.url.params)
            self.consultas.append(parametros)
            limite = int(parametros.get("limit", 1000))
            if "after_seq" in parametros:
                desde = int(parametros["after_seq"])
                lista = [m for m in self.mensajes if m["seq"] > desde]
            else:
                desde = int(parametros.get("since", 0))
                lista = sorted(
                    (m for m in self.mensajes if m["lamport"] >= desde),
                    key=lambda m: (m["lamport"], m["origin"], m["id"]),
                )
            return httpx.Response(200, json=lista[:limite])
        return httpx.Response(404, json={"error": "no existe"})


@pytest.fixture
def central() -> CentralFalso:
    return CentralFalso()


@pytest.fixture
def rapida(config):
    """La configuración de prueba con tiempos cortos."""
    return dataclasses.replace(
        config,
        heartbeat_intervalo_s=0.01,
        registro_intervalo_s=0.05,
        backoff_base_s=0.01,
        backoff_max_s=0.02,
        pull_intervalo_s=0.01,
    )


def crear_contexto(config, central, almacen=None) -> Contexto:
    if almacen is None:
        almacen = Almacen(config.ruta_bd)
        almacen.inicializar()
    http = httpx.AsyncClient(base_url=config.url_central, transport=httpx.MockTransport(central))
    contexto = Contexto(config=config, almacen=almacen, http=http)
    contexto.central_disponible.set()
    return contexto


def correr_hasta(contexto, tarea, condicion, timeout=2.0, antes=None) -> None:
    """Corre una tarea de fondo hasta que se cumpla la condición y luego la cancela."""

    async def ejecutar():
        corriendo = asyncio.create_task(tarea(contexto))
        try:
            limite = asyncio.get_running_loop().time() + timeout
            if antes is not None:
                await antes()
            while not condicion():
                if corriendo.done():
                    corriendo.result()
                if asyncio.get_running_loop().time() >= limite:
                    raise TimeoutError("No se cumplió la condición esperada")
                await asyncio.sleep(0.005)
        finally:
            corriendo.cancel()
            await asyncio.gather(corriendo, return_exceptions=True)
            await contexto.http.aclose()

    asyncio.run(ejecutar())


def correr(coro_fn, contexto):
    async def ejecutar():
        try:
            return await coro_fn(contexto)
        finally:
            await contexto.http.aclose()

    return asyncio.run(ejecutar())


def guardar_propio(almacen: Almacen, grupo: str) -> Mensaje:
    with almacen.transaccion() as tx:
        mensaje = Mensaje.nuevo(usuario="ana", grupo=grupo, lamport=tick(tx), body="mío")
        tx.guardar_mensaje_si_no_existe(mensaje)
    return mensaje


# --- #15 · /fed/health ----------------------------------------------------------------


def test_fed_health_refleja_el_reloj_despues_de_recibir(cliente):
    cliente.post(
        "/fed/messages",
        json={"id": "m1", "from": "ana@g1", "origin": "g1", "lamport": 7, "sent_at": "", "body": ""},
    )
    assert cliente.get("/fed/health").json() == {"server": "gprueba", "lamport": 8}


# --- #16 · Registro ---------------------------------------------------------------------


def test_registro_en_pull_no_necesita_url(config, central, caplog):
    contexto = crear_contexto(dataclasses.replace(config, url_publica=""), central)
    with caplog.at_level(logging.INFO, logger="chat.eventos"):
        assert correr(registro.registrar_una_vez, contexto) == registro.REGISTRADO
    assert central.registros == [{"server": "gprueba", "mode": "pull"}]
    assert "REGISTRADO modo=pull nuevo=true" in caplog.text


def test_registro_en_push_lleva_la_url(config, central):
    contexto = crear_contexto(dataclasses.replace(config, modo_recepcion="push"), central)
    correr(registro.registrar_una_vez, contexto)
    assert central.registros == [{"server": "gprueba", "mode": "push", "url": "http://gprueba:8000"}]


def test_registro_reintenta_un_503_y_despues_renueva(rapida, central, caplog):
    central.codigos_registro = [503]
    contexto = crear_contexto(rapida, central)
    with caplog.at_level(logging.INFO, logger="chat.eventos"):
        correr_hasta(contexto, registro.mantener_registro, lambda: len(central.registros) >= 3)
    assert "REINTENTO ruta=/register intento=1 causa=HTTP_503" in caplog.text
    assert caplog.text.count("REGISTRADO") >= 2


def test_registro_sin_conexion_no_tumba_la_tarea(rapida, caplog):
    def sin_conexion(request):
        raise httpx.ConnectError("sin red", request=request)

    contexto = crear_contexto(rapida, sin_conexion)
    with caplog.at_level(logging.INFO, logger="chat.eventos"):
        correr_hasta(contexto, registro.mantener_registro, lambda: caplog.text.count("REINTENTO") >= 3)
    assert "causa=ConnectError" in caplog.text


def test_registro_rechazado_queda_en_el_log(config, central, caplog):
    central.codigos_registro = [400]
    contexto = crear_contexto(config, central)
    with caplog.at_level(logging.INFO, logger="chat.eventos"):
        assert correr(registro.registrar_una_vez, contexto) == registro.RECHAZADO
    assert "RECHAZADO_4XX estado=400 ruta=/register" in caplog.text


# --- Recepción en pull (D27) -------------------------------------------------------------


def test_el_cursor_solo_avanza(config):
    almacen = Almacen(config.ruta_bd)
    almacen.inicializar()
    assert almacen.leer_cursor_seq() == 0
    with almacen.transaccion() as tx:
        tx.avanzar_cursor_seq(5)
        tx.avanzar_cursor_seq(3)
    assert almacen.leer_cursor_seq() == 5


def test_pull_recibe_ajusta_el_reloj_y_guarda_el_cursor(rapida, central, caplog):
    contexto = crear_contexto(rapida, central)
    propio = guardar_propio(contexto.almacen, rapida.grupo)  # reloj en 1
    central.agregar("m1", lamport=5, origin="g1")
    central.agregar("m2", lamport=3, origin="g2")  # concurrente, llega tarde con marca menor
    central.mensajes.append({**propio.a_json(), "seq": 3})  # el nuestro vuelve por el pull
    with caplog.at_level(logging.INFO, logger="chat.eventos"):
        correr_hasta(contexto, historial.recibir_por_pull, lambda: contexto.almacen.leer_cursor_seq() == 3)
    almacen = contexto.almacen
    assert almacen.contar_mensajes() == 3
    assert almacen.leer_reloj() == 7  # max(1, 5) + 1 = 6; max(6, 3) + 1 = 7; el propio no cuenta
    assert central.consultas[0] == {"after_seq": "0", "server": "gprueba", "limit": "1000"}
    assert "RECIBIDO id=m2" in caplog.text and "via=pull" in caplog.text
    assert f"DUPLICADO_DESCARTADO id={propio.id}" in caplog.text
    assert "HISTORIAL_RECUPERADO after_seq=0 nuevos=2 duplicados=1 via=pull" in caplog.text


def test_pull_sigue_desde_el_cursor_despues_de_reiniciar(rapida, central):
    for i in range(3):
        central.agregar(f"m{i}", lamport=i + 1)
    contexto = crear_contexto(rapida, central)
    correr_hasta(contexto, historial.recibir_por_pull, lambda: contexto.almacen.leer_cursor_seq() == 3)
    central.agregar("m3", lamport=1, origin="g9")  # llega tarde y con marca vieja
    central.consultas.clear()
    # Mismo archivo SQLite: otro arranque del servidor.
    contexto = crear_contexto(rapida, central)
    correr_hasta(contexto, historial.recibir_por_pull, lambda: contexto.almacen.leer_cursor_seq() == 4)
    assert central.consultas[0]["after_seq"] == "3"
    assert contexto.almacen.contar_mensajes() == 4


def test_pull_pide_la_pagina_siguiente_sin_esperar(rapida, central, monkeypatch):
    monkeypatch.setattr(historial, "LIMITE_PAGINA", 2)
    for i in range(5):
        central.agregar(f"m{i}", lamport=i + 1)
    contexto = crear_contexto(dataclasses.replace(rapida, pull_intervalo_s=30), central)
    correr_hasta(contexto, historial.recibir_por_pull, lambda: contexto.almacen.leer_cursor_seq() == 5)
    assert [c["after_seq"] for c in central.consultas[:3]] == ["0", "2", "4"]


def test_pull_no_consulta_con_el_central_caido(rapida, central):
    central.agregar("m1", lamport=1)
    contexto = crear_contexto(rapida, central)
    contexto.central_disponible.clear()

    async def esperar_y_reanudar():
        await asyncio.sleep(0.1)
        assert central.consultas == []
        contexto.central_disponible.set()

    correr_hasta(
        contexto,
        historial.recibir_por_pull,
        lambda: contexto.almacen.leer_cursor_seq() == 1,
        antes=esperar_y_reanudar,
    )


def test_pull_y_fed_messages_comparten_la_deduplicacion(cliente):
    contexto = cliente.app.state.contexto
    mensaje = {"id": "m1", "from": "ana@g1", "origin": "g1", "lamport": 4, "sent_at": "", "body": "", "seq": 1}
    assert historial.procesar_pagina_pull(contexto, [mensaje]) == (1, 0)
    respuesta = cliente.post("/fed/messages", json=mensaje)
    assert respuesta.json() == {"duplicate": True}
    assert contexto.almacen.leer_reloj() == 5


def test_pull_salta_un_mensaje_invalido_pero_avanza_el_cursor(cliente):
    contexto = cliente.app.state.contexto
    invalido = {"id": "", "from": "x", "origin": "g1", "lamport": 1, "seq": 1}
    assert historial.procesar_pagina_pull(contexto, [invalido]) == (0, 0)
    assert contexto.almacen.leer_cursor_seq() == 1
    assert contexto.almacen.contar_mensajes() == 0


# --- #18 · Recuperación en push ------------------------------------------------------------


def test_en_push_recupera_con_since_0_al_arrancar(rapida, central, caplog):
    central.agregar("m1", lamport=2)
    central.agregar("m2", lamport=6, origin="g2")
    contexto = crear_contexto(dataclasses.replace(rapida, modo_recepcion="push"), central)
    with caplog.at_level(logging.INFO, logger="chat.eventos"):
        correr(historial.recuperar_al_arrancar, contexto)
    assert central.consultas == [{"since": "0", "limit": "1000"}]
    assert "HISTORIAL_RECUPERADO since=0 nuevos=2 duplicados=0 via=historial" in caplog.text
    assert "via=historial" in caplog.text


def test_cada_modo_solo_corre_su_tarea_de_recepcion(rapida, central):
    push = crear_contexto(dataclasses.replace(rapida, modo_recepcion="push"), central)
    assert correr(historial.recibir_por_pull, push) is None
    pull = crear_contexto(rapida, central)
    assert correr(historial.recuperar_al_arrancar, pull) is None
    assert central.consultas == []


# --- #17 · Heartbeat ---------------------------------------------------------------------


def test_heartbeat_marca_caido_y_al_volver_reanuda(rapida, central, caplog):
    contexto = crear_contexto(rapida, central)
    with contexto.almacen.transaccion() as tx:
        mensaje = Mensaje.nuevo(usuario="ana", grupo=rapida.grupo, lamport=tick(tx), body="x")
        tx.guardar_mensaje_si_no_existe(mensaje)
        tx.encolar_pendiente(mensaje.id, time.time() + 3600)  # reintento lejano
    central.salud = "sin conexión"

    async def caer_y_volver():
        while contexto.central_disponible.is_set():
            await asyncio.sleep(0.005)
        assert "CENTRAL_CAIDO fallos=3" in caplog.text
        central.salud = 200

    with caplog.at_level(logging.INFO, logger="chat.eventos"):
        correr_hasta(
            contexto,
            heartbeat.vigilar_central,
            lambda: contexto.central_disponible.is_set() and "CENTRAL_VOLVIO" in caplog.text,
            antes=caer_y_volver,
        )
    assert central.registros, "al volver se renueva el registro"
    assert contexto.almacen.pendientes_listos(time.time()), "al volver se adelantan los pendientes"
    assert central.consultas == [], "en pull no se pide since aparte"


def test_un_fallo_suelto_no_marca_caido(rapida, central):
    contexto = crear_contexto(rapida, central)
    respuestas = iter([500, 500, 200, 500, 500, 200])
    vistas: list[int] = []

    def salud(request):
        if request.url.path != "/health":
            return central(request)
        codigo = next(respuestas, 200)
        vistas.append(codigo)
        return httpx.Response(codigo)

    contexto = crear_contexto(rapida, salud)
    correr_hasta(contexto, heartbeat.vigilar_central, lambda: len(vistas) >= 6)
    assert contexto.central_disponible.is_set()


def test_en_push_al_volver_pide_since_el_ultimo_visto(config, central):
    contexto = crear_contexto(dataclasses.replace(config, modo_recepcion="push"), central)
    with contexto.almacen.transaccion() as tx:
        tx.guardar_mensaje_si_no_existe(
            Mensaje(id="viejo", from_="ana@g1", origin="g1", lamport=9, sent_at="", body="")
        )
    correr(heartbeat.al_volver, contexto)
    assert central.consultas == [{"since": "9", "limit": "1000"}]


def test_heartbeat_reiniciado_con_el_central_caido_lo_recupera(rapida, central):
    # _vigilar reinicia la tarea si falla; el estado caído no debe quedar pegado.
    contexto = crear_contexto(rapida, central)
    contexto.central_disponible.clear()
    correr_hasta(contexto, heartbeat.vigilar_central, contexto.central_disponible.is_set)
