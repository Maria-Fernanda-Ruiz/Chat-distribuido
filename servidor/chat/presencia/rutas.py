"""Endpoint de presencia que llama el central: GET /fed/health.

La estructura (#3) deja la versión mínima, que solo responde con el nombre del servidor:
así el healthcheck del contenedor y el punto de control de la etapa 1 funcionan desde el
principio. Presencia (#15) agrega el reloj de Lamport actual (análisis, sección 4). Esta
ruta nunca hace llamadas de red ni escribe en la base (salvaguarda 7 de CD-002).
"""

from fastapi import APIRouter

from chat.contexto import ContextoDep

router = APIRouter(tags=["Federación (la llama el central)"])


@router.get("/fed/health")
def salud(ctx: ContextoDep) -> dict[str, object]:
    return {"server": ctx.config.grupo}
