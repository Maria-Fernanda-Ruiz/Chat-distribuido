
import pytest

from chat.almacen import Almacen
from chat.federacion.reloj import recibir, tick


@pytest.fixture
def almacen(tmp_path) -> Almacen:
    """Crea una base de datos temporal para las pruebas."""
    almacen = Almacen(tmp_path / "datos" / "chat.db")
    almacen.inicializar()
    return almacen


# --- Incremento del reloj ------------------------------------------------


def test_tick_incrementa_el_reloj_con_transaccion(almacen):
    with almacen.transaccion() as tx:
        resultado = tick(tx)

    assert resultado == 1
    assert almacen.leer_reloj() == 1


def test_tick_incrementa_el_reloj_sin_transaccion(almacen):
    assert tick(almacen=almacen) == 1
    assert tick(almacen=almacen) == 2
    assert almacen.leer_reloj() == 2


# --- Recepción de mensajes -----------------------------------------------


def test_recibir_mensaje_con_lamport_mayor(almacen):
    with almacen.transaccion() as tx:
        resultado = recibir(42, tx)

    assert resultado == 43
    assert almacen.leer_reloj() == 43


def test_recibir_mensaje_con_lamport_menor(almacen):
    with almacen.transaccion() as tx:
        tx.fijar_reloj(50)

    with almacen.transaccion() as tx:
        resultado = recibir(20, tx)

    assert resultado == 51
    assert almacen.leer_reloj() == 51


def test_recibir_mensaje_sin_transaccion(almacen):
    resultado = recibir(42, almacen=almacen)

    assert resultado == 43
    assert almacen.leer_reloj() == 43


# --- Persistencia --------------------------------------------------------


def test_el_reloj_persiste_al_reabrir_el_almacen(almacen):
    with almacen.transaccion() as tx:
        tick(tx)

    otro_almacen = Almacen(almacen.ruta)
    otro_almacen.inicializar()

    assert otro_almacen.leer_reloj() == 1


# --- Transacciones -------------------------------------------------------


def test_tick_reutiliza_la_transaccion_y_confirma_sus_cambios(almacen):
    with almacen.transaccion() as tx:
        resultado = tick(tx)
        tx.fijar_reloj(resultado + 1)

    assert almacen.leer_reloj() == 2


def test_si_falla_la_transaccion_el_reloj_no_se_actualiza(almacen):
    with pytest.raises(RuntimeError):
        with almacen.transaccion() as tx:
            tick(tx)
            raise RuntimeError("Error de prueba")

    assert almacen.leer_reloj() == 0


# --- Salvaguardas --------------------------------------------------------


def test_no_se_puede_actualizar_sin_transaccion_ni_almacen():
    with pytest.raises(ValueError):
        tick()


def test_no_se_puede_recibir_sin_transaccion_ni_almacen():
    with pytest.raises(ValueError):
        recibir(42)
