"""Registro en el central y renovación periódica (Manuel, #16).

Aquí va una tarea de fondo que se agrega a TAREAS_DE_FONDO en principal.py:
POST /register con {"server": GRUPO, "url": URL_PUBLICA} al arrancar y cada
REGISTRO_INTERVALO_S. Si responde 2xx registra REGISTRADO; si responde 4xx,
RECHAZADO_4XX; un fallo de red se intenta de nuevo en la siguiente renovación
(análisis, sección 3).
"""
