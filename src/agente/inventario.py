"""Inventario y sondeo de los videos del laboratorio.

Antes de medir nada hay que saber que tenemos. Este modulo:

  1. Parsea el nombre de cada video -> objeto, condicion, repeticion.
  2. Lee los metadatos del contenedor (fps declarado, resolucion, n frames).
  3. Verifica si el framerate es REAL o si el video es VFR (framerate variable),
     leyendo el timestamp de cada frame.

El punto 3 es el que importa. Los celulares graban a framerate variable y
cv2.CAP_PROP_FPS devuelve un valor nominal. Si asumimos t = frame/fps sobre un
video VFR, todo el eje temporal queda deformado y los graficos igual se ven
lindos: el error no avisa.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2

RAIZ = Path(__file__).resolve().parents[2]
CARPETA_VIDEOS = (
    RAIZ
    / "src"
    / "Fuerza de Rozamiento-videos"
    / "Fuerza de Rozamiento"
    / "Videos Proyecto mp4 120fps"
)
SALIDA = RAIZ / "datos" / "inventario.csv"

# "Tapa 4Libros Video1.mp4" / "Jabon Angulo Critico Video2.mp4"
PATRON = re.compile(
    r"^(?P<objeto>Tapa|Esponja|Jabon)\s+"
    r"(?P<condicion>\d+Libros|Angulo Critico)\s+"
    r"Video(?P<repeticion>\d+)\.mp4$",
    re.IGNORECASE,
)

# nombre de carpeta/archivo -> clave en datos/referencia/laboratorio.json
OBJETO_A_CLAVE = {"tapa": "objeto_1", "esponja": "objeto_2", "jabon": "objeto_3"}
CONDICION_A_CLAVE = {
    "4libros": "angulo_1",
    "3libros": "angulo_2",
    "2libros": "angulo_3",
    "angulo critico": "critico",
}


@dataclass
class FichaVideo:
    archivo: str
    objeto: str
    objeto_clave: str
    condicion: str
    angulo_clave: str
    repeticion: int
    ancho: int
    alto: int
    n_frames: int
    fps_declarado: float
    duracion_s: float
    # --- verificacion temporal ---
    fps_medido: float | None = None
    dt_mediano_ms: float | None = None
    dt_min_ms: float | None = None
    dt_max_ms: float | None = None
    jitter_relativo: float | None = None
    es_vfr: bool | None = None
    nota: str = ""


def parsear_nombre(ruta: Path) -> tuple[str, str, int] | None:
    m = PATRON.match(ruta.name)
    if not m:
        return None
    return (
        m.group("objeto").lower(),
        m.group("condicion").lower(),
        int(m.group("repeticion")),
    )


def leer_timestamps(ruta: Path) -> list[float]:
    """Timestamp (ms) de cada frame, usando grab() que no decodifica el bitmap."""
    cap = cv2.VideoCapture(str(ruta))
    ts: list[float] = []
    try:
        while cap.grab():
            ts.append(cap.get(cv2.CAP_PROP_POS_MSEC))
    finally:
        cap.release()
    return ts


def sondear(ruta: Path, verificar_tiempo: bool = True) -> FichaVideo | None:
    partes = parsear_nombre(ruta)
    if partes is None:
        return None
    objeto, condicion, repeticion = partes

    cap = cv2.VideoCapture(str(ruta))
    if not cap.isOpened():
        return None
    try:
        ancho = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        alto = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps_declarado = float(cap.get(cv2.CAP_PROP_FPS))
    finally:
        cap.release()

    ficha = FichaVideo(
        archivo=ruta.name,
        objeto=objeto,
        objeto_clave=OBJETO_A_CLAVE[objeto],
        condicion=condicion,
        angulo_clave=CONDICION_A_CLAVE[condicion],
        repeticion=repeticion,
        ancho=ancho,
        alto=alto,
        n_frames=n_frames,
        fps_declarado=round(fps_declarado, 4),
        duracion_s=round(n_frames / fps_declarado, 4) if fps_declarado else 0.0,
    )

    if not verificar_tiempo:
        return ficha

    ts = leer_timestamps(ruta)
    if len(ts) < 3:
        ficha.nota = "muy pocos frames para verificar el tiempo"
        return ficha

    deltas = [b - a for a, b in zip(ts, ts[1:]) if b > a]
    if not deltas:
        ficha.nota = "el contenedor no expone timestamps por frame"
        return ficha

    dt_med = statistics.median(deltas)
    ficha.fps_medido = round(1000.0 / dt_med, 4) if dt_med else None
    ficha.dt_mediano_ms = round(dt_med, 4)
    ficha.dt_min_ms = round(min(deltas), 4)
    ficha.dt_max_ms = round(max(deltas), 4)
    # jitter: cuanto se aparta el peor frame del espaciado tipico
    ficha.jitter_relativo = round(max(abs(d - dt_med) for d in deltas) / dt_med, 4)
    # criterio: mas de 5% de desvio en algun frame -> framerate no uniforme
    ficha.es_vfr = ficha.jitter_relativo > 0.05
    ficha.nota = "VFR: no usar t=frame/fps" if ficha.es_vfr else "CFR"
    return ficha


def construir(carpeta: Path, verificar_tiempo: bool = True) -> list[FichaVideo]:
    fichas = []
    sin_parsear = []
    archivos = sorted(carpeta.glob("*.mp4"))
    for i, ruta in enumerate(archivos, 1):
        print(f"  [{i:>2}/{len(archivos)}] {ruta.name}", flush=True)
        ficha = sondear(ruta, verificar_tiempo)
        if ficha is None:
            sin_parsear.append(ruta.name)
        else:
            fichas.append(ficha)
    if sin_parsear:
        print(f"\n[!] No se pudieron interpretar {len(sin_parsear)} archivos:")
        for n in sin_parsear:
            print(f"    {n}")
    return fichas


def resumir(fichas: list[FichaVideo]) -> None:
    print(f"\n{'=' * 70}\nRESUMEN\n{'=' * 70}")
    print(f"Videos: {len(fichas)}")

    print("\nPor objeto y condicion:")
    combos: dict[tuple[str, str], int] = {}
    for f in fichas:
        combos[(f.objeto, f.condicion)] = combos.get((f.objeto, f.condicion), 0) + 1
    for (obj, cond), n in sorted(combos.items()):
        print(f"  {obj:8s} {cond:15s} {n} repeticiones")

    resoluciones = {(f.ancho, f.alto) for f in fichas}
    print(f"\nResoluciones: {resoluciones}")

    declarados = {f.fps_declarado for f in fichas}
    print(f"fps declarados por el contenedor: {sorted(declarados)}")

    medidos = [f.fps_medido for f in fichas if f.fps_medido]
    if medidos:
        print(
            f"fps medidos de timestamps: min={min(medidos):.2f} "
            f"max={max(medidos):.2f} mediana={statistics.median(medidos):.2f}"
        )

    vfr = [f for f in fichas if f.es_vfr]
    print(f"\nVideos con framerate NO uniforme (VFR): {len(vfr)} de {len(fichas)}")
    if vfr:
        print("  -> para estos hay que usar los timestamps, no t = frame/fps")
        for f in sorted(vfr, key=lambda x: -(x.jitter_relativo or 0))[:8]:
            print(
                f"     {f.archivo:38s} jitter={f.jitter_relativo:.1%} "
                f"dt: {f.dt_min_ms:.1f}-{f.dt_max_ms:.1f} ms"
            )

    duraciones = [f.duracion_s for f in fichas]
    print(
        f"\nDuraciones: min={min(duraciones):.2f}s max={max(duraciones):.2f}s "
        f"mediana={statistics.median(duraciones):.2f}s"
    )
    cortos = [f for f in fichas if f.duracion_s < 0.5]
    if cortos:
        print(f"[!] {len(cortos)} videos duran menos de 0.5 s:")
        for f in cortos:
            print(f"    {f.archivo} ({f.duracion_s:.2f}s, {f.n_frames} frames)")


def guardar(fichas: list[FichaVideo], salida: Path) -> None:
    salida.parent.mkdir(parents=True, exist_ok=True)
    with salida.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(fichas[0]).keys()))
        w.writeheader()
        for ficha in fichas:
            w.writerow(asdict(ficha))
    print(f"\nInventario -> {salida.relative_to(RAIZ)}")

    resumen = salida.with_suffix(".json")
    with resumen.open("w", encoding="utf-8") as f:
        json.dump([asdict(x) for x in fichas], f, indent=2, ensure_ascii=False)
    print(f"Inventario -> {resumen.relative_to(RAIZ)}")


def main() -> None:
    p = argparse.ArgumentParser(description="Inventario de los videos del laboratorio")
    p.add_argument("--carpeta", type=Path, default=CARPETA_VIDEOS)
    p.add_argument("--salida", type=Path, default=SALIDA)
    p.add_argument(
        "--rapido",
        action="store_true",
        help="saltear la verificacion de timestamps (solo metadatos)",
    )
    args = p.parse_args()

    if not args.carpeta.is_dir():
        raise SystemExit(f"No existe la carpeta: {args.carpeta}")

    print(f"Sondeando {args.carpeta.name}/\n")
    fichas = construir(args.carpeta, verificar_tiempo=not args.rapido)
    if not fichas:
        raise SystemExit("No se encontro ningun video interpretable")
    resumir(fichas)
    guardar(fichas, args.salida)


if __name__ == "__main__":
    main()
