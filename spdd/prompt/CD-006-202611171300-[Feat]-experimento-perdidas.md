# CD-006 · Experimento: pérdidas ante una caída

| Campo | Valor |
|---|---|
| ID | CD-006 |
| Historia | [CD-001 · HU11](../../requirements/CD-001-202611132125-[Story]-chat-distribuido.md#hu11--experimento) |
| Análisis | [CD-001 · protocolo y parámetros](../analysis/CD-001-202611141940-[Analysis]-protocolo-y-parametros.md) |
| Estado | Borrador. Maria Fernanda toma #19 por encargo del equipo; D29 cierra P06 y el PM la confirma al aprobar este canvas (D15, salvaguarda 7 de CD-005) |
| Revisado por | Pendiente: visto bueno del PM en el PR |
| Issues | #19 |

El sistema ya cumple «al menos una vez» con deduplicación: el central numera cada mensaje
con `seq`, y cada servidor guarda su cursor en SQLite en la misma transacción que el
mensaje (D27). El experimento comprueba con datos que eso aguanta una caída real.

## R · Requirements (requisitos)

1. **Pregunta (D29):** ¿cuántos mensajes se pierden o se duplican cuando el servidor
   `gNa` se cae durante unos segundos mientras `gNb` escribe en `#general`?
2. **Hipótesis, escrita antes de medir:** 0 mensajes perdidos y 0 duplicados en todas
   las corridas, sin importar cuánto dure la caída. El tiempo para ponerse al día
   después de prender `gNa` será de unos pocos segundos (lo que tarda en arrancar más un
   ciclo de pull, 1,5 s) y casi no crecerá con la duración de la caída.
3. **Diseño:** caídas de 2, 5 y 10 s, 3 repeticiones de cada una (9 corridas). En cada
   corrida `gNb` envía 5 mensajes por segundo: 5 s antes de la caída, durante la caída
   y 5 s después de prender `gNa`.
4. **Medidas por corrida:**
   - `enviados`: mensajes que `gNb` aceptó (`201`).
   - `enviados_en_caida`: los de ellos que se enviaron mientras `gNa` estaba apagada.
   - `recibidos`: mensajes distintos de la corrida que aparecen en el historial de `gNa`.
   - `perdidos` = `enviados` − `recibidos`.
   - `duplicados`: copias de más en `gNa` (el mismo texto con otro `id`; el mismo `id`
     no puede repetirse por `UNIQUE(id)`).
   - `en_orden`: si `gNa` muestra los mensajes de la corrida en el orden en que se
     enviaron.
   - `t_arranque_s`: desde `docker start` hasta que `/fed/health` de `gNa` responde.
   - `t_al_dia_s`: desde `docker start` hasta que `gNa` tiene todos los mensajes
     enviados durante la caída.
5. **Terminado cuando:**
   - un solo comando corre las 9 corridas sin pasos a mano, con las caídas provocadas
     por el script;
   - los datos quedan en `experimento/resultados/perdidas.csv`, una fila por corrida;
   - hay una gráfica con unidades (`experimento/resultados/grafica.png`) y una tabla
     resumen (`experimento/resultados/resumen.md`) lista para el póster;
   - si una corrida no se pone al día en 60 s, se anota con lo que faltó y se sigue: no
     se repite para «arreglar» el dato.

## E · Entities (entidades)

- **Corrida:** `duracion_s`, `repeticion`, `etiqueta`
  (`exp-<hhmmss>-<duracion>s-r<repeticion>`, con la hora en que empezó la ejecución
  para no confundirse con mensajes de una ejecución anterior) y las medidas de R4.
- **Mensaje de prueba:** lo envía el usuario `medidor` de `gNb` por la API local
  (`POST /api/mensajes`), con el texto `<etiqueta>-<n>` y `n` de 0001 en adelante. El
  texto permite contar en `gNa` sin depender del `id`.
- **Fila del CSV:** `duracion_s, repeticion, enviados, enviados_en_caida, recibidos,
  perdidos, duplicados, en_orden, t_arranque_s, t_al_dia_s`, con los tiempos en segundos
  y dos decimales.

## A · Approach (enfoque)

- **Se apaga `gNa` y escribe `gNb` (D29).** Así se mide justo la recuperación de
  #18 y D27: mientras `gNa` está apagada, sus mensajes se acumulan en el central, y al
  volver debe traerlos con el cursor `seq`.
- **`docker kill` (D29):** apaga de golpe, sin cerrar la base. Es lo más parecido a que
  se vaya la luz.
- **Se cuenta por el texto, no por el `id`.** Un reintento que cambiara el `id`
  produciría dos mensajes con el mismo texto; contar por texto detecta ese error.
- **Se usa la API local de `gNb` y el historial de `gNa`**, lo mismo que usa el cliente
  web, sin tocar el código del servidor.
- **El script corre en un contenedor** (regla 8 de `AGENTS.md`), con el socket de
  Docker montado para poder apagar y prender `gNa`. No hace falta instalar Python en
  el equipo.
- **Solo librería estándar para medir;** matplotlib solo para la gráfica.

## S · Structure (estructura)

- `experimento/medir.py`: corre las corridas y escribe el CSV. Su función
  `contar(enviados, historial, etiqueta)` no usa la red, así que se puede probar sola.
- `experimento/grafica.py`: lee el CSV y escribe `grafica.png` y `resumen.md`.
- `experimento/test_medir.py`: pruebas de `contar`.
- `experimento/Dockerfile`: Python 3.12 con el cliente de Docker, matplotlib y pytest.
- `experimento/resultados/`: datos y gráfica, versionados en el repo.
- `docker-compose.local.yml`: servicio `experimento`, con el perfil `experimento` para
  que no arranque con `up`; monta `/var/run/docker.sock` y `experimento/resultados`.

Uso:

```bash
docker compose -f docker-compose.local.yml up -d --build central servidor-a servidor-b
docker compose -f docker-compose.local.yml run --rm --build experimento
```

## O · Operations (operaciones)

1. **`contar` y sus pruebas:** sin pérdidas, con una pérdida, con un duplicado por
   texto, con mensajes de otra corrida mezclados y con orden cambiado. Se comprueba con
   `docker compose -f docker-compose.local.yml run --rm --build experimento pytest`.
2. **`medir.py`:** crear `medidor` en `gNb` (un `409` vale), luego por cada corrida
   enviar, apagar, esperar, prender, medir los dos tiempos y contar. Se comprueba con
   una corrida corta (`DURACIONES=2 REPETICIONES=1`).
3. **Servicio `experimento`** en el compose local, con el perfil, el socket y la carpeta
   de resultados.
4. **`grafica.py`:** barras de mensajes enviados, perdidos y duplicados por duración, y
   puntos de `t_al_dia_s` por duración con la media de las 3 repeticiones; la tabla
   resumen con media, mínimo y máximo.
5. **Medición real:** las 9 corridas; se guardan el CSV, la gráfica y el resumen tal
   como salen. Si contradicen la hipótesis, se dejan así y se explican en el póster.

## N · Norms (normas)

- Todo en español (D13); los parámetros por variables de entorno del servicio:
  `URL_A`, `URL_B`, `SERVICIO_CAIDO` (`servidor-a`), `PROYECTO` (`chat-local`),
  `DURACIONES` (`2,5,10`), `REPETICIONES` (`3`), `TASA` (`5` mensajes por segundo).
- El script imprime una línea por corrida con su resultado, para seguirla en vivo.
- Commits en Conventional Commits con `Closes #19` (D14).

## S · Safeguards (salvaguardas)

1. **Nunca inventar ni retocar datos:** lo que sale del script es lo que va al póster.
2. **No se cambia el código del servidor** para el experimento.
3. El script solo apaga y prende el contenedor del servicio `SERVICIO_CAIDO` dentro del
   proyecto `PROYECTO`; nunca otro contenedor.
4. Si `gNa` no vuelve a responder, el script la prende otra vez antes de terminar con
   error, para no dejar el entorno apagado.
