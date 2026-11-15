
# CD-004 · Federación de mensajes: reloj de Lamport y envío

| Campo | Valor |
|---|---|
| ID | CD-004 |
| Historia | [Historias de usuario](../../requirements/) |
| Análisis | [Análisis del protocolo](../analysis/CD-001-202611141940-[Analysis]-protocolo-y-parametros.md) |
| Estado | Borrador |
| Revisado por | Karen Angelica Sandoval Martinez; pendiente de revisión del equipo |

## R · Requirements (requisitos)

El objetivo es implementar los mecanismos de federación necesarios para mantener la consistencia temporal de los mensajes y permitir su recepción y envío entre los servidores del chat distribuido.

El alcance comprende tres funcionalidades:

### Issue #12 · Reloj de Lamport

- El reloj debe persistir en SQLite y conservar su valor después de reiniciar el servidor.
- Al enviar un mensaje, el reloj debe incrementarse en una unidad: `L = L + 1`.
- Al recibir un mensaje nuevo, debe actualizarse mediante `L = max(L, lamport_recibido) + 1`.
- El reloj nunca debe retroceder.
- Las funciones del reloj deben poder reutilizar una transacción existente.

### Issue #13 · Recepción de mensajes

- El servidor debe exponer `POST /fed/messages` para recibir mensajes reenviados por el servidor central.
- Si el identificador del mensaje es nuevo, debe guardarse y actualizarse el reloj de Lamport.
- Si el identificador ya existe, el mensaje debe descartarse como duplicado, sin modificar el reloj.
- La persistencia del mensaje y la actualización del reloj deben ser atómicas.
- Los campos desconocidos del mensaje deben ignorarse, de acuerdo con el modelo existente.

### Issue #14 · Envío con reintentos

- El servidor debe tolerar la ausencia de respuesta y los errores HTTP `5xx` mediante reintentos.
- Los errores HTTP `4xx` no deben generar nuevos intentos.
- Todos los reintentos deben conservar el identificador original del mensaje.
- El mecanismo debe utilizar backoff exponencial, con espera inicial de 1 segundo, duplicación progresiva hasta 30 segundos y jitter.
- Los mensajes pendientes deben permanecer almacenados para reanudar su envío.

Los detalles del protocolo y los códigos de respuesta que dependan de la especificación OpenAPI quedan sujetos a su publicación y revisión (P07).


## E · Entities (entidades)

Las entidades y componentes que participan en la federación son:

### Mensaje

Representa la información que se recibe o se envía entre servidores.

Se utiliza el modelo `Mensaje`, definido en `servidor/chat/modelo.py`, que contiene los siguientes campos:

- `id`: identificador único del mensaje. Permite reconocer mensajes duplicados.
- `from`: usuario que originó el mensaje.
- `origin`: grupo de origen del mensaje.
- `lamport`: marca lógica del reloj del servidor que originó el mensaje.
- `sent_at`: fecha y hora asociada al mensaje.
- `body`: contenido del mensaje.

El modelo acepta campos desconocidos sin incorporarlos al objeto, según su configuración actual.

### Reloj de Lamport

Representa el contador lógico persistente del servidor.

- Se almacena en SQLite.
- Se incrementa antes de enviar un mensaje.
- Se actualiza al recibir un mensaje nuevo mediante `max(reloj_local, lamport_recibido) + 1`.
- No cambia cuando se recibe un mensaje duplicado.

### Transacción

Representa una unidad de trabajo sobre la base de datos SQLite.

La clase `Transaccion`, definida en `servidor/chat/almacen.py`, proporciona operaciones para leer y actualizar el reloj y guardar mensajes evitando duplicados.

Las operaciones relacionadas con un mismo mensaje deben reutilizar la transacción abierta para mantener su atomicidad.

### Almacén

Es el componente encargado de la persistencia.

La clase `Almacen`, definida en `servidor/chat/almacen.py`, administra la base de datos y permite abrir transacciones para ejecutar operaciones de forma controlada.

### Cola de mensajes pendientes

Representa los mensajes que todavía deben enviarse al servidor central.

Su persistencia permite reanudar los envíos después de interrupciones y conservar el identificador original de cada mensaje durante los reintentos.

### Servidor central

Es el componente externo que reenvía mensajes a nuestro servidor y recibe los mensajes que este envía.

La comunicación se realiza mediante los endpoints definidos por el protocolo del proyecto. Los detalles pendientes de confirmación se mantienen sujetos a P07.

## A · Approach (enfoque)

La federación de mensajes se implementará mediante módulos independientes que reutilizan el almacén y las operaciones transaccionales existentes.

### Issue #12 · Reloj de Lamport

Se utilizará un reloj lógico persistente en SQLite para mantener la continuidad del contador incluso después de reiniciar el servidor (D11).

Se implementarán dos operaciones:

- `tick()`: incrementa el reloj en una unidad antes del envío de un mensaje.
- `recibir(valor)`: actualiza el reloj mediante `max(reloj_local, valor) + 1` al recibir un mensaje nuevo.

