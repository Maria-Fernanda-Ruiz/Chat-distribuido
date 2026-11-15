import pytest

from chat.configuracion import ErrorDeConfiguracion, cargar_configuracion

MINIMO = {
    "GRUPO": "g3",
    "URL_PUBLICA": "http://192.168.0.10:8000",
    "URL_CENTRAL": "http://central:9000",
}


def errores(entorno: dict[str, str]) -> list[str]:
    with pytest.raises(ErrorDeConfiguracion) as error:
        cargar_configuracion(entorno)
    return error.value.problemas


def test_faltan_las_tres_obligatorias_y_las_informa_todas_juntas():
    problemas = errores({})
    assert len(problemas) == 3
    assert any("Falta GRUPO" in p for p in problemas)
    assert any("Falta URL_PUBLICA" in p for p in problemas)
    assert any("Falta URL_CENTRAL" in p for p in problemas)


def test_una_variable_vacia_cuenta_como_no_definida():
    problemas = errores({**MINIMO, "GRUPO": "   "})
    assert problemas == ["Falta GRUPO: nombre de este servidor en el central, por ejemplo g3."]


def test_con_las_obligatorias_el_resto_toma_los_valores_de_d10():
    config = cargar_configuracion(MINIMO)
    assert config.grupo == "g3"
    assert config.heartbeat_intervalo_s == 5
    assert config.heartbeat_fallos_para_caido == 3
    assert config.registro_intervalo_s == 30
    assert config.backoff_base_s == 1
    assert config.backoff_max_s == 30
    assert config.http_timeout_s == 3
    assert config.ruta_bd == "/datos/chat.db"
    assert config.puerto == 8000
    assert config.log_accesos is False


def test_las_opcionales_vacias_toman_su_valor_por_defecto():
    config = cargar_configuracion({**MINIMO, "HEARTBEAT_INTERVALO_S": "", "PUERTO": ""})
    assert config.heartbeat_intervalo_s == 5
    assert config.puerto == 8000


def test_lee_las_opcionales():
    config = cargar_configuracion(
        {
            **MINIMO,
            "HEARTBEAT_INTERVALO_S": "2.5",
            "HEARTBEAT_FALLOS_PARA_CAIDO": "5",
            "BACKOFF_MAX_S": "10",
            "LOG_ACCESOS": "true",
        }
    )
    assert config.heartbeat_intervalo_s == 2.5
    assert config.heartbeat_fallos_para_caido == 5
    assert config.backoff_max_s == 10
    assert config.log_accesos is True


def test_quita_la_barra_final_de_las_urls():
    config = cargar_configuracion({**MINIMO, "URL_CENTRAL": "http://central:9000/"})
    assert config.url_central == "http://central:9000"


@pytest.mark.parametrize("url", ["central:9000", "ftp://central", "http://", "central"])
def test_rechaza_urls_sin_http(url):
    problemas = errores({**MINIMO, "URL_CENTRAL": url})
    assert "URL_CENTRAL debe ser una URL" in problemas[0]


@pytest.mark.parametrize("grupo", ["g 3", "ana@g3", "g3/", "x" * 21])
def test_rechaza_nombres_de_grupo_invalidos(grupo):
    assert "GRUPO solo admite" in errores({**MINIMO, "GRUPO": grupo})[0]


@pytest.mark.parametrize("valor", ["cero", "0", "-1", "inf", "nan"])
def test_los_segundos_deben_ser_numeros_positivos(valor):
    assert "HEARTBEAT_INTERVALO_S" in errores({**MINIMO, "HEARTBEAT_INTERVALO_S": valor})[0]


@pytest.mark.parametrize("valor", ["0", "2.5", "tres"])
def test_los_fallos_para_caido_son_un_entero_de_al_menos_1(valor):
    problemas = errores({**MINIMO, "HEARTBEAT_FALLOS_PARA_CAIDO": valor})
    assert "HEARTBEAT_FALLOS_PARA_CAIDO" in problemas[0]


def test_el_puerto_debe_estar_en_rango():
    assert "entre 1 y 65535" in errores({**MINIMO, "PUERTO": "70000"})[0]


def test_el_backoff_maximo_no_puede_ser_menor_que_la_base():
    problemas = errores({**MINIMO, "BACKOFF_BASE_S": "10", "BACKOFF_MAX_S": "5"})
    assert "BACKOFF_MAX_S (5) no puede ser menor que BACKOFF_BASE_S (10)" in problemas[0]


def test_log_accesos_solo_acepta_verdadero_o_falso():
    assert "LOG_ACCESOS" in errores({**MINIMO, "LOG_ACCESOS": "quizas"})[0]


def test_la_explicacion_dice_donde_se_corrige():
    with pytest.raises(ErrorDeConfiguracion) as error:
        cargar_configuracion({})
    texto = error.value.explicacion()
    assert texto.startswith("Configuración inválida; el servidor no arranca:")
    assert ".env.example" in texto
