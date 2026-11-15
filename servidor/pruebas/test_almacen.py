import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from chat.almacen import Almacen
from chat.modelo import Mensaje
from chat.principal import crear_app


def mensaje(id: str, lamport: int, origin: str = "g3", body: str = "hola") -> Mensaje:
    return Mensaje.model_validate(
        {"id": id, "from": f"ana@{origin}", "origin": origin, "lamport": lamport,
         "sent_at": "2026-11-14T19:00:00Z", "body": body}
    )


@pytest.fixture
def almacen(tmp_path) -> Almacen:
    almacen = Almacen(tmp_path / "datos" / "chat.db")
    almacen.inicializar()
    return almacen


# --- Esquema y persistencia ---------------------------------------------------------------

def test_inicializar_crea_la_carpeta_y_arranca_vacio(almacen):
    assert almacen.ruta.exists()
    assert almacen.leer_reloj() == 0
    assert almacen.contar_mensajes() == 0
    assert almacen.contar_pendientes() == 0
    assert almacen.ultimo_lamport_visto() == 0


def test_inicializar_dos_veces_no_borra_nada(almacen):
    almacen.crear_usuario("ana")
    with almacen.transaccion() as tx:
        tx.fijar_reloj(7)
    almacen.inicializar()
    assert almacen.listar_usuarios() == ["ana"]
    assert almacen.leer_reloj() == 7


def test_todo_sobrevive_a_reabrir_el_archivo(almacen):
    almacen.crear_usuario("ana")
    with almacen.transaccion() as tx:
        tx.guardar_mensaje_si_no_existe(mensaje("m1", 5))
        tx.encolar_pendiente("m1", proximo_intento=0)
        tx.fijar_reloj(5)
    otro = Almacen(almacen.ruta)  # como después de docker compose restart
    otro.inicializar()
    assert otro.listar_usuarios() == ["ana"]
    assert [m.id for m in otro.listar_historial()] == ["m1"]
    assert otro.leer_reloj() == 5
    assert otro.contar_pendientes() == 1


# --- Usuarios ----------------------------------------------------------------------------

def test_crear_usuario_dice_si_era_nuevo(almacen):
    assert almacen.crear_usuario("ana") is True
    assert almacen.crear_usuario("ana") is False
    assert almacen.existe_usuario("ana")
    assert not almacen.existe_usuario("beto")


def test_listar_usuarios_en_orden(almacen):
    for nombre in ("karen", "ana", "manuel"):
        almacen.crear_usuario(nombre)
    assert almacen.listar_usuarios() == ["ana", "karen", "manuel"]


def test_no_guarda_nombres_invalidos(almacen):
    with pytest.raises(ValueError):
        almacen.crear_usuario("Ana María")
    assert almacen.listar_usuarios() == []


# --- Deduplicación -----------------------------------------------------------------------

def test_guardar_el_mismo_id_dos_veces_solo_cuenta_la_primera(almacen):
    assert almacen.guardar_mensaje_si_no_existe(mensaje("m1", 1)) is True
    assert almacen.guardar_mensaje_si_no_existe(mensaje("m1", 1, body="otro")) is False
    historial = almacen.listar_historial()
    assert len(historial) == 1 and historial[0].body == "hola"


def test_la_deduplicacion_es_atomica_con_peticiones_a_la_vez(almacen):
    """Figura 3 del enunciado: el mismo id llega varias veces casi al mismo tiempo."""
    with ThreadPoolExecutor(max_workers=16) as hilos:
        resultados = list(hilos.map(lambda _: almacen.guardar_mensaje_si_no_existe(mensaje("m1", 1)), range(64)))
    assert resultados.count(True) == 1
    assert almacen.contar_mensajes() == 1


def test_guarda_el_mensaje_tal_como_llego(almacen):
    original = mensaje("m1", 42, origin="g5", body="¿Ya subieron el compose?")
    almacen.guardar_mensaje_si_no_existe(original)
    assert almacen.listar_historial() == [original]


# --- Orden -------------------------------------------------------------------------------

def test_el_historial_sale_ordenado_por_lamport_origin_e_id(almacen):
    for m in [mensaje("c", 2, "g5"), mensaje("a", 3, "g1"), mensaje("b", 2, "g1"),
              mensaje("d", 1, "g9"), mensaje("f", 2, "g5"), mensaje("e", 2, "g5")]:
        almacen.guardar_mensaje_si_no_existe(m)
    assert [m.id for m in almacen.listar_historial()] == ["d", "b", "c", "e", "f", "a"]


def test_con_limite_devuelve_los_ultimos_en_orden(almacen):
    for i in range(1, 11):
        almacen.guardar_mensaje_si_no_existe(mensaje(f"m{i}", i))
    assert [m.lamport for m in almacen.listar_historial(limite=3)] == [8, 9, 10]


