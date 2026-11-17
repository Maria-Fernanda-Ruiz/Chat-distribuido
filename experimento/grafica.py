"""Gráfica y tabla resumen del experimento (canvas CD-006, operación 4).

Lee resultados/perdidas.csv y escribe resultados/grafica.png y resultados/resumen.md.
No cambia ningún dato: solo los agrupa por duración de la caída (salvaguarda 1).
"""

import csv
from pathlib import Path
from statistics import mean

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RESULTADOS = Path(__file__).parent / "resultados"
AZUL, NARANJA, ROJO, GRIS = "#2563eb", "#d97706", "#b91c1c", "#9ca3af"


def leer() -> list[dict]:
    with (RESULTADOS / "perdidas.csv").open() as f:
        return list(csv.DictReader(f))


def por_duracion(filas: list[dict]) -> dict[float, list[dict]]:
    grupos: dict[float, list[dict]] = {}
    for fila in filas:
        grupos.setdefault(float(fila["duracion_s"]), []).append(fila)
    return dict(sorted(grupos.items()))


def segundos(filas: list[dict], campo: str) -> list[float]:
    return [float(f[campo]) for f in filas if f[campo]]


def grafica(grupos: dict[float, list[dict]]) -> None:
    duraciones = list(grupos)
    etiquetas = [f"{d:g} s" for d in duraciones]
    x = range(len(duraciones))
    fig, (izq, der) = plt.subplots(1, 2, figsize=(11, 4.5))

    # Izquierda: mensajes por corrida (media de las repeticiones).
    ancho = 0.2
    series = [("enviados", "Enviados por gNb", AZUL), ("recibidos", "Recibidos en gNa", NARANJA),
              ("perdidos", "Perdidos", ROJO), ("duplicados", "Duplicados", GRIS)]
    for i, (campo, nombre, color) in enumerate(series):
        valores = [mean(int(f[campo]) for f in grupos[d]) for d in duraciones]
        barras = izq.bar([p + (i - 1.5) * ancho for p in x], valores, ancho, label=nombre, color=color)
        izq.bar_label(barras, fmt="%.0f", fontsize=8)
    izq.set_xticks(list(x), etiquetas)
    izq.set_xlabel("Duración de la caída de gNa")
    izq.set_ylabel("Mensajes por corrida (media)")
    izq.set_title("Mensajes perdidos y duplicados")
    izq.legend(fontsize=8, frameon=False)

    # Derecha: tiempo para ponerse al día, cada repetición y la media.
    for i, d in enumerate(duraciones):
        al_dia = segundos(grupos[d], "t_al_dia_s")
        arranque = segundos(grupos[d], "t_arranque_s")
        der.scatter([i] * len(arranque), arranque, color=GRIS, s=25,
                    label="Arranque (cada repetición)" if i == 0 else None)
        der.scatter([i] * len(al_dia), al_dia, color=AZUL, s=25,
                    label="Al día (cada repetición)" if i == 0 else None)
        if al_dia:
            der.hlines(mean(al_dia), i - 0.2, i + 0.2, color=AZUL, linewidth=2,
                       label="Al día (media)" if i == 0 else None)
    der.set_xticks(list(x), etiquetas)
    der.set_xlabel("Duración de la caída de gNa")
    der.set_ylabel("Segundos desde que se prende gNa")
    der.set_ylim(bottom=0)
    der.set_title("Tiempo para ponerse al día")
    der.legend(fontsize=8, frameon=False)

    for eje in (izq, der):
        eje.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(RESULTADOS / "grafica.png", dpi=200)


def resumen(filas: list[dict], grupos: dict[float, list[dict]]) -> None:
    def rango(valores: list[float]) -> str:
        if not valores:
            return "—"
        return f"{mean(valores):.2f} ({min(valores):.2f}–{max(valores):.2f})"

    lineas = [
        "# Resultados: pérdidas ante una caída",
        "",
        "Datos de `perdidas.csv`, tal como salieron de `medir.py` (canvas CD-006). Tiempos en "
        "segundos desde que se prende gNa: media (mínimo–máximo).",
        "",
        "| Caída | Corridas | Enviados | En la caída | Perdidos | Duplicados | En orden | Arranque (s) | Al día (s) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for d, g in grupos.items():
        lineas.append(
            f"| {d:g} s | {len(g)} | {sum(int(f['enviados']) for f in g)} "
            f"| {sum(int(f['enviados_en_caida']) for f in g)} "
            f"| {sum(int(f['perdidos']) for f in g)} | {sum(int(f['duplicados']) for f in g)} "
            f"| {sum(f['en_orden'] == 'True' for f in g)} de {len(g)} "
            f"| {rango(segundos(g, 't_arranque_s'))} | {rango(segundos(g, 't_al_dia_s'))} |"
        )
    lineas += ["", "## Cada corrida", "",
               "| Caída | Repetición | Enviados | En la caída | Recibidos | Perdidos | Duplicados | En orden | Arranque (s) | Al día (s) |",
               "|---|---|---|---|---|---|---|---|---|---|"]
    for f in filas:
        lineas.append(
            f"| {f['duracion_s']} s | {f['repeticion']} | {f['enviados']} | {f['enviados_en_caida']} | {f['recibidos']} "
            f"| {f['perdidos']} | {f['duplicados']} | {'sí' if f['en_orden'] == 'True' else 'no'} "
            f"| {f['t_arranque_s']} | {f['t_al_dia_s'] or 'no se puso al día en 60 s'} |"
        )
    (RESULTADOS / "resumen.md").write_text("\n".join(lineas) + "\n")


def main() -> None:
    filas = leer()
    grupos = por_duracion(filas)
    grafica(grupos)
    resumen(filas, grupos)
    print(f"Listo: {RESULTADOS / 'grafica.png'} y {RESULTADOS / 'resumen.md'}")


if __name__ == "__main__":
    main()
