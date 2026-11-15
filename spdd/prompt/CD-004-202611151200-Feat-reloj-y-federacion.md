# CD-004 Â· FederaciÃ³n de mensajes: reloj de Lamport y envÃ­o

**Responsable:** Karen Angelica Sandoval Martinez
**Issues:** #12, #13 y #14
**Fecha:** 2026-11-15
**Estado:** Borrador para revisiÃ³n y aprobaciÃ³n del PM

---

## R â€” Requerimiento

Implementar los mecanismos necesarios para mantener la consistencia temporal de los mensajes y permitir su recepciÃ³n y envÃ­o entre servidores del chat distribuido.

El trabajo comprende:

- **Issue #12:** implementar un reloj de Lamport persistente.
- **Issue #13:** implementar el endpoint `POST /fed/messages` para recibir mensajes reenviados por el servidor central.
- **Issue #14:** implementar el envÃ­o de mensajes con reintentos cuando ocurran fallos de comunicaciÃ³n.

La implementaciÃ³n debe respetar las decisiones arquitectÃ³nicas del proyecto y las reglas de persistencia establecidas.

## E â€” Evidencia

El enunciado del proyecto establece las siguientes reglas:

- Antes de enviar un mensaje, el servidor incrementa su reloj de Lamport y adjunta el valor al mensaje.
- Al recibir un mensaje, actualiza el reloj mediante `max(reloj_local, lamport_recibido) + 1`.
- El identificador `id` del mensaje se conserva durante los reenvÃ­os y permite detectar duplicados.
- Recibir un mensaje cuyo identificador ya existe debe ser una operaciÃ³n idempotente.
- Los errores HTTP `5xx` y la ausencia de respuesta requieren reintentos.
- Los errores HTTP `4xx` no deben reintentarse.
- El reloj debe persistir en SQLite y sobrevivir a los reinicios.

El almacÃ©n ya proporciona operaciones para leer y actualizar el reloj, guardar mensajes evitando duplicados y gestionar mensajes pendientes.

## A â€” AnÃ¡lisis

### Issue #12 Â· Reloj de Lamport

El reloj debe ser persistente y compartido por las funcionalidades que necesitan ordenar eventos del servidor.

Las reglas de actualizaciÃ³n son:

- Al enviar: `L = L + 1`.
- Al recibir un mensaje nuevo: `L = max(L, recibido) + 1`.
- Al recibir un duplicado: el reloj no cambia.

El reloj se almacena en SQLite mediante las operaciones de `Transaccion`.

La actualizaciÃ³n debe realizarse dentro de la misma transacciÃ³n que las operaciones relacionadas con el mensaje, para evitar estados inconsistentes.

### Issue #13 Â· RecepciÃ³n de mensajes

El endpoint `POST /fed/messages` recibe los mensajes reenviados por el servidor central.

La recepciÃ³n debe:

1. Procesar el mensaje recibido.
2. Comprobar si su identificador ya existe.
3. Si es nuevo, guardarlo en el almacÃ©n.
4. Actualizar el reloj de Lamport.
5. Mantener la atomicidad de las operaciones.

Si el mensaje ya existe, no debe volver a guardarse ni producir efectos adicionales.

### Issue #14 Â· EnvÃ­o con reintentos

El envÃ­o debe tolerar fallos de comunicaciÃ³n con el servidor central.

Reglas:

- Ante ausencia de respuesta o error `5xx`, se programa un reintento.
- Ante error `4xx`, no se programa otro intento y se registra el fallo.
- Todos los reintentos deben conservar el mismo identificador `id`.
- El mecanismo utiliza backoff exponencial, con espera inicial de 1 segundo, duplicaciÃ³n progresiva hasta 30 segundos y jitter.
- Los mensajes pendientes deben permanecer almacenados para poder reanudar su envÃ­o.

## S â€” SoluciÃ³n propuesta

### Reloj de Lamport

Implementar las funciones `tick()` y `recibir()` en:

`servidor/chat/federacion/reloj.py`

Estas funciones permiten incrementar el reloj antes de enviar y actualizarlo al recibir mensajes.

