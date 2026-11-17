# Chat distribuido entre grupos

Proyecto final de Sistemas Distribuidos (Escuela de Ingeniería de Sistemas e
Informática, UIS). Un servidor de chat en contenedores que se conecta al servidor
central del curso, para que los usuarios de todos los grupos conversen en una sola sala
global, `#general`, con entrega al menos una vez, deduplicación, relojes de Lamport,
heartbeat y recuperación de historial.

El requerimiento se trabaja con **SPDD** (Structured Prompt-Driven Development): se
decide y se escribe la especificación antes de generar código, y cada decisión queda
registrada en este README.

## Estado

> **Fase actual: código de las áreas y conexión al central (pasos 5 y 6 de SPDD).** Está
> la [historia](requirements/) con HU1–HU12, el [análisis](spdd/analysis/) del protocolo,
> revisado contra la [especificación v1.0.0](https://github.com/javierchacon262/central-server-dsp/tree/main/especificacion)
> del central, y los [canvas](spdd/prompt/) de la estructura (CD-002), la API local
> (CD-003), la federación (CD-004) y la presencia (CD-005). Hay 30 decisiones tomadas y
> 1 pendiente. El trabajo está repartido en
> [23 issues y 5 milestones](#tareas-y-responsables), con entrega el **jueves 19 de
> noviembre**.

```mermaid
flowchart LR
    H["1 · Historia<br/>requirements/"] --> C["2 · Aclarar con el equipo<br/>log de decisiones"]
    C --> AN["3 · Análisis<br/>spdd/analysis/"]
    AN --> CV["4 · Canvas REASONS<br/>spdd/prompt/"]
    CV --> G["5 · Código<br/>tarea por tarea"]
    G --> T["6 · Pruebas"]
    T -.->|"cambia el comportamiento:<br/>primero el canvas"| CV
    G -.->|"refactor sin cambio:<br/>se sincroniza el canvas"| CV
    classDef hecho fill:#2e7d32,stroke:#1b5e20,color:#ffffff
    classDef actual fill:#f9a825,stroke:#f57f17,color:#000000
    class H,C,AN,CV hecho
    class G,T actual
```

Verde: terminado. Amarillo: en curso.

## Integrantes y roles

| Integrante | Código | Rol |
|---|---|---|
| Maria Fernanda Ruiz Velasquez | 2253689 | API local y cliente web |
| Javier Alexi Chacón Suárez | 2160044 | PM, estructura, documentación y póster |
| Karen Angelica Sandoval Martinez | 2253637 | Federación de mensajes: envío, recepción, Lamport, deduplicación, reintentos |
| Manuel Augusto Utrera Saltaren | Por definir | Presencia y recuperación: registro, heartbeat, historial; experimento |

Grupo: **gN**, por confirmar ([P01](#decisiones-pendientes)). El reparto es la decisión
[D03](#log-de-decisiones): cada integrante es dueño de un tramo del recorrido del mensaje
y todos escriben código.

## Arquitectura

Es una arquitectura en estrella, según la sección 2 del enunciado. Nuestro servidor solo
habla con el servidor central y con nuestro cliente, nunca con los otros grupos. Todo el
servidor es **un solo contenedor** con **un volumen** para SQLite (D06), conectado a la
red por defecto que crea `docker compose`. Al central solo se sale hacia afuera, así que
funciona detrás de NAT (pull, D27).

```mermaid
flowchart TB
    NAV(["Navegador<br/>cliente web en /"])
    subgraph EQ["docker compose"]
        SV["<b>contenedor servidor</b><br/>Python 3.12 + FastAPI · puerto 8000<br/>api_local · federacion<br/>presencia · almacen"]
        VOL[("<b>volumen datos</b><br/>SQLite /datos/chat.db<br/>mensajes · reloj de Lamport<br/>pendientes · cursor seq")]
        SV <--> VOL
    end
    CE["<b>Servidor central</b><br/>dsp.cshire.io"]
    OT["servidores de<br/>los otros grupos"]
    NAV -->|"HTTP :8000"| SV
    SV -->|"POST /register · POST /messages · GET /health<br/>GET /history?after_seq= cada 1,5 s"| CE
    CE -.->|"solo en push: POST /fed/messages"| SV
    CE <--> OT
```

El mismo diagrama, como imagen para el póster:
[`entregables/arquitectura.png`](entregables/arquitectura.png).

Así viaja un mensaje: el cliente lo envía a `/api/mensajes`. El servidor sube el reloj,
guarda el mensaje y lo deja en pendientes, todo en una sola transacción. Una tarea de
fondo lo envía al central y lo reintenta con el mismo `id` hasta que el central lo
acepta. Los otros grupos lo traen con su pull, y nuestro servidor trae los de ellos de la
misma forma. Lo repetido se descarta por `id`, y el historial se ordena por
`(lamport, origin, id)`.

Rutas del protocolo, según la
[especificación v1.0.0](https://github.com/javierchacon262/central-server-dsp/tree/main/especificacion)
del central:

| Lado | Método y ruta | Qué hace |
|---|---|---|
| Central (lo llamamos) | `POST /register` | Registrar o renovar `{"server": "gN", "mode": "pull"}`, más `url` en push. Al arrancar y cada 30 s |
| Central (lo llamamos) | `POST /messages` | Entregar un mensaje de un usuario nuestro; responde `{"id", "seq", "duplicate"}` |
| Central (lo llamamos) | `GET /history?after_seq={cursor}&server={GRUPO}` | Pull (D27): los mensajes nuevos desde el último `seq` visto, cada 1,5 s |
| Central (lo llamamos) | `GET /history?since={lamport}` | Solo en push: recuperar el historial al arrancar y al volver el central (D16) |
| Central (lo llamamos) | `GET /health` | Heartbeat del central, cada 5 s |
| Nuestro (nos llaman) | `GET /fed/health` | Nombre del servidor y reloj de Lamport actual |
| Nuestro (nos llaman) | `POST /fed/messages` | Solo en push: recibir un mensaje reenviado por el central |

La API local, entre nuestro cliente y nuestro servidor (CD-003):

| Método y ruta | Qué hace |
|---|---|
| `GET /` | El cliente web |
| `POST /api/usuarios` · `GET /api/usuarios` | Crear (`409` si ya existe, `422` si el nombre no es válido) y listar usuarios |
| `POST /api/mensajes` | Escribir en `#general` (`404` si el usuario no existe, `422` si el texto no es válido) |
| `GET /api/mensajes?desde_lamport=N` | Historial ordenado; con `desde_lamport`, solo lo nuevo |

## Metodología: SPDD

SPDD es un método de Thoughtworks (Wei Zhang y Jessie Jie Xia, publicado en el sitio de
Martin Fowler en 2026) que trata los prompts como artefactos de ingeniería versionados
junto al código. El prompt estructurado se llama **canvas REASONS**:

| Letra | Sección | Pregunta que responde |
|---|---|---|
| R | Requirements | ¿Qué problema resolvemos y cuándo está terminado? |
| E | Entities | ¿Qué entidades hay y cómo se relacionan? |
| A | Approach | ¿Con qué estrategia lo resolvemos? |
| S | Structure | ¿Dónde encaja en el sistema? |
| O | Operations | ¿En qué pasos concretos y verificables se implementa? |
| N | Norms | ¿Qué convenciones aplican a todo? |
| S | Safeguards | ¿Qué no se puede romper nunca? |

Reglas que seguimos:

1. Primero la historia, después el análisis, después el canvas, y solo entonces el
   código, revisando en equipo entre cada paso.
2. **Cuando la realidad diverge, se corrige primero el canvas** y después el código.
   Un refactor que no cambia el comportamiento va al revés: código primero y luego se
   sincroniza el canvas.
3. SPDD no trae un log de decisiones propio. Lo agregamos aquí y cada decisión dice a
   qué sección del canvas alimenta, para que el canvas pueda citarla.

| Carpeta | Contenido |
|---|---|
| [`requirements/`](requirements/) | Historia y criterios de aceptación (paso 1), y el [enunciado del docente](requirements/enunciado/enunciado.md) |
| [`spdd/analysis/`](spdd/analysis/) | Análisis (paso 3): [contrato del protocolo y parámetros](spdd/analysis/CD-001-202611141940-[Analysis]-protocolo-y-parametros.md), y la especificación OpenAPI y el script de conformidad cuando lleguen |
| [`spdd/template/`](spdd/template/) | Plantilla del canvas REASONS |
| [`spdd/prompt/`](spdd/prompt/) | Canvas REASONS (paso 4): [CD-002, estructura](spdd/prompt/CD-002-202611141940-[Feat]-estructura.md). Cada área agrega el suyo |

Los archivos siguen el patrón del artículo: `ID-AAAAMMDDhhmm-[Tipo]-descripcion.md`, con
el prefijo `CD` (chat distribuido).

## Log de decisiones

La ronda 0 es lo que el equipo trajo decidido antes de iterar. La ronda 3 (2026-11-14) es la de la API local y el cliente web, con su [canvas](spdd/prompt/) (CD-003). La ronda 5 (2026-11-16) ajusta presencia y recepción a la especificación publicada (CD-005). La ronda 6 (2026-11-17) elige el experimento (CD-006).

| ID | Decisión | Alternativas descartadas | Por qué | REASONS | Ronda |
|---|---|---|---|---|---|
| D01 | Metodología **SPDD** con log de decisiones en este README | Desarrollo directo sin especificación | Elección del equipo; deja trazable por qué el código es como es | N | 0 |
| D02 | **Repo propio del grupo** en GitHub: `Maria-Fernanda-Ruiz/Chat-distribuido` | — | Es trabajo en grupo y todos deben poder clonar y hacer push; el historial de commits se evalúa | S | 0 |
| D03 | **Reparto por flujo del mensaje.** Javier: PM, estructura (esqueleto, compose, configuración, persistencia, modelo, logging, central simulado), especificación, documentación y póster. Maria Fernanda: API local y cliente. Karen: federación de mensajes. Manuel: presencia y recuperación, y experimento. Cierra P02 | Por lado del protocolo; parejas por etapa; los cuatro roles del enunciado con póster compartido | Cada tramo del recorrido se prueba y se explica por separado, todos escriben código y la base común la hace una sola persona para que no haya cuatro estilos | O | 1 |
| D04 | **Seguimiento con GitHub Issues y un milestone por etapa del enunciado**; cada PR cierra su issue con `Closes #N` | Tablero de GitHub Projects; tabla en el repo | Enlaza cada tarea con su PR y deja visible la participación de cada integrante, que se evalúa con el historial | N | 1 |
| D05 | **Python 3.12 con FastAPI y httpx.** Cierra P03 | Node.js; Go | Lo recomienda el enunciado y el grupo ya lo usó en el curso; todos deben poder explicar cada línea | S | 1 |
| D06 | **SQLite en un volumen de Docker.** Cierra P04 | PostgreSQL en otro contenedor; Redis con AOF | Un solo contenedor; `UNIQUE(id)` hace la deduplicación atómica, y el reloj y los pendientes se guardan en la misma transacción | S | 1 |
| D07 | **Cliente web mínimo** (HTML y JS sin build) servido por el mismo FastAPI, que consulta el historial cada segundo. Cierra P05 | Línea de comandos; ambos | Se ve mejor en la demo y en el póster y no hay que instalar nada | S | 1 |
| D08 | **Entrega y sesión de interoperabilidad: jueves 19 de noviembre de 2026.** Un milestone por etapa: 15, 16, 17, 18 y 19 de noviembre | — | Fecha del curso; las etapas del enunciado tienen un punto de control verificable cada una | O | 1 |
| D09 | **Póster a partir de la plantilla en PowerPoint**, a cargo de Javier | LaTeX; Canva | Es el formato de partida; una sola persona mantiene el póster coherente mientras los demás programan. *Ajustada por D30:* vertical A1 con el estilo de la plantilla | N | 1 |
| D10 | **Parámetros iniciales**, todos configurables por variables de entorno: heartbeat al central cada 5 s y caído tras 3 fallos seguidos; registro renovado cada 30 s; backoff de 1 s que se duplica hasta 30 s, con jitter y sin límite de intentos; timeout HTTP de 3 s. Cierra P09 | Valores rápidos para la demo (2 s, 2 fallos, 15 s, hasta 10 s); esperar a la especificación | Detecta la caída en 15–24 s sin falsos positivos por un timeout suelto. Sin límite de intentos, porque un tope perdería mensajes. El jitter evita que todos los grupos reintenten a la vez cuando vuelve el central | A | 2 |
| D11 | **El reloj de Lamport y la cola de pendientes se guardan en SQLite**, en la misma base que los mensajes. Cierra P10 | Tenerlos solo en memoria | Si el reloj vuelve a 0, nuestros mensajes nuevos quedan ordenados antes que los viejos; si se pierden los pendientes, se pierden mensajes | E | 2 |
| D12 | **Usuarios sin contraseña:** un nombre único en el grupo, de 1 a 20 caracteres entre minúsculas, números, `_` y `-`, para que `nombre@gN` sea válido en cualquier grupo. El cliente recuerda el nombre elegido. Cierra P11 | Contraseña con hash y token de sesión; token entregado al crear el usuario | El enunciado no pide autenticación, y cada cosa extra es trabajo para la API local y código que hay que saber explicar | E | 2 |
| D13 | **Todo en español:** código, API propia, commits y documentos. Los campos y rutas del protocolo con el central quedan como los define la especificación. Cierra P13 | Todo en inglés | El equipo y el curso trabajan en español; el protocolo no se negocia | N | 2 |
| D14 | **Flujo de Git:** una rama y un PR por cosa terminada (prefijos `docs/`, `feat/`, `fix/`), Conventional Commits y `Closes #N`; nunca push directo a `main`. Cierra P14 | Trabajar directo en `main` | Cada PR se revisa como una sola cosa y el historial muestra quién hizo qué, que también se evalúa | N | 2 |
| D15 | **El PM aprueba el canvas** para que el código pueda empezar; el equipo lo revisa en el PR y, si pide un cambio, primero se corrige el canvas. Ajusta la regla 1 de `AGENTS.md` | Esperar a que los cuatro lo revisen antes de programar | La etapa 1 vence el 15 de noviembre y las demás áreas no pueden programar sin la estructura | N | 2 |
| D16 | **`since` al recuperar historial:** al arrancar se pide `since=0` y la deduplicación descarta lo repetido; al volver el central se pide el último `lamport` visto. Cierra P15, que surgió en el análisis | Siempre el último visto; último visto menos un margen | Lamport no ordena los mensajes concurrentes: un grupo que acaba de arrancar puede mandar una marca menor que la nuestra, y con «último visto» lo perderíamos. Es justo lo que mide el experimento ([análisis, sección 6](spdd/analysis/CD-001-202611141940-[Analysis]-protocolo-y-parametros.md#6-qué-since-pedir-al-recuperar-historial-d16)). *Ajustada por D27:* rige solo en push; en pull el cursor `seq` la reemplaza | A | 2 |
| D17 | **Rutas de la API local bajo `/api`:** `/api/usuarios` y `/api/mensajes` | `/v1/…`; rutas sin prefijo | Quedan separadas de las rutas `/fed/…` que usa el central y del cliente en `/` | S | 3 |
| D18 | **Crear usuario: 409 si el nombre ya existe y 422 si no cumple D12**, con `{"detail": "…"}` en español | 400 para los dos casos | Son los códigos estándar de HTTP y el cliente puede mostrar un mensaje distinto para cada caso | R | 3 |
| D19 | **El cliente pide lo nuevo por `lamport`** (`GET /api/mensajes?desde_lamport=N`), como dice [#22](https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido/issues/22). Un mensaje concurrente que llega tarde con una marca menor o igual no aparece hasta recargar | Por `secuencia` (orden de llegada); pedir siempre todo | Decisión a propósito: la idea es **evidenciar** el comportamiento erróneo probable de un sistema distribuido (Lamport no ordena los concurrentes) y mostrarlo como hallazgo y caso de mejora en la sesión y el póster. La mejora, pedir por `secuencia`, queda escrita en el canvas | A | 3 |
| D20 | **Cliente: un color para los mensajes de nuestro grupo y otro para los de otros grupos**, y todos con la etiqueta `usuario@gN` | Solo la etiqueta; un color por grupo | Se distingue a simple vista en la demo y en el póster, con poco código | S | 3 |
| D21 | **Enviar con un usuario que no existe responde 404** | 422 | Es lo estándar cuando lo que se nombra no existe | R | 3 |
| D22 | **El texto del mensaje va de 1 a 1 000 caracteres;** vacío o solo espacios, o más de 1 000 → 422 | Solo no vacío; sin límites; 2 000 (Discord) o 4 000 (Telegram) | Evita mensajes en blanco en `#general` y textos enormes que viajan a todos los grupos, sin limitar un mensaje normal de chat | R | 3 |
| D23 | **El cliente web se abre en `/`** | `/cliente` | Es lo más cómodo en la demo: se abre la URL del servidor y aparece el chat | S | 3 |
| D24 | **`tick(tx)` y `recibir(valor, tx)` reutilizan la transacción SQLite recibida.** Si no reciben una transacción, pueden abrir una propia mediante `Almacen`. Cierra P16 | Abrir siempre una transacción propia, incluso cuando ya existe una abierta | Evita transacciones anidadas y permite que el mensaje y el reloj compartan la misma confirmación o rollback | S | 4 |
| D25 | **En el cliente web, el usuario se elige o se crea en la misma pantalla del chat:** arriba, una lista con los usuarios del grupo y un campo para crear uno nuevo | Una pantalla de entrada aparte | Es lo más simple y lo más rápido en la demo, con menos código que explicar | S | 4 |
| D26 | **Cada mensaje del cliente muestra su número de Lamport junto a la hora**, por ejemplo `#12 · 3:15 p. m.` | Mostrar solo la hora | En la demo y en el póster se ve por qué los mensajes salen en ese orden, y se puede mostrar la limitación de D19 | S | 4 |
| D27 | **Recepción en pull, según la [especificación v1.0.0](https://github.com/javierchacon262/central-server-dsp/tree/main/especificacion) del central** (`https://dsp.cshire.io`). `MODO_RECEPCION` es `pull` por defecto o `push`. En pull, el servidor pide `GET /history?after_seq=<cursor>&server=<GRUPO>` cada `PULL_INTERVALO_S` (1,5 s) y guarda el cursor `seq` en SQLite, en la misma transacción que el mensaje; `URL_PUBLICA` solo es obligatoria en push. Todo mensaje recibido, por `/fed/messages`, por pull o por historial, pasa por la misma recepción de `federacion.reloj` ([CD-005](spdd/prompt/CD-005-202611161200-[Feat]-presencia-y-recuperacion.md)). Cierra P07, P08 y P12; ajusta D16 | Push con un túnel (cloudflared o ngrok) como modo principal; seguir con el supuesto S9 | Los portátiles están detrás de NAT y el central no puede llamarlos sin túnel; pull solo necesita salida a internet. El cursor `seq` no pierde los mensajes concurrentes que llegan tarde con una marca menor, el riesgo que D16 dejaba abierto | E, A, O | 5 |
| D28 | **El central simulado de #7 es el central oficial**, construido desde su repositorio público en `docker-compose.local.yml` como servicio `central` (panel en `http://localhost:9000/`) | Escribir un central falso propio | Es el mismo código que corre en `dsp.cshire.io`, así que lo que pasa en local pasa en la sesión, y no hay un central propio que mantener. Una caída se simula con `docker compose -f docker-compose.local.yml stop central` | S | 5 |
| D29 | **Experimento: pérdidas ante una caída**, variando la duración de la caída (2, 5 y 10 s, 3 repeticiones de cada una). Un script envía 5 mensajes por segundo desde `gNb` mientras apaga `gNa` con `docker kill` y la vuelve a prender; luego cuenta en `gNa` los mensajes perdidos y duplicados, y de paso el tiempo que tarda en ponerse al día ([CD-006](spdd/prompt/CD-006-202611171300-[Feat]-experimento-perdidas.md)). Cierra P06 | Latencia de extremo a extremo; tiempo de recuperación solo; no variar ningún parámetro; caída con `docker compose restart` | Mide lo mismo que muestra la demo (al menos una vez, deduplicación y recuperación). Variar la duración suma en la evaluación. `docker kill` apaga de golpe, sin cierre ordenado, así que es la prueba más dura para la base y el cursor | R, A, O | 6 |
| D30 | **Póster vertical A1** con el estilo de la plantilla SystemsFest: sus logos, colores y letra, y las secciones que pide el enunciado. Va en [`entregables/poster.pptx`](entregables/poster.pptx) y en PDF, con las gráficas como gráficos de PowerPoint que se pueden editar. Ajusta D09 | Usar la plantilla tal cual, que es horizontal (48 × 36 pulgadas) | El enunciado pide formato vertical, pliego o A1 (sección 8), y el póster vale 15 % | N | 6 |

## Decisiones pendientes

Se cierran con el equipo: cada pregunta se discute con sus opciones y, al decidir, pasa al
log como una D que dice «cierra P0X». No se genera código para una parte hasta cerrar su
pendiente.

| ID | Pregunta | Propuesta para discutir | Bloquea |
|---|---|---|---|
| P01 | ¿Qué número de grupo somos (`gN`)? | Preguntar al profesor o revisar la lista del curso | Configuración, póster |

## Tareas y responsables

Cada tarea es un issue con responsable, criterios de aceptación y dependencias, dentro
del [milestone](https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido/milestones) de su etapa ([D04](#log-de-decisiones)). Los PR cierran su
issue con `Closes #N`. Los issues con la etiqueta `protocolo-provisional` salen del
resumen del enunciado y se revisan cuando llegue la especificación (P07).

| Etapa | Javier | Maria Fernanda | Karen | Manuel |
|---|---|---|---|---|
| 1 · Arranque (dom 15) | [#1](https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido/issues/1) especificación y grupo<br>[#2](https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido/issues/2) análisis y canvas<br>[#3](https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido/issues/3) esqueleto<br>[#4](https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido/issues/4) compose<br>[#5](https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido/issues/5) SQLite<br>[#6](https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido/issues/6) modelo y logs | — | — | — |
| 2 · Servidor local (lun 16) | [#7](https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido/issues/7) central simulado | [#20](https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido/issues/20) usuarios<br>[#21](https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido/issues/21) enviar<br>[#22](https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido/issues/22) historial<br>[#23](https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido/issues/23) cliente web | [#12](https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido/issues/12) reloj de Lamport | [#15](https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido/issues/15) `/fed/health` |
| 3 · Conexión al central (mar 17) | [#8](https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido/issues/8) conformidad | — | [#13](https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido/issues/13) `/fed/messages`<br>[#14](https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido/issues/14) envío con reintentos | [#16](https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido/issues/16) registro<br>[#17](https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido/issues/17) heartbeat<br>[#18](https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido/issues/18) recuperar historial |
| 4 · Experimento (mié 18) | — | — | — | [#19](https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido/issues/19) experimento |
| 5 · Cierre (jue 19) | [#9](https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido/issues/9) README y diagrama<br>[#10](https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido/issues/10) póster<br>[#11](https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido/issues/11) bitácora y sustentación | — | — | — |

La base común (etapa 1) va primero porque las demás áreas programan sobre ella. Mientras
tanto, el resto del equipo revisa el análisis y el canvas ([#2](https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido/issues/2)).

## Cómo levantarlo

Todo corre en contenedores (regla 8 de [`AGENTS.md`](AGENTS.md)). En un equipo limpio
solo hacen falta **Git** y **Docker con Compose v2** (Docker Desktop en Windows y macOS,
o Docker Engine con el plugin `compose` en Linux). No hay que instalar Python.

```bash
git clone https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido.git
cd Chat-distribuido
cp .env.example .env          # escribir GRUPO; URL_CENTRAL ya viene con el central del curso
docker compose up --build     # servidor en http://localhost:8000
```

Después:

1. Abrir <http://localhost:8000/> en el navegador.
2. Crear un usuario arriba y escribir en `#general`. Los mensajes de nuestro grupo salen
   en azul y los de otros grupos en amarillo.
3. Comprobar que responde: `curl localhost:8000/fed/health` devuelve
   `{"server": "gN", "lamport": …}`.

Si falta una variable obligatoria o un valor no es válido, el servidor no arranca y el
log dice cuál es. Los datos (SQLite) viven en el volumen `datos` y sobreviven a
`docker compose restart` y a `docker compose down`. `docker compose down -v` los borra.

### Variables de entorno

Van en `.env`. Cada una está explicada en [`.env.example`](.env.example), y las
opcionales vacías toman los valores de [D10](#log-de-decisiones).

| Variable | Obligatoria | Por defecto | Para qué |
|---|---|---|---|
| `GRUPO` | Sí | — | Nombre del servidor en el central, por ejemplo `g3` |
| `URL_CENTRAL` | Sí | `https://dsp.cshire.io` en `.env.example` | Dirección del servidor central |
| `MODO_RECEPCION` | No | `pull` | `pull` consulta al central; `push` espera que el central nos llame (D27) |
| `URL_PUBLICA` | Solo en push | — | URL con la que el central llega a nosotros desde internet |
| `PULL_INTERVALO_S` | No | 1,5 | Cada cuánto se consulta el central en pull |
| `PUERTO_HOST` | No | 8000 | Puerto del equipo donde se publica el servidor |
| `HEARTBEAT_INTERVALO_S` | No | 5 | Cada cuánto se revisa `GET /health` del central |
| `HEARTBEAT_FALLOS_PARA_CAIDO` | No | 3 | Fallos seguidos para dar el central por caído |
| `REGISTRO_INTERVALO_S` | No | 30 | Cada cuánto se renueva el registro |
| `BACKOFF_BASE_S` · `BACKOFF_MAX_S` | No | 1 · 30 | Primera espera de un reintento y espera máxima; se duplica en cada intento |
| `HTTP_TIMEOUT_S` | No | 3 | Tiempo máximo de cada llamada al central |
| `LOG_ACCESOS` | No | `false` | Una línea de log por cada petición HTTP recibida |

Para probar sin otros grupos hay un segundo archivo de compose, que no se entrega:

```bash
docker compose -f docker-compose.local.yml up --build              # central en :9000, gNa en :8001 y gNb en :8002
docker compose -f docker-compose.local.yml run --rm --build pruebas # todas las pruebas (pytest)
```

El archivo local levanta el central oficial (D28) y dos servidores del grupo en pull
contra él. El panel del central, en <http://localhost:9000/>, muestra los dos servidores y
la sala `#general`. Para simular una caída del central:
`docker compose -f docker-compose.local.yml stop central` (y `start central` para que
vuelva).

**Modo de recepción (D27).** Por defecto el servidor recibe en **pull**: consulta al
central cada 1,5 s y no necesita una URL pública, así que funciona en un portátil detrás
de NAT. Con `MODO_RECEPCION=push` el central llama a `POST /fed/messages`; entonces
`URL_PUBLICA` es obligatoria y tiene que ser alcanzable desde internet, por ejemplo con
un túnel de cloudflared.

**Script de conformidad (#8).** La salida de la última corrida está en
[`entregables/conformidad.txt`](entregables/conformidad.txt): 9 de 9 casos, el 2026-11-17,
contra nuestro servidor conectado al central real con el nombre de prueba `g2`
([bitácora](entregables/bitacora-interoperabilidad.md)). Para repetirlo con el servidor levantado en `:8000`:

```bash
docker build -t conformidad-dsp "https://github.com/javierchacon262/central-server-dsp.git#main:conformidad"
docker run --rm --network host conformidad-dsp http://localhost:8000 > entregables/conformidad.txt
```

En Windows y macOS se quita `--network host` y se usa `http://host.docker.internal:8000`.
La corrida que se entrega se repite con el nombre real del grupo cuando se cierre P01.

## Código

El servidor está en [`servidor/chat/`](servidor/chat/). La estructura y los contratos
entre módulos están en el [canvas CD-002](spdd/prompt/CD-002-202611141940-[Feat]-estructura.md).
Cada área programa en su carpeta, donde un archivo de partida explica qué va ahí:

| Carpeta | Qué hay | Responsable | Issues |
|---|---|---|---|
| [`chat/api_local/`](servidor/chat/api_local/) | API local y cliente web | Maria Fernanda | #20–#23 |
| [`chat/federacion/`](servidor/chat/federacion/) | Reloj de Lamport, `POST /fed/messages`, envío con reintentos | Karen | #12–#14 |
| [`chat/presencia/`](servidor/chat/presencia/) | `GET /fed/health`, registro, heartbeat, recuperación de historial | Manuel | #15–#18 |
| El resto de [`chat/`](servidor/chat/) | Configuración, contexto, arranque, almacén, modelo y eventos | Javier | #3–#6 |

Una tarea de fondo nueva se agrega a `TAREAS_DE_FONDO` en
[`principal.py`](servidor/chat/principal.py). Lo que comparten las áreas pasa por
[`Contexto`](servidor/chat/contexto.py); las áreas no se importan entre sí.

### Cómo registrar eventos

Los logs son la base del experimento y de la demo, así que todas las áreas registran
sus eventos con la misma función de [`eventos.py`](servidor/chat/eventos.py):

```python
from chat.eventos import Evento, registrar

registrar(Evento.REINTENTO, mensaje, intento=2, espera_s=1.7, causa="timeout")
```

```text
2026-11-14T19:40:05.210Z g3 REINTENTO id=6f1c2a9e-… lamport=42 origin=g3 from=ana@g3 intento=2 espera_s=1.7 causa=timeout
```

- Si se pasa el mensaje, la línea lleva su `id`, `lamport`, `origin` y `from`; después
  van los detalles en el orden en que se escriben.
- Un valor con espacios sale entre comillas, y un detalle `None` no sale.
- El cuerpo del mensaje nunca va al log.
- Los eventos y los campos de cada uno están en el
  [análisis, sección 10](spdd/analysis/CD-001-202611141940-[Analysis]-protocolo-y-parametros.md#10-eventos-del-log).
  Para agregar uno, primero se agrega al análisis y al canvas.

Los mensajes del protocolo se leen y se crean con [`Mensaje`](servidor/chat/modelo.py):

- `Mensaje.model_validate(json)` acepta campos desconocidos.
- `Mensaje.nuevo(usuario=…, grupo=…, lamport=…, body=…)` crea uno nuestro con un `id`
  nuevo.
- `mensaje.a_json()` lo deja listo para enviar, con `from`.

## Cómo continuar

Las instrucciones para cualquier persona o agente están en [`AGENTS.md`](AGENTS.md).
Cada integrante toma sus issues en el orden de los milestones. Antes de programar su
parte, cada área escribe su canvas sobre los contratos de la
[estructura](spdd/prompt/CD-002-202611141940-[Feat]-estructura.md) y lo aprueba el PM
(D15). Las preguntas nuevas se agregan como pendientes. La especificación del central ya está
publicada (D27) y manda sobre el resumen del enunciado.

## Fuentes

- Wei Zhang y Jessie Jie Xia (Thoughtworks), [Structured-Prompt-Driven Development (SPDD)](https://martinfowler.com/articles/structured-prompt-driven/), martinfowler.com, 2026.
- Enunciado del docente: [`requirements/enunciado/`](requirements/enunciado/enunciado.md).
- Leslie Lamport, *Time, Clocks, and the Ordering of Events in a Distributed System*, Communications of the ACM, 1978.
- Vitillo, *Understanding Distributed Systems*.