Ambas operaciones podrán recibir una transacción existente mediante el parámetro `tx`. Cuando reciban una transacción, deberán reutilizarla en lugar de abrir otra. Si no reciben una, podrán abrir su propia transacción utilizando `Almacen` (D25).

### Issue #13 · Recepción de mensajes

La recepción se realizará mediante el endpoint `POST /fed/messages`.

Se utilizará la operación de persistencia que permite guardar un mensaje únicamente si su identificador todavía no existe.

La estrategia será:

1. Recibir y validar el mensaje mediante el modelo `Mensaje`.
2. Abrir una transacción SQLite.
3. Intentar guardar el mensaje.
4. Si es nuevo, actualizar el reloj de Lamport dentro de esa misma transacción.
5. Confirmar la transacción.
6. Registrar el evento correspondiente: `RECIBIDO` o `DUPLICADO_DESCARTADO`.

De esta manera, un mensaje duplicado no modifica el reloj ni vuelve a almacenarse.

### Issue #14 · Envío con reintentos

El envío utilizará la cola persistente de mensajes pendientes.

Se aplicará una estrategia de reintentos con backoff exponencial y jitter, siguiendo los parámetros acordados en D10.

- Los errores `5xx` y la ausencia de respuesta permitirán programar nuevos intentos.
- Los errores `4xx` no se reintentarán.
- El identificador original del mensaje se conservará durante todos los intentos.

Esta estrategia busca tolerar interrupciones de comunicación sin perder los mensajes pendientes (D10, D11 y D14).

## S · Structure (estructura)

La federación de mensajes se organiza dentro del paquete `servidor/chat/federacion/`, reutilizando los componentes compartidos del servidor.

### Archivos y responsabilidades

| Archivo | Responsabilidad |
|---|---|
| `servidor/chat/federacion/reloj.py` | Implementar las operaciones del reloj de Lamport: `tick()` y `recibir()`. |
| `servidor/chat/federacion/rutas.py` | Definir los endpoints de federación, incluida la recepción de mensajes mediante `POST /fed/messages`. |
| `servidor/chat/federacion/envio.py` | Gestionar el envío de mensajes al servidor central y los reintentos. |
| `servidor/chat/almacen.py` | Proporcionar persistencia SQLite, operaciones de reloj, almacenamiento de mensajes y gestión de pendientes. |
| `servidor/chat/modelo.py` | Definir el modelo `Mensaje` y validar los datos recibidos. |
| `servidor/chat/eventos.py` | Registrar los eventos relacionados con la recepción, los duplicados y los reintentos. |
| `servidor/chat/contexto.py` | Proporcionar acceso al almacén y a los componentes compartidos mediante `Contexto`. |
| `servidor/chat/principal.py` | Integrar el router de federación en la aplicación FastAPI. |

### Relaciones entre componentes

- Las rutas de federación reciben las solicitudes del servidor central.
- El modelo `Mensaje` valida los datos de entrada.
- Las rutas utilizan `Contexto` para acceder al `Almacen`.
- El `Almacen` proporciona transacciones para guardar mensajes y actualizar el reloj.
- El módulo `reloj.py` aplica las reglas de Lamport utilizando las transacciones existentes cuando corresponda.
- El módulo `envio.py` utiliza el almacén y la cola persistente para gestionar los mensajes pendientes.
- El módulo `eventos.py` registra los resultados de las operaciones.

### Persistencia y comunicación

SQLite es la base de datos compartida por las funcionalidades del servidor (D06 y D11).

La comunicación con los demás grupos se realiza a través del servidor central. Nuestro servidor no se comunica directamente con los servidores de otros grupos, de acuerdo con la arquitectura definida en D02 y D06.

## O · Operations (operaciones)

La implementación se divide en los siguientes pasos, respetando las dependencias entre módulos y las responsabilidades asignadas.

### 1. Implementar el reloj de Lamport

- **Archivo:** `servidor/chat/federacion/reloj.py`.
- **Responsable:** Karen.
- **Actividad:** implementar `tick()` y `recibir()` para incrementar y actualizar el reloj lógico. Ambas funciones deben reutilizar una transacción existente cuando reciban el parámetro `tx`.
- **Verificación:** ejecutar las pruebas unitarias del reloj y comprobar que los valores se incrementan correctamente y persisten en SQLite.

### 2. Implementar la recepción de mensajes

- **Archivo:** `servidor/chat/federacion/rutas.py`.
- **Responsable:** Karen.
- **Actividad:** implementar `POST /fed/messages`, validar el mensaje, descartar duplicados y actualizar el reloj dentro de la misma transacción cuando el mensaje sea nuevo.
- **Verificación:** probar la recepción de mensajes nuevos, duplicados, campos desconocidos y mensajes inválidos mediante pruebas automatizadas.

### 3. Implementar el envío con reintentos

- **Archivo:** `servidor/chat/federacion/envio.py`.
- **Responsable:** Karen.
- **Actividad:** implementar el envío al servidor central, la gestión de mensajes pendientes y los reintentos con backoff exponencial y jitter.
- **Verificación:** probar respuestas exitosas, errores HTTP `4xx`, errores HTTP `5xx`, ausencia de respuesta y conservación del identificador original.

