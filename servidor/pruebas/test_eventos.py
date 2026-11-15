import io
import logging
import re

import pytest
from fastapi.testclient import TestClient

from chat.eventos import Evento, FormatoDeLinea, configurar_logging, registrar
from chat.modelo import Mensaje
from chat.principal import crear_app

MENSAJE = Mensaje.model_validate(
    {"id": "6f1c", "from": "ana@g3", "origin": "g3", "lamport": 42, "sent_at": "", "body": "hola"}
)


def test_estan_los_eventos_del_analisis():
    assert {e.value for e in Evento} == {
        "ARRANQUE", "PARADA", "ENCOLADO", "ENVIADO", "REINTENTO", "RECHAZADO_4XX", "RECIBIDO",
        "DUPLICADO_DESCARTADO", "REGISTRADO", "CENTRAL_CAIDO", "CENTRAL_VOLVIO",
        "HISTORIAL_RECUPERADO",
    }


def test_con_mensaje_la_linea_lleva_id_lamport_origin_y_from_en_ese_orden():
    linea = registrar(Evento.ENVIADO, MENSAJE, intento=1)
    assert linea == "ENVIADO id=6f1c lamport=42 origin=g3 from=ana@g3 intento=1"


def test_el_cuerpo_del_mensaje_no_va_al_log():
    assert "hola" not in registrar(Evento.RECIBIDO, MENSAJE, via="fed")


def test_formatea_los_valores():
    linea = registrar(
        Evento.REINTENTO, espera_s=1.23456, causa="sin conexión", vacio="", nada=None, ok=True
    )
    assert linea == 'REINTENTO espera_s=1.235 causa="sin conexión" vacio="" ok=true'


def test_las_advertencias_salen_con_nivel_warning(caplog):
    with caplog.at_level(logging.INFO, logger="chat.eventos"):
        registrar(Evento.CENTRAL_CAIDO, fallos=3)
        registrar(Evento.ENVIADO, MENSAJE, intento=1)
    assert [r.levelno for r in caplog.records] == [logging.WARNING, logging.INFO]


def test_la_linea_completa_lleva_hora_utc_con_milisegundos_y_grupo():
    registro = logging.LogRecord("chat.eventos", logging.INFO, "", 0, "ENVIADO id=1", None, None)
    linea = FormatoDeLinea("g3").format(registro)
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z g3 ENVIADO id=1", linea)


def test_los_errores_que_no_son_eventos_llevan_su_nivel():
    registro = logging.LogRecord("chat", logging.ERROR, "", 0, "falló algo", None, None)
    assert " g3 ERROR falló algo" in FormatoDeLinea("g3").format(registro)


@pytest.fixture
def logger_chat_restaurado():
    logger = logging.getLogger("chat")
    antes = (list(logger.handlers), logger.level, logger.propagate)
    yield
    logger.handlers[:] = antes[0]
    logger.setLevel(antes[1])
    logger.propagate = antes[2]


def test_configurar_logging_escribe_en_la_salida_estandar(logger_chat_restaurado, monkeypatch):
    salida = io.StringIO()
    monkeypatch.setattr("sys.stdout", salida)
    configurar_logging("g3")
    configurar_logging("g3")  # llamarla dos veces no duplica las líneas
    registrar(Evento.REGISTRADO, url="http://x:8000")
    lineas = salida.getvalue().splitlines()
    assert len(lineas) == 1
    assert lineas[0].endswith(" g3 REGISTRADO url=http://x:8000")


def test_el_servidor_registra_arranque_y_parada(config, caplog):
    with caplog.at_level(logging.INFO, logger="chat.eventos"):
        with TestClient(crear_app(config, tareas=[])):
            pass
    eventos = [r.getMessage().split()[0] for r in caplog.records]
    assert eventos == ["ARRANQUE", "PARADA"]
    assert "central=http://central:9000" in caplog.records[0].getMessage()
