"""Reloj de Lamport persistente (Karen, #12).

Aquí van las reglas del análisis (sección 5), escritas sobre una transacción del
almacén para que el reloj y el mensaje se guarden juntos:

- al enviar: L ← L + 1 y el mensaje sale con lamport = L;
- al recibir un mensaje nuevo: L ← max(L, recibido) + 1;
- al recibir un duplicado: nada.

El reloj nunca retrocede (D11). Lo usan también la API local, al enviar, y presencia,
al recuperar historial: hay un solo reloj.
"""
