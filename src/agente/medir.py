"""Mide una corrida de punta a punta: video -> aceleracion -> diagnostico.

    python src/agente/medir.py "Tapa 4Libros Video1.mp4"

El calculo esta en analizar_corrida(), que no imprime nada y devuelve TODO lo
que produjo (series incluidas). medir() le pone el resumen de texto encima y
el visor grafica lo mismo. Asi la ventana y la linea de comandos recorren
exactamente el mismo camino, en vez de tener dos orquestaciones que se van
separando con el tiempo.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from uncertainties import ufloat

from calibracion import calibrar, verificar_escala
from cinematica import analizar
from referencia import cargar as cargar_referencia
from tracking import (
    PERFILES,
    proyectar,
    recortar_fuera_de_rampa,
    seguir,
    sigma_posicion,
    ventana_deslizamiento,
)
import fisica
from inventario import CARPETA_VIDEOS, OBJETO_A_CLAVE, parsear_nombre

RAIZ = Path(__file__).resolve().parents[2]
FPS = 120.0

CONDICION_A_ANGULO = {"4libros": "angulo_1", "3libros": "angulo_2", "2libros": "angulo_3"}


class ErrorMedicion(RuntimeError):
    """La corrida no se puede medir. Lleva un mensaje para mostrarle al usuario."""


@dataclass
class Corrida:
    """Todo lo que produjo una medicion, ya calculado.

    Existe para que nadie tenga que volver a abrir el video: el resumen de
    texto, los graficos y el overlay de la trayectoria salen todos de aca.
    """

    ruta: Path
    objeto: str
    condicion: str
    repeticion: int
    # calibracion
    cal: Any
    chequeo_escala: dict
    # seguimiento
    tray: Any
    frames: np.ndarray
    s_px: np.ndarray
    n_px: np.ndarray
    i0: int
    i1: int
    sigma_px: float
    sigma_s_m: float
    motivo_fin: str
    # cinematica
    t: np.ndarray
    s_m: np.ndarray
    cin: Any
    aceleracion: Any
    # fisica
    theta: Any | None
    mu_estatico: Any | None
    diagnostico: Any | None

    @property
    def recorrido_cm(self) -> float:
        return 100.0 * (self.s_m[-1] - self.s_m[0])

    @property
    def duracion_s(self) -> float:
        return float(self.t[-1] - self.t[0])

    @property
    def es_angulo_critico(self) -> bool:
        return self.condicion not in CONDICION_A_ANGULO


def analizar_corrida(ruta: Path) -> Corrida:
    """Video -> aceleracion y diagnostico. No imprime: devuelve todo."""
    partes = parsear_nombre(ruta)
    if partes is None:
        raise ErrorMedicion(f"Nombre no interpretable: {ruta.name}")
    objeto, condicion, repeticion = partes

    ref = cargar_referencia()

    cap = cv2.VideoCapture(str(ruta))
    ok, frame0 = cap.read()
    cap.release()
    if not ok:
        raise ErrorMedicion(f"No se pudo leer el primer cuadro de {ruta.name}")

    # --- 1. calibracion ---
    try:
        cal = calibrar(frame0)
    except ValueError as e:
        raise ErrorMedicion(str(e)) from e
    chequeo = verificar_escala(frame0, cal)

    # --- 2. seguimiento ---
    perfil = PERFILES[objeto]
    tray = seguir(ruta, perfil)
    if tray.cobertura < 0.5:
        raise ErrorMedicion(
            f"Cobertura del tracker demasiado baja ({tray.cobertura:.0%}): "
            f"el perfil de color de '{objeto}' no sirve para este video"
        )

    frames, s_px, n_px = proyectar(tray, cal.versor_rampa)
    sigma_px = sigma_posicion(tray, cal.versor_rampa)

    # --- 3. ventana util ---
    try:
        i0, i1 = ventana_deslizamiento(frames, s_px, FPS)
    except ValueError as e:
        raise ErrorMedicion(str(e)) from e
    i1, motivo_fin = recortar_fuera_de_rampa(n_px, i0, i1)

    t = frames[i0:i1] / FPS
    # La escala px/cm es un factor multiplicativo global, no un ruido punto a
    # punto: se ajusta con el valor central y su error relativo se suma al de
    # la aceleracion al final.
    s_central = (s_px[i0:i1] - s_px[i0]) / cal.px_por_cm.n / 100.0
    sigma_s_m = sigma_px / cal.px_por_cm.n / 100.0

    # --- 4. cinematica ---
    cin = analizar(t, s_central, sigma_s_m)

    rel_escala = cal.px_por_cm.s / cal.px_por_cm.n
    a = cin.aceleracion
    a_final = ufloat(a.n, math.hypot(a.s, abs(a.n) * rel_escala))

    # --- 5. fisica ---
    theta = (
        ref.angulo_rad(CONDICION_A_ANGULO[condicion])
        if condicion in CONDICION_A_ANGULO
        else None
    )
    mu_e = ref.mu_estatico(OBJETO_A_CLAVE[objeto])
    diag = fisica.diagnosticar(a_final, theta, mu_e) if theta is not None else None

    return Corrida(
        ruta=ruta,
        objeto=objeto,
        condicion=condicion,
        repeticion=repeticion,
        cal=cal,
        chequeo_escala=chequeo,
        tray=tray,
        frames=frames,
        s_px=s_px,
        n_px=n_px,
        i0=i0,
        i1=i1,
        sigma_px=sigma_px,
        sigma_s_m=sigma_s_m,
        motivo_fin=motivo_fin,
        t=t,
        s_m=s_central,
        cin=cin,
        aceleracion=a_final,
        theta=theta,
        mu_estatico=mu_e,
        diagnostico=diag,
    )


def informe_texto(c: Corrida) -> str:
    """El resumen que imprime la linea de comandos, como string."""
    cal, cin, tray = c.cal, c.cin, c.tray
    rel_escala = cal.px_por_cm.s / cal.px_por_cm.n

    lineas = [
        f"\n{'=' * 68}\n{c.ruta.name}\n{'=' * 68}",
        f"objeto={c.objeto}  condicion={c.condicion}  repeticion={c.repeticion}",
        "\nCALIBRACION",
        f"  eje de la rampa   = {math.degrees(cal.angulo_rampa_rad):.2f} grados",
        f"  papel rosa        = {cal.largo_papel_px:.1f} px para 7.5 cm",
        f"  escala            = {cal.px_por_cm:.2f} px/cm",
    ]
    if c.chequeo_escala.get("disponible"):
        lineas.append(
            f"  control con rampa = {c.chequeo_escala['px_por_cm_rampa']:.2f} px/cm "
            f"(discrepancia {c.chequeo_escala['discrepancia_relativa']:+.1%}, cota inferior)"
        )

    lineas += [
        "\nSEGUIMIENTO",
        f"  cobertura         = {tray.cobertura:.0%} ({len(tray.detecciones)}/{tray.n_frames})",
        f"  sigma de posicion = {c.sigma_px:.2f} px = {1000 * c.sigma_s_m:.2f} mm "
        f"(medido con el cuerpo quieto)",
        f"  ventana util      = cuadros {int(c.frames[c.i0])}-{int(c.frames[c.i1 - 1])} "
        f"({len(c.t)} puntos, {c.duracion_s:.2f} s)",
        f"  fin de la ventana = {c.motivo_fin}",
        f"  recorrido         = {c.recorrido_cm:.1f} cm",
        "\nCINEMATICA",
        f"  a (ajuste)        = {c.aceleracion:.3f} m/s^2",
        f"     del ajuste {cin.aceleracion.s:.3f} + de la escala "
        f"{abs(cin.aceleracion.n) * rel_escala:.3f}",
        f"  v inicial         = {cin.v_inicial:.3f} m/s",
        f"  residuo RMS       = {1000 * cin.residuo_rms:.2f} mm   "
        f"max {1000 * cin.residuo_max:.2f} mm",
        f"  chi2 reducido     = {cin.chi2_reducido:.2f}",
        f"  a por diferencias = {np.median(cin.a_filtrada):.3f} m/s^2 (mediana, filtrada)",
    ]
    if c.diagnostico is not None:
        lineas += ["\nFISICA", fisica.informe(c.diagnostico)]
    return "\n".join(lineas)


def resumen_dict(c: Corrida) -> dict:
    """Los numeros de la corrida, serializables a JSON."""
    diag = c.diagnostico
    return {
        "archivo": c.ruta.name,
        "objeto": c.objeto,
        "condicion": c.condicion,
        "repeticion": c.repeticion,
        "px_por_cm": [c.cal.px_por_cm.n, c.cal.px_por_cm.s],
        "cobertura": c.tray.cobertura,
        "sigma_posicion_px": c.sigma_px,
        "n_puntos": len(c.t),
        "recorrido_cm": c.recorrido_cm,
        "aceleracion": [c.aceleracion.n, c.aceleracion.s],
        "residuo_rms_mm": 1000 * c.cin.residuo_rms,
        "chi2_reducido": c.cin.chi2_reducido,
        "mu_d_si_desliza": [diag.mu_d_si_desliza.n, diag.mu_d_si_desliza.s] if diag else None,
        "veredicto": diag.veredicto if diag else None,
        "advertencias": diag.advertencias if diag else [],
    }


def medir(ruta: Path, verbose: bool = True) -> dict:
    corrida = analizar_corrida(ruta)
    if verbose:
        print(informe_texto(corrida))
    return resumen_dict(corrida)


def main() -> None:
    p = argparse.ArgumentParser(description="Mide una corrida")
    p.add_argument("video", help="nombre del archivo dentro de la carpeta de videos")
    p.add_argument("--carpeta", type=Path, default=CARPETA_VIDEOS)
    p.add_argument("--json", type=Path, help="guardar el resultado en este archivo")
    args = p.parse_args()

    ruta = args.carpeta / args.video
    if not ruta.is_file():
        raise SystemExit(f"No existe: {ruta}")

    try:
        resultado = medir(ruta)
    except ErrorMedicion as e:
        raise SystemExit(str(e)) from e

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n-> {args.json}")


if __name__ == "__main__":
    main()
