# Instrucciones para agentes y personas que continúan este proyecto

Servidor de chat en contenedores para el proyecto final de Sistemas Distribuidos (UIS):
se conecta al servidor central del profesor para que todos los grupos conversen en una
sola sala global, `#general`. El requerimiento se trabaja con **SPDD**.

## Dónde quedó el trabajo

El 2026-11-13 Maria Fernanda montó el repo con la base SPDD: el enunciado (PDF y
transcripción), la historia CD-001 con HU1–HU12, la plantilla del canvas REASONS y el
README con D01–D02 y los pendientes P01–P14. El 2026-11-14 Javier, como PM, cerró la
ronda 1 (D03–D09): reparto por flujo del mensaje, FastAPI con httpx, SQLite, cliente web,
entrega el jueves 19 de noviembre, y 23 issues en 5 milestones con responsable cada uno.
El mismo día cerró la ronda 2 (D10–D16): parámetros, persistencia del reloj, usuarios sin
contraseña, idioma, flujo de Git, aprobación del canvas por el PM y el `since` del
historial. Escribió el análisis del protocolo (provisional hasta P07) y el canvas de la
estructura (CD-002), y abrió en PR el código de la etapa 1 (#3–#6). Las áreas todavía no
tienen canvas ni código.

Leer en este orden:

0. [`requirements/enunciado/`](requirements/enunciado/enunciado.md): el enunciado del
   docente, en PDF y transcrito. Es la fuente de todo lo demás, salvo el protocolo, donde
   manda la especificación OpenAPI (P07).
1. [`README.md`](README.md): estado, integrantes y roles, log de decisiones y tabla de
   pendientes.
2. [`requirements/CD-001-…-[Story]-…`](requirements/): historias HU1–HU12 con sus
   criterios de aceptación.
3. [`spdd/analysis/`](spdd/analysis/): el análisis CD-001 con el contrato de cada
   endpoint, las reglas de Lamport, los parámetros, los eventos del log y los supuestos
   S1–S9 que se revisan cuando llegue la especificación.
4. [`spdd/prompt/`](spdd/prompt/): el canvas CD-002 de la estructura, con los contratos
   (configuración, contexto, almacén, modelo y eventos) sobre los que programa cada área.
5. [`spdd/template/REASONS-canvas.md`](spdd/template/REASONS-canvas.md): la plantilla.

## Reglas

1. **No escribir código de la aplicación** hasta que el canvas REASONS de esa parte esté
   escrito y aprobado por el PM (D15). El equipo lo revisa en el PR; si pide un cambio,
   primero se corrige el canvas. Es una decisión del equipo, no una sugerencia.
2. **Las decisiones se iteran con el equipo; el agente no decide solo.** Se presenta
   cada pregunta con sus opciones, se marca una recomendada y se explica qué cambia
   con cada una. Cuando el equipo confirma:
   - se agrega una fila a la tabla «Log de decisiones» del README con el siguiente ID
     (D03, D04, …), las alternativas descartadas, el porqué, la sección REASONS que
     alimenta y la ronda;
   - si cierra un pendiente, se borra de la tabla de pendientes y la decisión dice
     «cierra P0X»;
   - si modifica una decisión anterior, esa no se borra: se le agrega la nota
     «Ajustada por DXX»;
   - se actualiza el contador de la sección «Estado».

   Si al escribir el análisis, el canvas o el código aparece una pregunta nueva, se
   agrega a la tabla de pendientes con el siguiente ID (P15, P16, …), y no se genera
   código para esa parte hasta cerrarla.
3. **Primero el canvas, después el código.** Si cambia el comportamiento, se corrige
   el canvas y luego se regenera el código. Si es un refactor sin cambio de
   comportamiento, se cambia el código y luego se sincroniza el canvas. Las secciones
   del canvas no se editan a mano sin dejar constancia de por qué.
4. **El protocolo con el servidor central no se negocia.** Lo fija la especificación
   OpenAPI del profesor; ante cualquier diferencia con el resumen del enunciado, manda la
   especificación. Las dudas se resuelven en el foro del curso. No se comparte código con
   otros grupos.
5. Idioma: español en el código, la API propia, los commits y los documentos; los campos
   y rutas del protocolo, como en la especificación (D13).
6. Los diagramas Mermaid deben renderizar en GitHub. Hay que probarlos antes de hacer
   commit.
7. Git: una rama y un PR por cada cosa terminada, con Conventional Commits y
   `Closes #N`. Nunca se hace push directo a `main` (el primer commit, que creó la rama,
   fue la excepción). Prefijos de rama: `docs/`, `feat/`, `fix/` (D14).
8. **Todo lo que se ejecute corre en contenedores**: el enunciado exige
   `docker compose up` en un equipo limpio. La configuración (grupo, URL pública, URL del
   central) va por variables de entorno, nunca escrita en el código.
9. Cada integrante debe poder explicar cualquier línea del código entregado (regla del
   enunciado sobre asistentes de IA): el código se escribe por tareas pequeñas y cada una
   se revisa con el equipo.

## Próximos pasos, en orden

1. Fusionar, en orden, los PR de la etapa 1: análisis y canvas (#2), esqueleto (#3),
   contenedores (#4), modelo y eventos (#6) y persistencia (#5). Antes de cada uno,
   comprobar que su base ya sea `main`.
2. Conseguir la especificación OpenAPI, los ejemplos JSON y el script de conformidad
   (P07), guardarlos en `spdd/analysis/especificacion/` y revisar contra ellos los
   supuestos S1–S9 del análisis.
3. Cada área escribe su canvas en `spdd/prompt/` sobre los contratos de CD-002 (CD-003
   API local, CD-004 federación, CD-005 presencia) y lo aprueba el PM. Su sección
   Operations es la lista de tareas de su código.
4. Código de cada área, tarea por tarea. Punto de control de la etapa 2: dos usuarios
   del grupo conversan localmente y el historial sobrevive a un reinicio.

## Cómo seguir

Cada ronda o cosa terminada va en su propia rama, creada desde `main`, y en su propio PR:

```bash
git clone https://github.com/Maria-Fernanda-Ruiz/Chat-distribuido.git
cd Chat-distribuido
git switch main && git pull
git switch -c docs/ronda-1-decisiones
# … trabajar, y luego:
git add -A && git commit -m "docs(spdd): ronda 1 de decisiones"
git push -u origin docs/ronda-1-decisiones
# abrir el PR en GitHub
```

> **Antes de fusionar un PR apilado, comprobar que su base ya sea `main`.** Si no, el
> PR se fusiona contra la rama vieja y sus cambios nunca llegan a `main`. Conviene activar «Automatically delete head branches» en la configuración del repo.
