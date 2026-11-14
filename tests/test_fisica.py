"""Modelos fisicos: deslizamiento, rodadura y el diagnostico entre los dos."""

from __future__ import annotations

import math

import pytest
from uncertainties import ufloat

import fisica

G = fisica.G
THETA_4L = ufloat(math.radians(34.3527047), math.radians(0.19))
THETA_3L = ufloat(math.radians(24.6243183), math.radians(0.16))
MU_E_TAPA = ufloat(0.29274, 0.0028)


# --------------------------------------------------------------------------
# VERDE
# --------------------------------------------------------------------------


@pytest.mark.verde
def test_sin_rozamiento_la_aceleracion_es_g_sen_theta() -> None:
    a = fisica.aceleracion_deslizando(THETA_4L, mu=0.0)
    assert a.n == pytest.approx(G * math.sin(THETA_4L.n), rel=1e-9)


@pytest.mark.verde
def test_mu_dinamico_invierte_la_formula_de_deslizamiento() -> None:
    """Ida y vuelta: calcular a con un mu y despejarlo tiene que devolverlo."""
    for mu in (0.1, 0.25, 0.4, 0.6):
        a = fisica.aceleracion_deslizando(THETA_4L, mu)
        assert fisica.mu_dinamico(a, THETA_4L).n == pytest.approx(mu, rel=1e-9)


@pytest.mark.verde
@pytest.mark.parametrize(
    "nombre,inercia,divisor",
    [
        ("aro o cilindro hueco", 1.0, 2.0),      # a = g sen / 2
        ("disco o cilindro macizo", 0.5, 1.5),   # a = 2 g sen / 3
        ("esfera maciza", 0.4, 1.4),             # a = 5 g sen / 7
    ],
)
def test_rodadura_coincide_con_el_libro(nombre: str, inercia: float, divisor: float) -> None:
    a = fisica.aceleracion_rodando(THETA_4L, inercia)
    esperado = G * math.sin(THETA_4L.n) / divisor
    assert a.n == pytest.approx(esperado, rel=1e-9), nombre


@pytest.mark.verde
def test_rodar_siempre_es_mas_lento_que_deslizar_sin_rozamiento() -> None:
    libre = G * math.sin(THETA_4L.n)
    for inercia in fisica.INERCIAS.values():
        assert fisica.aceleracion_rodando(THETA_4L, inercia).n < libre


@pytest.mark.verde
def test_mas_inercia_rotacional_es_mas_lento() -> None:
    aro = fisica.aceleracion_rodando(THETA_4L, 1.0).n
    disco = fisica.aceleracion_rodando(THETA_4L, 0.5).n
    esfera = fisica.aceleracion_rodando(THETA_4L, 0.4).n
    assert aro < disco < esfera


@pytest.mark.verde
def test_mu_estatico_de_angulo_critico() -> None:
    theta = ufloat(math.radians(16.317), math.radians(0.15))
    assert fisica.mu_estatico_de_angulo_critico(theta).n == pytest.approx(
        math.tan(theta.n), rel=1e-9
    )


@pytest.mark.verde
def test_sigmas_entre_mide_la_distancia_en_sigmas() -> None:
    a = ufloat(2.0, 0.1)
    b = ufloat(2.0, 0.1)
    assert fisica.sigmas_entre(a, b) == pytest.approx(0.0)
    c = ufloat(2.3, 0.1)
    # diferencia 0.3 sobre sigma combinado sqrt(0.01+0.01)=0.1414
    assert fisica.sigmas_entre(a, c) == pytest.approx(0.3 / math.hypot(0.1, 0.1), rel=1e-6)


@pytest.mark.verde
def test_diagnostico_acepta_deslizamiento_cuando_mu_es_coherente() -> None:
    """Con un mu_d claramente menor que el estatico, no hay contradiccion."""
    a = fisica.aceleracion_deslizando(THETA_4L, mu=0.15)
    d = fisica.diagnosticar(a, THETA_4L, MU_E_TAPA)
    assert d.veredicto != "deslizamiento descartado"
    assert not any("no puede superar" in s for s in d.advertencias)


# --------------------------------------------------------------------------
# ROJO
# --------------------------------------------------------------------------


@pytest.mark.rojo
def test_aceleracion_mayor_que_g_sen_theta_se_denuncia() -> None:
    """Imposible con rozamiento: solo puede ser error de escala o de angulo."""
    a = ufloat(G * math.sin(THETA_4L.n) * 1.3, 0.05)
    d = fisica.diagnosticar(a, THETA_4L, MU_E_TAPA)
    assert any("supera a g sen" in s for s in d.advertencias), d.advertencias


