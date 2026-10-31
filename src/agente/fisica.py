"""Modelos fisicos y el chequeo desliza-vs-rueda.

La consigna lo pide explicito: "Verificar si el cuerpo desliza o rueda, porque
cambia la ecuacion". No es un detalle: las dos hipotesis predicen
aceleraciones muy distintas sobre el mismo plano, y aplicar la formula
equivocada da un mu que no significa nada.

  Desliza:                    a = g (sen@ - mu cos@)
  Rueda sin deslizar:         a = g sen@ / (1 + I/(m R^2))
      aro / cilindro hueco (I = m R^2)      -> a = g sen@ / 2
      disco / cilindro macizo (I = m R^2/2) -> a = 2 g sen@ / 3
      esfera maciza (I = 2 m R^2/5)         -> a = 5 g sen@ / 7

El criterio para elegir entre hipotesis no es a ojo: se compara la aceleracion
medida contra cada prediccion y se mira a cuantos sigma queda. Si la hipotesis
de deslizamiento da un mu_dinamico MAYOR que el mu_estatico medido por angulo
critico, la hipotesis es insostenible: el rozamiento dinamico no puede superar
al estatico.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from uncertainties import umath
from uncertainties.core import Variable

G = 9.81  # m/s^2, La Plata / Buenos Aires

# nombre -> I/(m R^2)
INERCIAS = {
    "aro o cilindro hueco": 1.0,
    "disco o cilindro macizo": 0.5,
    "esfera maciza": 0.4,
}


def aceleracion_deslizando(theta: Variable, mu: float) -> Variable:
    return G * (umath.sin(theta) - mu * umath.cos(theta))


def aceleracion_rodando(theta: Variable, inercia_rel: float) -> Variable:
    """a = g sen@ / (1 + I/(m R^2)). No depende de la masa ni del radio."""
    return G * umath.sin(theta) / (1.0 + inercia_rel)


def mu_dinamico(a_medida: Variable, theta: Variable) -> Variable:
    """Despeja mu de a = g(sen@ - mu cos@). Vale SOLO si el cuerpo desliza."""
    return (G * umath.sin(theta) - a_medida) / (G * umath.cos(theta))


def mu_estatico_de_angulo_critico(theta_critico: Variable) -> Variable:
    """mu_e = tan(@_c), del angulo al que arranca el movimiento."""
    return umath.tan(theta_critico)


def sigmas_entre(a: Variable, b: Variable) -> float:
    """Diferencia entre dos magnitudes, en unidades de sigma combinado."""
    sigma = math.hypot(a.s, b.s)
    return abs(a.n - b.n) / sigma if sigma > 0 else float("inf")


@dataclass
class Diagnostico:
    a_medida: Variable
    theta: Variable
    a_sin_rozamiento: Variable
    mu_d_si_desliza: Variable
    mu_e_referencia: Variable | None
    predicciones_rodando: dict[str, tuple[Variable, float]]
    veredicto: str
    advertencias: list[str]


def diagnosticar(
    a_medida: Variable,
    theta: Variable,
    mu_estatico: Variable | None = None,
) -> Diagnostico:
    """Confronta la aceleracion medida con las dos hipotesis."""
    advertencias: list[str] = []

    a_libre = G * umath.sin(theta)
    mu_d = mu_dinamico(a_medida, theta)

    rodando = {}
    for nombre, inercia in INERCIAS.items():
        pred = aceleracion_rodando(theta, inercia)
        rodando[nombre] = (pred, sigmas_entre(a_medida, pred))

    if a_medida.n > a_libre.n:
        advertencias.append(
            f"La aceleracion medida ({a_medida.n:.2f}) supera a g sen@ "
            f"({a_libre.n:.2f}): imposible con rozamiento. Revisar la escala "
            f"px/cm o el angulo."
        )

    veredicto = "deslizamiento compatible"
    if mu_estatico is not None:
        if mu_d.n > mu_estatico.n:
            exceso = sigmas_entre(mu_d, mu_estatico)
            advertencias.append(
                f"mu_d = {mu_d.n:.3f} > mu_e = {mu_estatico.n:.3f} "
                f"({exceso:.1f} sigma). El rozamiento dinamico no puede superar "
                f"al estatico: la hipotesis de deslizamiento puro NO se sostiene."
            )
            veredicto = "deslizamiento descartado"

    mejor = min(rodando.items(), key=lambda kv: kv[1][1])
    if mejor[1][1] < 3.0 and veredicto == "deslizamiento descartado":
        veredicto = f"compatible con rodadura ({mejor[0]})"
    elif mejor[1][1] < 1.5:
        veredicto = f"ambiguo: tambien compatible con rodadura ({mejor[0]})"

    return Diagnostico(
        a_medida=a_medida,
        theta=theta,
        a_sin_rozamiento=a_libre,
        mu_d_si_desliza=mu_d,
        mu_e_referencia=mu_estatico,
        predicciones_rodando=rodando,
        veredicto=veredicto,
        advertencias=advertencias,
    )


def informe(d: Diagnostico) -> str:
    lineas = [
        f"  angulo del plano     = {math.degrees(d.theta.n):.2f} +/- "
        f"{math.degrees(d.theta.s):.2f} grados",
        f"  a medida             = {d.a_medida:.3f} m/s^2",
        f"  g sen@ (sin rozam.)  = {d.a_sin_rozamiento:.3f} m/s^2",
        "",
        "  HIPOTESIS A - desliza:",
        f"    mu_dinamico        = {d.mu_d_si_desliza:.4f}",
    ]
    if d.mu_e_referencia is not None:
        lineas.append(
            f"    mu_estatico (ref.) = {d.mu_e_referencia:.4f}   "
            f"(debe cumplirse mu_d < mu_e)"
        )
    lineas += ["", "  HIPOTESIS B - rueda sin deslizar:"]
    for nombre, (pred, sig) in sorted(d.predicciones_rodando.items(), key=lambda kv: kv[1][1]):
        lineas.append(f"    {nombre:26s} a = {pred.n:5.3f} m/s^2   ({sig:5.1f} sigma)")
    lineas += ["", f"  VEREDICTO: {d.veredicto}"]
    for adv in d.advertencias:
        lineas.append(f"  [!] {adv}")
    return "\n".join(lineas)
