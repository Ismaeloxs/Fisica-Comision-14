"""Filtros de calidad y agregacion del lote.

El criterio de que corrida sirve y cual no es lo que separa un numero
defendible de uno inventado. Se prueba con fichas armadas a mano, sin tocar
videos, porque lo que importa es la regla y no la medicion.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import lote


def ficha(**cambios) -> dict:
    """Una corrida medida, sana por defecto."""
    base = {
        "archivo": "Tapa 4Libros Video1.mp4",
        "objeto": "tapa",
        "condicion": "4libros",
        "repeticion": 1,
        "error": None,
        "n_puntos": 50,
        "recorrido_cm": 25.0,
        "cobertura": 1.0,
        "aceleracion": [2.3, 0.1],
    }
    base.update(cambios)
    return base


def lote_de(n: int, objeto: str = "tapa", condicion: str = "4libros",
            aceleraciones: list[float] | None = None) -> list[dict]:
    # valores levemente distintos: dispersion cero entre mediciones
    # independientes es el caso degenerado, que se prueba aparte.
    acs = aceleraciones or [2.3 + 0.05 * i for i in range(n)]
    filas = []
    for i, a in enumerate(acs[:n], 1):
        f = ficha(archivo=f"{objeto} {condicion} Video{i}.mp4", objeto=objeto,
                  condicion=condicion, repeticion=i, aceleracion=[a, 0.1])
        ok, motivo = lote._confiable(f)
        f["confiable"] = ok
        f["motivo_descarte"] = motivo or None
        filas.append(f)
    return filas


# --------------------------------------------------------------------------
# VERDE
# --------------------------------------------------------------------------


@pytest.mark.verde
def test_una_corrida_sana_pasa_el_filtro() -> None:
    ok, motivo = lote._confiable(ficha())
    assert ok and motivo == ""


@pytest.mark.verde
def test_la_media_y_la_dispersion_son_las_de_los_datos() -> None:
    import statistics

    acs = [2.1, 2.3, 2.5, 2.2, 2.4]
    g = lote.agregar(lote_de(5, aceleraciones=acs))
    c = next(c for c in g["condiciones"] if c["condicion"] == "4libros")
    assert c["aceleracion_media"] == pytest.approx(statistics.mean(acs))
    assert c["dispersion_entre_repeticiones"] == pytest.approx(statistics.stdev(acs))


@pytest.mark.verde
def test_el_error_de_la_media_es_la_dispersion_sobre_raiz_de_n() -> None:
    import math
    import statistics

    acs = [2.1, 2.3, 2.5, 2.2, 2.4]
    g = lote.agregar(lote_de(5, aceleraciones=acs))
    c = next(c for c in g["condiciones"] if c["condicion"] == "4libros")
    esperado = statistics.stdev(acs) / math.sqrt(5)
    assert c["error_de_la_media"] == pytest.approx(esperado)


@pytest.mark.verde
def test_el_agregado_calcula_mu_y_el_factor_de_inercia() -> None:
    g = lote.agregar(lote_de(5))
    c = next(c for c in g["condiciones"] if c["condicion"] == "4libros")
    assert c["mu_d_si_desliza"][0] > 0
    assert c["factor_inercia_si_rueda"][0] > 1.0
    assert c["angulo_grados"][0] == pytest.approx(34.3527, abs=1e-3)


@pytest.mark.verde
def test_el_agregado_incluye_los_tres_objetos_con_su_mu_estatico() -> None:
    g = lote.agregar(lote_de(5))
    assert set(g["objetos"]) == {"tapa", "esponja", "jabon"}
    for o in g["objetos"].values():
        assert o["mu_estatico"][0] > 0 and o["mu_estatico"][1] > 0


# --------------------------------------------------------------------------
# ROJO
# --------------------------------------------------------------------------


@pytest.mark.rojo
@pytest.mark.parametrize(
    "cambio,fragmento",
    [
        ({"error": "ErrorMedicion: no se detecto el papel"}, "papel"),
        ({"n_puntos": 10}, "puntos"),
        ({"recorrido_cm": 1.5}, "recorrido"),
        ({"aceleracion": [-3.9, 2.5]}, "no positiva"),
        ({"aceleracion": [0.0, 0.1]}, "no positiva"),
        ({"cobertura": 0.6}, "tracker"),
    ],
)
def test_el_filtro_rechaza_y_dice_por_que(cambio: dict, fragmento: str) -> None:
    ok, motivo = lote._confiable(ficha(**cambio))
    assert not ok
    assert fragmento in motivo, f"motivo poco claro: {motivo}"


@pytest.mark.rojo
def test_una_sola_corrida_buena_no_alcanza_para_dar_dispersion() -> None:
    """Con n=1 no hay dispersion posible: no puede inventar una incerteza."""
    g = lote.agregar(lote_de(1))
    c = next(c for c in g["condiciones"] if c["condicion"] == "4libros")
    assert c["aceleracion_media"] is None
    assert "nota" in c


@pytest.mark.rojo
def test_cero_corridas_buenas_no_rompe_el_agregado() -> None:
    filas = lote_de(3, aceleraciones=[-1.0, -2.0, -3.0])
    g = lote.agregar(filas)
    c = next(c for c in g["condiciones"] if c["condicion"] == "4libros")
    assert c["aceleracion_media"] is None
    assert c["n_confiables"] == 0
    assert len(c["archivos_descartados"]) == 3


@pytest.mark.rojo
def test_lista_vacia_no_rompe() -> None:
    g = lote.agregar([])
    assert g["condiciones"] == []
    assert g["totales"]["videos"] == 0


@pytest.mark.rojo
def test_el_agregado_es_json_serializable() -> None:
    """Se escribe a disco y lo leen las herramientas del chat."""
    g = lote.agregar(lote_de(5))
    assert json.loads(json.dumps(g, ensure_ascii=False))


# --------------------------------------------------------------------------
# AMARILLO
# --------------------------------------------------------------------------


@pytest.mark.amarillo
def test_el_angulo_critico_se_marca_no_aplica_y_no_como_falla() -> None:
    filas = lote_de(5, condicion="angulo critico", aceleraciones=[0.01] * 5)
    g = lote.agregar(filas)
    c = next(c for c in g["condiciones"] if c["condicion"] == "angulo critico")
    assert c["no_aplica"], "sin explicacion de por que no aplica"
    assert c["archivos_descartados"] == [], "no deberia reportar descartes"
    assert c["aceleracion_media"] is None


@pytest.mark.amarillo
def test_los_umbrales_son_explicitos_y_razonables() -> None:
    """Estan en el codigo como constantes, no como numeros magicos sueltos."""
    assert lote.MIN_PUNTOS >= 10, "menos de 10 puntos no sostiene un ajuste cuadratico"
    assert lote.MIN_RECORRIDO_CM >= 1.0


@pytest.mark.amarillo
def test_una_dispersion_enorme_igual_se_reporta_con_su_numero() -> None:
    """No se oculta ni se descarta: se informa para que se vea el problema."""
    g = lote.agregar(lote_de(4, aceleraciones=[0.2, 0.5, 0.9, 0.1]))
    c = next(c for c in g["condiciones"] if c["condicion"] == "4libros")
    assert c["dispersion_relativa"] > 0.5
    assert c["aceleracion_media"] is not None


@pytest.mark.amarillo
def test_los_totales_cuadran_con_las_filas() -> None:
    filas = lote_de(5) + lote_de(3, objeto="jabon", aceleraciones=[-1.0, -1.0, -1.0])
    g = lote.agregar(filas)
    assert g["totales"]["videos"] == 8
    assert g["totales"]["confiables"] == 5


@pytest.mark.amarillo
def test_el_cache_real_en_disco_es_coherente(exige_resultados, raiz: Path) -> None:  # noqa: ANN001
    """Guarda contra un global.json escrito por una version vieja del codigo."""
    corridas = json.loads((raiz / "resultados" / "corridas.json").read_text(encoding="utf-8"))
    glob = json.loads((raiz / "resultados" / "global.json").read_text(encoding="utf-8"))
    assert glob["totales"]["videos"] == len(corridas)
    confiables = sum(1 for c in corridas if c["confiable"])
    assert glob["totales"]["confiables"] == confiables
    for c in glob["condiciones"]:
        assert c["n_confiables"] <= c["n_videos"]


@pytest.mark.amarillo
def test_dispersion_cero_se_denuncia_como_sospechosa() -> None:
    """Entre mediciones independientes no puede dar exactamente lo mismo: suele
    ser un video duplicado o un cache sin invalidar. Avisarlo es mejor que
    emitir un mu con incerteza cero."""
    g = lote.agregar(lote_de(4, aceleraciones=[2.3, 2.3, 2.3, 2.3]))
    c = next(c for c in g["condiciones"] if c["condicion"] == "4libros")
    assert c.get("sospecha"), "no avisa que la dispersion dio cero"
    assert "duplicados" in c["sospecha"]
