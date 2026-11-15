"""Pruebas de la API local (canvas CD-003)."""

import pytest
from fastapi.testclient import TestClient

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
