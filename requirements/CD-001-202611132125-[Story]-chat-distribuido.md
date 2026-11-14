# CD-001 · Historia: servidor de chat distribuido entre grupos

| Campo | Valor |
|---|---|
| ID | CD-001 |
| Tipo | Historia (paso 1 de SPDD) |
| Estado | Borrador, sin revisar por el equipo; pendientes P01–P14 abiertos |
| Fecha | 2026-11-13 |
| Fuente | [Enunciado «Proyecto final: chat distribuido entre grupos»](enunciado/enunciado.md), Sistemas Distribuidos, UIS ([PDF](enunciado/proyecto_final_v2.pdf)) |

## Problema

El curso pide que cada grupo construya un **servidor de chat en contenedores** que se
conecte al **servidor central del profesor**. Entre todos forman un único chat
distribuido en forma de estrella con una sola sala global, `#general`. Los servidores de
grupo no se hablan entre sí: todo pasa por el central.

Lo difícil no es el chat, sino que **interopere con implementaciones que no
controlamos** (las de los otros grupos y la del profesor) y que **siga siendo correcto
ante fallos**: mensajes que se pierden, respuestas que se pierden, el central caído o
nuestro propio servidor reiniciado. Para eso el enunciado pide reintentos con backoff,
deduplicación por `id`, relojes de Lamport, heartbeat y recuperación de historial.

