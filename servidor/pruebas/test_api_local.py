"""Pruebas de la API local (canvas CD-003)."""

import pytest
from fastapi.testclient import TestClient

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
