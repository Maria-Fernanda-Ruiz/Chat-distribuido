"""Experimento: pérdidas ante una caída (canvas CD-006, D29, #19).

Mientras gNb escribe en #general a una tasa fija, apaga gNa de golpe con `docker kill`,
la vuelve a prender y cuenta en su historial los mensajes perdidos y duplicados. Mide
también cuánto tarda gNa en arrancar y en ponerse al día.

Corre dentro del servicio `experimento` del compose local, con el socket de Docker
montado. Escribe una fila por corrida en resultados/perdidas.csv.
"""

import csv
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

URL_A = os.environ.get("URL_A", "http://servidor-a:8000")
URL_B = os.environ.get("URL_B", "http://servidor-b:8000")
SERVICIO_CAIDO = os.environ.get("SERVICIO_CAIDO", "servidor-a")
PROYECTO = os.environ.get("PROYECTO", "chat-local")
DURACIONES = [float(d) for d in os.environ.get("DURACIONES", "2,5,10").split(",")]
REPETICIONES = int(os.environ.get("REPETICIONES", "3"))
TASA = float(os.environ.get("TASA", "5"))  # mensajes por segundo

ANTES_S = 5.0        # se envía durante 5 s antes de la caída…
DESPUES_S = 5.0      # …y 5 s después de prender gNa (CD-006, R3)
ESPERA_MAX_S = 60.0  # si no se pone al día en 60 s, se anota lo que faltó (R5)
PAUSA_ENTRE_CORRIDAS_S = 3.0
USUARIO = "medidor"

RESULTADOS = Path(__file__).parent / "resultados"
CAMPOS = [
    "duracion_s", "repeticion", "enviados", "enviados_en_caida", "recibidos", "perdidos", "duplicados",
    "en_orden", "t_arranque_s", "t_al_dia_s",
]


# ------------------------------------------------------------ conteo (sin red)


def contar(enviados: list[str], historial: list[dict], etiqueta: str) -> dict:
    """Compara los textos enviados con el historial de gNa, solo para esta corrida.

    Cuenta por texto y no por id: un reintento que cambiara el id dejaría dos mensajes
    con el mismo texto, y eso es un duplicado (CD-006, enfoque). El historial llega en
    el orden lógico del servidor, (lamport, origin, id)."""
    prefijo = f"{etiqueta}-"
    textos = [m.get("body", "") for m in historial if m.get("body", "").startswith(prefijo)]
    veces = Counter(textos)
    recibidos = len(set(enviados) & set(veces))
    duplicados = sum(n - 1 for n in veces.values())

    # En orden si la primera aparición de cada mensaje sigue el número con que se envió.
    numeros = [int(t.rsplit("-", 1)[1]) for t in dict.fromkeys(textos)]
    return {
        "enviados": len(enviados),
        "recibidos": recibidos,
        "perdidos": len(enviados) - recibidos,
        "duplicados": duplicados,
        "en_orden": numeros == sorted(numeros),
    }


# ------------------------------------------------------------ HTTP y Docker


