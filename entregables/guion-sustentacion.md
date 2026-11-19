# Guion de la sustentación

Son 10 minutos como máximo, frente al póster: el póster (pregunta, diseño y resultados),
una demo en vivo que provoca un fallo y muestra la recuperación, y las preguntas del
profesor, que pueden ir a cualquiera sobre cualquier parte (enunciado, sección 8).

Lo que se califica (15 %): que no pase de 10 minutos, que la demo muestre un fallo y su
recuperación, y que cualquier integrante responda sobre cualquier parte.

## Tiempos

| Tiempo | Quién | Qué se dice | Qué se muestra |
|---|---|---|---|
| 0:00–0:45 | Javier | «Somos el grupo 2: Maria Fernanda, Javier, Karen y Manuel. Hicimos un servidor de chat en contenedores que se conecta al servidor central del curso, para que todos los grupos conversen en una sola sala, `#general`.» | Título del póster |
| 0:45–2:00 | Javier | «El servidor es un solo contenedor con un volumen para SQLite. Al central solo salimos hacia afuera: cada 1,5 segundos le preguntamos si hay mensajes nuevos (pull), porque desde internet no se puede llegar a nuestros portátiles.» | Diagrama de arquitectura |
| 2:00–3:15 | Maria Fernanda | «El usuario escribe en el cliente web. El servidor sube el reloj, guarda el mensaje y lo deja en una cola de pendientes, las tres cosas de una vez: si algo falla, no queda nada a medias. Azul es nuestro grupo, amarillo los otros, y cada mensaje muestra su número de Lamport.» | El cliente web |
| 3:15–4:30 | Karen | «El reloj de Lamport ordena los mensajes sin depender de la hora de cada computador. Si el central no responde, el mensaje se reintenta con el mismo `id`, esperando cada vez más. Como cada mensaje tiene un `id` único, si llega dos veces se guarda una sola.» | Sección de método del póster |
| 4:30–7:30 | Maria Fernanda o Karen | La demo (abajo) | Dos navegadores y la terminal |
| 7:30–9:15 | Manuel | Experimento: pregunta, hipótesis, método y resultados (abajo) | Gráfica del póster |
| 9:15–10:00 | Javier | «La sesión con los otros grupos se canceló, así que probamos con el central real: nos registramos, enviamos y, después de apagar el servidor, recuperó lo que se perdió en 0,6 segundos sin duplicados. La conformidad dio 9 de 9.» Luego limitaciones y conclusión | Secciones de interoperabilidad y conclusiones |

## Demo: caída y recuperación (3 minutos)

**Antes de empezar** (ya construido, para no esperar en vivo):

```bash
docker compose -f docker-compose.local.yml up -d --build central servidor-a servidor-b
```

Abrir dos ventanas, una al lado de la otra: <http://localhost:8001> (g2a) y
<http://localhost:8002> (g2b). Agrandar la letra del navegador y de la terminal.

1. **Chat normal (30 s).** Crear `ana` en g2a y `beto` en g2b y mandar un par de
   mensajes. Llegan a los dos lados, en el mismo orden y con su número de Lamport.
2. **El fallo (30 s).** Apagar g2a de golpe:
   ```bash
   docker compose -f docker-compose.local.yml kill servidor-a
   ```
   La ventana de g2a muestra «Sin conexión». Desde g2b, `beto` escribe 3 mensajes.
3. **La recuperación (1 min).**
   ```bash
   docker compose -f docker-compose.local.yml start servidor-a
   ```
   Recargar g2a: aparecen los 3 mensajes que se perdió, sin repetidos y en orden, y los
   viejos siguen ahí porque estaban en el disco. Decir: «No se perdió nada y no hay
   duplicados.»
4. **Si alcanza el tiempo (1 min): se cae el central.**
   ```bash
   docker compose -f docker-compose.local.yml stop central
   ```
   `ana` escribe: el mensaje queda en pendientes. Luego:
   ```bash
   docker compose -f docker-compose.local.yml start central
   ```
   y el mensaje llega solo a g2b. Así se ven los reintentos.

