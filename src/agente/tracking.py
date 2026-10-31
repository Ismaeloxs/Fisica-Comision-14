"""Seguimiento del cuerpo que desliza.

Cada objeto tiene su propio perfil de color. Los umbrales NO son arbitrarios:
salen de muestrear el objeto y sus distractores en el primer cuadro.

El caso que obliga a ajustar fino es la tapita: en la pila de libros hay un
libro AZUL, mucho mas grande que ella. Tomar "el componente azul mas grande"
devuelve el libro, que ademas esta quieto, asi que el error no es evidente:
da una trayectoria perfectamente plana. Lo que los separa no es el tono (105
contra 109, indistinguibles) sino la saturacion y el brillo: la tapita es
plastico brillante (S~239, V~157) y el libro es tela mate (S~156, V~85).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class PerfilColor:
    """Rango HSV y tamano esperado de un objeto."""

    nombre: str
    hsv_min: tuple[int, int, int]
    hsv_max: tuple[int, int, int]
    area_min: int
    area_max: int
    nota: str = ""


PERFILES: dict[str, PerfilColor] = {
    "tapa": PerfilColor(
        nombre="tapa",
        hsv_min=(98, 200, 110),
        hsv_max=(118, 255, 255),
        area_min=800,
        area_max=6000,
        nota=(
            "S>=200 y V>=110 separan la tapita (plastico brillante) del libro "
            "azul de la pila (tela mate, S~156 V~85). Medido sobre el cuadro 0."
        ),
    ),
    "esponja": PerfilColor(
        nombre="esponja",
        hsv_min=(20, 120, 120),
        hsv_max=(40, 255, 255),
        area_min=2000,
        area_max=40000,
        nota="Amarillo saturado. PENDIENTE de verificar contra la regla de madera (H~14).",
    ),
    "jabon": PerfilColor(
        nombre="jabon",
        hsv_min=(18, 30, 150),
        hsv_max=(38, 120, 255),
        area_min=2000,
        area_max=40000,
        nota=(
            "EL DIFICIL: crema palido, poco saturado, sobre pared blanca y "
            "regla de madera. El umbral de color probablemente NO alcance; "
            "este objeto seguramente necesite CSRT o diferencia de cuadros."
        ),
    ),
}


@dataclass
class Deteccion:
    frame: int
    x_px: float
    y_px: float
    area_px: int


@dataclass
class Trayectoria:
    detecciones: list[Deteccion]
    n_frames: int
    perfil: str

    @property
    def cobertura(self) -> float:
        return len(self.detecciones) / self.n_frames if self.n_frames else 0.0


def seguir(ruta, perfil: PerfilColor) -> Trayectoria:
    """Recorre el video y devuelve el centroide del objeto en cada cuadro."""
    cap = cv2.VideoCapture(str(ruta))
    if not cap.isOpened():
        raise ValueError(f"No se pudo abrir {ruta}")

    nucleo = np.ones((5, 5), np.uint8)
    detecciones: list[Deteccion] = []
    i = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            mascara = cv2.inRange(hsv, perfil.hsv_min, perfil.hsv_max)
            mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, nucleo)

            n, _, stats, centros = cv2.connectedComponentsWithStats(mascara)
            mejor, mejor_area = None, 0
            for j in range(1, n):
                area = int(stats[j, cv2.CC_STAT_AREA])
                if perfil.area_min <= area <= perfil.area_max and area > mejor_area:
                    mejor, mejor_area = j, area
            if mejor is not None:
                detecciones.append(
                    Deteccion(i, float(centros[mejor][0]), float(centros[mejor][1]), mejor_area)
                )
            i += 1
    finally:
        cap.release()

    return Trayectoria(detecciones, i, perfil.nombre)


def proyectar(
    tray: Trayectoria, versor: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Reduce la trayectoria 2D a coordenadas del plano inclinado.

    Devuelve (frames, s, n): s a lo largo de la rampa y n perpendicular a ella.
    La perpendicular no se descarta: mientras el cuerpo esta sobre la rampa es
    practicamente constante, y en cuanto se despega cambia de golpe. Es el
    criterio mas limpio para saber donde termina el deslizamiento.
    """
    if not tray.detecciones:
        raise ValueError("Trayectoria vacia")
    frames = np.array([d.frame for d in tray.detecciones], dtype=float)
    x = np.array([d.x_px for d in tray.detecciones])
    y = np.array([d.y_px for d in tray.detecciones])
    s = (x - x[0]) * versor[0] + (y - y[0]) * versor[1]
    n = -(x - x[0]) * versor[1] + (y - y[0]) * versor[0]
    return frames, s, n


