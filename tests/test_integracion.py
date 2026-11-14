"""Pipeline completo sobre videos reales.

Lento (segundos por video) y depende de archivos que no estan en el repo, asi
que se saltea solo si faltan. Estos son los unicos tests que verifican que la
cadena entera -- calibracion, seguimiento, ventana, ajuste -- da el numero que
esperamos sobre un video concreto.

    pytest -m video
"""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
import pytest

import calibracion
import tracking
from medir import ErrorMedicion, analizar_corrida, resumen_dict

pytestmark = pytest.mark.video

# Medido sobre "Tapa 4Libros Video1.mp4". Si cambia el pipeline y estos valores
# se mueven, hay que entender por que antes de actualizarlos.
ESCALA_PX_CM = 27.07
ACELERACION = 2.24


@pytest.fixture(scope="module")
def frame0(un_video: Path) -> np.ndarray:
    cap = cv2.VideoCapture(str(un_video))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        pytest.skip("no se pudo leer el primer cuadro")
    return frame


@pytest.fixture(scope="module")
def corrida(un_video: Path):  # noqa: ANN201
    return analizar_corrida(un_video)


# --------------------------------------------------------------------------
# VERDE
# --------------------------------------------------------------------------


@pytest.mark.verde
def test_la_calibracion_encuentra_el_papel_y_da_la_escala(frame0: np.ndarray) -> None:
    cal = calibracion.calibrar(frame0)
    assert cal.px_por_cm.n == pytest.approx(ESCALA_PX_CM, rel=0.02)
    assert cal.px_por_cm.s > 0, "la escala salio sin incerteza"


@pytest.mark.verde
def test_el_eje_de_la_rampa_sale_del_papel_y_no_de_la_mesa(frame0: np.ndarray) -> None:
    """El borde de la mesa esta a ~13 grados. Si el eje da cerca de ese valor,
    volvio el bug de promediar rectas ajenas con Hough."""
    eje = math.degrees(calibracion.detectar_eje_rampa(frame0))
    assert 25.0 < eje < 40.0, f"eje en {eje:.1f} grados: no es la rampa"


@pytest.mark.verde
def test_el_tracker_sigue_la_tapita_en_todos_los_cuadros(un_video: Path) -> None:
    tray = tracking.seguir(un_video, tracking.PERFILES["tapa"])
    assert tray.cobertura > 0.95, f"cobertura {tray.cobertura:.0%}"


@pytest.mark.verde
def test_el_pipeline_completo_da_la_aceleracion_esperada(corrida) -> None:  # noqa: ANN001
    a = corrida.aceleracion
    assert a.n == pytest.approx(ACELERACION, rel=0.06), f"a = {a.n:.3f} +/- {a.s:.3f}"
    assert a.s > 0


@pytest.mark.verde
def test_el_ajuste_es_bueno(corrida) -> None:  # noqa: ANN001
    """Residuo chico quiere decir que el movimiento es uniformemente acelerado,
    que es la hipotesis del ajuste."""
    assert corrida.cin.residuo_rms < 0.005, f"{1000 * corrida.cin.residuo_rms:.1f} mm"


@pytest.mark.verde
def test_la_velocidad_inicial_es_casi_cero(corrida) -> None:  # noqa: ANN001
    """La ventana arranca al soltar el cuerpo: si v0 es grande, el recorte del
    tramo quieto fallo."""
    assert abs(corrida.cin.v_inicial.n) < 0.25, f"v0 = {corrida.cin.v_inicial.n:.3f} m/s"


@pytest.mark.verde
def test_el_resumen_serializa(corrida) -> None:  # noqa: ANN001
    import json

    assert json.loads(json.dumps(resumen_dict(corrida), ensure_ascii=False))


# --------------------------------------------------------------------------
# ROJO
# --------------------------------------------------------------------------


@pytest.mark.rojo
def test_un_cuadro_sin_papel_rosa_falla_claro() -> None:
    """Una imagen gris no tiene nada que calibrar: tiene que decirlo."""
    gris = np.full((1080, 1920, 3), 128, dtype=np.uint8)
    with pytest.raises(ValueError, match="papel"):
        calibracion.calibrar(gris)


@pytest.mark.rojo
def test_el_perfil_equivocado_da_cobertura_baja(un_video: Path) -> None:
    """Buscar el jabon en el video de la tapa no puede devolver una trayectoria
    como si nada."""
    tray = tracking.seguir(un_video, tracking.PERFILES["jabon"])
    assert tray.cobertura < 0.9 or len(tray.detecciones) == 0


