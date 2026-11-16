"""Pruebas de la API local (canvas CD-003)."""

import logging
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from chat.almacen import Transaccion
from chat.modelo import Mensaje
from chat.principal import crear_app

# ---------------------------------------------------------------- usuarios (#20)


def test_crear_usuario_responde_201_con_su_direccion(cliente):
    respuesta = cliente.post("/api/usuarios", json={"nombre": "ana"})
    assert respuesta.status_code == 201
    assert respuesta.json() == {"nombre": "ana", "direccion": "ana@gprueba"}


@pytest.mark.parametrize(
    "nombre",
    ["Ana", "ana maria", "", "a" * 21, "ana@g3", "señor"],
    ids=["mayuscula", "espacio", "vacio", "21-caracteres", "arroba", "enie"],
)
def test_nombre_invalido_responde_422_con_mensaje_en_espanol(cliente, nombre):
    respuesta = cliente.post("/api/usuarios", json={"nombre": nombre})
    assert respuesta.status_code == 422
    assert "no es válido" in respuesta.json()["detail"]


def test_nombres_en_el_limite_de_d12_son_validos(cliente):
    for nombre in ["a", "x" * 20, "ana_maria-2"]:
        assert cliente.post("/api/usuarios", json={"nombre": nombre}).status_code == 201


def test_nombre_repetido_responde_409(cliente):
    cliente.post("/api/usuarios", json={"nombre": "ana"})
    respuesta = cliente.post("/api/usuarios", json={"nombre": "ana"})
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == "El usuario «ana» ya existe en gprueba"


def test_listar_usuarios_en_orden_alfabetico(cliente):
    assert cliente.get("/api/usuarios").json() == []
    for nombre in ["luis", "ana"]:
        cliente.post("/api/usuarios", json={"nombre": nombre})
    assert cliente.get("/api/usuarios").json() == [
        {"nombre": "ana", "direccion": "ana@gprueba"},
        {"nombre": "luis", "direccion": "luis@gprueba"},
    ]


def test_los_usuarios_sobreviven_a_un_reinicio(config):
    """Una app nueva sobre el mismo archivo de base es lo que pasa con `docker compose restart`."""
    with TestClient(crear_app(config, tareas=[])) as cliente:
        cliente.post("/api/usuarios", json={"nombre": "ana"})
    with TestClient(crear_app(config, tareas=[])) as cliente:
        assert cliente.get("/api/usuarios").json() == [{"nombre": "ana", "direccion": "ana@gprueba"}]


# ---------------------------------------------------------------- historial (#22)


def guardar(cliente, id: str, lamport: int, origin: str, sent_at: str = "2026-11-14T19:00:00Z"):
    """Guarda un mensaje directo en el almacén, como si hubiera llegado de ese grupo."""
    m = Mensaje.model_validate(
        {"id": id, "from": f"ana@{origin}", "origin": origin, "lamport": lamport,
         "sent_at": sent_at, "body": f"hola desde {origin}"}
    )
    cliente.app.state.contexto.almacen.guardar_mensaje_si_no_existe(m)


def ids(respuesta) -> list[str]:
    assert respuesta.status_code == 200
    return [m["id"] for m in respuesta.json()]


def test_historial_vacio(cliente):
    assert ids(cliente.get("/api/mensajes")) == []


def test_historial_ordenado_por_lamport_origin_propios_y_de_otros_grupos(cliente):
    guardar(cliente, "c", 2, "gprueba")
    guardar(cliente, "a", 3, "g1")
    guardar(cliente, "b", 2, "g1")
    guardar(cliente, "d", 1, "g9")
    assert ids(cliente.get("/api/mensajes")) == ["d", "b", "c", "a"]


def test_el_historial_trae_los_campos_del_protocolo_con_from(cliente):
    guardar(cliente, "x", 7, "g3")
    (m,) = cliente.get("/api/mensajes").json()
    assert m == {"id": "x", "from": "ana@g3", "origin": "g3", "lamport": 7,
                 "sent_at": "2026-11-14T19:00:00Z", "body": "hola desde g3"}