Con el central real es lo mismo, con un solo servidor: `docker compose kill servidor`
y `docker compose start servidor` (así se hizo la prueba de la
[bitácora](bitacora-interoperabilidad.md)).

## Experimento (lo que dice Manuel)

- **Pregunta:** ¿cuántos mensajes se pierden o se duplican cuando nuestro servidor se
  cae unos segundos mientras otro grupo escribe?
- **Hipótesis:** ninguno, porque guardamos en disco el número del último mensaje que
  vimos (`seq`) y al volver pedimos desde ahí.
- **Método:** un script envía 5 mensajes por segundo desde g2b, apaga g2a de golpe con
  `docker kill` durante 2, 5 o 10 segundos y la vuelve a prender. Tres repeticiones de
  cada duración, nueve corridas en total.
- **Resultado:** 723 mensajes enviados, 264 de ellos con g2a apagada. **0 perdidos y
  0 duplicados** en las nueve corridas, todos en orden. g2a se puso al día en 0,5 a
  0,7 segundos después de prenderse
  ([datos](../experimento/resultados/resumen.md)).
- **Qué significa:** la recuperación no depende de cuánto dure la caída, sino de lo que
  tarda el servidor en arrancar.

## Preguntas que pueden hacer

| Pregunta | Respuesta corta |
|---|---|
| ¿Qué es un reloj de Lamport? | Un contador que sube con cada evento; al recibir un mensaje se toma `max(local, recibido) + 1`. Ordena causa y efecto sin depender de la hora del computador. |
| ¿Por qué no ordenan por la hora? | Cada computador tiene su propia hora y pueden estar desfasadas; `sent_at` solo se muestra. |
| ¿Cómo evitan los duplicados? | Cada mensaje tiene un `id` (UUID) que nunca cambia al reintentar, y la base tiene `UNIQUE(id)`: si llega dos veces, la segunda se descarta. |
| ¿Qué pasa si se cae el central? | El heartbeat lo detecta tras 3 fallos seguidos. Los mensajes quedan en pendientes en SQLite y se reintentan con espera creciente (1 s, 2 s, 4 s… hasta 30 s) y el mismo `id`. |
| ¿Qué pasa si se cae nuestro servidor? | Todo está en el volumen: usuarios, mensajes, reloj, pendientes y el cursor `seq`. Al arrancar sigue desde donde quedó. Es lo que mide el experimento. |
| ¿Por qué pull y no push? | Nuestros portátiles están detrás de NAT: el central no puede llamarnos sin un túnel. En pull solo salimos hacia afuera. Push sigue disponible con `MODO_RECEPCION=push`. |
| ¿Qué limitación tiene Lamport? | No distingue mensajes concurrentes: dos mensajes de grupos distintos pueden tener la misma marca. Se desempata por `origin` y luego por `id`, que es arbitrario pero igual en todos. |
| ¿Qué limitación tiene el cliente? | Pide lo nuevo por `lamport` (D19): un mensaje concurrente que llega tarde con una marca menor no aparece hasta recargar. Lo dejamos a propósito para mostrarlo; la mejora es pedir por orden de llegada. |
| ¿Por qué SQLite? | Un solo contenedor, y la deduplicación, el reloj y los pendientes se guardan en la misma transacción. |
| ¿Cómo lo levanto en otro equipo? | `git clone`, `cp .env.example .env` con el grupo y `docker compose up --build`. |

## Antes de grabar o presentar

- [ ] Los PR del experimento, el README y el póster están fusionados.
- [x] El número del grupo (2, D31) está en el póster y en `.env` (`GRUPO=g2`).
- [ ] Las imágenes ya están construidas (`up -d --build` antes de empezar).
- [ ] Cada uno ensayó su parte con cronómetro, contándola y no leyéndola.
- [ ] Dos ensayos completos de menos de 10 minutos.
- [ ] Para un video: grabar la demo sin cortes, para que se vea que es real.
