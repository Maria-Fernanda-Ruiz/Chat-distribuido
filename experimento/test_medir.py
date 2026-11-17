"""Pruebas del conteo del experimento (canvas CD-006, operación 1)."""

from medir import contar

ETIQUETA = "exp-120000-5s-r1"


def textos(*numeros: int, etiqueta: str = ETIQUETA) -> list[str]:
    return [f"{etiqueta}-{n:04d}" for n in numeros]


def historial(*cuerpos: str) -> list[dict]:
    return [{"id": f"id-{i}", "body": c} for i, c in enumerate(cuerpos)]


def test_sin_perdidas_ni_duplicados():
    enviados = textos(1, 2, 3)
    r = contar(enviados, historial(*enviados), ETIQUETA)
    assert r == {"enviados": 3, "recibidos": 3, "perdidos": 0, "duplicados": 0, "en_orden": True}


def test_cuenta_un_perdido():
    r = contar(textos(1, 2, 3), historial(*textos(1, 3)), ETIQUETA)
    assert (r["recibidos"], r["perdidos"]) == (2, 1)


def test_el_mismo_texto_con_otro_id_es_duplicado():
    enviados = textos(1, 2)
    r = contar(enviados, historial(*enviados, enviados[1]), ETIQUETA)
    assert (r["recibidos"], r["duplicados"]) == (2, 1)


def test_ignora_mensajes_de_otras_corridas_y_de_personas():
    enviados = textos(1, 2)
    otros = textos(1, 2, 3, etiqueta="exp-120000-2s-r1") + ["hola a todos"]
    r = contar(enviados, historial(*otros, *enviados), ETIQUETA)
    assert r == {"enviados": 2, "recibidos": 2, "perdidos": 0, "duplicados": 0, "en_orden": True}


def test_detecta_orden_cambiado():
    enviados = textos(1, 2, 3)
    r = contar(enviados, historial(*textos(1, 3, 2)), ETIQUETA)
    assert r["en_orden"] is False


def test_no_confunde_r1_con_r10():
    enviados = textos(1)
    r = contar(enviados, historial(*enviados, *textos(1, etiqueta=ETIQUETA + "0")), ETIQUETA)
    assert (r["recibidos"], r["duplicados"]) == (1, 0)