def recortar_fuera_de_rampa(
    n: np.ndarray, i0: int, i1: int, k_sigma: float = 6.0, n_base: int = 12, piso_px: float = 12.0
) -> tuple[int, str]:
    """Adelanta el fin de la ventana al cuadro en que el cuerpo deja la rampa.

    Mientras desliza, la distancia del centroide al eje de la rampa es
    constante (es media altura del cuerpo). Cuando cae a la mesa, se despega.
    """
    tramo = n[i0 : min(i0 + n_base, i1)]
    if len(tramo) < 4:
        return i1, "sin datos para el control perpendicular"
    base = float(np.median(tramo))
    sigma = float(np.std(tramo, ddof=1)) or 1.0
    # Piso absoluto: con el cuerpo casi quieto la dispersion perpendicular es
    # de decimas de pixel, y k_sigma veces eso dispara con cualquier deriva
    # normal del centroide (el blob cambia de forma al moverse). Despegarse de
    # la rampa de verdad significa varios pixeles.
    umbral = max(k_sigma * sigma, piso_px)
    for k in range(i0 + n_base, i1):
        if abs(n[k] - base) > umbral:
            return max(i0 + 10, k - 2), f"deja la rampa en el indice {k} (umbral {umbral:.1f} px)"
    return i1, "no se detecta salida de la rampa"


def sigma_posicion(tray: Trayectoria, versor: np.ndarray, n_quietos: int = 20) -> float:
    """Incerteza de localizacion, medida con el objeto QUIETO.

    Al principio del video el cuerpo esta sostenido por la mano y no se mueve.
    La dispersion del centroide en esos cuadros es el ruido del detector, que
    es lo que hay que propagar. No se inventa un numero.
    """
    if len(tray.detecciones) < n_quietos:
        raise ValueError("Muy pocas detecciones para estimar el ruido")
    _, s, _ = proyectar(tray, versor)
    return float(np.std(s[:n_quietos], ddof=1))


def ventana_deslizamiento(
    frames: np.ndarray,
    s: np.ndarray,
    fps: float,
    n_quietos: int = 20,
    k_sigma: float = 8.0,
    margen_final: int = 3,
) -> tuple[int, int]:
    """Indices entre los que el cuerpo esta deslizando sobre la rampa.

    Recorta dos tramos que no sirven:
      - el principio, donde la mano todavia sostiene el cuerpo;
      - el final, donde el cuerpo ya dejo la rampa.

    El arranque NO se detecta umbralizando la velocidad instantanea. A 120 fps
    un ruido de posicion de ~1 px se convierte en ~120 px/s de ruido en la
    derivada, que supera a la velocidad real de los primeros cuadros: el
    umbral dispara con el cuerpo todavia quieto. Se usa en cambio el
    DESPLAZAMIENTO acumulado respecto de la linea de base, que no amplifica el
    ruido, y se exige que el avance se sostenga en los cuadros siguientes para
    no arrancar en un pico aislado.
    """
    if len(s) < n_quietos + 10:
        raise ValueError("Muy pocos puntos para encontrar la ventana")

    base = float(np.median(s[:n_quietos]))
    sigma = float(np.std(s[:n_quietos], ddof=1)) or 1.0
    umbral = base + k_sigma * sigma

    i0 = None
    for i in range(n_quietos, len(s) - 5):
        if s[i] > umbral and np.all(np.diff(s[i : i + 5]) > 0):
            i0 = i
            break
    if i0 is None:
        raise ValueError("No se detecto el arranque del deslizamiento")

    # el final: ultimo cuadro en que sigue avanzando de forma sostenida
    i1 = len(s)
    for i in range(i0 + 5, len(s) - 3):
        if np.all(np.diff(s[i : i + 4]) <= 0):
            i1 = i
            break

    i1 = max(i0 + 10, i1 - margen_final)
    return i0, min(i1, len(s))


def recortar_por_area(tray: Trayectoria, i0: int, i1: int, tolerancia: float = 1.6) -> int:
    """Adelanta el fin de la ventana al cuadro donde el area se dispara."""
    areas = np.array([d.area_px for d in tray.detecciones], dtype=float)
    base = float(np.median(areas[i0:i1])) if i1 > i0 else float(np.median(areas))
    for k in range(i0, min(i1, len(areas))):
        if areas[k] > base * tolerancia:
            return max(i0 + 10, k - 2)
    return i1
