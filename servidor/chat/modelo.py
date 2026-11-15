"""Mensaje del protocolo y nombres de usuario (análisis, sección 2; D12).

Estrictos al enviar y tolerantes al recibir (análisis, sección 1). `Mensaje` solo exige
lo imprescindible para deduplicar, ordenar y mostrar: `id`, `from`, `origin` y
`lamport`. Los campos desconocidos se ignoran sin error. Los mensajes nuestros se crean
con `Mensaje.nuevo`, que sí cumple el formato al pie de la letra.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

# D12: hasta 20 caracteres entre minúsculas, números, '_' y '-', para que
# `nombre@gN` sea válido en cualquier grupo.
PATRON_NOMBRE_USUARIO = re.compile(r"^[a-z0-9_-]{1,20}$")

# Tope de `lamport` al recibir: deja margen para max(local, recibido) + 1 sin salirse
# del entero de 64 bits de SQLite (análisis, sección 2).
LAMPORT_MAXIMO = 2**62


def es_nombre_valido(nombre: str) -> bool:
    return PATRON_NOMBRE_USUARIO.fullmatch(nombre) is not None


def direccion(nombre: str, grupo: str) -> str:
    """Cómo se escribe un usuario en el protocolo: `ana@g3`."""
    return f"{nombre}@{grupo}"


def ahora_iso() -> str:
    """Hora UTC en el formato de `sent_at`: `2026-11-10T14:03:22Z`."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Mensaje(BaseModel):
    """Un mensaje de `#general`, tal como viaja entre servidores (enunciado, sección 4)."""

    model_config = ConfigDict(
        extra="ignore",
        frozen=True,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
    )

    id: str = Field(min_length=1, max_length=100)
    # En el JSON es "from", pero `from` es palabra reservada de Python.
    from_: str = Field(alias="from", min_length=1, max_length=100)
    origin: str = Field(min_length=1, max_length=50)
    lamport: int = Field(ge=0, le=LAMPORT_MAXIMO)
    # Informativo: se guarda como viene y nunca se usa para ordenar.
    sent_at: str = Field(default="", max_length=64)
    body: str = Field(default="", max_length=10_000)

    @classmethod
    def nuevo(cls, *, usuario: str, grupo: str, lamport: int, body: str) -> Mensaje:
        """Crea un mensaje de un usuario nuestro con un `id` nuevo. El reloj ya debe haber
        subido: `lamport` es el valor después de incrementarlo (análisis, sección 5)."""
        if not es_nombre_valido(usuario):
            raise ValueError(f"Nombre de usuario inválido: {usuario!r}")
        return cls(
            id=str(uuid.uuid4()),
            from_=direccion(usuario, grupo),
            origin=grupo,
            lamport=lamport,
            sent_at=ahora_iso(),
            body=body,
        )

    def a_json(self) -> dict[str, object]:
        """El mensaje como lo espera el protocolo, con "from"; listo para httpx."""
        return self.model_dump(mode="json")
