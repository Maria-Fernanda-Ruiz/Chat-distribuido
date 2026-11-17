# Bitácora de interoperabilidad

**La sesión del jueves 19 de noviembre se canceló.** En su lugar, el 17 de noviembre de
2026 conectamos nuestro servidor al central del curso (`https://dsp.cshire.io`) y
repetimos las dos pruebas del enunciado (sección 7) con lo que había en ese momento.
Usamos el nombre **g2** solo para la prueba, porque el número del grupo (P01) todavía no
está confirmado.

## Datos de la prueba

| Campo | Valor |
|---|---|
| Fecha | 2026-11-17, de 23:57 a 23:59 UTC |
| Nombre del servidor | `g2` (de prueba) |
| Central | `https://dsp.cshire.io`, especificación 1.0.0 |
| Modo de recepción | pull, cada 1,5 s (D27) |
| Equipo y red | Portátil con Docker Desktop, detrás de NAT, sin URL pública |
| Otros grupos conectados | Ninguno. `GET /servers` estaba vacío antes de registrarnos |

## Antes de conectarnos

- `GET /health` respondió `{"status": "ok", "spec_version": "1.0.0", "last_seq": 22}`.
- `GET /history?after_seq=0` respondió una lista vacía, aunque `last_seq` era 22: los
  mensajes de pruebas anteriores ya no estaban (es probable que el central se haya
  reiniciado y conserve solo el contador).

## Prueba 1 · Registro y envío

| Hora (UTC) | Qué hicimos | Qué pasó (log) | ¿Funcionó? |
|---|---|---|---|
| 23:57:16 | `docker compose up` con `GRUPO=g2` | `REGISTRADO modo=pull nuevo=true`. En `GET /servers` aparece `g2` con estado `up` | Sí |
| 23:57:32 | `prueba@g2` escribe en el cliente | `ENCOLADO` y, 0,38 s después, `ENVIADO intento=1`. El central le dio `seq` 23 | Sí |
| 23:57:33 | El pull trae de vuelta nuestro propio mensaje | `DUPLICADO_DESCARTADO via=pull`: el `id` ya estaba y no se guardó dos veces | Sí |

## Prueba 2 · Caída y recuperación

Como no había otro grupo que escribiera mientras estábamos apagados, pusimos 3 mensajes
directamente en el central (`POST /messages` con `origin` `g2`) con el servidor apagado.

| Paso | Hora (UTC) | Resultado |
|---|---|---|
| `docker compose kill servidor` | 23:57:53 | Servidor apagado de golpe |
| 3 mensajes al central | 23:57:53–23:57:55 | `seq` 24, 25 y 26, con `"duplicate": false` |
| `docker compose start servidor` | 23:58:00 | `ARRANQUE reloj=1 mensajes=1`: el volumen conservó el reloj y el mensaje anterior |
| Recuperación | 23:58:02 | `HISTORIAL_RECUPERADO after_seq=23 nuevos=3 duplicados=0`, 0,6 s después de arrancar |
| Reloj | 23:58:02 | Pasó de 1 a 14 (`max(local, recibido) + 1` con el último de marca 13) |

Los 4 mensajes quedaron en el historial local, en orden y sin repetidos.

## Script de conformidad

Corrimos el script del curso contra el servidor `g2` mientras estaba conectado al central
real: **9 de 9 casos, veredicto CONFORME**. La salida está en
[`conformidad.txt`](conformidad.txt).

## Fallas encontradas

No hubo fallas propias. Lo único raro fue del lado del central: `last_seq` era 22 con el
historial vacío. No nos afecta, porque pedimos por `after_seq` y el cursor empieza en 0.

## Hallazgos para el póster

1. El servidor funciona con el central real sin URL pública, gracias al modo pull.
2. Después de una caída recupera lo que se perdió apenas arranca (0,6 s), sin duplicados:
   lo mismo que midió el experimento en local.
3. No se pudo probar con otros grupos: no había ninguno conectado y la sesión se canceló.
