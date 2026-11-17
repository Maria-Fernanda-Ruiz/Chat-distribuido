# CD-005 · Presencia y recuperación

| Campo | Valor |
|---|---|
| ID | CD-005 |
| Historia | [CD-001 · historias HU1–HU12](../../requirements/CD-001-202611132125-[Story]-chat-distribuido.md) |
| Análisis | [CD-001 · protocolo y parámetros](../analysis/CD-001-202611141940-[Analysis]-protocolo-y-parametros.md) |
| Estado | **Borrador para revisión del equipo y aprobación del PM (D15)** |
| Revisado por | Pendiente |
| Issues | #15, #16, #17, #18 y #19 |

Este canvas se basa en el README, CD-001 de análisis, CD-002 de estructura, CD-004 y
el texto de trabajo compartido por Manuel. No se pudieron verificar los cuerpos,
criterios completos, dependencias ni estados actuales de los issues en GitHub. El
protocolo del central sigue **provisional** hasta recibir y revisar P07.

## R · Requirements (requisitos)

Los criterios siguientes son la síntesis disponible localmente; deben cotejarse con
cada issue antes de implementar.

1. **#15 · `GET /fed/health`:** responde `200` con `server` y el reloj Lamport actual.
   Responde aunque el central esté caído; no hace llamadas de red ni escribe en la base.
2. **#16 · Registro:** envía `POST /register` al arrancar y renueva cada
   `REGISTRO_INTERVALO_S`. Un error del central no impide el arranque. Aplica el
   backoff de D10 y registra los eventos acordados en el análisis.
3. **#17 · Heartbeat:** consulta `GET /health` cada `HEARTBEAT_INTERVALO_S`; tras
   `HEARTBEAT_FALLOS_PARA_CAIDO` fallos consecutivos cambia
   `ctx.central_disponible`, registra `CENTRAL_CAIDO` o `CENTRAL_VOLVIO` y, al volver,
   adelanta los pendientes mediante el almacén.
4. **#18 · Recuperar historial:** al arrancar pide `GET /history?since=0`; al volver el
   central usa `ultimo_lamport_visto()` (D16). Deduplica por `id`, actualiza mensaje y
   reloj dentro de la misma transacción, y registra `HISTORIAL_RECUPERADO`.
5. **#19 · Experimento:** producir un procedimiento reproducible para medir pérdidas
   ante una caída, con al menos tres repeticiones, unidades, datos observados y script.
   El script podrá provocar caídas de contenedores de forma automática. No se incluyen
   resultados hasta ejecutar mediciones reales. La selección del experimento sigue
   pendiente de acuerdo con el PM (P06).

## E · Entities (entidades)

- `Configuracion`: parámetros de D10 y direcciones configurables; no leer
  `os.environ` desde módulos de presencia.
- `Contexto`: `config`, `almacen`, cliente HTTP y `central_disponible` compartidos entre
  tareas y rutas.
- `Almacen` y `Transaccion`: reloj persistente, último Lamport visto, deduplicación,
  recepción atómica de mensajes y adelanto de pendientes (D06, D11, D16).
- Eventos: `REGISTRADO`, `CENTRAL_CAIDO`, `CENTRAL_VOLVIO` y
  `HISTORIAL_RECUPERADO`; registrar mediante `eventos.registrar`, sin cuerpos de
  mensajes.
- Protocolo provisional: `POST /register` con `server` y `url`; `GET /health`;
  `GET /history?since=...`; respuesta de `/fed/health` con `server` y `lamport`.
  Confirmar rutas y estructuras con P07 antes de cerrar el trabajo de protocolo.
- #19: mediciones observadas de pérdida durante caídas, junto al script y sus
  parámetros. No se fabrican datos ni se anticipan resultados.

## A · Approach (enfoque)

- Mantener la ruta de salud como lectura local y barata. El nombre y el reloj se leen
  del contexto y almacén (contrato de CD-002).
- Ejecutar registro, heartbeat y recuperación como tareas de fondo registradas en
  `TAREAS_DE_FONDO`, tolerantes a excepciones y con los intervalos/backoff de D10.
- Al recuperar historial, reutilizar el flujo existente de recepción para aplicar
  deduplicación y reglas Lamport en vez de crear una segunda ruta de persistencia
  (D06, D11, D16).