def test_llegados_despues_de_usa_el_orden_de_llegada_y_no_el_lamport(almacen):
    almacen.guardar_mensaje_si_no_existe(mensaje("viejo", 50))
    (cursor, _), = almacen.listar_llegados_despues_de(0)
    # Llega tarde un mensaje concurrente con una marca MENOR (análisis, sección 6).
    almacen.guardar_mensaje_si_no_existe(mensaje("tardio", 3, "g5"))
    nuevos = almacen.listar_llegados_despues_de(cursor)
    assert [m.id for _, m in nuevos] == ["tardio"]
    assert nuevos[0][0] > cursor


def test_ultimo_lamport_visto_es_el_mayor_guardado(almacen):
    for i, lamport in enumerate([5, 90, 12]):
        almacen.guardar_mensaje_si_no_existe(mensaje(f"m{i}", lamport))
    assert almacen.ultimo_lamport_visto() == 90


# --- Reloj y transacciones ---------------------------------------------------------------

def test_el_reloj_nunca_retrocede(almacen):
    with almacen.transaccion() as tx:
        tx.fijar_reloj(10)
    with pytest.raises(ValueError, match="no puede retroceder"):
        with almacen.transaccion() as tx:
            tx.fijar_reloj(9)
    assert almacen.leer_reloj() == 10


def test_si_algo_falla_en_la_transaccion_no_queda_nada(almacen):
    with pytest.raises(RuntimeError):
        with almacen.transaccion() as tx:
            tx.guardar_mensaje_si_no_existe(mensaje("m1", 8))
            tx.fijar_reloj(9)
            raise RuntimeError("se cae a mitad de camino")
    assert almacen.contar_mensajes() == 0
    assert almacen.leer_reloj() == 0


def test_la_regla_de_recepcion_se_compone_dentro_de_una_transaccion(almacen):
    """Lo que hará federación (#12, #13): guardar y mover el reloj juntos."""
    def recibir(m: Mensaje) -> bool:
        with almacen.transaccion() as tx:
            nuevo = tx.guardar_mensaje_si_no_existe(m)
            if nuevo:
                tx.fijar_reloj(max(tx.leer_reloj(), m.lamport) + 1)
            return nuevo

    assert recibir(mensaje("m1", 42)) is True
    assert almacen.leer_reloj() == 43
    assert recibir(mensaje("m1", 42)) is False  # duplicado: sin efecto
    assert almacen.leer_reloj() == 43


# --- Pendientes --------------------------------------------------------------------------

def guardar_y_encolar(almacen, m: Mensaje, proximo: float) -> None:
    with almacen.transaccion() as tx:
        tx.guardar_mensaje_si_no_existe(m)
        tx.encolar_pendiente(m.id, proximo)


def test_pendientes_listos_respeta_la_hora_y_sale_en_orden_de_lamport(almacen):
    guardar_y_encolar(almacen, mensaje("tarde", 1), proximo=200)
    guardar_y_encolar(almacen, mensaje("b", 9), proximo=50)
    guardar_y_encolar(almacen, mensaje("a", 4), proximo=100)
    listos = almacen.pendientes_listos(ahora=100)
    assert [p.mensaje.id for p in listos] == ["a", "b"]
    assert listos[0].intentos == 0 and listos[0].proximo_intento == 100


def test_reprogramar_y_quitar_pendientes(almacen):
    guardar_y_encolar(almacen, mensaje("m1", 1), proximo=0)
    almacen.reprogramar_pendiente("m1", intentos=1, proximo_intento=500)
    assert almacen.pendientes_listos(ahora=100) == []
    (pendiente,) = almacen.pendientes_listos(ahora=500)
    assert pendiente.intentos == 1
    almacen.quitar_pendiente("m1")
    assert almacen.contar_pendientes() == 0
    assert almacen.contar_mensajes() == 1  # el mensaje sigue en el historial


def test_adelantar_pendientes_los_deja_listos_ya(almacen):
    guardar_y_encolar(almacen, mensaje("m1", 1), proximo=900)
    guardar_y_encolar(almacen, mensaje("m2", 2), proximo=50)
    assert almacen.adelantar_pendientes(ahora=100) == 1
    assert [p.mensaje.id for p in almacen.pendientes_listos(ahora=100)] == ["m1", "m2"]


def test_no_se_encola_un_mensaje_que_no_esta_guardado(almacen):
    with pytest.raises(sqlite3.IntegrityError):
        with almacen.transaccion() as tx:
            tx.encolar_pendiente("fantasma", proximo_intento=0)


# --- Integración con la aplicación -------------------------------------------------------

def test_la_aplicacion_abre_el_almacen_de_la_configuracion(config, caplog):
    import logging

    with caplog.at_level(logging.INFO, logger="chat.eventos"):
        with TestClient(crear_app(config, tareas=[])) as cliente:
            ctx = cliente.app.state.contexto
            assert str(ctx.almacen.ruta) == config.ruta_bd
            ctx.almacen.crear_usuario("ana")
    assert "ARRANQUE reloj=0 mensajes=0 pendientes=0" in caplog.records[0].getMessage()
    assert Almacen(config.ruta_bd).listar_usuarios() == ["ana"]
