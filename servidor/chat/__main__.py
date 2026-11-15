"""Punto de entrada del contenedor: `python -m chat`.

Lee la configuración y, si es válida, arranca uvicorn con la aplicación. Si no, explica
qué falta y sale con código 2, sin llegar a levantar la API.
"""

from __future__ import annotations

import os
import sys

import uvicorn

from chat.configuracion import ErrorDeConfiguracion, cargar_configuracion
from chat.eventos import configurar_logging
from chat.principal import crear_app


def main() -> int:
    try:
        config = cargar_configuracion(os.environ)
    except ErrorDeConfiguracion as error:
        print(error.explicacion(), file=sys.stderr)
        return 2
    configurar_logging(config.grupo)
    uvicorn.run(
        crear_app(config),
        host="0.0.0.0",
        port=config.puerto,
        access_log=config.log_accesos,
        # docker compose stop debe terminar en menos de 2 s (#4).
        timeout_graceful_shutdown=1,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
