"""API local: lo que usa nuestro cliente (Maria Fernanda, #20–#23).

La API entre el cliente y nuestro servidor es libre (enunciado, sección 2). Aquí van,
con el prefijo /api:

- crear y listar usuarios del grupo, sin contraseña y con el nombre validado por D12 (#20);
- enviar un mensaje a #general: el reloj sube, el mensaje se guarda y entra a
  pendientes en una sola transacción (análisis, sección 5) (#21);
- leer el historial de #general, ordenado por (lamport, origin) (#22);

y el cliente web mínimo servido por este mismo FastAPI (#23, D07).

Antes de programar: el canvas CD-003, sobre los contratos de CD-002.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["API local"])
