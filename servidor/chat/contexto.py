"""Lo que comparten las rutas y las tareas de fondo de todas las áreas (canvas CD-002, S).

Las áreas no se importan entre sí: lo que necesitan en común pasa por aquí. En una ruta
se pide con `ContextoDep`; una tarea de fondo lo recibe como argumento.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Annotated

import httpx
from fastapi import Depends, Request

from chat.configuracion import Configuracion


@dataclass
class Contexto:
    config: Configuracion
    # Cliente para hablar con el central: base_url = URL_CENTRAL y timeout = HTTP_TIMEOUT_S.
    # Se usa con rutas relativas: `await ctx.http.post("/messages", json=...)`.
    http: httpx.AsyncClient
    # Puesto = el central está vivo. Lo cambia presencia (#17) y lo espera federación
    # antes de enviar (#14): `await ctx.central_disponible.wait()`.
    central_disponible: asyncio.Event = field(default_factory=asyncio.Event)


def obtener_contexto(request: Request) -> Contexto:
    return request.app.state.contexto


ContextoDep = Annotated[Contexto, Depends(obtener_contexto)]
