"""Persistencia en SQLite: el único módulo con SQL (D06, D11; canvas CD-002).

Guarda usuarios, mensajes, el reloj de Lamport y la cola de pendientes en un archivo
dentro del volumen, así que todo sobrevive a `docker compose restart`.

Las reglas del protocolo no viven aquí: el almacén no sabe de Lamport. Ofrece
operaciones sueltas, y cuando varias tienen que pasar juntas (guardar un mensaje y
mover el reloj, por ejemplo), el área las compone dentro de una transacción:

    with ctx.almacen.transaccion() as tx:
        if tx.guardar_mensaje_si_no_existe(mensaje):
            tx.fijar_reloj(max(tx.leer_reloj(), mensaje.lamport) + 1)

O pasan todas o no pasa ninguna. Cada operación abre una conexión corta, porque así
se puede llamar desde cualquier hilo sin coordinar nada.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from chat.modelo import Mensaje, es_nombre_valido

VERSION_ESQUEMA = 1

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    nombre     TEXT PRIMARY KEY,
    creado_en  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mensajes (
    -- Orden de llegada a ESTE servidor; no es el orden lógico. Sirve de cursor para
    -- pedir "lo nuevo desde la última vez" sin perder mensajes concurrentes.
    secuencia    INTEGER PRIMARY KEY AUTOINCREMENT,
    -- UNIQUE: la deduplicación la hace la base, de forma atómica (D06).
    id           TEXT NOT NULL UNIQUE,
    remitente    TEXT NOT NULL,  -- el campo "from" del protocolo
    origin       TEXT NOT NULL,
    lamport      INTEGER NOT NULL,
    sent_at      TEXT NOT NULL,  -- informativo, nunca se ordena por él
    body         TEXT NOT NULL,
    guardado_en  TEXT NOT NULL   -- hora UTC de llegada, para el experimento
);
CREATE INDEX IF NOT EXISTS mensajes_por_orden_logico ON mensajes (lamport, origin, id);

CREATE TABLE IF NOT EXISTS estado (
    clave  TEXT PRIMARY KEY,
    valor  INTEGER NOT NULL
);
INSERT OR IGNORE INTO estado (clave, valor) VALUES ('reloj', 0);
-- Último `seq` del central procesado en pull (D27): el cursor de GET /history?after_seq=.
INSERT OR IGNORE INTO estado (clave, valor) VALUES ('cursor_seq', 0);

-- Mensajes nuestros que todavía no llegan al central (análisis, sección 7).
CREATE TABLE IF NOT EXISTS pendientes (
    id               TEXT PRIMARY KEY REFERENCES mensajes (id),
    intentos         INTEGER NOT NULL DEFAULT 0,
    proximo_intento  REAL NOT NULL  -- segundos desde 1970 (time.time())
);
"""

_COLUMNAS_MENSAJE = "m.id, m.remitente, m.origin, m.lamport, m.sent_at, m.body"
_ORDEN_LOGICO = "m.lamport, m.origin, m.id"


@dataclass(frozen=True)
class Pendiente:
    mensaje: Mensaje
    intentos: int
    proximo_intento: float


