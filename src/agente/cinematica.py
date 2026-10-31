"""De la trayectoria s(t) a la aceleracion, con incerteza.

La aceleracion se obtiene del AJUSTE cuadratico de s(t), no de derivar dos
veces. Derivar amplifica el ruido: con sigma de posicion de ~1 px y dt = 1/120 s,
la derivada segunda numerica queda dominada por el ruido. El ajuste usa los
~60 puntos de una vez y devuelve el error del parametro.

Igual se calculan v(t) y a(t) por diferencias finitas, crudas y filtradas,
porque la consigna pide compararlas explicitamente contra el ajuste.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.signal import savgol_filter
from uncertainties import ufloat
from uncertainties.core import Variable


@dataclass
class Cinematica:
    t: np.ndarray
    s: np.ndarray
    sigma_s: float
    aceleracion: Variable
    v_inicial: Variable
    residuo_rms: float
    residuo_max: float
    chi2_reducido: float
    n_puntos: int
    # series derivadas, para los graficos
    v_cruda: np.ndarray
    a_cruda: np.ndarray
    s_filtrada: np.ndarray
    v_filtrada: np.ndarray
    a_filtrada: np.ndarray


def ajustar(t: np.ndarray, s: np.ndarray, sigma_s: float) -> tuple[Variable, Variable, dict]:
    """Ajusta s(t) = s0 + v0 t + a t^2 / 2 por cuadrados minimos.

    Devuelve (a, v0, diagnostico). El sigma de cada parametro sale de la matriz
    de covarianza del ajuste.
    """
    if len(t) < 5:
        raise ValueError("Muy pocos puntos para ajustar")

    t0 = t - t[0]
    coef, cov = np.polyfit(t0, s, 2, cov=True)
    a = ufloat(2.0 * coef[0], 2.0 * math.sqrt(cov[0, 0]))
    v0 = ufloat(coef[1], math.sqrt(cov[1, 1]))

    residuo = s - np.polyval(coef, t0)
    n_libres = len(t) - 3
    chi2_red = (
        float(np.sum((residuo / sigma_s) ** 2) / n_libres) if n_libres > 0 and sigma_s > 0 else float("nan")
    )

    return a, v0, {
        "residuo_rms": float(np.sqrt(np.mean(residuo**2))),
        "residuo_max": float(np.max(np.abs(residuo))),
        "chi2_reducido": chi2_red,
        "n_puntos": len(t),
    }


def _ventana_impar(n: int, fraccion: float = 0.25, minimo: int = 5) -> int:
    v = max(minimo, int(n * fraccion))
    return v if v % 2 == 1 else v + 1


def derivar(t: np.ndarray, s: np.ndarray) -> dict[str, np.ndarray]:
    """v y a por diferencias finitas, crudas y con Savitzky-Golay.

    Orden que pide la consigna: filtrar posicion -> derivar -> filtrar
    velocidad -> derivar -> filtrar aceleracion.
    """
    v_cruda = np.gradient(s, t)
    a_cruda = np.gradient(v_cruda, t)

    ventana = min(_ventana_impar(len(s)), len(s) if len(s) % 2 == 1 else len(s) - 1)
    if ventana < 5:
        return {
            "v_cruda": v_cruda,
            "a_cruda": a_cruda,
            "s_filtrada": s.copy(),
            "v_filtrada": v_cruda,
            "a_filtrada": a_cruda,
        }

    s_f = savgol_filter(s, ventana, 3)
    v_f = savgol_filter(np.gradient(s_f, t), ventana, 3)
    a_f = savgol_filter(np.gradient(v_f, t), ventana, 3)
    return {
        "v_cruda": v_cruda,
        "a_cruda": a_cruda,
        "s_filtrada": s_f,
        "v_filtrada": v_f,
        "a_filtrada": a_f,
    }


def analizar(t: np.ndarray, s: np.ndarray, sigma_s: float) -> Cinematica:
    a, v0, diag = ajustar(t, s, sigma_s)
    d = derivar(t, s)
    return Cinematica(
        t=t,
        s=s,
        sigma_s=sigma_s,
        aceleracion=a,
        v_inicial=v0,
        residuo_rms=diag["residuo_rms"],
        residuo_max=diag["residuo_max"],
        chi2_reducido=diag["chi2_reducido"],
        n_puntos=diag["n_puntos"],
        **d,
    )
