"""Recuperación de historial con GET /history?since= (Manuel, #18).

Según D16 y el análisis (sección 6):

- al arrancar se pide since=0 y la deduplicación descarta lo que ya teníamos;
- al volver el central se pide since = último lamport visto (almacén);
- cada mensaje entra por la misma recepción que POST /fed/messages (deduplicación y
  reloj), y al final se registra HISTORIAL_RECUPERADO con los nuevos y los duplicados.
"""
