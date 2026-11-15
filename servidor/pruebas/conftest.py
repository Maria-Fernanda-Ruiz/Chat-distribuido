"""Piezas comunes de las pruebas: una configuración válida y un cliente HTTP de prueba."""

import pytest
from fastapi.testclient import TestClient

from chat.configuracion import Configuracion
from chat.principal import crear_app


@pytest.fixture
def config(tmp_path) -> Configuracion:
    return Configuracion(
        grupo="gprueba",
        url_publica="http://gprueba:8000",
        url_central="http://central:9000",
        ruta_bd=str(tmp_path / "chat.db"),
    )


@pytest.fixture
def cliente(config):
    """La aplicación sin tareas de fondo; el `with` corre el arranque y la parada."""
    with TestClient(crear_app(config, tareas=[])) as cliente:
        yield cliente
