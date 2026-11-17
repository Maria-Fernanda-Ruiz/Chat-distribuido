# CD-005 · Presencia y recuperación

| Campo | Valor |
|---|---|
| ID | CD-005 |
| Historia | [CD-001 · historias HU1–HU12](../../requirements/CD-001-202611132125-[Story]-chat-distribuido.md) |
| Análisis | [CD-001 · protocolo y parámetros](../analysis/CD-001-202611141940-[Analysis]-protocolo-y-parametros.md) |
| Especificación | [v1.0.0 del central](https://github.com/javierchacon262/central-server-dsp/tree/main/especificacion), publicada el 2026-11-15 (cierra P07) |
| Estado | **Ajustado a la especificación v1.0.0 (D27, D28).** Borrador de Manuel (PR #40); el PM pidió el código en el mismo PR el 2026-11-16, así que aprobar el PR aprueba este canvas (D15) |
| Revisado por | Pendiente: visto bueno del PM y del equipo en el PR |
| Issues | #15, #16, #17 y #18. #19 (experimento) pasa a [CD-006](CD-006-202611171300-[Feat]-experimento-perdidas.md): D29 cierra P06 (nota del 2026-11-17) |

La primera versión de este canvas la escribió Manuel con el protocolo provisional. Con la
especificación publicada se ajustaron R, E, A, S, O y las salvaguardas 6 y 7; la parte del
experimento (#19) queda como estaba.

## R · Requirements (requisitos)

1. **#15 · `GET /fed/health`:** responde `200` con `{"server": GRUPO, "lamport": L}`,
   donde `L` es el reloj actual. Responde aunque el central esté caído; no hace llamadas
   de red ni escribe en la base. El script de conformidad lo usa en sus casos 1, 3, 5 y 7.
2. **#16 · Registro:** `POST /register` con `{"server", "mode"}`, y `url` si hay
   `URL_PUBLICA`, al arrancar y cada `REGISTRO_INTERVALO_S` (30 s). Si falla por red o
   `5xx`, se reintenta con el backoff de D10 sin tumbar el servidor. Un `4xx` queda en el
   log como `RECHAZADO_4XX` y se vuelve a intentar en la siguiente renovación.
3. **#17 · Heartbeat:** `GET /health` del central cada `HEARTBEAT_INTERVALO_S` (5 s);
   tras `HEARTBEAT_FALLOS_PARA_CAIDO` (3) fallos seguidos limpia
   `ctx.central_disponible` y registra `CENTRAL_CAIDO`. Con el primer `2xx` después de
   estar caído registra `CENTRAL_VOLVIO` y, en este orden, renueva el registro, recupera
   el historial (solo en push, ver 5), adelanta los pendientes y pone
   `ctx.central_disponible`.
4. **Recepción en pull (D27):** en el modo por defecto el servidor consulta
   `GET /history?after_seq=<cursor>&server=<GRUPO>` cada `PULL_INTERVALO_S` (1,5 s). Cada
   mensaje pasa por la **misma recepción** que `POST /fed/messages` (deduplicación por
   `id` y `max(L, lamport) + 1`), y el cursor `seq` avanza en la misma transacción. Una
   página llena (1000) se sigue pidiendo sin esperar.
5. **#18 · Recuperar historial:**
   - **En pull**, el cursor es la recuperación: al arrancar por primera vez vale 0 y
     trae todo; después de un reinicio o de una caída del central sigue donde quedó, sin
     perder los mensajes concurrentes que llegan tarde con una marca menor (lo que D16
     no podía evitar). La primera consulta completa después de arrancar o de volver el
     central registra `HISTORIAL_RECUPERADO`.
   - **En push**, como dice D16: al arrancar `GET /history?since=0`, y al volver el
     central `since` = último `lamport` visto. `since` es inclusivo en la especificación,
     así que los de la misma marca llegan y la deduplicación los descarta. Termina con
     `HISTORIAL_RECUPERADO` con `since`, `nuevos` y `duplicados`.
6. **#19 · Experimento:** igual que en la primera versión: procedimiento reproducible,
   al menos tres repeticiones, unidades, datos observados y script. No se incluyen
   resultados hasta medir. Sigue esperando P06.

## E · Entities (entidades)

- `Configuracion`: agrega `modo_recepcion` (`"pull"` por defecto o `"push"`,
  `MODO_RECEPCION`) y `pull_intervalo_s` (`PULL_INTERVALO_S`, 1,5 s). `url_publica` solo
  es obligatoria en push; en pull puede quedar vacía (D27).
- `Contexto`: sin cambios: `config`, `almacen`, `http` y `central_disponible`.
- `Almacen`: agrega a la tabla `estado` la clave `cursor_seq`, el último `seq` del
  central procesado en pull. Solo avanza.
- Recepción compartida: `federacion.reloj.recibir_mensaje(mensaje, tx)` guarda el
  mensaje si su `id` es nuevo y ajusta el reloj; devuelve el reloj nuevo o `None` si era
  duplicado. `registrar_recepcion(mensaje, reloj, via)` deja `RECIBIDO` o
  `DUPLICADO_DESCARTADO`. Las usan `/fed/messages` (`via=fed`), el pull (`via=pull`) y
  la recuperación por `since` (`via=historial`).
- Eventos: `REGISTRADO`, `CENTRAL_CAIDO`, `CENTRAL_VOLVIO`, `HISTORIAL_RECUPERADO`,
  `RECHAZADO_4XX` y `REINTENTO` (con `ruta=/register`), sin cuerpos de mensajes.
- Protocolo, según la especificación v1.0.0:
  - `POST /register` responde `200` con `{"server", "url", "mode", "new"}`; `400` si algo
    no cumple. El registro no vence; se renueva cada 30 s.
  - `GET /health` responde `200` con `{"status", "spec_version", "last_seq"}`.
  - `GET /history` responde una lista JSON; cada mensaje trae además `seq`. `since` es
    inclusivo; `after_seq` y `since` no se combinan; `limit` va de 1 a 1000.
- #19: mediciones observadas de pérdida durante caídas, junto al script y sus
  parámetros. No se fabrican datos ni se anticipan resultados.

## A · Approach (enfoque)

- **Pull por defecto (D27).** Los servidores corren en portátiles detrás de NAT y el
  central no puede llamarlos sin un túnel. Pull solo necesita salida a internet. Push
  queda disponible con `MODO_RECEPCION=push` y una `URL_PUBLICA` alcanzable (por ejemplo
  un túnel de cloudflared), y entonces `/fed/messages` recibe y el historial se recupera
  con `since` como en D16.
- **Una sola recepción.** El reloj y la deduplicación viven en `federacion.reloj`, la
  excepción de importación que ya permite CD-002. Presencia la usa; no copia la regla.
- `/fed/health` sigue siendo una lectura local y barata.
- Registro, heartbeat, pull y recuperación son tareas de `TAREAS_DE_FONDO`. Cada una
  revisa el modo al empezar: la que no corresponde termina enseguida. `_vigilar` las
  reinicia si fallan.
- El pull espera `ctx.central_disponible` antes de consultar: con el central caído no
  insiste, y el heartbeat decide cuándo volver, igual que el envío de pendientes.
- **P06 para #19 queda abierto**, con las alternativas que dejó Manuel: (a) pérdidas
  ante caída y recuperación del central, la recomendada; (b) latencia de detección y
  recuperación; (c) otro experimento que elija el PM.

## S · Structure (estructura)

- `servidor/chat/configuracion.py`: `MODO_RECEPCION` y `PULL_INTERVALO_S`; `URL_PUBLICA`
  obligatoria solo en push.
- `servidor/chat/almacen.py`: `cursor_seq` en `estado`, con `leer_cursor_seq` y
  `avanzar_cursor_seq`.
- `servidor/chat/federacion/reloj.py`: `recibir_mensaje` y `registrar_recepcion`.
  `federacion/rutas.py` pasa a usarlas, sin cambiar su comportamiento.
- `servidor/chat/presencia/rutas.py`: `/fed/health` con `lamport` (#15).
- `servidor/chat/presencia/registro.py`: `registrar_una_vez` y `mantener_registro` (#16).
- `servidor/chat/presencia/heartbeat.py`: `vigilar_central` (#17).
- `servidor/chat/presencia/historial.py`: `recibir_por_pull`, `recuperar_desde` y
  `recuperar_al_arrancar` (#18 y D27).
- `servidor/chat/principal.py`: las cuatro tareas en `TAREAS_DE_FONDO`.
- `docker-compose.local.yml`: el central oficial como servicio `central` (D28), y las dos
  instancias en pull contra él.
- #19: carpeta de experimento por definir tras cerrar P06.

## O · Operations (operaciones)

1. **Configuración:** `MODO_RECEPCION`, `PULL_INTERVALO_S` y `URL_PUBLICA` condicional,
   con pruebas de cada caso.
2. **Almacén:** `cursor_seq` que solo avanza, con pruebas.
3. **Recepción compartida:** extraer `recibir_mensaje` y `registrar_recepcion` de
   `/fed/messages`; las pruebas de federación siguen pasando sin cambios.
4. **#15:** `/fed/health` con el reloj; prueba de respuesta y de que refleja una
   recepción.
5. **#16:** registro inicial, renovación y reintento con backoff; pruebas con un central
   simulado en `httpx.MockTransport`: cuerpo en pull y en push, `REGISTRADO`, un `503`
   seguido de `200`.
6. **#17:** fallos seguidos, transición a caído, vuelta con registro, adelanto de
   pendientes y `central_disponible`; pruebas de caída y vuelta.
7. **Pull y #18:** recepción por cursor, página llena, cursor persistente entre
   reinicios, mensajes propios como duplicados, `HISTORIAL_RECUPERADO`; en push,
   `since=0` al arrancar. Pruebas de cada caso.
8. **Integración:** `docker compose -f docker-compose.local.yml up --build` con el central
   oficial y `gNa`, `gNb` en pull: un mensaje enviado en una aparece en la otra y en el
   panel del central. Luego el script de conformidad contra una instancia; su salida
   va a `entregables/` (#8).
9. **#19:** después de P06, como en la primera versión.

## N · Norms (normas)

- Código, API propia, commits y documentación en español; rutas y campos del protocolo
  como en la especificación (D13).
- No leer variables de entorno fuera de `configuracion.py` y `__main__.py` (D10).
- SQL solo en `almacen.py`; eventos con `eventos.registrar`; tareas de fondo sin
  excepciones que escapen; trabajo pequeño y explicable.
- Todo comando de ejecución corre en contenedores. No usar `docker compose down -v`.
- No afirmar que una prueba, medición, aprobación, revisión o publicación ocurrió si no
  se observó directamente.

## S · Safeguards (salvaguardas)

1. `/fed/health` nunca hace llamadas de red ni escribe en SQLite (CD-002, salvaguarda 7).
2. Mensaje, reloj y cursor se guardan en la misma transacción; el reloj nunca retrocede y
   el cursor tampoco.
3. Un central caído no impide que el servidor local arranque; las tareas no mueren por
   un fallo.
4. Las áreas no se importan entre sí, salvo `federacion.reloj` (CD-002).
5. No registrar el cuerpo de ningún mensaje.
6. El protocolo es el de la especificación v1.0.0. Lo que el central agrega y no
   usamos, como `seq` en push o `new` en el registro, se ignora sin error.
7. No cerrar P06 ni implementar #19 hasta que el PM elija el experimento.
8. No inventar ni extrapolar resultados: las mediciones del experimento solo se
   publican después de ser ejecutadas y registradas.
