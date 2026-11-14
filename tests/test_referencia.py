"""Datos del laboratorio y magnitudes derivadas de ellos."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from uncertainties import ufloat

import referencia

# Los valores que el Grupo 3 escribio a mano en las fotos del docx. Son el
# ancla de todo el proyecto: si un cambio en el codigo o en el JSON los mueve,
# se rompio algo de lo que depende cada aceleracion y cada mu.
ANGULOS_MANUSCRITOS = {
    "angulo_1": 34.3527047,
    "angulo_2": 24.6243183,
    "angulo_3": 20.1963306,
}


# --------------------------------------------------------------------------
# VERDE
# --------------------------------------------------------------------------


@pytest.mark.verde
@pytest.mark.parametrize("clave,grados", ANGULOS_MANUSCRITOS.items())
def test_angulos_reproducen_lo_manuscrito(referencia, clave: str, grados: float) -> None:
    """Los angulos derivados tienen que dar los mismos que calculo el Grupo 3."""
    calculado = math.degrees(referencia.angulo_rad(clave).n)
    assert calculado == pytest.approx(grados, abs=1e-4), (
        f"{clave}: el codigo da {calculado:.4f} y el manuscrito dice {grados:.4f}"
    )


@pytest.mark.verde
def test_los_angulos_estan_ordenados(referencia) -> None:
    """Mas libros, mas inclinacion. Ordena por altura, no por el nombre."""
    a1 = referencia.angulo_rad("angulo_1").n
    a2 = referencia.angulo_rad("angulo_2").n
    a3 = referencia.angulo_rad("angulo_3").n
    assert a1 > a2 > a3


@pytest.mark.verde
def test_mu_estatico_es_tangente_del_angulo_critico(referencia) -> None:
    for clave, obj in referencia.objetos.items():
        theta = obj.angulo_critico(referencia.hipotenusa_cm)
        assert referencia.mu_estatico(clave).n == pytest.approx(math.tan(theta.n), rel=1e-9)


@pytest.mark.verde
def test_mu_estatico_en_rango_fisico(referencia) -> None:
    """Materiales secos comunes: mu entre 0.1 y 1. Fuera de ahi, algo se cargo mal."""
    for clave, obj in referencia.objetos.items():
        mu = referencia.mu_estatico(clave).n
        assert 0.1 < mu < 1.0, f"{obj.nombre}: mu_e = {mu:.3f} fuera de rango creible"


@pytest.mark.verde
def test_las_masas_son_positivas_y_en_kilos(referencia) -> None:
    for obj in referencia.objetos.values():
        assert 0 < obj.masa_kg.n < 1.0, f"{obj.nombre}: {obj.masa_kg.n} kg no es creible"


@pytest.mark.verde
def test_estan_los_tres_objetos_y_los_tres_angulos(referencia) -> None:
    assert {o.nombre for o in referencia.objetos.values()} == {"tapa", "esponja", "jabon"}
    assert set(referencia.angulos) == {"angulo_1", "angulo_2", "angulo_3"}


# --------------------------------------------------------------------------
# ROJO
# --------------------------------------------------------------------------


@pytest.mark.rojo
def test_archivo_inexistente_falla_claro(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        referencia.cargar(tmp_path / "no-existe.json")


@pytest.mark.rojo
def test_json_incompleto_no_pasa_silencioso(tmp_path: Path) -> None:
    """Un JSON al que le falta una seccion tiene que explotar, no cargar a medias."""
    archivo = tmp_path / "parcial.json"
    archivo.write_text(json.dumps({"geometria": {"hipotenusa_cm": 42.0}}), encoding="utf-8")
    with pytest.raises(KeyError):
        referencia.cargar(archivo)


@pytest.mark.rojo
def test_angulo_desconocido_falla(referencia) -> None:
    with pytest.raises(KeyError):
        referencia.angulo_rad("angulo_47")


@pytest.mark.rojo
def test_altura_mayor_que_hipotenusa_es_imposible() -> None:
    """asin(h/H) con h > H no tiene solucion: no puede devolver un numero igual."""
    from referencia import Objeto

    obj = Objeto(
        clave="x", nombre="imposible", masa_kg=ufloat(0.1, 0.001),
        altura_inicio_cm=ufloat(50.0, 0.1),
    )
    with pytest.raises(ValueError):
        obj.angulo_critico(ufloat(42.0, 0.1))


# --------------------------------------------------------------------------
# AMARILLO
# --------------------------------------------------------------------------


@pytest.mark.amarillo
def test_toda_magnitud_derivada_lleva_incerteza(referencia) -> None:
    """La regla del proyecto: nada devuelve un float pelado."""
    for clave in referencia.angulos:
        assert referencia.angulo_rad(clave).s > 0, f"{clave} salio con incerteza cero"
    for clave in referencia.objetos:
        assert referencia.mu_estatico(clave).s > 0


@pytest.mark.amarillo
def test_la_incerteza_del_angulo_es_chica_pero_no_nula(referencia) -> None:
    """Si da 0 es que se perdio la propagacion; si da mas de 1 grado, el dato no sirve."""
    for clave in referencia.angulos:
        sigma = math.degrees(referencia.angulo_rad(clave).s)
        assert 0.0 < sigma < 1.0, f"{clave}: sigma = {sigma:.3f} grados"


@pytest.mark.amarillo
def test_la_esponja_tiene_masa_con_mucho_error_relativo(referencia) -> None:
    """3 g anotados en gramos enteros dan 33% de error. Hay que saberlo al
    reportar fuerzas; no afecta a mu, que no depende de la masa."""
    esponja = next(o for o in referencia.objetos.values() if o.nombre == "esponja")
    relativo = esponja.masa_kg.s / esponja.masa_kg.n
    assert relativo > 0.2, "si bajo, revisar que el criterio de la catedra siga siendo el mismo"


@pytest.mark.amarillo
def test_los_saltos_de_altura_no_son_uniformes(referencia) -> None:
    """Documenta la irregularidad que la catedra confirmo que NO es un error:
    los libros son de espesores distintos. El test existe para que nadie
    'arregle' las alturas pensando que estan mal cargadas."""
    alturas = sorted(a.altura_cm.n for a in referencia.angulos.values())
    saltos = [b - a for a, b in zip(alturas, alturas[1:])]
    assert saltos[0] != pytest.approx(saltos[1], rel=0.2), (
        "los saltos se volvieron uniformes: alguien cambio las alturas"
    )