El mÃ³dulo debe permitir trabajar con una transacciÃ³n existente o utilizar el almacÃ©n para abrir una transacciÃ³n cuando no exista una previamente.

### RecepciÃ³n

Implementar el endpoint `POST /fed/messages` en el mÃ³dulo de rutas de federaciÃ³n.

La operaciÃ³n de recepciÃ³n debe aprovechar las funciones existentes del almacÃ©n y realizar la deduplicaciÃ³n y actualizaciÃ³n del reloj de forma atÃ³mica.

### EnvÃ­o

Implementar la lÃ³gica de envÃ­o y reintentos en el mÃ³dulo de envÃ­o de federaciÃ³n.

El mecanismo debe conservar el identificador original del mensaje y utilizar la cola persistente de pendientes para gestionar los reintentos.

## O â€” Operaciones y responsabilidades

Los mÃ³dulos involucrados son:

- `servidor/chat/federacion/reloj.py`: reglas del reloj de Lamport.
- `servidor/chat/federacion/rutas.py`: endpoints de federaciÃ³n y recepciÃ³n.
- `servidor/chat/federacion/envio.py`: envÃ­o de mensajes y reintentos.
- `servidor/chat/almacen.py`: persistencia y operaciones transaccionales.

Las reglas de Lamport pertenecen al mÃ³dulo de federaciÃ³n, mientras que el almacÃ©n proporciona las operaciones necesarias para persistir los cambios.

Las funcionalidades deben reutilizar las operaciones existentes y evitar duplicar lÃ³gica de persistencia.

## N â€” No objetivos y lÃ­mites

- No modificar el formato del protocolo establecido por el profesor.
- No cambiar el identificador de un mensaje durante los reintentos.
- No utilizar `sent_at` para establecer el orden lÃ³gico de los mensajes.
- No actualizar el reloj cuando se recibe un mensaje duplicado.
- No abrir transacciones anidadas cuando ya existe una transacciÃ³n abierta.
- No duplicar las responsabilidades que ya pertenecen al almacÃ©n.

Los cÃ³digos de respuesta y detalles del protocolo deben ajustarse a la especificaciÃ³n OpenAPI del profesor cuando estÃ© disponible.

## S â€” Salvaguardas

1. **Atomicidad:** las operaciones relacionadas con el reloj y el mensaje deben ejecutarse dentro de una misma transacciÃ³n.
2. **Persistencia:** el reloj y los mensajes deben conservarse en SQLite.
3. **Idempotencia:** un mensaje duplicado no debe generar efectos adicionales.
4. **Identidad:** el `id` original debe mantenerse durante todos los reintentos.
5. **MonotonÃ­a:** el reloj de Lamport nunca debe retroceder.
6. **ReutilizaciÃ³n transaccional:** cuando una funciÃ³n recibe una transacciÃ³n existente, debe utilizarla en lugar de abrir otra.
7. **Pruebas:** verificar tanto los casos normales como los errores y las operaciones revertidas por rollback.

## DecisiÃ³n P16 Â· ReutilizaciÃ³n de transacciones

**DecisiÃ³n acordada entre Karen y Maria Fernanda:**

Cuando ya existe una transacciÃ³n SQLite abierta, siempre se debe pasar mediante el parÃ¡metro `tx`.

Por tanto:

- `tick(tx)` debe reutilizar la transacciÃ³n recibida.
- `recibir(valor, tx)` debe reutilizar la transacciÃ³n recibida.
- Ninguna de estas funciones debe abrir una transacciÃ³n adicional cuando ya recibiÃ³ una.
- Si no existe una transacciÃ³n abierta, las funciones pueden utilizar `Almacen` para abrir su propia transacciÃ³n.

Esta decisiÃ³n permite que las operaciones relacionadas con la recepciÃ³n o el envÃ­o del mensaje compartan una misma transacciÃ³n.

De esta manera, el reloj, el mensaje y el encolamiento de pendientes pueden mantenerse consistentes y sujetos a la misma confirmaciÃ³n o rollback.

**Resultado esperado:** evitar transacciones anidadas y garantizar la atomicidad de las operaciones relacionadas.

---

**Fin del documento CD-004.**
