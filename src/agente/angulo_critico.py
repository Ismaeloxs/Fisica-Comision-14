"""Angulo critico medido por el agente, contra el anotado a mano por el Grupo 3.

    python src/agente/angulo_critico.py                 # los videos de angulo critico
    python src/agente/angulo_critico.py --objeto tapa   # solo uno
    python src/agente/angulo_critico.py --validar       # control con 2/3/4 libros

QUE MIDE
En estos videos la rampa NO esta fija: una persona levanta el extremo de
arriba a mano hasta que el objeto arranca. Por eso no sirve medir.py (que
calibra una vez con el cuadro 0 y busca una aceleracion constante). Lo que
importa aca es el angulo de la rampa en el instante en que el objeto arranca:

    mu_e = tan(theta_c)

El Grupo 3 lo obtuvo midiendo con regla la altura del extremo (h) y haciendo
theta_c = asin(h / 42 cm). El agente lo mide en la imagen, cuadro a cuadro.

COMO
Por cada cuadro:
  1. Angulo de la rampa: el canto de madera de la tabla es una franja larga
     de color marron (H 5-20, S alta, V 60-112). Se toma el componente mas
     largo y se le ajusta una recta (PCA). El angulo se corrige por el giro
     de la camara, medido sobre los bordes verticales del termo.
  2. Referencia fija a la rampa: el papel rosa, pegado arriba.
  3. Objeto: su perfil de color, buscado solo cerca de la recta de la rampa
     (asi no se confunde con la tapita que a veces esta sobre la mesa).
  4. d(t) = distancia objeto-papel medida A LO LARGO de la rampa. Mientras el
     objeto esta quieto sobre la rampa, d es constante aunque la rampa gire,
     porque las dos cosas giran juntas. Cuando arranca, d crece.
El cuadro de arranque es el primero donde d crece de forma sostenida; el
angulo de la rampa en ese cuadro es theta_c.

LIMITACIONES QUE HAY QUE REPORTAR
  - El angulo en la imagen es una PROYECCION. Si la camara no mira la rampa
    perpendicularmente, el angulo aparente difiere del real. --validar lo
    cuantifica con los videos de 2/3/4 libros, donde el angulo es conocido.
    Ojo: esos videos se filmaron con otro encuadre, asi que el control es
    indicativo, no una calibracion exacta de estos.
  - Si el objeto rueda (la tapa sobre su canto), theta_c no mide rozamiento
    estatico sino la resistencia a empezar a rodar.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np
from uncertainties import ufloat, umath

from inventario import CARPETA_VIDEOS
from referencia import cargar as cargar_referencia

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = RAIZ / "resultados" / "angulo_critico"
FPS = 120.0
ESCALA = 0.5  # se procesa a 960x540: sobra para el angulo y es 4 veces mas rapido

# --- colores (HSV de OpenCV, medidos sobre cuadros reales de estos videos) ---
# Canto de madera de la rampa: H 10-17, S 130-210, V 72-103. La mano tiene un
# tono parecido (H 5-10) pero es mas clara (V 114-150): el tope de V la deja
# afuera. La tabla oscura que se ve abajo a la izquierda tiene V ~40.
MADERA_MIN, MADERA_MAX = (5, 110, 60), (20, 255, 112)
ROSA_MIN, ROSA_MAX = (150, 80, 100), (179, 255, 255)
OBJETOS_HSV = {
    # tapita azul: S y V altos la separan de cualquier otra cosa azul mate
    "tapa": ((98, 180, 90), (118, 255, 255)),
    # amarillo de la esponja: S~180 V~190. La madera tiene S parecida pero V<112
    "esponja": ((17, 120, 140), (30, 255, 255)),
    # jabon: H 15-19, S 128-164, V 137-166. La pared (S~16) y la mesa (S~33)
    # quedan afuera por saturacion; el canto de madera, por brillo.
    "jabon": ((12, 105, 125), (22, 200, 215)),
}
# area minima de cada mancha, en pixeles a la escala de proceso
AREA_MIN = {"madera": 1500, "rosa": 400, "objeto": 250}
# hasta que distancia perpendicular de la recta de la rampa se busca el objeto
BANDA_OBJETO_PX = 90
LARGO_PAPEL_CM = 7.5

# Criterio de arranque. El jabon y la esponja NO arrancan de golpe: se corren
# despacio (creep, ~0,4 cm/s) o a saltitos (stick-slip) mientras la rampa sube,
# y recien despues deslizan. Por eso se reportan dos angulos:
#   - theta_c (deslizamiento): primer instante en que la velocidad sobre la
#     rampa supera V_DESLIZA y se sostiene SOSTENER_S segundos. Es el que se
#     compara con el Grupo 3, que anoto "cuando arranca a moverse".
#   - theta_corrimiento: primer instante en que el objeto se corrio mas de
#     CORRIMIENTO_CM de su posicion inicial, a cualquier velocidad.
V_DESLIZA_CM_S = 1.0
SOSTENER_S = 0.25
CORRIMIENTO_CM = 0.3
VENTANA_V_S = 0.25  # suavizado (Savitzky-Golay) para derivar d(t)

PATRON = re.compile(
    r"^(?P<objeto>Tapa|Esponja|Jabon) Angulo Critico Video(?P<rep>\d+)(?P<dup>\(\d+\))?\.mp4$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------- deteccion


def _componentes(mascara: np.ndarray, area_min: int):
    n, etiquetas, stats, centros = cv2.connectedComponentsWithStats(mascara)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= area_min:
            yield i, etiquetas, int(stats[i, cv2.CC_STAT_AREA]), centros[i]


def recta_rampa(hsv: np.ndarray) -> tuple[float, np.ndarray, np.ndarray, float] | None:
    """(angulo_imagen_rad, punto, versor, largo_px) del canto de madera, o None.

    El versor apunta hacia abajo de la rampa (hacia la derecha en estos
    videos). angulo > 0 significa que el extremo izquierdo esta mas alto.
    """
    m = cv2.inRange(hsv, MADERA_MIN, MADERA_MAX)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mejor = None
    for i, et, area, _ in _componentes(m, AREA_MIN["madera"]):
        ys, xs = np.where(et == i)
        pts = np.column_stack([xs, ys]).astype(np.float64)
        centro = pts.mean(axis=0)
        _, sv, vt = np.linalg.svd(pts - centro, full_matrices=False)
        u = vt[0]
        if u[0] < 0:
            u = -u
        proy = (pts - centro) @ u
        largo = float(proy.max() - proy.min())
        elongacion = sv[0] / max(sv[1], 1e-9)
        ang = math.atan2(u[1], u[0])
        # la rampa es una franja larga y no vertical (descarta la silla)
        if elongacion < 6 or abs(math.degrees(ang)) > 60:
            continue
        if mejor is None or largo > mejor[3]:
            mejor = (ang, centro, u, largo)
    return mejor


def mancha(hsv: np.ndarray, hsv_min, hsv_max, area_min: int, filtro=None):
    """Centroide de la mancha mas grande que pasa el filtro, o None."""
    m = cv2.inRange(hsv, hsv_min, hsv_max)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mejor, mejor_area = None, 0
    for _, _, area, c in _componentes(m, area_min):
        if filtro is not None and not filtro(c):
            continue
        if area > mejor_area:
            mejor, mejor_area = np.array(c, dtype=np.float64), area
    return mejor


def largo_papel(hsv: np.ndarray, u: np.ndarray, centro: np.ndarray) -> float:
    """Largo del papel rosa proyectado sobre el eje de la rampa, en pixeles.

    Igual que calibracion.detectar_papel: se proyecta sobre el eje porque el
    papel esta doblado sobre el canto y la cara lateral infla el rectangulo.
    """
    m = cv2.inRange(hsv, ROSA_MIN, ROSA_MAX)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, et, stats, cs = cv2.connectedComponentsWithStats(m)
    if n <= 1:
        return float("nan")
    j = 1 + int(np.argmin(np.linalg.norm(cs[1:] - centro, axis=1)))
    ys, xs = np.where(et == j)
    proy = xs * u[0] + ys * u[1]
    return float(proy.max() - proy.min())


def giro_camara(frame_bgr: np.ndarray) -> float | None:
    """Giro de la camara en radianes (0 si esta derecha), o None si no se mide.

    Referencia: los bordes del termo, que es un cilindro vertical con bordes
    nitidos y aparece en todos los videos (franja 55-85 % del ancho). Si la
    camara esta girada un angulo r, una recta vertical aparece a 90 + r grados
    y todas las demas rectas, incluida la rampa, quedan corridas el mismo r.
    La linea mesa-pared seria lo natural, pero tiene muy poco contraste
    (blanco sobre blanco) y Hough no la encuentra.
    """
    gris = cv2.GaussianBlur(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    bordes = cv2.Canny(gris, 30, 90)
    alto, ancho = gris.shape
    bordes[:, : int(0.55 * ancho)] = 0
    bordes[:, int(0.85 * ancho) :] = 0
    lineas = cv2.HoughLinesP(
        bordes, 1, np.pi / 720, threshold=50, minLineLength=int(0.12 * alto), maxLineGap=10
    )
    if lineas is None:
        return None
    angs, pesos = [], []
    for x1, y1, x2, y2 in lineas.reshape(-1, 4):
        if y2 < y1:  # orientar hacia abajo
            x1, y1, x2, y2 = x2, y2, x1, y1
        a = math.atan2(y2 - y1, x2 - x1) - math.pi / 2
        if abs(math.degrees(a)) < 4:
            angs.append(a)
            pesos.append(math.hypot(x2 - x1, y2 - y1))
    if len(angs) < 2:
        return None
    return float(np.average(angs, weights=pesos))


# ---------------------------------------------------------------- serie


@dataclass
class Serie:
    frames: np.ndarray
    theta_img: np.ndarray  # rad, sin corregir giro
    d_px: np.ndarray  # objeto-papel a lo largo de la rampa
    perp_px: np.ndarray  # objeto respecto de la recta, perpendicular
    papel_px: np.ndarray  # largo del papel a lo largo de la rampa (escala)
    giro: float  # rad
    giro_detectado: bool


def recorrer(ruta: Path, objeto: str, paso: int = 2) -> Serie:
    cap = cv2.VideoCapture(str(ruta))
    if not cap.isOpened():
        raise ValueError(f"No se pudo abrir {ruta}")
    hsv_obj = OBJETOS_HSV[objeto]
    frames, thetas, ds, perps, papeles = [], [], [], [], []
    giro = None
    i = 0
    try:
        while True:
            ok = cap.grab()
            if not ok:
                break
            if i % paso:
                i += 1
                continue
            ok, fr = cap.retrieve()
            if not ok:
                break
            fr = cv2.resize(fr, None, fx=ESCALA, fy=ESCALA, interpolation=cv2.INTER_AREA)
            if giro is None:
                giro = giro_camara(fr)
                giro_ok = giro is not None
                giro = giro if giro is not None else 0.0
            hsv = cv2.cvtColor(fr, cv2.COLOR_BGR2HSV)

            th, d, pp, lp = np.nan, np.nan, np.nan, np.nan
            r = recta_rampa(hsv)
            if r is not None:
                ang, p0, u, largo = r
                th = ang
                nrm = np.array([-u[1], u[0]])

                def cerca(c, p0=p0, u=u, nrm=nrm, largo=largo):
                    v = np.asarray(c) - p0
                    return abs(v @ nrm) < BANDA_OBJETO_PX and abs(v @ u) < 0.75 * largo

                papel = mancha(hsv, ROSA_MIN, ROSA_MAX, AREA_MIN["rosa"], cerca)
                if papel is not None:
                    lp = largo_papel(hsv, u, papel)
                obj = mancha(hsv, *hsv_obj, AREA_MIN["objeto"], cerca)
                if papel is not None and obj is not None:
                    d = float((obj - papel) @ u)
                    pp = float((obj - p0) @ nrm)
            frames.append(i)
            thetas.append(th)
            ds.append(d)
            perps.append(pp)
            papeles.append(lp)
            i += 1
    finally:
        cap.release()
    return Serie(
        np.array(frames, dtype=float),
        np.array(thetas),
        np.array(ds) / ESCALA,  # devuelto en pixeles del video original
        np.array(perps) / ESCALA,
        np.array(papeles) / ESCALA,
        float(giro or 0.0),
        bool(giro_ok) if frames else False,
    )


# ---------------------------------------------------------------- arranque


def _mediana_movil(x: np.ndarray, k: int) -> np.ndarray:
    out = np.full_like(x, np.nan)
    h = k // 2
    for j in range(len(x)):
        w = x[max(0, j - h) : j + h + 1]
        w = w[~np.isnan(w)]
        if len(w):
            out[j] = np.median(w)
    return out


def detectar_arranque(
    d: np.ndarray, base_n: int = 60, k_sigma: float = 5.0, piso_px: float = 6.0, sostener: int = 6
) -> tuple[int, dict]:
    """Indice del cuadro en que el objeto arranca a deslizar sobre la rampa.

    Se recorre la serie comparando cada punto contra la linea de base de los
    base_n puntos anteriores (la rampa se mueve lento, el objeto no). El
    arranque es el primer punto que supera base + umbral y desde el cual d
    sigue creciendo `sostener` puntos seguidos; despues se retrocede hasta el
    ultimo punto que todavia estaba en la linea de base.
    """
    ds = _mediana_movil(d, 5)
    n = len(ds)
    for j in range(base_n, n - sostener):
        base_w = ds[j - base_n : j]
        base_w = base_w[~np.isnan(base_w)]
        if len(base_w) < base_n // 2 or np.isnan(ds[j]):
            continue
        base = float(np.median(base_w))
        sigma = float(1.4826 * np.median(np.abs(base_w - base))) or 0.5
        umbral = max(k_sigma * sigma, piso_px)
        if ds[j] - base <= umbral:
            continue
        sig = ds[j : j + sostener]
        if np.any(np.isnan(sig)) or not np.all(np.diff(sig) > 0):
            continue
        # retroceder al ultimo punto todavia "quieto"
        k = j
        while k > 0 and not np.isnan(ds[k - 1]) and ds[k - 1] - base > 2 * max(sigma, 0.5):
            k -= 1
        return k, {"base_px": base, "sigma_base_px": sigma, "umbral_px": umbral, "supera_en": j}
    raise ValueError("No se detecto el arranque del objeto")


def _rellenar(x: np.ndarray, max_hueco: int) -> np.ndarray:
    """Interpola linealmente huecos (NaN) cortos; deja NaN los largos."""
    y = x.copy()
    idx = np.arange(len(y))
    ok = ~np.isnan(y)
    if ok.sum() < 2:
        return y
    interp = np.interp(idx, idx[ok], y[ok])
    j = 0
    while j < len(y):
        if np.isnan(y[j]):
            k = j
            while k < len(y) and np.isnan(y[k]):
                k += 1
            if k - j <= max_hueco and j > 0 and k < len(y):
                y[j:k] = interp[j:k]
            j = k
        else:
            j += 1
    return y


def detectar_por_velocidad(t: np.ndarray, d_cm: np.ndarray) -> dict:
    """Arranque por velocidad (deslizamiento) y por corrimiento acumulado.

    Devuelve indices (o None) y la serie de velocidad suavizada, para graficar.
    """
    from scipy.signal import savgol_filter

    dt = float(np.median(np.diff(t)))
    d = _rellenar(d_cm, max_hueco=int(0.1 / dt))
    w = int(round(VENTANA_V_S / dt)) | 1
    v = np.full_like(d, np.nan)
    ok = ~np.isnan(d)
    # derivar por tramos continuos
    j = 0
    while j < len(d):
        if not ok[j]:
            j += 1
            continue
        k = j
        while k < len(d) and ok[k]:
            k += 1
        if k - j > w:
            v[j:k] = savgol_filter(d[j:k], w, 2, deriv=1, delta=dt)
        j = k

    n_sost = max(2, int(round(SOSTENER_S / dt)))
    i_desliza = None
    for j in range(len(v) - n_sost):
        tramo = v[j : j + n_sost]
        if np.all(tramo > V_DESLIZA_CM_S):
            i_desliza = j
            break

    n_base = max(3, int(round(0.3 / dt)))
    base = np.nanmedian(d[:n_base]) if np.any(~np.isnan(d[:n_base])) else np.nan
    i_corr = None
    n_conf = max(3, int(round(0.1 / dt)))
    if not np.isnan(base):
        for j in range(n_base, len(d) - n_conf):
            tramo = d[j : j + n_conf]
            if np.all(tramo - base > CORRIMIENTO_CM):
                i_corr = j
                break
    return {"i_desliza": i_desliza, "i_corrimiento": i_corr, "v_cm_s": v, "d_cm": d}


def _angulo_en(theta: np.ndarray, k: int, paso: int) -> tuple[float, float] | None:
    """(theta, sigma) de la rampa en el indice k, en radianes.

    theta: mediana en los ~50 ms previos. sigma: ruido cuadro a cuadro de la
    recta (dispersion respecto de una tendencia lineal en el segundo previo)
    combinado con cuanto sube la rampa en +-2 puntos de incertidumbre del
    instante de arranque.
    """
    ventana = max(3, int(0.05 * FPS / paso))
    w = theta[max(0, k - ventana) : k + 1]
    w = w[~np.isnan(w)]
    if len(w) == 0:
        return None
    th = float(np.median(w))
    w_larga = theta[max(0, k - int(FPS / paso)) : k + 1]
    x = np.arange(len(w_larga))
    ok = ~np.isnan(w_larga)
    if ok.sum() > 5:
        coef = np.polyfit(x[ok], w_larga[ok], 1)
        ruido = float(np.std(w_larga[ok] - np.polyval(coef, x[ok]), ddof=2))
        subida = abs(coef[0]) * 2
    else:
        ruido, subida = (float(np.std(w)) if len(w) > 1 else 0.0), 0.0
    return th, math.hypot(ruido, subida)


# ---------------------------------------------------------------- medicion


@dataclass
class ResultadoVideo:
    archivo: str
    objeto: str
    repeticion: int
    duplicado: bool
    n_cuadros: int
    cobertura_rampa: float
    cobertura_objeto: float
    giro_camara_grados: float
    giro_detectado: bool
    cuadro_arranque: int | None = None
    t_arranque_s: float | None = None
    theta_c_grados: float | None = None
    sigma_theta_c_grados: float | None = None
    mu_e: float | None = None
    sigma_mu_e: float | None = None
    px_por_cm: float | None = None
    theta_max_grados: float | None = None
    theta_corrimiento_grados: float | None = None
    t_corrimiento_s: float | None = None
    error: str | None = None
    avisos: list[str] = field(default_factory=list)


def medir_video(ruta: Path, objeto: str, paso: int = 2, graficar: bool = True) -> ResultadoVideo:
    m = PATRON.match(ruta.name)
    rep = int(m.group("rep")) if m else 0
    dup = bool(m and m.group("dup"))
    s = recorrer(ruta, objeto, paso)
    theta = s.theta_img - s.giro
    res = ResultadoVideo(
        archivo=ruta.name,
        objeto=objeto,
        repeticion=rep,
        duplicado=dup,
        n_cuadros=int(s.frames[-1]) + 1 if len(s.frames) else 0,
        cobertura_rampa=float(np.mean(~np.isnan(theta))) if len(theta) else 0.0,
        cobertura_objeto=float(np.mean(~np.isnan(s.d_px))) if len(theta) else 0.0,
        giro_camara_grados=math.degrees(s.giro),
        giro_detectado=s.giro_detectado,
    )
    if not s.giro_detectado:
        res.avisos.append("no se pudo medir el giro de camara (termo): angulo sin corregir")
    if res.cobertura_objeto < 0.3:
        res.error = f"el objeto se detecto solo en el {res.cobertura_objeto:.0%} de los cuadros"
        _guardar_serie(ruta, s, theta, None, res, graficar)
        return res
    # escala: largo del papel en pixeles / 7,5 cm (mediana de toda la toma)
    lp = s.papel_px[~np.isnan(s.papel_px)]
    if len(lp) < 10:
        res.error = "no se pudo medir el papel rosa para la escala"
        _guardar_serie(ruta, s, theta, None, res, graficar)
        return res
    px_cm = float(np.median(lp)) / LARGO_PAPEL_CM
    res.px_por_cm = px_cm
    t = s.frames / FPS
    det = detectar_por_velocidad(t, s.d_px / px_cm)
    s.v_cm_s = det["v_cm_s"]
    th_ok = theta[~np.isnan(theta)]
    res.theta_max_grados = float(np.degrees(np.percentile(th_ok, 99))) if len(th_ok) else None

    kc = det["i_corrimiento"]
    if kc is not None:
        r = _angulo_en(theta, kc, paso)
        if r is not None:
            res.theta_corrimiento_grados = math.degrees(r[0])
            res.t_corrimiento_s = float(t[kc])
    s.k_corr = kc

    k = det["i_desliza"]
    if k is None:
        res.error = (
            f"el objeto nunca supera {V_DESLIZA_CM_S:.1f} cm/s sostenido: no desliza en la toma "
            f"(rampa hasta {res.theta_max_grados:.1f} grados)"
        )
        _guardar_serie(ruta, s, theta, None, res, graficar)
        return res
    r = _angulo_en(theta, k, paso)
    if r is None:
        res.error = "no hay angulo de rampa medido en el cuadro de arranque"
        _guardar_serie(ruta, s, theta, k, res, graficar)
        return res
    th, sigma = r
    th_u = ufloat(th, sigma)
    mu = umath.tan(th_u)

    res.cuadro_arranque = int(s.frames[k])
    res.t_arranque_s = float(s.frames[k] / FPS)
    res.theta_c_grados = math.degrees(th)
    res.sigma_theta_c_grados = math.degrees(sigma)
    res.mu_e = mu.n
    res.sigma_mu_e = mu.s
    if res.cobertura_objeto < 0.7:
        res.avisos.append(f"objeto detectado en solo {res.cobertura_objeto:.0%} de los cuadros")
    _guardar_serie(ruta, s, theta, k, res, graficar)
    return res


def _guardar_serie(ruta, s: Serie, theta, k, res: ResultadoVideo, graficar: bool) -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    base = SALIDA / ruta.stem.replace(" ", "_")
    with base.with_suffix(".csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["cuadro", "t_s", "theta_grados", "d_px", "perp_px"])
        for fr, th, d, p in zip(s.frames, theta, s.d_px, s.perp_px):
            w.writerow([int(fr), f"{fr / FPS:.4f}", f"{math.degrees(th):.4f}", f"{d:.2f}", f"{p:.2f}"])
    if not graficar:
        return
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = s.frames / FPS
    fig, (a1, a2, a3) = plt.subplots(3, 1, figsize=(9, 8), sharex=True)
    a1.plot(t, np.degrees(theta), ".", ms=2, color="#2563cb")
    a1.set_ylabel("angulo rampa [grados]")
    escala = res.px_por_cm or 1.0
    unidad = "cm" if res.px_por_cm else "px"
    a2.plot(t, s.d_px / escala, ".", ms=2, color="#7b5ea7")
    a2.set_ylabel(f"objeto-papel [{unidad}]")
    v = getattr(s, "v_cm_s", None)
    if v is not None:
        a3.plot(t, v, "-", lw=1, color="#2a9d8f")
        a3.axhline(V_DESLIZA_CM_S, color="#d1495b", lw=1, ls=":", label=f"umbral {V_DESLIZA_CM_S} cm/s")
        a3.legend(fontsize=8)
    a3.set_ylabel("v sobre la rampa [cm/s]")
    a3.set_xlabel("t [s]")
    kc = getattr(s, "k_corr", None)
    if kc is not None:
        for a in (a1, a2, a3):
            a.axvline(t[kc], color="#c08a2b", lw=1, ls="--")
    if res.theta_corrimiento_grados is not None:
        a1.axhline(res.theta_corrimiento_grados, color="#c08a2b", lw=0.8, ls="--")
    if res.theta_max_grados is not None:
        a1.axhline(res.theta_max_grados, color="#888888", lw=0.8, ls=":")
    if k is not None and res.theta_c_grados is not None:
        for a in (a1, a2, a3):
            a.axvline(t[k], color="#d1495b", lw=1.2)
        a1.axhline(res.theta_c_grados, color="#d1495b", lw=1, ls="--")
        a1.set_title(
            f"{ruta.stem}:  theta_c = {res.theta_c_grados:.2f} +/- {res.sigma_theta_c_grados:.2f} grados"
            f"  ->  mu_e = {res.mu_e:.3f}",
            fontsize=10,
        )
    else:
        a1.set_title(f"{ruta.stem}: {res.error}", fontsize=10)
    for a in (a1, a2, a3):
        a.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(base.with_suffix(".png"), dpi=110)
    plt.close(fig)


# ---------------------------------------------------------------- comparacion


def referencia_por_objeto() -> dict[str, tuple]:
    """nombre -> (theta_c ufloat [rad], mu_e ufloat) del Grupo 3."""
    ref = cargar_referencia()
    out = {}
    for o in ref.objetos.values():
        out[o.nombre] = (o.angulo_critico(ref.hipotenusa_cm), o.mu_estatico(ref.hipotenusa_cm))
    return out


def comparar(resultados: list[ResultadoVideo]) -> dict:
    refs = referencia_por_objeto()
    resumen = {}
    print(f"\n{'=' * 78}\nCOMPARACION AGENTE vs GRUPO 3 (angulo critico)\n{'=' * 78}")
    for nombre in ("tapa", "esponja", "jabon"):
        rs = [r for r in resultados if r.objeto == nombre and r.theta_c_grados is not None]
        if nombre not in refs:
            continue
        th_ref, mu_ref = refs[nombre]
        print(f"\n{nombre.upper()}")
        print(
            f"  Grupo 3 (regla):  theta_c = {math.degrees(th_ref.n):6.2f} +/- "
            f"{math.degrees(th_ref.s):.2f} grados   mu_e = {mu_ref.n:.4f} +/- {mu_ref.s:.4f}"
        )
        todos = [r for r in resultados if r.objeto == nombre]
        maxs = [r.theta_max_grados for r in todos if r.theta_max_grados is not None]
        sin_desl = [r for r in todos if r.theta_c_grados is None]
        if maxs:
            print(
                f"  Rampa maxima en los videos: {min(maxs):.1f} a {max(maxs):.1f} grados"
                + (
                    f"   ({sum(m < math.degrees(th_ref.n) for m in maxs)} de {len(maxs)} videos "
                    f"nunca llegan al theta_c del Grupo 3)"
                )
            )
        for r in sin_desl:
            print(f"    {r.archivo:38s} sin deslizamiento: {r.error}")
        if not rs:
            print("  Agente: ninguna corrida con deslizamiento")
            continue
        ths = np.array([r.theta_c_grados for r in rs])
        mus = np.array([r.mu_e for r in rs])
        n = len(rs)
        th_m = float(ths.mean())
        # la dispersion ENTRE repeticiones es el error honesto; el error de la
        # media divide por sqrt(n)
        th_disp = float(ths.std(ddof=1)) if n > 1 else float(rs[0].sigma_theta_c_grados)
        th_err = th_disp / math.sqrt(n)
        mu_m, mu_disp = float(mus.mean()), float(mus.std(ddof=1)) if n > 1 else rs[0].sigma_mu_e
        mu_err = mu_disp / math.sqrt(n)
        for r in rs:
            corr = (
                f"   corrimiento desde {r.theta_corrimiento_grados:5.2f}"
                if r.theta_corrimiento_grados is not None
                else ""
            )
            print(
                f"    {r.archivo:38s} theta_c = {r.theta_c_grados:6.2f} +/- "
                f"{r.sigma_theta_c_grados:.2f}   mu_e = {r.mu_e:.4f}   (t = {r.t_arranque_s:.2f} s){corr}"
            )
        dif = th_m - math.degrees(th_ref.n)
        sig_comb = math.hypot(th_err, math.degrees(th_ref.s))
        n_sig = abs(dif) / sig_comb if sig_comb > 0 else float("inf")
        print(
            f"  Agente ({n} corridas): theta_c = {th_m:6.2f} +/- {th_err:.2f} grados "
            f"(dispersion {th_disp:.2f})   mu_e = {mu_m:.4f} +/- {mu_err:.4f}"
        )
        veredicto = "COMPATIBLES" if n_sig < 2 else "NO compatibles"
        print(f"  Diferencia: {dif:+.2f} grados = {n_sig:.1f} sigma  ->  {veredicto} (criterio 2 sigma)")
        resumen[nombre] = {
            "n": n,
            "theta_c_agente_grados": [th_m, th_err],
            "dispersion_grados": th_disp,
            "mu_e_agente": [mu_m, mu_err],
            "theta_c_grupo3_grados": [math.degrees(th_ref.n), math.degrees(th_ref.s)],
            "mu_e_grupo3": [mu_ref.n, mu_ref.s],
            "diferencia_grados": dif,
            "sigmas": n_sig,
        }
    print(
        "\n  Nota: el angulo del agente es el aparente en la imagen. Correr --validar\n"
        "  para ver cuanto difiere el aparente del real en los videos con libros."
    )
    return resumen


# ---------------------------------------------------------------- validacion


def validar(carpeta: Path) -> None:
    """Angulo aparente del canto de madera vs asin(h/42) en los videos con libros."""
    ref = cargar_referencia()
    claves = {"4Libros": "angulo_1", "3Libros": "angulo_2", "2Libros": "angulo_3"}
    print(f"\n{'=' * 78}\nVALIDACION: angulo en imagen vs angulo de la regla (rampa fija)\n{'=' * 78}")
    filas = []
    for cond, clave in claves.items():
        real = math.degrees(ref.angulo_rad(clave).n)
        medidos = []
        for ruta in sorted(carpeta.glob(f"* {cond} Video*.mp4")):
            cap = cv2.VideoCapture(str(ruta))
            angs = []
            giro = None
            for _ in range(15):  # el objeto todavia sostenido: la rampa se ve entera
                ok, fr = cap.read()
                if not ok:
                    break
                fr = cv2.resize(fr, None, fx=ESCALA, fy=ESCALA, interpolation=cv2.INTER_AREA)
                if giro is None:
                    giro = giro_camara(fr) or 0.0
                r = recta_rampa(cv2.cvtColor(fr, cv2.COLOR_BGR2HSV))
                if r is not None:
                    angs.append(r[0])
            cap.release()
            if angs:
                medidos.append(math.degrees(float(np.median(angs)) - giro))
        if not medidos:
            print(f"  {cond}: no se pudo medir")
            continue
        m = np.array(medidos)
        filas.append((real, m.mean()))
        print(
            f"  {cond}: regla {real:6.2f}   imagen {m.mean():6.2f} +/- {m.std(ddof=1) if len(m) > 1 else 0:.2f} "
            f"grados ({len(m)} videos)   diferencia {m.mean() - real:+.2f}"
        )
    if len(filas) >= 2:
        r, im = np.array(filas).T
        pend, ord0 = np.polyfit(r, im, 1)
        print(f"\n  Recta imagen = {pend:.3f} * regla {ord0:+.2f} grados")
        print(
            "  Si la pendiente es ~1 y la ordenada ~0, el angulo aparente es confiable.\n"
            "  Si no, hay perspectiva (o la altura de algun angulo esta mal anotada)."
        )


# ---------------------------------------------------------------- main


def main() -> None:
    p = argparse.ArgumentParser(description="Angulo critico: agente vs Grupo 3")
    p.add_argument("--carpeta", type=Path, default=CARPETA_VIDEOS)
    p.add_argument("--objeto", choices=["tapa", "esponja", "jabon"])
    p.add_argument("--video", help="un solo archivo dentro de la carpeta")
    p.add_argument("--paso", type=int, default=2, help="procesar 1 de cada N cuadros (default 2)")
    p.add_argument("--incluir-duplicados", action="store_true", help='incluir archivos tipo "Video5(1)"')
    p.add_argument("--validar", action="store_true", help="control con los videos de 2/3/4 libros")
    p.add_argument("--sin-graficos", action="store_true")
    args = p.parse_args()

    if args.validar:
        validar(args.carpeta)
        return

    if args.video:
        rutas = [args.carpeta / args.video]
    else:
        rutas = sorted(args.carpeta.glob("* Angulo Critico Video*.mp4"))
    resultados = []
    for ruta in rutas:
        m = PATRON.match(ruta.name)
        if not m:
            print(f"[salteado] nombre no interpretable: {ruta.name}")
            continue
        objeto = m.group("objeto").lower()
        if args.objeto and objeto != args.objeto:
            continue
        if m.group("dup") and not args.incluir_duplicados and not args.video:
            print(f"[salteado] duplicado: {ruta.name} (usar --incluir-duplicados)")
            continue
        print(f"midiendo {ruta.name} ...", flush=True)
        r = medir_video(ruta, objeto, args.paso, not args.sin_graficos)
        if r.error:
            print(f"   FALLA: {r.error}")
        else:
            print(
                f"   theta_c = {r.theta_c_grados:.2f} +/- {r.sigma_theta_c_grados:.2f} grados  "
                f"mu_e = {r.mu_e:.4f}  (arranque t = {r.t_arranque_s:.2f} s, "
                f"giro camara {r.giro_camara_grados:+.2f})"
            )
        extra = []
        if r.theta_corrimiento_grados is not None:
            extra.append(
                f"empieza a correrse a {r.theta_corrimiento_grados:.2f} grados (t = {r.t_corrimiento_s:.2f} s)"
            )
        if r.theta_max_grados is not None:
            extra.append(f"rampa maxima {r.theta_max_grados:.2f} grados")
        if extra:
            print("   " + ";  ".join(extra))
        for a in r.avisos:
            print(f"   [!] {a}")
        resultados.append(r)

    resumen = comparar(resultados)
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "resumen.json").write_text(
        json.dumps(
            {"corridas": [asdict(r) for r in resultados], "por_objeto": resumen},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\n-> {SALIDA / 'resumen.json'}  (y un .csv y .png por video)")


if __name__ == "__main__":
    main()
