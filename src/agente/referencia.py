"""Datos de referencia del laboratorio (Grupo 3).

Lee las mediciones crudas de datos/referencia/laboratorio.json y deriva de ahi
los angulos y el coeficiente estatico, propagando incertezas.

Regla del proyecto: nada devuelve un float pelado. Todo sale como ufloat
(valor +/- sigma) del paquete `uncertainties`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from uncertainties import ufloat, umath
from uncertainties.core import Variable

RAIZ = Path(__file__).resolve().parents[2]
ARCHIVO_REFERENCIA = RAIZ / "datos" / "referencia" / "laboratorio.json"


@dataclass(frozen=True)
class Objeto:
    """Un cuerpo que desliza, con su masa y su altura de inicio de movimiento."""

    clave: str
    nombre: str
    masa_kg: Variable
    altura_inicio_cm: Variable

    def angulo_critico(self, hipotenusa_cm: Variable) -> Variable:
        """Angulo al que el cuerpo arranca a moverse, en radianes."""
        return umath.asin(self.altura_inicio_cm / hipotenusa_cm)

    def mu_estatico(self, hipotenusa_cm: Variable) -> Variable:
        """Coeficiente de rozamiento estatico, mu_e = tan(theta_critico).

        Vale solo en el instante en que arranca el movimiento, donde la
        componente del peso iguala al rozamiento estatico maximo.
        """
        return umath.tan(self.angulo_critico(hipotenusa_cm))


@dataclass(frozen=True)
class Angulo:
    """Una inclinacion del plano, definida por la altura de los libros."""

    clave: str
    descripcion: str
    altura_cm: Variable

    def radianes(self, hipotenusa_cm: Variable) -> Variable:
        return umath.asin(self.altura_cm / hipotenusa_cm)


@dataclass(frozen=True)
class Referencia:
    """Todo lo que el Grupo 3 midio a mano."""

    hipotenusa_cm: Variable
    patron_cm: Variable
    fps_declarado: int
    objetos: dict[str, Objeto]
    angulos: dict[str, Angulo]
    inconsistencias: dict

    def angulo_rad(self, clave: str) -> Variable:
        return self.angulos[clave].radianes(self.hipotenusa_cm)

    def mu_estatico(self, clave_objeto: str) -> Variable:
        return self.objetos[clave_objeto].mu_estatico(self.hipotenusa_cm)


def _u(datos: dict, campo: str, campo_sigma: str) -> Variable:
    return ufloat(datos[campo], datos[campo_sigma])


def cargar(archivo: Path | None = None) -> Referencia:
    """Carga las mediciones del laboratorio y arma los objetos derivados."""
    archivo = archivo or ARCHIVO_REFERENCIA
    with archivo.open(encoding="utf-8") as f:
        d = json.load(f)

    objetos = {}
    for clave, o in d["objetos"].items():
        objetos[clave] = Objeto(
            clave=clave,
            nombre=o["nombre"],
            masa_kg=ufloat(o["masa_g"], o["sigma_masa_g"]) / 1000.0,
            altura_inicio_cm=_u(o, "altura_inicio_movimiento_cm", "sigma_altura_cm"),
        )

    angulos = {}
    for clave, a in d["angulos"].items():
        angulos[clave] = Angulo(
            clave=clave,
            descripcion=a["descripcion"],
            altura_cm=_u(a, "altura_cm", "sigma_altura_cm"),
        )

    return Referencia(
        hipotenusa_cm=_u(d["geometria"], "hipotenusa_cm", "sigma_hipotenusa_cm"),
        patron_cm=_u(d["calibracion_espacial"], "largo_cm", "sigma_largo_cm"),
        fps_declarado=d["fps_declarado"],
        objetos=objetos,
        angulos=angulos,
        inconsistencias=d.get("_inconsistencia_detectada", {}),
    )


if __name__ == "__main__":
    import math

    ref = cargar()
    print("ANGULOS DEL PLANO")
    for clave, ang in ref.angulos.items():
        rad = ang.radianes(ref.hipotenusa_cm)
        print(
            f"  {clave} ({ang.descripcion}): "
            f"{math.degrees(rad.n):.3f} +/- {math.degrees(rad.s):.3f} grados"
        )

    print("\nCOEFICIENTE ESTATICO (del angulo critico)")
    for clave, obj in ref.objetos.items():
        mu = ref.mu_estatico(clave)
        tc = obj.angulo_critico(ref.hipotenusa_cm)
        print(
            f"  {obj.nombre:9s}: theta_c = {math.degrees(tc.n):.2f} +/- "
            f"{math.degrees(tc.s):.2f} grados -> mu_e = {mu:.4f}"
        )

    if ref.inconsistencias:
        print(f"\n[!] {ref.inconsistencias['que']}")
