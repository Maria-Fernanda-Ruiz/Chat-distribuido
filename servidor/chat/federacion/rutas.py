"""Endpoints de federación que llama el central (Karen, #13).

Aquí va POST /fed/messages (análisis, sección 4):

- `id` nuevo: guardar y aplicar la regla de Lamport de recepción en la misma
  transacción, responder 200 y registrar RECIBIDO;
- `id` ya conocido: no hacer nada, responder 200 y registrar DUPLICADO_DESCARTADO;
- campos desconocidos: se ignoran sin error.

Antes de programar: el canvas CD-004, sobre los contratos de CD-002.
"""

from fastapi import APIRouter

router = APIRouter(tags=["Federación (la llama el central)"])
