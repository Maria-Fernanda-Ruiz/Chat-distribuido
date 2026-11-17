"""Configuración del servidor, leída de variables de entorno (análisis, sección 9; D10).

Es el único módulo que conoce los nombres de las variables. El resto del código recibe
una `Configuracion` ya validada y nunca lee `os.environ`.

Una variable vacía cuenta como no definida y toma su valor por defecto. Así,
`docker-compose.yml` puede pasar todas las variables aunque el `.env` deje algunas sin
llenar.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

PATRON_GRUPO = re.compile(r"^[A-Za-z0-9_-]{1,20}$")
VALORES_VERDADEROS = {"1", "true", "si", "sí", "yes"}
VALORES_FALSOS = {"0", "false", "no"}
# D27: en pull consultamos al central; en push el central nos llama a /fed/messages.
MODOS_RECEPCION = ("pull", "push")


class ErrorDeConfiguracion(Exception):
    """La configuración no es válida. `problemas` trae una línea por cada error."""

    def __init__(self, problemas: list[str]) -> None:
        super().__init__("\n".join(problemas))
        self.problemas = problemas

    def explicacion(self) -> str:
        """Texto para la persona que levanta el servidor: qué falla y dónde se arregla."""
        lineas = ["Configuración inválida; el servidor no arranca:"]
        lineas += [f"  - {problema}" for problema in self.problemas]
        lineas.append(
            "Revise el archivo .env; la plantilla con cada variable explicada está en .env.example."
        )
        return "\n".join(lineas)


@dataclass(frozen=True)
class Configuracion:
    """Parámetros del servidor. Los valores por defecto son los de D10."""

    grupo: str
    url_publica: str
    url_central: str
    heartbeat_intervalo_s: float = 5.0
    heartbeat_fallos_para_caido: int = 3
    registro_intervalo_s: float = 30.0
    backoff_base_s: float = 1.0
    backoff_max_s: float = 30.0
    http_timeout_s: float = 3.0
    ruta_bd: str = "/datos/chat.db"
    puerto: int = 8000
    log_accesos: bool = False
    modo_recepcion: str = "pull"
    pull_intervalo_s: float = 1.5


def cargar_configuracion(entorno: Mapping[str, str]) -> Configuracion:
    """Lee y valida todas las variables. Si algo falla, informa todos los problemas juntos."""
    lector = _Lector(entorno)
    modo = lector.opcion("MODO_RECEPCION", MODOS_RECEPCION, "pull")
    config = Configuracion(
        grupo=lector.grupo("GRUPO"),
        # Solo en push el central nos llama, así que solo ahí hace falta la URL (D27).
        url_publica=lector.url(
            "URL_PUBLICA",
            "URL con la que el central llega a este servidor; obligatoria con MODO_RECEPCION=push",
            obligatoria=modo == "push",
        ),
        url_central=lector.url("URL_CENTRAL", "URL del servidor central del curso"),
        heartbeat_intervalo_s=lector.segundos("HEARTBEAT_INTERVALO_S", 5.0),
        heartbeat_fallos_para_caido=lector.entero("HEARTBEAT_FALLOS_PARA_CAIDO", 3, minimo=1),
        registro_intervalo_s=lector.segundos("REGISTRO_INTERVALO_S", 30.0),
        backoff_base_s=lector.segundos("BACKOFF_BASE_S", 1.0),
        backoff_max_s=lector.segundos("BACKOFF_MAX_S", 30.0),
        http_timeout_s=lector.segundos("HTTP_TIMEOUT_S", 3.0),
        ruta_bd=lector.texto("RUTA_BD", "/datos/chat.db"),
        puerto=lector.entero("PUERTO", 8000, minimo=1, maximo=65535),
        log_accesos=lector.booleano("LOG_ACCESOS", False),
        modo_recepcion=modo,
        pull_intervalo_s=lector.segundos("PULL_INTERVALO_S", 1.5),
    )
    if config.backoff_max_s < config.backoff_base_s:
        lector.problemas.append(
            f"BACKOFF_MAX_S ({config.backoff_max_s:g}) no puede ser menor que "
            f"BACKOFF_BASE_S ({config.backoff_base_s:g})."
        )
    if lector.problemas:
        raise ErrorDeConfiguracion(lector.problemas)
    return config


class _Lector:
    """Lee variables una por una y acumula los problemas en lugar de fallar en el primero."""

    def __init__(self, entorno: Mapping[str, str]) -> None:
        self.entorno = entorno
        self.problemas: list[str] = []

    def _valor(self, nombre: str) -> str | None:
        valor = self.entorno.get(nombre, "").strip()
        return valor or None

    def grupo(self, nombre: str) -> str:
        valor = self._valor(nombre)
        if valor is None:
            self.problemas.append(
                f"Falta {nombre}: nombre de este servidor en el central, por ejemplo g3."
            )
            return ""
        if not PATRON_GRUPO.fullmatch(valor):
            self.problemas.append(
                f"{nombre} solo admite letras, números, '_' y '-', hasta 20 caracteres "
                f"(llegó {valor!r})."
            )
        return valor

    def url(self, nombre: str, que_es: str, *, obligatoria: bool = True) -> str:
        valor = self._valor(nombre)
        if valor is None:
            if obligatoria:
                self.problemas.append(f"Falta {nombre}: {que_es}.")
            return ""
        partes = urlsplit(valor)
        if partes.scheme not in ("http", "https") or not partes.netloc:
            self.problemas.append(
                f"{nombre} debe ser una URL que empiece con http:// o https:// (llegó {valor!r})."
            )
        return valor.rstrip("/")

    def texto(self, nombre: str, por_defecto: str) -> str:
        return self._valor(nombre) or por_defecto

    def segundos(self, nombre: str, por_defecto: float) -> float:
        valor = self._valor(nombre)
        if valor is None:
            return por_defecto
        try:
            numero = float(valor)
        except ValueError:
            self.problemas.append(f"{nombre} debe ser un número de segundos (llegó {valor!r}).")
            return por_defecto
        if not math.isfinite(numero) or numero <= 0:
            self.problemas.append(f"{nombre} debe ser mayor que 0 (llegó {valor!r}).")
            return por_defecto
        return numero

    def entero(
        self, nombre: str, por_defecto: int, *, minimo: int, maximo: int | None = None
    ) -> int:
        valor = self._valor(nombre)
        if valor is None:
            return por_defecto
        try:
            numero = int(valor)
        except ValueError:
            self.problemas.append(f"{nombre} debe ser un número entero (llegó {valor!r}).")
            return por_defecto
        if numero < minimo or (maximo is not None and numero > maximo):
            rango = f"entre {minimo} y {maximo}" if maximo is not None else f"al menos {minimo}"
            self.problemas.append(f"{nombre} debe ser {rango} (llegó {valor!r}).")
            return por_defecto
        return numero

    def opcion(self, nombre: str, opciones: tuple[str, ...], por_defecto: str) -> str:
        valor = self._valor(nombre)
        if valor is None:
            return por_defecto
        if valor.lower() in opciones:
            return valor.lower()
        self.problemas.append(
            f"{nombre} debe ser {' o '.join(opciones)} (llegó {valor!r})."
        )
        return por_defecto

    def booleano(self, nombre: str, por_defecto: bool) -> bool:
        valor = self._valor(nombre)
        if valor is None:
            return por_defecto
        if valor.lower() in VALORES_VERDADEROS:
            return True
        if valor.lower() in VALORES_FALSOS:
            return False
        self.problemas.append(f"{nombre} debe ser true o false (llegó {valor!r}).")
        return por_defecto