class Transaccion:
    """Operaciones que comparten una transacción. Se obtiene con `almacen.transaccion()`."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        self._con = conexion

    def leer_reloj(self) -> int:
        return self._con.execute("SELECT valor FROM estado WHERE clave = 'reloj'").fetchone()[0]

    def fijar_reloj(self, valor: int) -> None:
        """Guarda el reloj. Lanza ValueError si el valor es menor que el actual (D11)."""
        actual = self.leer_reloj()
        if valor < actual:
            raise ValueError(f"El reloj de Lamport no puede retroceder: {actual} → {valor}")
        self._con.execute("UPDATE estado SET valor = ? WHERE clave = 'reloj'", (valor,))

    def leer_cursor_seq(self) -> int:
        return self._con.execute(
            "SELECT valor FROM estado WHERE clave = 'cursor_seq'"
        ).fetchone()[0]

    def avanzar_cursor_seq(self, seq: int) -> None:
        """Mueve el cursor del pull a `seq` si es mayor; nunca lo hace retroceder (D27)."""
        self._con.execute(
            "UPDATE estado SET valor = ? WHERE clave = 'cursor_seq' AND valor < ?",
            (seq, seq),
        )

    def guardar_mensaje_si_no_existe(self, mensaje: Mensaje) -> bool:
        """Devuelve True si el mensaje era nuevo y False si su `id` ya estaba."""
        cursor = self._con.execute(
            "INSERT INTO mensajes (id, remitente, origin, lamport, sent_at, body, guardado_en)"
            " VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (id) DO NOTHING",
            (
                mensaje.id,
                mensaje.from_,
                mensaje.origin,
                mensaje.lamport,
                mensaje.sent_at,
                mensaje.body,
                _ahora(),
            ),
        )
        return cursor.rowcount == 1

    def encolar_pendiente(self, id: str, proximo_intento: float) -> None:
        """Pone en la cola un mensaje ya guardado. Falla si el mensaje no existe."""
        self._con.execute(
            "INSERT INTO pendientes (id, intentos, proximo_intento) VALUES (?, 0, ?)",
            (id, proximo_intento),
        )

    def reprogramar_pendiente(self, id: str, intentos: int, proximo_intento: float) -> None:
        self._con.execute(
            "UPDATE pendientes SET intentos = ?, proximo_intento = ? WHERE id = ?",
            (intentos, proximo_intento, id),
        )

    def quitar_pendiente(self, id: str) -> None:
        self._con.execute("DELETE FROM pendientes WHERE id = ?", (id,))

    def adelantar_pendientes(self, ahora: float) -> int:
        """Deja todos los pendientes listos ya (al volver el central). Devuelve cuántos."""
        cursor = self._con.execute(
            "UPDATE pendientes SET proximo_intento = ? WHERE proximo_intento > ?",
            (ahora, ahora),
        )
        return cursor.rowcount

    def crear_usuario(self, nombre: str) -> bool:
        """Devuelve True si el usuario es nuevo y False si ya existía."""
        if not es_nombre_valido(nombre):
            raise ValueError(f"Nombre de usuario inválido: {nombre!r}")
        cursor = self._con.execute(
            "INSERT INTO usuarios (nombre, creado_en) VALUES (?, ?)"
            " ON CONFLICT (nombre) DO NOTHING",
            (nombre, _ahora()),
        )
        return cursor.rowcount == 1


class Almacen:
    def __init__(self, ruta: str | Path) -> None:
        self.ruta = Path(ruta)

    def inicializar(self) -> None:
        """Crea el archivo y las tablas si no existen. No borra nada de lo guardado."""
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._conectar()) as con:
            # WAL: las lecturas no esperan a las escrituras. Queda guardado en el archivo.
            con.execute("PRAGMA journal_mode = WAL")
            con.executescript(ESQUEMA)
            con.execute(f"PRAGMA user_version = {VERSION_ESQUEMA}")

    @contextmanager
    def transaccion(self) -> Iterator[Transaccion]:
        """Si el bloque termina bien se confirma todo; si lanza una excepción, nada."""
        with closing(self._conectar()) as con:
            # IMMEDIATE toma el permiso de escritura al empezar; otra transacción espera
            # hasta 5 s en lugar de fallar a mitad de camino.
            con.execute("BEGIN IMMEDIATE")
            try:
                yield Transaccion(con)
            except BaseException:
                con.execute("ROLLBACK")
                raise
            con.execute("COMMIT")

    # --- Atajos: cada uno es su propia transacción o lectura ----------------------------

    def crear_usuario(self, nombre: str) -> bool:
        with self.transaccion() as tx:
            return tx.crear_usuario(nombre)

    def existe_usuario(self, nombre: str) -> bool:
        return self._uno("SELECT 1 FROM usuarios WHERE nombre = ?", (nombre,)) is not None

    def listar_usuarios(self) -> list[str]:
        with closing(self._conectar()) as con:
            return [fila[0] for fila in con.execute("SELECT nombre FROM usuarios ORDER BY nombre")]

    def guardar_mensaje_si_no_existe(self, mensaje: Mensaje) -> bool:
        with self.transaccion() as tx:
            return tx.guardar_mensaje_si_no_existe(mensaje)

    def listar_historial(self, limite: int | None = None) -> list[Mensaje]:
        """El historial en orden lógico, (lamport, origin, id). Con `limite`, los últimos."""
        consulta = f"SELECT {_COLUMNAS_MENSAJE} FROM mensajes m ORDER BY {_ORDEN_LOGICO}"
        parametros: tuple[object, ...] = ()
        if limite is not None:
            consulta = (
                f"SELECT * FROM (SELECT {_COLUMNAS_MENSAJE} FROM mensajes m"
                " ORDER BY m.lamport DESC, m.origin DESC, m.id DESC LIMIT ?) m"
                f" ORDER BY {_ORDEN_LOGICO}"
            )
            parametros = (limite,)
        with closing(self._conectar()) as con:
            return [_a_mensaje(fila) for fila in con.execute(consulta, parametros)]

    def listar_historial_desde_lamport(self, lamport: int) -> list[Mensaje]:
        """Los mensajes con marca MAYOR que `lamport`, en orden lógico (CD-003, D19).

        Lo usa el cliente para pedir solo lo nuevo. Ojo, a propósito: un mensaje
        concurrente que llega tarde con una marca menor o igual a `lamport` no sale aquí.
        Para no perder ninguno está `listar_llegados_despues_de`."""
        with closing(self._conectar()) as con:
            filas = con.execute(
                f"SELECT {_COLUMNAS_MENSAJE} FROM mensajes m"
                f" WHERE m.lamport > ? ORDER BY {_ORDEN_LOGICO}",
                (lamport,),
            )
            return [_a_mensaje(fila) for fila in filas]

    def listar_llegados_despues_de(self, secuencia: int) -> list[tuple[int, Mensaje]]:
        """Lo que llegó a este servidor después de `secuencia`, en orden de llegada.
        Para que un cliente pida solo lo nuevo; luego lo muestra en orden lógico."""
        with closing(self._conectar()) as con:
            filas = con.execute(
                f"SELECT m.secuencia, {_COLUMNAS_MENSAJE} FROM mensajes m"
                " WHERE m.secuencia > ? ORDER BY m.secuencia",
                (secuencia,),
            )
            return [(fila["secuencia"], _a_mensaje(fila)) for fila in filas]

    def ultimo_lamport_visto(self) -> int:
        """El mayor `lamport` guardado; 0 si no hay mensajes (D16). Se calcula, no se
        guarda aparte, para que no pueda desincronizarse."""
        return self._uno("SELECT COALESCE(MAX(lamport), 0) FROM mensajes")[0]

    def leer_reloj(self) -> int:
        return self._uno("SELECT valor FROM estado WHERE clave = 'reloj'")[0]

    def leer_cursor_seq(self) -> int:
        """El último `seq` del central procesado en pull; 0 si todavía no hay (D27)."""
        return self._uno("SELECT valor FROM estado WHERE clave = 'cursor_seq'")[0]

    def contar_mensajes(self) -> int:
        return self._uno("SELECT COUNT(*) FROM mensajes")[0]

    def contar_pendientes(self) -> int:
        return self._uno("SELECT COUNT(*) FROM pendientes")[0]

    def pendientes_listos(self, ahora: float, limite: int = 50) -> list[Pendiente]:
        """Los pendientes cuyo próximo intento ya llegó, en orden de lamport."""
        with closing(self._conectar()) as con:
            filas = con.execute(
                f"SELECT {_COLUMNAS_MENSAJE}, p.intentos, p.proximo_intento"
                " FROM pendientes p JOIN mensajes m ON m.id = p.id"
                f" WHERE p.proximo_intento <= ? ORDER BY {_ORDEN_LOGICO} LIMIT ?",
                (ahora, limite),
            )
            return [
                Pendiente(_a_mensaje(fila), fila["intentos"], fila["proximo_intento"])
                for fila in filas
            ]

    def reprogramar_pendiente(self, id: str, intentos: int, proximo_intento: float) -> None:
        with self.transaccion() as tx:
            tx.reprogramar_pendiente(id, intentos, proximo_intento)

    def quitar_pendiente(self, id: str) -> None:
        with self.transaccion() as tx:
            tx.quitar_pendiente(id)

    def adelantar_pendientes(self, ahora: float) -> int:
        """Deja todos los pendientes listos ya (al volver el central). Devuelve cuántos."""
        with self.transaccion() as tx:
            return tx.adelantar_pendientes(ahora)

    # --- Internos ------------------------------------------------------------------------

    def _conectar(self) -> sqlite3.Connection:
        # isolation_level=None: nosotros decidimos dónde empieza y termina cada transacción.
        con = sqlite3.connect(self.ruta, timeout=5.0, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        return con

    def _uno(self, consulta: str, parametros: tuple[object, ...] = ()) -> sqlite3.Row | None:
        with closing(self._conectar()) as con:
            return con.execute(consulta, parametros).fetchone()


def _a_mensaje(fila: sqlite3.Row) -> Mensaje:
    return Mensaje.model_validate(
        {
            "id": fila["id"],
            "from": fila["remitente"],
            "origin": fila["origin"],
            "lamport": fila["lamport"],
            "sent_at": fila["sent_at"],
            "body": fila["body"],
        }
    )


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
