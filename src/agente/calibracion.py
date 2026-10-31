"""Calibracion espacial y geometrica de una corrida.

Dos cosas salen de aca:

  - px_por_cm: cuantos pixeles mide un centimetro en el plano del movimiento.
    Se obtiene del papel rosa de 7,5 cm pegado sobre la rampa.
  - eje de la rampa: el versor a lo largo del cual se mueve el cuerpo, para
    reducir el movimiento 2D a una coordenada s(t) de una sola dimension.

Por que el papel rosa y no la regla de 42 cm: el papel esta SOBRE el plano del
movimiento y sus bordes son nitidos. Los extremos de la regla, en cambio, se
pierden (el de arriba queda tapado por el papel, el de abajo se mete contra la
mesa), asi que medir sus 42 cm en pixeles da un valor poco confiable.
Ver verificar_escala() para el contraste entre ambos.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np
from uncertainties import ufloat
from uncertainties.core import Variable

# El papel rosa: magenta saturado. Los libros rojos caen cerca en tono, asi que
# ademas se exige que el componente este en la mitad superior del cuadro.
HSV_ROSA_MIN = (150, 80, 100)
HSV_ROSA_MAX = (179, 255, 255)

LARGO_PAPEL_CM = 7.5
SIGMA_PAPEL_CM = 0.1
LARGO_RAMPA_CM = 42.0


@dataclass(frozen=True)
class Calibracion:
    px_por_cm: Variable
    angulo_rampa_rad: float
    origen_px: tuple[float, float]
    area_papel_px: int
    largo_papel_px: float

    @property
    def versor_rampa(self) -> np.ndarray:
        """Versor unitario a lo largo de la rampa, en coordenadas de imagen."""
        return np.array(
            [math.cos(self.angulo_rampa_rad), math.sin(self.angulo_rampa_rad)]
        )

    def a_metros(self, px: float | np.ndarray):
        """Convierte una longitud en pixeles a metros."""
        return px / self.px_por_cm / 100.0


def _blob_papel(frame: np.ndarray) -> tuple[np.ndarray, np.ndarray, int, tuple[float, float]]:
    """Pixeles del papel rosa de calibracion. Devuelve (xs, ys, area, centro)."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mascara = cv2.inRange(hsv, HSV_ROSA_MIN, HSV_ROSA_MAX)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))

    n, etiquetas, stats, centros = cv2.connectedComponentsWithStats(mascara)
    alto = frame.shape[0]
    mejor, mejor_area = None, 0
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        # el papel esta en la mitad superior; los libros rojos, abajo
        if area > 2000 and centros[i][1] < alto * 0.45 and area > mejor_area:
            mejor, mejor_area = i, area
    if mejor is None:
        raise ValueError("No se encontro el papel rosa de calibracion")

    ys, xs = np.where(etiquetas == mejor)
    return xs, ys, mejor_area, (float(centros[mejor][0]), float(centros[mejor][1]))


def detectar_eje_rampa(frame: np.ndarray) -> float:
    """Angulo de la rampa en radianes, a partir del papel rosa.

    El papel esta pegado SOBRE la rampa, asi que su eje largo es el eje del
    movimiento. Se usa esto y no Hough porque Hough no distingue la rampa de
    otras rectas largas de la escena: el borde de la mesa aparece a unos 13
    grados y, al promediar, arrastra el eje varios grados. Y un error de pocos
    grados en el eje se mete directo en la proyeccion s(t) y por lo tanto en
    la aceleracion.

    La orientacion sale de los ejes principales (PCA) de la mancha, que usa
    todos sus pixeles en vez de depender de cuatro esquinas.
    """
    xs, ys, _, _ = _blob_papel(frame)
    puntos = np.column_stack([xs - xs.mean(), ys - ys.mean()]).astype(float)
    # vector propio dominante de la matriz de covarianza = direccion del lado largo
    _, _, vt = np.linalg.svd(puntos, full_matrices=False)
    vx, vy = vt[0]
    ang = math.atan2(vy, vx)
    # normalizar a la rampa que baja hacia la derecha
    if vx < 0:
        ang = math.atan2(-vy, -vx)
    return ang


def detectar_papel(frame: np.ndarray, eje_rad: float) -> tuple[float, int, tuple[float, float]]:
    """Largo del papel rosa proyectado sobre el eje de la rampa, en pixeles.

    Devuelve (largo_px, area_px, centro). Se proyecta sobre el eje en vez de
    usar minAreaRect porque el papel esta doblado sobre el canto de la regla:
    la cara lateral infla el rectangulo pero no el largo a lo largo del eje.
    """
    xs, ys, area, centro = _blob_papel(frame)
    u = np.array([math.cos(eje_rad), math.sin(eje_rad)])
    proy = xs * u[0] + ys * u[1]
    return float(proy.max() - proy.min()), area, centro


def calibrar(frame: np.ndarray) -> Calibracion:
    eje = detectar_eje_rampa(frame)
    largo_px, area, centro = detectar_papel(frame, eje)

    # sigma del largo en pixeles: el borde del papel se resuelve a ~2 px por lado
    largo_u = ufloat(largo_px, 3.0)
    papel_u = ufloat(LARGO_PAPEL_CM, SIGMA_PAPEL_CM)

    return Calibracion(
        px_por_cm=largo_u / papel_u,
        angulo_rampa_rad=eje,
        origen_px=centro,
        area_papel_px=area,
        largo_papel_px=largo_px,
    )


def verificar_escala(frame: np.ndarray, cal: Calibracion) -> dict:
    """Contrasta la escala del papel contra la longitud aparente de la rampa.

    No sirve para calibrar (los extremos de la regla no se ven bien), pero si
    para detectar un error grueso. Una discrepancia grande puede significar
    perspectiva fuerte, o que el papel no mide lo que creemos.
    """
    gris = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    bordes = cv2.Canny(gris, 40, 120)
    lineas = cv2.HoughLinesP(
        bordes, 1, np.pi / 360, threshold=80, minLineLength=250, maxLineGap=25
    )
    u = cal.versor_rampa
    eje_grados = math.degrees(cal.angulo_rampa_rad)
    proyecciones = []
    for x1, y1, x2, y2 in np.asarray(lineas).reshape(-1, 4):
        ang = math.degrees(math.atan2(float(y2 - y1), float(x2 - x1)))
        # solo rectas practicamente paralelas al eje ya establecido por el
        # papel: si no, entra el borde de la mesa y el control no mide la rampa
        if abs(ang - eje_grados) < 8.0 and math.hypot(float(x2 - x1), float(y2 - y1)) > 300.0:
            proyecciones += [x1 * u[0] + y1 * u[1], x2 * u[0] + y2 * u[1]]

    if not proyecciones:
        return {"disponible": False}

    largo_rampa_px = max(proyecciones) - min(proyecciones)
    px_cm_rampa = largo_rampa_px / LARGO_RAMPA_CM
    discrepancia = (cal.px_por_cm.n - px_cm_rampa) / px_cm_rampa

    return {
        "disponible": True,
        "px_por_cm_papel": cal.px_por_cm.n,
        "px_por_cm_rampa": px_cm_rampa,
        "largo_rampa_px": largo_rampa_px,
        "discrepancia_relativa": discrepancia,
        "nota": (
            "La rampa es cota inferior: sus extremos quedan ocultos, asi que "
            "su largo en pixeles se subestima y px/cm sale chico."
        ),
    }