El protocolo con el central **no se negocia**: lo fija la especificación OpenAPI del
profesor, que manda sobre el resumen del enunciado. Todavía no la tenemos en el repo
([P07](../README.md#decisiones-pendientes)), así que los criterios de aceptación de abajo
salen del resumen de la sección 4 y se ajustan cuando llegue.

Además del software se entregan un **experimento** con al menos 3 repeticiones, la
**bitácora de la sesión de interoperabilidad**, un **póster científico** y una
**sustentación** de 10 minutos.

## Historias

### HU1 · Levantar todo con un comando

Como docente quiero levantar el servidor del grupo con un solo comando en un equipo
limpio, para revisarlo sin instalar nada (requisito 1).

- `docker compose up` levanta el servidor, el almacenamiento y cualquier servicio
  auxiliar.
- La configuración se pasa por variables de entorno: nombre del grupo (`gN`), URL pública
  del servidor y URL del servidor central. Nada de eso está escrito en el código.
- Se pueden levantar dos instancias en la misma máquina con nombres distintos (`gNa`,
  `gNb`) para probar sin otros grupos (recomendación de la sección 10).
- Punto de control de la etapa 1: el compose levanta un servidor vacío que responde
  `GET /fed/health`.

### HU2 · Usuarios locales y persistencia

Como integrante del grupo quiero crear usuarios del grupo y que ellos y el historial
sobrevivan a un reinicio (requisitos 2 y 3).

- Se pueden crear usuarios del grupo; se escriben `usuario@gN`, por ejemplo `ana@g3`.
- Un usuario puede enviar y leer mensajes de `#general`.
- Usuarios e historial sobreviven a `docker compose restart`. El almacenamiento (SQLite en
  volumen, Redis con persistencia o PostgreSQL) está por decidir
  ([P04](../README.md#decisiones-pendientes)).
- Punto de control de la etapa 2: dos usuarios del grupo conversan localmente y el
  historial sobrevive a un reinicio.

### HU3 · Registrarse en el servidor central

Como servidor del grupo quiero registrarme en el central al arrancar y renovar el
registro, para que me reenvíe los mensajes (requisito 4).

- Al arrancar: `POST /register` con `{"server": "gN", "url": "<URL pública>"}`.
- El registro se renueva periódicamente; el intervalo está por decidir
  ([P09](../README.md#decisiones-pendientes)).
- La URL del central sale de la configuración (HU1).

### HU4 · Enviar y recibir mensajes de `#general`

Como usuario quiero que lo que escribo llegue a todos los grupos y ver lo que escriben
ellos (requisito 5).

- Al enviar, el servidor genera un `id` UUID nuevo y hace `POST /messages` al central con
  el formato de la sección 4: `id`, `from`, `origin`, `lamport`, `sent_at`, `body`.
- El servidor expone `POST /fed/messages` para recibir lo que reenvía el central, con el
  mismo `id` de origen.
- El servidor expone `GET /fed/health`, que responde con el nombre del servidor y su reloj
  de Lamport actual.
- Los campos desconocidos se ignoran sin error.
- Los códigos de respuesta exactos y los errores salen de la especificación
  ([P07](../README.md#decisiones-pendientes)).

### HU5 · Entrega al menos una vez, sin duplicados

Como usuario quiero que mis mensajes lleguen aunque falle la red, y nunca ver un mensaje
repetido (requisito 6, figura 3).

- Un envío al central que no recibe respuesta, o que recibe `5xx`, se reintenta con espera
  exponencial (backoff), **siempre con el mismo `id`**.
- Un `4xx` **no** se reintenta y queda en el log.
- Recibir en `POST /fed/messages` un `id` ya conocido responde **200 sin efectos**
  (idempotente).
- Reintentar nunca produce mensajes repetidos en pantalla.
- Base del backoff, máximo y número de intentos: por decidir
  ([P09](../README.md#decisiones-pendientes)).

### HU6 · Orden lógico con relojes de Lamport

Como usuario quiero ver `#general` en el mismo orden que los demás grupos, sin depender de
los relojes físicos (requisito 7).

- Antes de enviar, el servidor incrementa su reloj y pone el valor en `lamport`.
- Al recibir, el reloj pasa a `max(local, recibido) + 1`.
- El historial se muestra ordenado por `(lamport, origin)`.
- `sent_at` es solo informativo y nunca se usa para ordenar.
- Si el reloj se guarda o no para sobrevivir a un reinicio: por decidir
  ([P10](../README.md#decisiones-pendientes)).

### HU7 · Detectar que el central se cayó

Como servidor del grupo quiero saber si el central está caído, para guardar los mensajes y
mandarlos cuando vuelva (requisito 8).

- El servidor consulta `GET /health` del central periódicamente.
- Si no responde tras un número **configurable** de intentos, lo marca como caído.
- Mientras está caído, los mensajes de los usuarios se guardan como pendientes.
- Cuando vuelve, los pendientes se envían (con HU5).
- Intervalo y número de intentos: por decidir ([P09](../README.md#decisiones-pendientes)).

### HU8 · Recuperar lo que me perdí

Como servidor del grupo quiero ponerme al día después de arrancar o de una caída
(requisito 9).

- Al arrancar, y al volver de una caída, el servidor pide
  `GET /history?since={lamport}` al central.
- Lo recibido pasa por la misma deduplicación de HU5 y el mismo reloj de HU6.
- Qué valor de `since` se usa (el último `lamport` visto, guardado en el almacenamiento):
  se fija en el análisis.

### HU9 · Cliente sencillo

Como usuario quiero un cliente para escribir y leer `#general` y distinguir a los de otros
grupos (requisito 10).

- El cliente solo habla con nuestro servidor; esa API es libre.
- Distingue visualmente a los usuarios de otros grupos.
- Línea de comandos o página web mínima: por decidir
  ([P05](../README.md#decisiones-pendientes)).

### HU10 · Logs de eventos

Como equipo queremos ver en los logs todo lo que pasa, porque son la base del experimento
y de la demo (requisito 11, sección 10).

- Una línea legible por cada mensaje enviado, recibido, reintentado o descartado, con su
  `id` y su marca de Lamport.
- `docker compose logs` los muestra desde el arranque.
- El formato exacto se fija en el análisis o el canvas.

### HU11 · Experimento

Como equipo queremos medir el comportamiento del sistema ante fallos, para el póster
(sección 5).

- Una de las tres preguntas: pérdidas ante una caída, latencia de extremo a extremo o
  tiempo de recuperación ([P06](../README.md#decisiones-pendientes)).
- Hipótesis escrita antes de medir.
- Al menos 3 repeticiones, con el resultado de cada una.
- Gráfica o tabla con unidades.
- Script de medición y datos en el repo; los fallos se provocan con scripts
  (`docker kill`, `docker compose restart` o `tcpspy.py`), no a mano.
- Opcional, y suma: variar un parámetro (duración de la caída o tasa de envío).

### HU12 · Sesión de interoperabilidad

Como grupo queremos que nuestro servidor funcione con el de todos en la sesión de clase
(sección 7).

- Conversación global: todos ven los mensajes de todos, en el mismo orden.
- Caída y recuperación: apagamos nuestro servidor mientras los demás escriben; al volver
  recupera lo perdido sin duplicados.
- Bitácora de la sesión: qué funcionó, qué falló y por qué.
- Si la red no deja que el central nos llame, se usa el modo alternativo de la
  especificación ([P08](../README.md#decisiones-pendientes)).

## Definición de terminado (de la entrega)

1. Código del servidor y del cliente, con `docker-compose.yml` que funciona en un equipo
   limpio.
2. README con instrucciones de arranque, variables de entorno y decisiones de diseño.
3. Diagrama de arquitectura: contenedores, redes, volúmenes y conexión con el central.
4. Script de medición y datos del experimento.
5. Salida del script de conformidad completa.
6. Bitácora de la sesión de interoperabilidad.
7. Historial de commits con la participación de todos los integrantes.
8. Póster vertical (pliego o A1), también en PDF, con las 8 secciones de la sección 8.
9. Sustentación de máximo 10 minutos con demo de un fallo y su recuperación.

## Cómo se califica (para priorizar)

| Componente | Peso (%) | Historias |
|---|---|---|
| Mínimo común: conformidad, un comando, persistencia, reintentos, deduplicación, heartbeat | 40 | HU1–HU10 |
| Experimento | 15 | HU11 |
| Interoperabilidad | 15 | HU12 |
| Póster | 15 | HU11, HU12 (resultados y hallazgos) |
| Sustentación y demo | 15 | Todas; la demo usa HU7, HU8 y HU10 |

El mínimo común se verifica en buena parte con el **script de conformidad** del profesor,
así que conseguirlo pronto ([P07](../README.md#decisiones-pendientes)) es lo que más
reduce el riesgo.
