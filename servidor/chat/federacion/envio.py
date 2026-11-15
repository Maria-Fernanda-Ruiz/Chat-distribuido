"""Envío al central con reintentos y cola de pendientes (Karen, #14).

Aquí va una tarea de fondo que se agrega a TAREAS_DE_FONDO en principal.py
(análisis, sección 7):

- toma los pendientes listos en orden de lamport y hace POST /messages con el mismo id;
- 2xx: ENVIADO y se quita de pendientes; 4xx: RECHAZADO_4XX y se quita sin reintentar;
- 5xx, timeout o sin conexión: REINTENTO con backoff y jitter, sin límite de intentos
  (D10);
- con el central marcado caído no intenta nada: espera a `ctx.central_disponible`.
"""