### 4. Integrar y verificar las funcionalidades de federación

- **Archivos:** módulos de federación y pruebas correspondientes en `servidor/pruebas/`.
- **Responsable:** Karen.
- **Actividad:** comprobar que el reloj, la recepción y el envío utilizan correctamente las operaciones del almacén y respetan las reglas de atomicidad e idempotencia.
- **Verificación:** ejecutar las pruebas específicas de federación y la suite completa de pruebas del servidor.

### 5. Actualizar y sincronizar la documentación

- **Archivos:** `spdd/prompt/CD-004-202611151200-[Feat]-reloj-y-federacion.md` y `README.md`.
- **Responsable:** Karen, con revisión del PM.
- **Actividad:** mantener el canvas sincronizado con el comportamiento implementado y registrar las decisiones acordadas.
- **Verificación:** revisar que las siete secciones REASONS estén completas y que las decisiones citadas existan en el README.

## N · Norms (normas)

Las funcionalidades de federación deben respetar las convenciones generales establecidas para el proyecto.

### Convenciones de código

- El código, los nombres de las funciones propias, las variables y los comentarios deben mantenerse en español, siguiendo D13.
- Se conservarán los nombres de los campos del protocolo definidos por el servidor central, aunque estén en inglés.
- Las funciones del reloj serán `tick()` y `recibir()`.
- El parámetro utilizado para reutilizar una transacción existente será `tx`.

### Manejo de errores

- Los mensajes recibidos deben validarse mediante el modelo `Mensaje`.
- Los campos desconocidos se ignoran de acuerdo con la configuración del modelo.
- Los errores de validación deben manejarse mediante las respuestas de FastAPI.
- Los errores HTTP `4xx` del servidor central no deben generar reintentos.
- Los errores HTTP `5xx` y la ausencia de respuesta deben gestionarse mediante el mecanismo de reintentos.

Los detalles definitivos del protocolo quedan sujetos a la especificación OpenAPI (P07).

### Registro de eventos

Las funcionalidades deben utilizar la función compartida `registrar()` de `servidor/chat/eventos.py`.

Se deben registrar los eventos correspondientes a:

- Recepción de mensajes nuevos: `RECIBIDO`.
- Recepción de mensajes duplicados: `DUPLICADO_DESCARTADO`.
- Reintentos de envío: `REINTENTO`.
- Fallos definitivos de envío, cuando corresponda según el catálogo de eventos.

Los registros deben respetar el formato y las convenciones definidos en el análisis del proyecto.

### Convenciones de Git

- Utilizar una rama de trabajo por issue o funcionalidad.
- Aplicar Conventional Commits.
- Crear un Pull Request para revisión.
- Relacionar el Pull Request con su issue mediante `Closes #N`.
- No realizar push directamente a `main` (D14).

## S · Safeguards (salvaguardas)

Las siguientes condiciones deben cumplirse durante toda la ejecución del sistema de federación.

### 1. Atomicidad

La recepción de un mensaje nuevo y la actualización del reloj de Lamport deben realizarse dentro de la misma transacción SQLite.

Si alguna operación falla, los cambios deben revertirse mediante rollback.

### 2. Persistencia

El reloj de Lamport y los mensajes pendientes deben conservarse en SQLite para sobrevivir a los reinicios del servidor (D06 y D11).

### 3. Idempotencia

Un mensaje cuyo identificador ya existe no debe almacenarse nuevamente ni producir efectos adicionales.

La recepción de un duplicado no debe modificar el reloj de Lamport.

### 4. Identidad del mensaje

El identificador `id` debe conservarse durante todos los intentos de envío y reintentos.

Nunca se debe generar un identificador nuevo para reenviar el mismo mensaje.

### 5. Monotonía del reloj

El reloj de Lamport nunca debe disminuir.

Al recibir un mensaje nuevo, el valor actualizado debe ser `max(reloj_local, lamport_recibido) + 1`.

### 6. Reutilización de transacciones

Cuando `tick()` o `recibir()` reciban una transacción mediante el parámetro `tx`, deben utilizar esa misma transacción.

No deben abrir transacciones anidadas cuando ya existe una transacción abierta (D25).

### 7. Política de reintentos

Los errores HTTP `4xx` no deben generar reintentos.

Los errores HTTP `5xx` y la ausencia de respuesta deben permitir nuevos intentos, respetando los parámetros definidos en D10.

### 8. Verificación

Las pruebas deben comprobar:

- El incremento y la actualización correcta del reloj.
- La persistencia del reloj después de reiniciar el almacén.
- La recepción correcta de mensajes nuevos.
- El descarte de mensajes duplicados sin modificar el reloj.
- La atomicidad de las operaciones y el comportamiento del rollback.
- La conservación del identificador durante los reintentos.
- La diferenciación entre errores HTTP `4xx`, errores `5xx` y ausencia de respuesta.

Ningún cambio de comportamiento debe considerarse terminado sin sus pruebas correspondientes y la sincronización del canvas.
