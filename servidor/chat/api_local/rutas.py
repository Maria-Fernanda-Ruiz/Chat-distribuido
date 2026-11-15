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

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from chat.contexto import ContextoDep
from chat.modelo import direccion, es_nombre_valido

router = APIRouter(prefix="/api", tags=["API local"])


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