@pytest.mark.rojo
def test_video_inexistente_falla(tmp_path: Path) -> None:
    with pytest.raises((ValueError, ErrorMedicion, SystemExit)):
        analizar_corrida(tmp_path / "no-existe.mp4")


@pytest.mark.rojo
def test_trayectoria_sin_movimiento_no_inventa_una_ventana() -> None:
    frames = np.arange(60, dtype=float)
    quieto = np.zeros(60)
    with pytest.raises(ValueError):
        tracking.ventana_deslizamiento(frames, quieto, fps=120.0)


@pytest.mark.rojo
def test_trayectoria_muy_corta_falla() -> None:
    with pytest.raises(ValueError):
        tracking.ventana_deslizamiento(np.arange(5.0), np.zeros(5), fps=120.0)


# --------------------------------------------------------------------------
# AMARILLO
# --------------------------------------------------------------------------


@pytest.mark.amarillo
def test_el_sigma_de_posicion_se_mide_y_es_de_pocos_pixeles(corrida) -> None:  # noqa: ANN001
    """Sale de la dispersion del centroide con el cuerpo quieto. Si diera 0 se
    perdio la medicion; si diera mas de 10 px el tracker no sirve."""
    assert 0.0 < corrida.sigma_px < 10.0, f"sigma = {corrida.sigma_px:.2f} px"


@pytest.mark.amarillo
def test_el_chi2_delata_que_el_sigma_esta_subestimado(corrida) -> None:  # noqa: ANN001
    """Limitacion documentada: el sigma del cuerpo quieto no incluye el
    desenfoque de movimiento. Si este test empieza a fallar por chi2 cercano a
    1, quiere decir que se mejoro la estimacion y hay que actualizar
    hallazgos.md."""
    assert corrida.cin.chi2_reducido > 5, (
        "el chi2 bajo: revisar si se corrigio la estimacion de sigma"
    )


@pytest.mark.amarillo
def test_la_ventana_recorta_el_tramo_quieto_y_la_caida(corrida) -> None:  # noqa: ANN001
    """La ventana util tiene que ser bastante menor que el video entero."""
    usados = corrida.i1 - corrida.i0
    total = len(corrida.tray.detecciones)
    assert 15 < usados < total, f"ventana de {usados} sobre {total} cuadros"


@pytest.mark.amarillo
def test_el_control_de_escala_contra_la_rampa_queda_por_debajo(frame0: np.ndarray) -> None:
    """La regla de 42 cm es cota inferior: sus extremos quedan ocultos, asi que
    su px/cm sale chico. Que la discrepancia sea negativa es lo esperado; si se
    diera vuelta, algo cambio en la deteccion."""
    cal = calibracion.calibrar(frame0)
    chequeo = calibracion.verificar_escala(frame0, cal)
    if not chequeo.get("disponible"):
        pytest.skip("no se detecto la rampa para el control")
    assert chequeo["px_por_cm_rampa"] < cal.px_por_cm.n


@pytest.mark.amarillo
def test_la_deteccion_se_degrada_con_la_velocidad(corrida) -> None:  # noqa: ANN001
    """Limitacion medida: el area detectada CAE a medida que el cuerpo acelera.

    Es desenfoque de movimiento. A 120 fps el cuerpo rapido se estira en el
    cuadro, baja la saturacion del borde y menos pixeles pasan el umbral HSV.
    Dentro de la ventana util el area va de ~2200 a ~1300 px con una
    correlacion de -0.65 contra la velocidad.

    Importa por dos razones:
      - Explica por que el sigma medido con el cuerpo QUIETO subestima el error
        real y el chi2 sale alto: al centroide de un blob mas chico y corrido lo
        afecta mas el ruido.
      - Invalida usar el area como medida de perspectiva. El area esta
        confundida con la velocidad, asi que de su variacion NO se puede
        concluir cuanto aporta la perspectiva a la escala.
    """
    det = corrida.tray.detecciones[corrida.i0 : corrida.i1]
    areas = np.array([d.area_px for d in det], dtype=float)
    v = np.abs(np.gradient(corrida.s_m, corrida.t))
    n = min(len(areas), len(v))
    correlacion = float(np.corrcoef(areas[:n], v[:n])[0, 1])
    assert correlacion < -0.3, (
        f"la correlacion area-velocidad dio {correlacion:+.2f}: si subio, puede "
        "ser que se haya mitigado el desenfoque (buena noticia, actualizar "
        "hallazgos.md) o que el tracker cambie de objeto"
    )
