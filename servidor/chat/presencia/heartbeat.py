"""Heartbeat al central y estado vivo o caído (Manuel, #17).

Aquí va una tarea de fondo que se agrega a TAREAS_DE_FONDO en principal.py
(análisis, sección 8):

- GET /health cada HEARTBEAT_INTERVALO_S;
- tras HEARTBEAT_FALLOS_PARA_CAIDO fallos seguidos: CENTRAL_CAIDO y
  `ctx.central_disponible.clear()`;
- con el primer 2xx después de estar caído: CENTRAL_VOLVIO, renovar el registro,
  recuperar el historial con since = último visto y `ctx.central_disponible.set()`.
"""