- **P06 para #19 queda abierto.** Alternativas para que Manuel y el PM decidan:
  (a) medir pérdidas ante caída y recuperación del central — recomendada en README y
  texto de trabajo; mide la función central de #16–#18;
  (b) medir latencia de detección y recuperación — cambia la métrica principal y el
  guion, sin responder directamente cuántos mensajes se pierden;
  (c) otro experimento elegido por el PM — requiere modificar requisitos, script y
  entregables. Ninguna alternativa queda adoptada hasta el acuerdo del PM; al decidir,
  actualizar P06, el log de decisiones y el estado del README según las reglas del repo.

## S · Structure (estructura)

- `servidor/chat/presencia/rutas.py`: completar la respuesta de `/fed/health` (#15).
- `servidor/chat/presencia/registro.py`: registro inicial y renovación (#16).
- `servidor/chat/presencia/heartbeat.py`: disponibilidad, transiciones y reanudación
  del envío pendiente (#17).
- `servidor/chat/presencia/historial.py`: descarga y recuperación (#18).
- `servidor/chat/principal.py`: agregar las tareas a `TAREAS_DE_FONDO` y conservar el
  ciclo de vida tolerante a fallos.
- `servidor/chat/almacen.py`: única ubicación de SQL; extender sus operaciones solo si
  el contrato existente no basta y acompañar cada extensión con pruebas.
- Recepción federada: reutilizar la operación existente expuesta por el módulo de
  federación/contexto; no importar módulos de otras áreas directamente, salvo el uso
  del reloj autorizado por las instrucciones del proyecto.
- #19: carpeta de experimento por definir tras cerrar P06; incluir script, instrucciones
  Docker y archivo de resultados vacíos o alimentados solo con mediciones reales.

## O · Operations (operaciones)

Cada issue se trabajará en una rama y PR independientes desde `main`, con Conventional
Commits y `Closes #N` (D14). Antes de programar: validar criterios y dependencias del
issue en GitHub, aprobación del PM a este canvas (D15) y revisión de P07 para el
protocolo.

1. **#15:** implementar la lectura del reloj en `rutas.py`; comprobar respuesta 200,
   contenido, disponibilidad sin central y que no haya red ni escrituras.
2. **#16:** implementar registro inicial, renovación y reintentos; conectar tarea en
   `principal.py`; comprobar éxito, indisponibilidad del central y backoff D10.
3. **#17:** implementar conteo de fallos consecutivos, transiciones del evento de
   disponibilidad y adelanto de pendientes; comprobar caída y recuperación.
4. **#18:** implementar recuperación al inicio y al volver el central, usando los
   valores `since` de D16; comprobar deduplicación y actualización transaccional del
   reloj.
5. **#19:** después de resolver P06 con el PM, escribir el protocolo y el script de
   medición; automatizar las caídas/reinicios de contenedores; definir al menos tres
   repeticiones; registrar unidades y datos reales. No reportar cifras hasta ejecutar
   el experimento.
6. Verificar cada cambio con las pruebas existentes dentro de contenedores cuando
   corresponda y documentar comandos y resultados realmente observados. Los diagramas
   Mermaid, si se agregan, deben validarse para GitHub.

## N · Norms (normas)

- Código, API propia, commits y documentación en español; nombres de ruta y campos del
  protocolo según la especificación oficial cuando esté disponible (D13).
- No leer variables de entorno fuera de `configuracion.py` y `__main__.py`; no fijar
  URLs, grupo o intervalos en el código (D10).
- SQL solo en `almacen.py`; eventos con `eventos.registrar`; tareas de fondo sin
  excepciones que escapen; trabajo pequeño y explicable.
- Todo comando de ejecución debe correr en contenedores. No usar
  `docker compose down -v`.
- No afirmar que una prueba, medición, aprobación, revisión o publicación ocurrió si
  no se observó directamente.

## S · Safeguards (salvaguardas)

1. `/fed/health` nunca hace llamadas de red ni escribe en SQLite (CD-002, Safeguard 7).
2. Mensajes, reloj y deduplicación mantienen la atomicidad definida por D11; el reloj
   nunca retrocede.
3. Un central caído no debe impedir que el servidor local arranque; fallos de tareas
   no deben terminarlas permanentemente.
4. No importar áreas directamente; pasar por `Contexto`, con la excepción de reloj
   especificada en las instrucciones del proyecto.
5. No registrar el cuerpo de ningún mensaje.
6. Todo contrato con el central continúa etiquetado **protocolo-provisional** hasta
   comprobarlo contra P07; no inventar campos ni rutas.
7. No generar código de presencia antes de la aprobación del PM. No cerrar P06 ni
   implementar #19 hasta que el PM elija el experimento.
8. No inventar ni extrapolar resultados: las mediciones del experimento solo se
   publican después de ser ejecutadas y registradas.