def test_sent_at_nunca_se_usa_para_ordenar(cliente):
    # El de lamport menor tiene la hora física MÁS TARDE: igual sale primero.
    guardar(cliente, "temprano", 5, "g1", sent_at="2026-11-14T10:00:00Z")
    guardar(cliente, "tarde", 1, "g2", sent_at="2026-11-14T23:00:00Z")
    assert ids(cliente.get("/api/mensajes")) == ["tarde", "temprano"]


def test_desde_lamport_devuelve_solo_lo_posterior(cliente):
    for i in range(1, 6):
        guardar(cliente, f"m{i}", i, "g1")
    assert ids(cliente.get("/api/mensajes", params={"desde_lamport": 3})) == ["m4", "m5"]
    assert ids(cliente.get("/api/mensajes", params={"desde_lamport": 0})) == [
        "m1", "m2", "m3", "m4", "m5"]
    assert ids(cliente.get("/api/mensajes", params={"desde_lamport": 5})) == []


@pytest.mark.parametrize("valor", ["-1", "abc", "2.5", "", str(2**62 + 1)])
def test_desde_lamport_invalido_responde_422(cliente, valor):
    respuesta = cliente.get("/api/mensajes", params={"desde_lamport": valor})
    assert respuesta.status_code == 422
    assert "desde_lamport" in respuesta.json()["detail"]


def test_limitacion_d19_un_concurrente_tardio_no_sale_en_lo_nuevo(cliente):
    """Documenta la limitación a propósito de D19 (canvas CD-003, enfoque 5).

    El cliente ya mostró hasta lamport 50. Llega tarde un mensaje concurrente de otro
    grupo con marca 48: no aparece en la consulta incremental, solo al pedir todo."""
    guardar(cliente, "visto", 50, "g1")
    ultimo_mostrado = cliente.get("/api/mensajes").json()[-1]["lamport"]
    guardar(cliente, "tardio", 48, "g5")
    assert ids(cliente.get("/api/mensajes", params={"desde_lamport": ultimo_mostrado})) == []
    assert ids(cliente.get("/api/mensajes")) == ["tardio", "visto"]


def test_el_historial_sobrevive_a_un_reinicio(config):
    with TestClient(crear_app(config, tareas=[])) as cliente:
        guardar(cliente, "m1", 1, "g1")
    with TestClient(crear_app(config, tareas=[])) as cliente:
        assert ids(cliente.get("/api/mensajes")) == ["m1"]


# ---------------------------------------------------------------- enviar (#21)


def enviar(cliente, body: str = "hola", usuario: str = "ana"):
    return cliente.post("/api/mensajes", json={"usuario": usuario, "body": body})


@pytest.fixture
def con_ana(cliente):
    cliente.post("/api/usuarios", json={"nombre": "ana"})
    return cliente


def test_enviar_responde_201_con_el_mensaje_del_protocolo(con_ana):
    respuesta = enviar(con_ana, "hola #general")
    assert respuesta.status_code == 201
    m = respuesta.json()
    assert set(m) == {"id", "from", "origin", "lamport", "sent_at", "body"}
    assert uuid.UUID(m["id"])
    assert m["from"] == "ana@gprueba" and m["origin"] == "gprueba"
    assert m["lamport"] == 1 and m["body"] == "hola #general"
    assert m["sent_at"].endswith("Z")


def test_cada_envio_tiene_id_nuevo_y_lamport_mayor(con_ana):
    mensajes = [enviar(con_ana, f"m{i}").json() for i in range(3)]
    assert len({m["id"] for m in mensajes}) == 3
    assert [m["lamport"] for m in mensajes] == [1, 2, 3]


def test_el_lamport_sigue_despues_de_un_mensaje_recibido(con_ana):
    # Si llegó uno de otro grupo con marca 41 y el reloj quedó en 42, el nuestro sale con 43.
    with con_ana.app.state.contexto.almacen.transaccion() as tx:
        tx.fijar_reloj(42)
    assert enviar(con_ana).json()["lamport"] == 43


