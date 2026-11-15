import re
import uuid

import pytest
from pydantic import ValidationError

from chat.modelo import LAMPORT_MAXIMO, Mensaje, direccion, es_nombre_valido

EJEMPLO = {  # el ejemplo de la sección 4 del enunciado
    "id": "6f1c2a9e-4b7d-4f0e-9a51-2c8e7d3b1f44",
    "from": "ana@g3",
    "origin": "g3",
    "lamport": 42,
    "sent_at": "2026-11-10T14:03:22Z",
    "body": "¿Ya subieron el compose?",
}


def test_lee_el_ejemplo_del_enunciado_y_lo_devuelve_igual():
    mensaje = Mensaje.model_validate(EJEMPLO)
    assert mensaje.from_ == "ana@g3"
    assert mensaje.a_json() == EJEMPLO


def test_ignora_campos_desconocidos_sin_error():
    mensaje = Mensaje.model_validate({**EJEMPLO, "room": "#general", "prioridad": 9})
    assert "room" not in mensaje.a_json()


def test_tambien_lee_desde_json_crudo():
    import json

    assert Mensaje.model_validate_json(json.dumps(EJEMPLO)).lamport == 42


@pytest.mark.parametrize("faltante", ["id", "from", "origin", "lamport"])
def test_exige_lo_necesario_para_deduplicar_ordenar_y_mostrar(faltante):
    datos = {k: v for k, v in EJEMPLO.items() if k != faltante}
    with pytest.raises(ValidationError):
        Mensaje.model_validate(datos)


def test_tolera_que_falten_sent_at_y_body():
    mensaje = Mensaje.model_validate({k: EJEMPLO[k] for k in ("id", "from", "origin", "lamport")})
    assert mensaje.sent_at == "" and mensaje.body == ""


def test_tolera_sent_at_en_otro_formato():
    assert Mensaje.model_validate({**EJEMPLO, "sent_at": "10/11/2026 9:03"}).sent_at


@pytest.mark.parametrize("lamport", ["abc", 42.5, -1, LAMPORT_MAXIMO + 1, None])
def test_rechaza_lamport_que_no_sirve_para_ordenar(lamport):
    with pytest.raises(ValidationError):
        Mensaje.model_validate({**EJEMPLO, "lamport": lamport})


def test_rechaza_id_vacio():
    with pytest.raises(ValidationError):
        Mensaje.model_validate({**EJEMPLO, "id": ""})


def test_es_inmutable():
    mensaje = Mensaje.model_validate(EJEMPLO)
    with pytest.raises(ValidationError):
        mensaje.lamport = 7


def test_nuevo_cumple_el_formato_al_pie_de_la_letra():
    mensaje = Mensaje.nuevo(usuario="ana", grupo="g3", lamport=43, body="hola")
    assert uuid.UUID(mensaje.id).version == 4
    assert mensaje.from_ == "ana@g3"
    assert mensaje.origin == "g3"
    assert mensaje.lamport == 43
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", mensaje.sent_at)
    assert set(mensaje.a_json()) == set(EJEMPLO)


def test_nuevo_genera_un_id_distinto_cada_vez():
    ids = {Mensaje.nuevo(usuario="ana", grupo="g3", lamport=1, body="x").id for _ in range(100)}
    assert len(ids) == 100


def test_nuevo_rechaza_nombres_de_usuario_invalidos():
    with pytest.raises(ValueError):
        Mensaje.nuevo(usuario="Ana María", grupo="g3", lamport=1, body="x")


@pytest.mark.parametrize("nombre", ["ana", "juan_p", "k-2", "x" * 20, "0"])
def test_nombres_validos(nombre):
    assert es_nombre_valido(nombre)


@pytest.mark.parametrize("nombre", ["", "Ana", "ana maria", "ana@g3", "x" * 21, "josé"])
def test_nombres_invalidos(nombre):
    assert not es_nombre_valido(nombre)


def test_direccion():
    assert direccion("ana", "g3") == "ana@g3"
