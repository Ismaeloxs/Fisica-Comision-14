"""Mide una corrida de punta a punta: video -> aceleracion -> diagnostico.

    python src/agente/medir.py "Tapa 4Libros Video1.mp4"
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

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


def medir(ruta: Path, verbose: bool = True) -> dict:
    partes = parsear_nombre(ruta)
    if partes is None:
        raise SystemExit(f"Nombre no interpretable: {ruta.name}")
    objeto, condicion, repeticion = partes

    ref = cargar_referencia()

    cap = cv2.VideoCapture(str(ruta))
    ok, frame0 = cap.read()
    cap.release()
    if not ok:
        raise SystemExit(f"No se pudo leer el primer cuadro de {ruta.name}")

    # --- 1. calibracion ---
    cal = calibrar(frame0)
    chequeo = verificar_escala(frame0, cal)

    # --- 2. seguimiento ---
    perfil = PERFILES[objeto]
    tray = seguir(ruta, perfil)
    if tray.cobertura < 0.5:
        raise SystemExit(
            f"Cobertura del tracker demasiado baja ({tray.cobertura:.0%}): "
            f"el perfil de color de '{objeto}' no sirve para este video"
        )

    frames, s_px, n_px = proyectar(tray, cal.versor_rampa)
    sigma_px = sigma_posicion(tray, cal.versor_rampa)

    # --- 3. ventana util ---
    i0, i1 = ventana_deslizamiento(frames, s_px, FPS)
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

    if verbose:
        print(f"\n{'=' * 68}\n{ruta.name}\n{'=' * 68}")
        print(f"objeto={objeto}  condicion={condicion}  repeticion={repeticion}")
        print("\nCALIBRACION")
        print(f"  eje de la rampa   = {math.degrees(cal.angulo_rampa_rad):.2f} grados")
        print(f"  papel rosa        = {cal.largo_papel_px:.1f} px para 7.5 cm")
        print(f"  escala            = {cal.px_por_cm:.2f} px/cm")
        if chequeo.get("disponible"):
            print(
                f"  control con rampa = {chequeo['px_por_cm_rampa']:.2f} px/cm "
                f"(discrepancia {chequeo['discrepancia_relativa']:+.1%}, cota inferior)"
            )
        print("\nSEGUIMIENTO")
        print(f"  cobertura         = {tray.cobertura:.0%} ({len(tray.detecciones)}/{tray.n_frames})")
        print(f"  sigma de posicion = {sigma_px:.2f} px = {1000 * sigma_s_m:.2f} mm (medido con el cuerpo quieto)")
        print(f"  ventana util      = cuadros {int(frames[i0])}-{int(frames[i1 - 1])} ({len(t)} puntos, {t[-1] - t[0]:.2f} s)")
        print(f"  fin de la ventana = {motivo_fin}")
        print(f"  recorrido         = {100 * (s_central[-1] - s_central[0]):.1f} cm")
        print("\nCINEMATICA")
        print(f"  a (ajuste)        = {a_final:.3f} m/s^2")
        print(f"     del ajuste {cin.aceleracion.s:.3f} + de la escala {abs(a.n) * rel_escala:.3f}")
        print(f"  v inicial         = {cin.v_inicial:.3f} m/s")
        print(f"  residuo RMS       = {1000 * cin.residuo_rms:.2f} mm   max {1000 * cin.residuo_max:.2f} mm")
        print(f"  chi2 reducido     = {cin.chi2_reducido:.2f}")
        print(f"  a por diferencias = {np.median(cin.a_filtrada):.3f} m/s^2 (mediana, filtrada)")
        if diag is not None:
            print("\nFISICA")
            print(fisica.informe(diag))

    return {
        "archivo": ruta.name,
        "objeto": objeto,
        "condicion": condicion,
        "repeticion": repeticion,
        "px_por_cm": [cal.px_por_cm.n, cal.px_por_cm.s],
        "cobertura": tray.cobertura,
        "sigma_posicion_px": sigma_px,
        "n_puntos": len(t),
        "recorrido_cm": 100 * (s_central[-1] - s_central[0]),
        "aceleracion": [a_final.n, a_final.s],
        "residuo_rms_mm": 1000 * cin.residuo_rms,
        "chi2_reducido": cin.chi2_reducido,
        "mu_d_si_desliza": [diag.mu_d_si_desliza.n, diag.mu_d_si_desliza.s] if diag else None,
        "veredicto": diag.veredicto if diag else None,
        "advertencias": diag.advertencias if diag else [],
    }


CONDICION_A_ANGULO = {"4libros": "angulo_1", "3libros": "angulo_2", "2libros": "angulo_3"}


def main() -> None:
    p = argparse.ArgumentParser(description="Mide una corrida")
    p.add_argument("video", help="nombre del archivo dentro de la carpeta de videos")
    p.add_argument("--carpeta", type=Path, default=CARPETA_VIDEOS)
    p.add_argument("--json", type=Path, help="guardar el resultado en este archivo")
    args = p.parse_args()

    ruta = args.carpeta / args.video
    if not ruta.is_file():
        raise SystemExit(f"No existe: {ruta}")

    resultado = medir(ruta)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n-> {args.json}")


if __name__ == "__main__":
    main()
