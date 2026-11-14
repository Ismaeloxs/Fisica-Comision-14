"""Ajuste y derivacion de la senal.

Se prueba contra datos SINTETICOS, de aceleracion conocida de antemano. Es la
unica forma de saber si el ajuste recupera el numero correcto: con un video
real no hay con que comparar.
"""

from __future__ import annotations

import numpy as np
import pytest

import cinematica

FPS = 120.0
A_VERDADERA = 2.5  # m/s^2


def trayectoria(a: float = A_VERDADERA, n: int = 60, ruido_m: float = 0.0, v0: float = 0.0,
                semilla: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """s(t) = v0 t + a t^2 / 2, opcionalmente con ruido gaussiano."""
    t = np.arange(n) / FPS
    s = v0 * t + 0.5 * a * t**2
    if ruido_m:
        s = s + np.random.default_rng(semilla).normal(0.0, ruido_m, size=n)
    return t, s


# --------------------------------------------------------------------------
# VERDE
# --------------------------------------------------------------------------


@pytest.mark.verde
def test_recupera_la_aceleracion_exacta_sin_ruido() -> None:
    t, s = trayectoria()
    a, v0, diag = cinematica.ajustar(t, s, sigma_s=1e-6)
    assert a.n == pytest.approx(A_VERDADERA, rel=1e-6)
    assert v0.n == pytest.approx(0.0, abs=1e-6)
    assert diag["residuo_rms"] < 1e-9


@pytest.mark.verde
def test_recupera_la_velocidad_inicial() -> None:
    t, s = trayectoria(v0=0.8)
    a, v0, _ = cinematica.ajustar(t, s, sigma_s=1e-6)
    assert a.n == pytest.approx(A_VERDADERA, rel=1e-6)
    assert v0.n == pytest.approx(0.8, rel=1e-6)


@pytest.mark.verde
@pytest.mark.parametrize("a_real", [0.4, 1.3, 2.5, 5.5])
def test_recupera_distintas_aceleraciones(a_real: float) -> None:
    t, s = trayectoria(a=a_real)
    a, _, _ = cinematica.ajustar(t, s, sigma_s=1e-6)
    assert a.n == pytest.approx(a_real, rel=1e-6)


@pytest.mark.verde
def test_con_ruido_realista_recupera_dentro_de_la_incerteza() -> None:
    """Ruido de 0.5 mm, que es el orden del sigma medido con el cuerpo quieto."""
    t, s = trayectoria(ruido_m=0.0005)
    a, _, _ = cinematica.ajustar(t, s, sigma_s=0.0005)
    assert abs(a.n - A_VERDADERA) < 3 * a.s, (
        f"a = {a.n:.4f} +/- {a.s:.4f}, verdadera {A_VERDADERA}: fuera de 3 sigma"
    )


@pytest.mark.verde
def test_mas_ruido_da_mas_incerteza() -> None:
    """La incerteza del ajuste tiene que crecer con el ruido, no ser decorativa."""
    _, s_poco = trayectoria(ruido_m=0.0002, semilla=1)
    t, s_mucho = trayectoria(ruido_m=0.005, semilla=1)
    a_poco, _, _ = cinematica.ajustar(t, s_poco, sigma_s=0.0002)
    a_mucho, _, _ = cinematica.ajustar(t, s_mucho, sigma_s=0.005)
    assert a_mucho.s > a_poco.s * 5


@pytest.mark.verde
def test_analizar_devuelve_todas_las_series() -> None:
    t, s = trayectoria(ruido_m=0.0005)
    c = cinematica.analizar(t, s, sigma_s=0.0005)
    for campo in ("v_cruda", "a_cruda", "s_filtrada", "v_filtrada", "a_filtrada"):
        serie = getattr(c, campo)
        assert len(serie) == len(t), f"{campo} tiene largo distinto de t"
        assert np.all(np.isfinite(serie)), f"{campo} tiene NaN o inf"


# --------------------------------------------------------------------------
# ROJO
# --------------------------------------------------------------------------


@pytest.mark.rojo
@pytest.mark.parametrize("n", [0, 1, 2, 4])
def test_pocos_puntos_falla_en_vez_de_devolver_cualquier_cosa(n: int) -> None:
    t, s = trayectoria(n=n)
    with pytest.raises(ValueError):
        cinematica.ajustar(t, s, sigma_s=0.001)


@pytest.mark.rojo
def test_posicion_constante_da_aceleracion_cero_no_un_error_numerico() -> None:
    """Un cuerpo quieto es un caso valido: a = 0, no NaN."""
    t = np.arange(40) / FPS
    s = np.full(40, 0.123)
    a, v0, _ = cinematica.ajustar(t, s, sigma_s=1e-9)
    assert a.n == pytest.approx(0.0, abs=1e-9)
    assert np.isfinite(a.n) and np.isfinite(v0.n)


@pytest.mark.rojo
def test_largos_distintos_falla() -> None:
    t = np.arange(30) / FPS
    s = np.zeros(20)
    with pytest.raises((ValueError, TypeError)):
        cinematica.ajustar(t, s, sigma_s=0.001)


@pytest.mark.rojo
def test_sigma_cero_no_rompe_el_chi2() -> None:
    """Con sigma 0 el chi2 no se puede calcular, pero no puede lanzar
    ZeroDivisionError: tiene que devolver nan y seguir."""
    t, s = trayectoria()
    a, _, diag = cinematica.ajustar(t, s, sigma_s=0.0)
    assert np.isfinite(a.n)
    assert np.isnan(diag["chi2_reducido"]) or diag["chi2_reducido"] >= 0


# --------------------------------------------------------------------------
# AMARILLO
# --------------------------------------------------------------------------


@pytest.mark.amarillo
def test_el_filtrado_alisa_de_verdad() -> None:
    """Savitzky-Golay tiene que reducir la varianza de la derivada segunda.
    Si no, el filtro esta mal configurado y derivar amplifica el ruido."""
    t, s = trayectoria(n=80, ruido_m=0.001)
    d = cinematica.derivar(t, s)
    assert np.std(d["a_filtrada"]) < np.std(d["a_cruda"]) / 2, (
        "la aceleracion filtrada no es mas suave que la cruda"
    )


@pytest.mark.amarillo
def test_el_ajuste_es_mas_preciso_que_derivar_dos_veces() -> None:
    """Justifica la decision de diseno: la aceleracion sale del ajuste y no de
    la derivada segunda, porque derivar amplifica el ruido."""
    t, s = trayectoria(n=80, ruido_m=0.001)
    a_ajuste, _, _ = cinematica.ajustar(t, s, sigma_s=0.001)
    d = cinematica.derivar(t, s)
    error_ajuste = abs(a_ajuste.n - A_VERDADERA)
    error_derivada = abs(float(np.median(d["a_cruda"])) - A_VERDADERA)
    assert error_ajuste < error_derivada


@pytest.mark.amarillo
def test_chi2_alto_cuando_el_sigma_esta_subestimado() -> None:
    """Es exactamente lo que pasa con los videos reales: el sigma medido con el
    cuerpo quieto no incluye el desenfoque de movimiento, y el chi2 lo delata."""
    t, s = trayectoria(n=60, ruido_m=0.003)
    _, _, diag = cinematica.ajustar(t, s, sigma_s=0.0003)  # 10x subestimado
    assert diag["chi2_reducido"] > 10


@pytest.mark.amarillo
def test_ventana_de_filtrado_impar_y_menor_que_los_datos() -> None:
    """savgol exige ventana impar y <= n. Con pocos puntos tiene que degradar
    sin romper."""
    for n in (6, 9, 15, 40):
        t, s = trayectoria(n=n, ruido_m=0.0005)
        d = cinematica.derivar(t, s)
        assert len(d["s_filtrada"]) == n
