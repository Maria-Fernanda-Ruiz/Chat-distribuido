# Bitácora de la sesión de interoperabilidad

La sesión es el jueves 19 de noviembre de 2026, con el central del curso
(`https://dsp.cshire.io`). Esta bitácora se llena **durante la sesión**: qué funcionó, qué
falló y por qué, sea nuestro o de otro grupo. Una incompatibilidad bien explicada vale
tanto como una prueba que pasa (enunciado, sección 7).

## Antes de la sesión

- [ ] Número de grupo confirmado (P01) y escrito en `.env` como `GRUPO`.
- [ ] `docker compose up --build` con `URL_CENTRAL=https://dsp.cshire.io` y el modo pull
      por defecto (D27).
- [ ] En el log aparece `REGISTRADO`, y nuestro servidor sale en el panel del central.
- [ ] Script de conformidad contra nuestro servidor con el nombre real; salida guardada
      en `entregables/conformidad.txt`.
- [ ] Cliente web abierto en <http://localhost:8000/>, con un usuario creado.
- [ ] Una terminal con `docker compose logs -f servidor`, para anotar los eventos.

## Datos de la sesión

| Campo | Valor |
|---|---|
| Fecha y hora | |
| Nuestro grupo | |
| Equipo y red | (portátil de quién, wifi de la sala o datos) |
| Modo de recepción | pull |
| Grupos conectados | |

## Prueba 1 · Conversación global

Cada grupo escribe en `#general` y todos deben ver los mensajes de todos, en el mismo
orden.

| Hora | Qué hicimos | Qué esperábamos | Qué pasó | ¿Funcionó? |
|---|---|---|---|---|
| | | | | |

Para comparar el orden con otro grupo: los dos miran el mismo tramo de mensajes y
comparan los números de Lamport y los autores.

## Prueba 2 · Caída y recuperación

Por turnos, un grupo apaga su servidor mientras los demás escriben. Al volver debe
recuperar lo perdido, sin duplicados.

**Nuestro turno:**

1. Anotar la hora y el último número de Lamport que se ve en el cliente.
2. `docker compose kill servidor`.
3. Esperar a que los otros grupos escriban (unos 30 s) y anotar cuántos mensajes
   mandaron, si lo dicen.
4. `docker compose start servidor` y anotar la hora.
5. En el log, buscar `HISTORIAL_RECUPERADO` con `nuevos` y `duplicados`.
6. Comparar el cliente con el panel del central: ¿están todos los mensajes?

| Hora de la caída | Duración (s) | Mensajes que llegaron después (`nuevos`) | Duplicados | ¿Faltó alguno? |
|---|---|---|---|---|
| | | | | |

**Cuando se cae otro grupo:**

| Grupo | Hora | ¿Recuperó lo que se perdió? | ¿Vimos duplicados de ellos? | Notas |
|---|---|---|---|---|
| | | | | |

## Fallas encontradas

Una fila por problema: el nuestro o el de otro grupo. Lo importante es **por qué** pasó.

| Hora | Grupo | Qué se vio | Causa (o la mejor explicación) | ¿Se resolvió? Cómo |
|---|---|---|---|---|
| | | | | |

Cosas que conviene revisar si algo falla:

- **Mensajes rechazados (`RECHAZADO_4XX` en el log):** un campo que no cumple la
  especificación (`from`, `origin`, `lamport` o `sent_at`).
- **Orden distinto entre grupos:** alguien ordena por hora en vez de `(lamport, origin,
  id)`, o no ajusta su reloj al recibir.
- **Duplicados:** alguien cambia el `id` al reintentar.
- **Un grupo no recibe nada:** está en push detrás de NAT sin túnel (el central no puede
  llamarlo).

## Hallazgos para el póster

1.
2.