def pedir(url: str, datos: dict | None = None, timeout: float = 3.0):
    """GET (o POST con JSON si hay datos). Devuelve (código, cuerpo) o (None, None)."""
    cuerpo = json.dumps(datos).encode() if datos is not None else None
    peticion = urllib.request.Request(
        url, data=cuerpo, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(peticion, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, OSError, ValueError):
        return None, None


def contenedor_caido() -> str:
    """El id del contenedor de SERVICIO_CAIDO en PROYECTO; nunca otro (salvaguarda 3)."""
    salida = subprocess.run(
        ["docker", "ps", "-aq",
         "--filter", f"label=com.docker.compose.project={PROYECTO}",
         "--filter", f"label=com.docker.compose.service={SERVICIO_CAIDO}"],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    if len(salida) != 1:
        sys.exit(f"Se esperaba un contenedor de {SERVICIO_CAIDO} en {PROYECTO}, hay {len(salida)}")
    return salida[0]


def docker(accion: str, contenedor: str) -> None:
    subprocess.run(["docker", accion, contenedor], capture_output=True, check=True)


def esperar_salud(url: str, limite_s: float) -> bool:
    fin = time.monotonic() + limite_s
    while time.monotonic() < fin:
        codigo, _ = pedir(f"{url}/fed/health", timeout=1.0)
        if codigo == 200:
            return True
        time.sleep(0.1)
    return False


def historial_a() -> list[dict]:
    codigo, datos = pedir(f"{URL_A}/api/mensajes", timeout=3.0)
    return datos if codigo == 200 and isinstance(datos, list) else []


# ------------------------------------------------------------ una corrida


class Emisor(threading.Thread):
    """Envía desde gNb a TASA mensajes por segundo hasta que se le pide parar."""

    def __init__(self, etiqueta: str):
        super().__init__(daemon=True)
        self.etiqueta = etiqueta
        self.parar = threading.Event()
        self.enviados: list[tuple[str, float]] = []  # (texto, momento aceptado)

    def run(self) -> None:
        inicio = time.monotonic()
        n = 0
        while not self.parar.is_set():
            n += 1
            texto = f"{self.etiqueta}-{n:04d}"
            codigo, _ = pedir(f"{URL_B}/api/mensajes", {"usuario": USUARIO, "body": texto})
            if codigo == 201:
                self.enviados.append((texto, time.monotonic()))
            # Tasa fija: cada mensaje tiene su hora programada.
            espera = inicio + n / TASA - time.monotonic()
            if espera > 0:
                self.parar.wait(espera)


def esperar_hasta_tener(textos: set[str], desde: float) -> float | None:
    """Segundos desde `desde` hasta que gNa tiene todos `textos`; None si pasa el límite."""
    while time.monotonic() - desde < ESPERA_MAX_S:
        vistos = {m.get("body") for m in historial_a()}
        if textos <= vistos:
            return time.monotonic() - desde
        time.sleep(0.25)
    return None


def corrida(sello: str, duracion: float, repeticion: int, contenedor: str) -> dict:
    etiqueta = f"exp-{sello}-{duracion:g}s-r{repeticion}"
    emisor = Emisor(etiqueta)
    emisor.start()
    time.sleep(ANTES_S)

    docker("kill", contenedor)
    t_caida = time.monotonic()
    time.sleep(duracion)
    docker("start", contenedor)
    t_inicio = time.monotonic()

    if not esperar_salud(URL_A, ESPERA_MAX_S):
        emisor.parar.set()
        docker("start", contenedor)  # salvaguarda 4: no dejar gNa apagada
        sys.exit(f"{SERVICIO_CAIDO} no volvió a responder en {ESPERA_MAX_S:g} s")
    t_arranque = time.monotonic() - t_inicio

    # Ponerse al día: tener todo lo que se envió mientras gNa estaba apagada.
    durante = {t for t, momento in emisor.enviados if t_caida <= momento <= t_inicio}
    t_al_dia = esperar_hasta_tener(durante, t_inicio)

    restante = t_inicio + DESPUES_S - time.monotonic()
    if restante > 0:
        time.sleep(restante)
    emisor.parar.set()
    emisor.join()

    enviados = [t for t, _ in emisor.enviados]
    esperar_hasta_tener(set(enviados), time.monotonic())
    fila = {"duracion_s": f"{duracion:g}", "repeticion": repeticion}
    fila |= contar(enviados, historial_a(), etiqueta)
    fila["enviados_en_caida"] = len(durante)
    fila["t_arranque_s"] = f"{t_arranque:.2f}"
    fila["t_al_dia_s"] = f"{t_al_dia:.2f}" if t_al_dia is not None else ""
    return fila


# ------------------------------------------------------------ todas las corridas


def main() -> None:
    for url in (URL_A, URL_B):
        if not esperar_salud(url, 30):
            sys.exit(f"{url} no responde: levanta antes el central y los dos servidores")
    codigo, _ = pedir(f"{URL_B}/api/usuarios", {"nombre": USUARIO})
    if codigo not in (201, 409):  # 409: ya existe, sirve igual
        sys.exit(f"No se pudo crear el usuario {USUARIO} en gNb (respuesta {codigo})")

    contenedor = contenedor_caido()
    sello = time.strftime("%H%M%S")  # separa esta ejecución de las anteriores
    RESULTADOS.mkdir(exist_ok=True)
    archivo = RESULTADOS / "perdidas.csv"
    print(f"{len(DURACIONES) * REPETICIONES} corridas, {TASA:g} mensajes/s, caídas de "
          f"{', '.join(f'{d:g}' for d in DURACIONES)} s → {archivo}")

    with archivo.open("w", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=CAMPOS)
        escritor.writeheader()
        for duracion in DURACIONES:
            for repeticion in range(1, REPETICIONES + 1):
                fila = corrida(sello, duracion, repeticion, contenedor)
                escritor.writerow(fila)
                f.flush()  # si algo falla, quedan las corridas ya hechas
                print(f"caída {fila['duracion_s']:>3} s · rep {repeticion}: "
                      f"enviados {fila['enviados']} ({fila['enviados_en_caida']} en la caída), perdidos {fila['perdidos']}, "
                      f"duplicados {fila['duplicados']}, en orden {fila['en_orden']}, "
                      f"arranque {fila['t_arranque_s']} s, al día {fila['t_al_dia_s'] or '—'} s")
                time.sleep(PAUSA_ENTRE_CORRIDAS_S)


if __name__ == "__main__":
    main()