@pytest.mark.rojo
def test_angulo_cero_no_divide_por_cero() -> None:
    """A 0 grados cos(theta)=1, asi que mu_dinamico es finito; el que se indefine
    seria a angulo 90, que no existe en este experimento."""
    theta = ufloat(0.0, 0.001)
    mu = fisica.mu_dinamico(ufloat(0.0, 0.01), theta)
    assert math.isfinite(mu.n)


@pytest.mark.rojo
def test_sigmas_entre_con_incerteza_nula_no_rompe() -> None:
    a = ufloat(2.0, 0.0)
    b = ufloat(2.5, 0.0)
    assert fisica.sigmas_entre(a, b) == float("inf")


@pytest.mark.rojo
def test_informe_funciona_sin_mu_estatico_de_referencia() -> None:
    """En angulo critico no hay mu_e con que comparar; no puede romper."""
    a = ufloat(2.3, 0.1)
    d = fisica.diagnosticar(a, THETA_4L, None)
    texto = fisica.informe(d)
    assert "mu_dinamico" in texto
    assert "mu_estatico (ref.)" not in texto


# --------------------------------------------------------------------------
# AMARILLO
# --------------------------------------------------------------------------


@pytest.mark.amarillo
def test_descarta_deslizamiento_cuando_mu_d_supera_al_estatico() -> None:
    """El hallazgo central del proyecto: con la a medida de la tapa a 4 libros,
    el deslizamiento puro es insostenible."""
    a = ufloat(2.324, 0.108)  # medido, 4 corridas confiables
    d = fisica.diagnosticar(a, THETA_4L, MU_E_TAPA)
    assert d.mu_d_si_desliza.n > MU_E_TAPA.n
    assert d.veredicto == "deslizamiento descartado" or "rodadura" in d.veredicto
    assert any("no puede superar" in s for s in d.advertencias)


@pytest.mark.amarillo
def test_senala_la_geometria_de_rodadura_mas_cercana() -> None:
    """Si la a medida coincide con un aro rodando, el diagnostico lo tiene que
    decir y no quedarse en 'deslizamiento descartado'."""
    a_aro = fisica.aceleracion_rodando(THETA_4L, 1.0)
    a = ufloat(a_aro.n, 0.05)
    d = fisica.diagnosticar(a, THETA_4L, MU_E_TAPA)
    mejor = min(d.predicciones_rodando.items(), key=lambda kv: kv[1][1])
    assert "aro" in mejor[0]
    assert mejor[1][1] < 1.0, "el aro deberia quedar a menos de 1 sigma"


@pytest.mark.amarillo
def test_el_factor_de_inercia_medido_no_es_constante_entre_angulos() -> None:
    """Documenta por que ningun modelo puro cierra: si la tapa rodara sin
    deslizar, 1+I/mR2 tendria que dar igual a 4 y a 3 libros. No da."""
    a4, a3 = ufloat(2.324, 0.108), ufloat(1.280, 0.057)
    f4 = (G * __import__("uncertainties").umath.sin(THETA_4L) / a4).n
    f3 = (G * __import__("uncertainties").umath.sin(THETA_3L) / a3).n
    assert abs(f4 - f3) > 0.3, (
        f"los factores se volvieron parecidos ({f4:.2f} vs {f3:.2f}): "
        "revisar si cambio la medicion"
    )


@pytest.mark.amarillo
def test_cuerpo_libre_cierra_la_segunda_ley() -> None:
    """La suma de fuerzas sobre el eje del plano tiene que dar masa por
    aceleracion, si no el diagrama esta mal armado."""
    masa = ufloat(0.005, 0.001)
    a = ufloat(2.324, 0.108)
    f = fisica.cuerpo_libre(masa, THETA_4L, a)
    neta = f.paralela.n - f.rozamiento.n
    assert neta == pytest.approx(masa.n * a.n, rel=1e-6), (
        f"F_paralela - F_roz = {neta:.6f} pero m*a = {masa.n * a.n:.6f}"
    )


@pytest.mark.amarillo
def test_la_normal_es_el_peso_por_coseno() -> None:
    masa = ufloat(0.116, 0.001)
    f = fisica.cuerpo_libre(masa, THETA_4L, ufloat(2.0, 0.1))
    assert f.normal.n == pytest.approx(masa.n * G * math.cos(THETA_4L.n), rel=1e-6)
    assert f.peso.n == pytest.approx(masa.n * G, rel=1e-9)
