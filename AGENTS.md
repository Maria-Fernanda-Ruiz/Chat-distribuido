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
**No hay código de la aplicación.**

Leer en este orden:

0. [`requirements/enunciado/`](requirements/enunciado/enunciado.md): el enunciado del
   docente, en PDF y transcrito. Es la fuente de todo lo demás, salvo el protocolo, donde
   manda la especificación OpenAPI (P07).
1. [`README.md`](README.md): estado, integrantes y roles, log de decisiones y tabla de
   pendientes.
2. [`requirements/CD-001-…-[Story]-…`](requirements/): historias HU1–HU12 con sus
   criterios de aceptación.
3. [`spdd/analysis/`](spdd/analysis/): vacío. Aquí va el análisis de la especificación y
   del script de conformidad.
4. [`spdd/prompt/`](spdd/prompt/): vacío. Aquí va el canvas.
5. [`spdd/template/REASONS-canvas.md`](spdd/template/REASONS-canvas.md): la plantilla.

## Reglas

1. **No escribir código de la aplicación** hasta que el canvas REASONS esté escrito y
   el equipo lo haya revisado. Es una decisión del equipo, no una sugerencia.
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
5. Idioma: español en el código, la API propia, los commits y los documentos (pendiente
   P13 hasta que el equipo lo confirme).
6. Los diagramas Mermaid deben renderizar en GitHub. Hay que probarlos antes de hacer
   commit.
7. Git: una rama y un PR por cada cosa terminada, con Conventional Commits. Nunca se
   hace push directo a `main` (el primer commit, que creó la rama, fue la excepción).
   Prefijos de rama: `docs/`, `feat/`, `fix/` (pendiente P14).
8. **Todo lo que se ejecute corre en contenedores**: el enunciado exige
   `docker compose up` en un equipo limpio. La configuración (grupo, URL pública, URL del
   central) va por variables de entorno, nunca escrita en el código.
9. Cada integrante debe poder explicar cualquier línea del código entregado (regla del
   enunciado sobre asistentes de IA): el código se escribe por tareas pequeñas y cada una
   se revisa con el equipo.

## Próximos pasos, en orden

1. Revisar la historia CD-001 y la tabla «Tareas y responsables» del README; cerrar los
   pendientes que quedan (paso 2).
2. Conseguir la especificación OpenAPI, los ejemplos JSON y el script de conformidad
   (P07) y guardarlos en el repo.
3. Escribir el análisis en `spdd/analysis/` (paso 3).
4. Escribir el canvas en `spdd/prompt/` a partir de la plantilla (paso 4). Su sección
   Operations será la lista de tareas del código, con el rol de cada una.
5. Código, tarea por tarea (paso 5). Punto de control de la etapa 1 del enunciado: el
   compose levanta un servidor vacío que responde `GET /fed/health`.

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
