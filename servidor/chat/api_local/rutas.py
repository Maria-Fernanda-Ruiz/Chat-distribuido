"""API local: lo que usa nuestro cliente (Maria Fernanda, #20–#23).

La API entre el cliente y nuestro servidor es libre (enunciado, sección 2). Aquí van,
con el prefijo /api:

- crear y listar usuarios del grupo, sin contraseña y con el nombre validado por D12 (#20);
- enviar un mensaje a #general: el reloj sube, el mensaje se guarda y entra a
  pendientes en una sola transacción (análisis, sección 5) (#21);
- leer el historial de #general, ordenado por (lamport, origin) (#22);

y el cliente web mínimo servido por este mismo FastAPI (#23, D07).

Antes de programar: el canvas CD-003, sobre los contratos de CD-002.
"""

import time
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from chat.contexto import ContextoDep
from chat.eventos import Evento, registrar
from chat.federacion.reloj import tick
from chat.modelo import LAMPORT_MAXIMO, Mensaje, direccion, es_nombre_valido

router = APIRouter(prefix="/api", tags=["API local"])
# El cliente web va sin el prefijo /api, en la raíz (D23).
router_cliente = APIRouter(tags=["Cliente web"])

# D22: el texto de un mensaje va de 1 a 1 000 caracteres.
LARGO_MAXIMO_BODY = 1000


# ---------------------------------------------------------------- usuarios (#20)


class UsuarioNuevo(BaseModel):
    """Lo que manda el cliente para crear un usuario: solo el nombre corto (D12)."""

    nombre: str


class UsuarioSalida(BaseModel):
    """Un usuario del grupo: su nombre y cómo se escribe en el protocolo (`ana@g3`)."""

    nombre: str
    direccion: str


def _usuario_salida(nombre: str, grupo: str) -> UsuarioSalida:
    return UsuarioSalida(nombre=nombre, direccion=direccion(nombre, grupo))


@router.post("/usuarios", status_code=status.HTTP_201_CREATED)
def crear_usuario(datos: UsuarioNuevo, ctx: ContextoDep) -> UsuarioSalida:
    """Crea un usuario del grupo. 422 si el nombre no cumple D12 y 409 si ya existe (D18)."""
    if not es_nombre_valido(datos.nombre):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"El nombre «{datos.nombre}» no es válido: usa de 1 a 20 caracteres "
                "entre minúsculas, números, _ y -"
            ),
        )
    # El repetido se detecta con lo que devuelve la base y no consultando antes:
    # entre consultar e insertar podría entrar otra petición con el mismo nombre.
    if not ctx.almacen.crear_usuario(datos.nombre):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El usuario «{datos.nombre}» ya existe en {ctx.config.grupo}",
        )
    return _usuario_salida(datos.nombre, ctx.config.grupo)


@router.get("/usuarios")
def listar_usuarios(ctx: ContextoDep) -> list[UsuarioSalida]:
    """Los usuarios del grupo, en orden alfabético."""
    return [_usuario_salida(nombre, ctx.config.grupo) for nombre in ctx.almacen.listar_usuarios()]


# ---------------------------------------------------------------- enviar (#21)


class MensajeNuevo(BaseModel):
    """Lo que manda el cliente para escribir en #general: quién y qué.

    El `id`, el `origin`, el `lamport` y el `sent_at` no se aceptan: los pone el
    servidor (salvaguarda 1). Si el cliente los manda, se ignoran."""

    usuario: str
    body: str


@router.post("/mensajes", status_code=status.HTTP_201_CREATED)
def enviar_mensaje(datos: MensajeNuevo, ctx: ContextoDep) -> dict[str, Any]:
    """Escribe un mensaje en #general. 404 si el usuario no existe (D21) y 422 si el
    texto está vacío, tiene solo espacios o pasa de 1 000 caracteres (D22).

    Subir el reloj, guardar el mensaje y dejarlo en pendientes pasan en una sola
    transacción (salvaguarda 3): si algo falla, no queda ninguna de las tres cosas. No
    se llama al central: el envío lo hace la tarea de fondo de federación (#14)."""
    if not ctx.almacen.existe_usuario(datos.usuario):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"El usuario «{datos.usuario}» no existe en {ctx.config.grupo}: "
                "créalo antes de escribir"
            ),
        )
    if not datos.body.strip() or len(datos.body) > LARGO_MAXIMO_BODY:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"El mensaje no es válido: escribe de 1 a {LARGO_MAXIMO_BODY} caracteres "
                f"(tiene {len(datos.body)}) y que no sean solo espacios"
            ),
        )
    with ctx.almacen.transaccion() as tx:
        mensaje = Mensaje.nuevo(
            usuario=datos.usuario, grupo=ctx.config.grupo, lamport=tick(tx), body=datos.body
        )
        tx.guardar_mensaje_si_no_existe(mensaje)
        tx.encolar_pendiente(mensaje.id, proximo_intento=time.time())
    # Se registra después de confirmar la transacción, para no anotar algo que se deshizo.
    registrar(Evento.ENCOLADO, mensaje)
    return mensaje.a_json()


# ---------------------------------------------------------------- historial (#22)


@router.get("/mensajes")
def leer_historial(
    ctx: ContextoDep,
    desde_lamport: Annotated[str | None, Query()] = None,
) -> list[dict[str, Any]]:
    """El historial de #general en orden lógico, (lamport, origin, id), propios y de otros
    grupos. Con `desde_lamport=N`, solo los mensajes con marca mayor que N (D19).

    `sent_at` viaja en la respuesta para que el cliente lo muestre, pero nunca se usa
    para ordenar."""
    if desde_lamport is None:
        mensajes = ctx.almacen.listar_historial()
    else:
        mensajes = ctx.almacen.listar_historial_desde_lamport(_lamport_valido(desde_lamport))
    return [m.a_json() for m in mensajes]


def _lamport_valido(texto: str) -> int:
    """`desde_lamport` debe ser un entero entre 0 y el máximo del protocolo; si no, 422.

    Se recibe como texto y se valida aquí para responder el error en español (canvas
    CD-003, enfoque 2) en vez de la lista en inglés que arma FastAPI."""
    try:
        valor = int(texto)
    except ValueError:
        valor = -1
    if not 0 <= valor <= LAMPORT_MAXIMO:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"desde_lamport «{texto}» no es válido: usa un entero mayor o igual a 0",
        )
    return valor


# ---------------------------------------------------------------- cliente web (#23)

INDEX_HTML = Path(__file__).parent / "estatico" / "index.html"


@router_cliente.get("/", include_in_schema=False)
def cliente_web() -> FileResponse:
    """El cliente web mínimo: un solo archivo con HTML, CSS y JS, sin librerías (D07, D23)."""
    return FileResponse(INDEX_HTML, media_type="text/html")