def test_el_servidor_ignora_id_lamport_origin_y_sent_at_del_cliente(con_ana):
    respuesta = con_ana.post("/api/mensajes", json={
        "usuario": "ana", "body": "hola", "id": "falso", "lamport": 999,
        "origin": "g9", "sent_at": "2000-01-01T00:00:00Z"})
    m = respuesta.json()
    assert m["id"] != "falso" and m["lamport"] == 1
    assert m["origin"] == "gprueba" and m["sent_at"] != "2000-01-01T00:00:00Z"


def test_usuario_que_no_existe_responde_404(cliente):
    respuesta = enviar(cliente, usuario="nadie")
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "El usuario «nadie» no existe en gprueba: créalo antes de escribir"
    assert cliente.get("/api/mensajes").json() == []


@pytest.mark.parametrize("body", ["", "   ", "\n\t ", "x" * 1001],
                         ids=["vacio", "espacios", "blancos", "1001-caracteres"])
def test_body_invalido_responde_422_y_no_guarda_nada(con_ana, body):
    respuesta = enviar(con_ana, body)
    assert respuesta.status_code == 422
    assert "no es válido" in respuesta.json()["detail"]
    almacen = con_ana.app.state.contexto.almacen
    assert almacen.contar_mensajes() == 0 and almacen.leer_reloj() == 0


def test_body_de_1000_caracteres_es_valido(con_ana):
    assert enviar(con_ana, "x" * 1000).status_code == 201


def test_el_mensaje_queda_en_el_historial_en_pendientes_y_en_el_reloj(con_ana):
    m = enviar(con_ana).json()
    almacen = con_ana.app.state.contexto.almacen
    assert con_ana.get("/api/mensajes").json() == [m]
    assert almacen.contar_pendientes() == 1
    (pendiente,) = almacen.pendientes_listos(ahora=time.time())
    assert pendiente.mensaje.id == m["id"]
    assert almacen.leer_reloj() == m["lamport"]


def test_si_falla_al_encolar_no_queda_nada(con_ana, monkeypatch):
    """Salvaguarda 3: reloj, mensaje y pendiente van juntos o no va ninguno."""
    def falla(*_args, **_kwargs):
        raise RuntimeError("se cae al encolar")

    monkeypatch.setattr(Transaccion, "encolar_pendiente", falla)
    with pytest.raises(RuntimeError):
        enviar(con_ana)
    almacen = con_ana.app.state.contexto.almacen
    assert almacen.leer_reloj() == 0
    assert almacen.contar_mensajes() == 0
    assert almacen.contar_pendientes() == 0


def test_enviar_registra_el_evento_encolado(con_ana, caplog):
    with caplog.at_level(logging.INFO, logger="chat.eventos"):
        m = enviar(con_ana).json()
    (linea,) = [r.getMessage() for r in caplog.records if r.getMessage().startswith("ENCOLADO")]
    assert f"id={m['id']}" in linea and "lamport=1" in linea


def test_lo_enviado_sobrevive_a_un_reinicio(config):
    with TestClient(crear_app(config, tareas=[])) as cliente:
        cliente.post("/api/usuarios", json={"nombre": "ana"})
        m = enviar(cliente).json()
    with TestClient(crear_app(config, tareas=[])) as cliente:
        assert cliente.get("/api/mensajes").json() == [m]
        assert enviar(cliente).json()["lamport"] == 2


# ---------------------------------------------------------------- cliente web (#23)


def test_la_raiz_sirve_el_cliente_web(cliente):
    respuesta = cliente.get("/")
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("text/html")
    assert "<title>Chat #general</title>" in respuesta.text


def test_el_cliente_nunca_usa_innerhtml_ni_librerias_externas(cliente):
    """Salvaguarda 6 y norma del cliente: textos con textContent y sin CDN."""
    html = cliente.get("/").text
    assert "innerHTML" not in html
    assert "http://" not in html and "https://" not in html


def test_el_cliente_usa_las_rutas_de_la_api_local(cliente):
    html = cliente.get("/").text
    for ruta in ["/api/usuarios", "/api/mensajes", "desde_lamport="]:
        assert ruta in html
