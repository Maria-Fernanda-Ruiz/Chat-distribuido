import asyncio
import os

from fastapi.testclient import TestClient

from chat import __main__ as entrada
from chat import principal
from chat.principal import crear_app


def test_fed_health_responde_con_el_nombre_del_servidor(cliente):
    respuesta = cliente.get("/fed/health")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"server": "gprueba"}


def test_al_arrancar_el_central_se_supone_vivo(cliente):
    assert cliente.app.state.contexto.central_disponible.is_set()


def test_el_cliente_http_apunta_al_central(cliente, config):
    assert str(cliente.app.state.contexto.http.base_url) == config.url_central


def test_las_tareas_de_fondo_arrancan_y_se_cancelan_al_parar(config):
    eventos: list[str] = []

    async def tarea(ctx):
        eventos.append("arrancó")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            eventos.append("cancelada")
            raise

    with TestClient(crear_app(config, tareas=[tarea])):
        pass
    assert eventos == ["arrancó", "cancelada"]


def test_una_tarea_que_falla_se_reinicia(config, monkeypatch):
    monkeypatch.setattr(principal, "ESPERA_REINICIO_TAREA_S", 0.01)
    intentos: list[int] = []
    tercera = asyncio.Event()

    async def tarea_fragil(ctx):
        intentos.append(1)
        if len(intentos) < 3:
            raise RuntimeError("falla a propósito")
        tercera.set()

    async def esperar_tercera(ctx):
        await asyncio.wait_for(tercera.wait(), timeout=2)

    app = crear_app(config, tareas=[tarea_fragil])
    with TestClient(app) as cliente:
        cliente.portal.call(esperar_tercera, None)
    assert len(intentos) == 3


def test_sin_configuracion_main_sale_con_codigo_2_y_explica(monkeypatch, capsys):
    for nombre in ("GRUPO", "URL_PUBLICA", "URL_CENTRAL"):
        monkeypatch.delenv(nombre, raising=False)
    assert entrada.main() == 2
    error = capsys.readouterr().err
    assert "Falta GRUPO" in error and ".env.example" in error


def test_ningun_modulo_lee_os_environ_salvo_configuracion_y_main():
    raiz = os.path.dirname(principal.__file__)
    permitidos = {"configuracion.py", "__main__.py"}
    for carpeta, _, archivos in os.walk(raiz):
        for archivo in archivos:
            if archivo.endswith(".py") and archivo not in permitidos:
                with open(os.path.join(carpeta, archivo), encoding="utf-8") as f:
                    assert "os.environ" not in f.read(), archivo
