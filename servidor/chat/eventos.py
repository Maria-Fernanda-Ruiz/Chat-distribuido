"""Log de eventos: una línea legible por cada cosa que pasa (análisis, sección 10; HU10).

Los logs son la base del experimento y de la demo, así que todas las áreas registran
igual:

    registrar(Evento.REINTENTO, mensaje, intento=2, espera_s=1.7, causa="timeout")

produce

    2026-11-14T19:40:05.210Z g3 REINTENTO id=6f1c… lamport=42 origin=g3 from=ana@g3 intento=2 espera_s=1.7 causa=timeout

Una persona lo lee sin herramientas y un script lo procesa con una expresión regular:
cada campo es `clave=valor`, y un valor con espacios va entre comillas.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from enum import StrEnum

from chat.modelo import Mensaje


class Evento(StrEnum):
    ARRANQUE = "ARRANQUE"
    PARADA = "PARADA"
    ENCOLADO = "ENCOLADO"
    ENVIADO = "ENVIADO"
    REINTENTO = "REINTENTO"
    RECHAZADO_4XX = "RECHAZADO_4XX"
    RECIBIDO = "RECIBIDO"
    DUPLICADO_DESCARTADO = "DUPLICADO_DESCARTADO"
    REGISTRADO = "REGISTRADO"
    CENTRAL_CAIDO = "CENTRAL_CAIDO"
    CENTRAL_VOLVIO = "CENTRAL_VOLVIO"
    HISTORIAL_RECUPERADO = "HISTORIAL_RECUPERADO"


# Se registran con nivel WARNING para que resalten; el formato de la línea es el mismo.
ADVERTENCIAS = frozenset({Evento.RECHAZADO_4XX, Evento.CENTRAL_CAIDO})

_log_eventos = logging.getLogger("chat.eventos")


def registrar(evento: Evento, mensaje: Mensaje | None = None, **detalles: object) -> str:
    """Registra un evento. Si hay mensaje, la línea lleva su `id`, `lamport`, `origin` y
    `from`; luego van los detalles en el orden en que se pasan. Devuelve la línea."""
    campos: dict[str, object] = {}
    if mensaje is not None:
        campos.update(
            {"id": mensaje.id, "lamport": mensaje.lamport, "origin": mensaje.origin, "from": mensaje.from_}
        )
    campos.update(detalles)
    partes = [str(evento)]
    partes += [f"{clave}={_formatear(valor)}" for clave, valor in campos.items() if valor is not None]
    linea = " ".join(partes)
    _log_eventos.log(logging.WARNING if evento in ADVERTENCIAS else logging.INFO, linea)
    return linea


def configurar_logging(grupo: str) -> None:
    """Manda los eventos y los errores del paquete `chat` a la salida estándar, una línea
    por evento con la hora UTC y el grupo delante. Se llama una vez, al arrancar."""
    logger = logging.getLogger("chat")
    for manejador in list(logger.handlers):
        logger.removeHandler(manejador)
    manejador = logging.StreamHandler(sys.stdout)
    manejador.setFormatter(FormatoDeLinea(grupo))
    logger.addHandler(manejador)
    logger.setLevel(logging.INFO)
    logger.propagate = False


class FormatoDeLinea(logging.Formatter):
    """`2026-11-14T19:40:05.210Z g3 <evento o nivel> …`"""

    def __init__(self, grupo: str) -> None:
        super().__init__()
        self.grupo = grupo

    def format(self, record: logging.LogRecord) -> str:
        instante = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
        texto = record.getMessage()
        if record.name != _log_eventos.name:
            # Un error del servidor, no un evento del protocolo: se marca con su nivel.
            texto = f"{record.levelname} {texto}"
        linea = f"{instante}.{int(record.msecs):03d}Z {self.grupo} {texto}"
        if record.exc_info:
            linea += "\n" + self.formatException(record.exc_info)
        return linea


def _formatear(valor: object) -> str:
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, float):
        return f"{round(valor, 3):g}"
    texto = str(valor)
    if texto == "" or any(c.isspace() or c in '="' for c in texto):
        return json.dumps(texto, ensure_ascii=False)
    return texto
