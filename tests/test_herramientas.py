"""Las funciones que el modelo de lenguaje puede llamar.

Lo que se verifica no es solo que devuelvan datos, sino que **fallen bien**: el
modelo lee lo que devuelven, asi que un error tiene que volver como un dato que
pueda explicar, no como una excepcion que corte el chat.
"""

from __future__ import annotations

import json

import pytest

from llm import herramientas as H

pytestmark = pytest.mark.usefixtures("exige_resultados")


def serializable(x) -> int:  # noqa: ANN001
    """Todo lo que vuelve viaja como JSON hacia el modelo."""
    return len(json.dumps(x, ensure_ascii=False))


# --------------------------------------------------------------------------
# VERDE
# --------------------------------------------------------------------------


@pytest.mark.verde
@pytest.mark.parametrize("funcion", H.HERRAMIENTAS, ids=lambda f: f.__name__)
def test_toda_herramienta_tiene_nombre_y_docstring(funcion) -> None:  # noqa: ANN001
    """El esquema que ve el modelo sale de la firma y el docstring: si falta,
    el modelo no sabe cuando ni como llamarla."""
    assert funcion.__doc__ and len(funcion.__doc__.strip()) > 40, (
        f"{funcion.__name__} necesita un docstring que explique cuando usarla"
    )


@pytest.mark.verde
def test_las_que_no_llevan_argumentos_devuelven_json() -> None:
    for funcion in (H.estado_del_proyecto, H.datos_del_laboratorio, H.inventario_videos):
        assert serializable(funcion()) > 100, funcion.__name__


@pytest.mark.verde
def test_resumen_por_condicion_trae_las_doce_combinaciones() -> None:
    r = H.resumen_por_condicion()
    assert len(r["condiciones"]) == 12, "3 objetos x 4 condiciones"
    assert set(r["objetos"]) == {"tapa", "esponja", "jabon"}


@pytest.mark.verde
@pytest.mark.parametrize("objeto", ["tapa", "esponja", "jabon"])
def test_filtro_por_objeto(objeto: str) -> None:
    r = H.resumen_por_condicion(objeto)
    assert r["condiciones"], f"sin datos para {objeto}"
    assert all(c["objeto"] == objeto for c in r["condiciones"])


@pytest.mark.verde
def test_listar_corridas_cuenta_los_61_videos() -> None:
    r = H.listar_corridas()
    assert r["n"] == 61
    assert r["n"] == len(r["corridas"])


@pytest.mark.verde
def test_detalle_de_una_corrida_conocida() -> None:
    r = H.detalle_corrida("Tapa 4Libros Video1.mp4")
    assert r["objeto"] == "tapa"
    assert r["condicion"] == "4libros"
    assert r["aceleracion"][0] > 0


@pytest.mark.verde
def test_comparar_hipotesis_trae_las_dos() -> None:
    r = H.comparar_hipotesis("tapa", "4libros")
    assert "hipotesis_desliza" in r and "hipotesis_rueda" in r
    assert r["hipotesis_desliza"]["mu_dinamico_necesario"]["valor"] > 0
    assert len(r["hipotesis_rueda"]["predicciones"]) == 3


@pytest.mark.verde
@pytest.mark.parametrize("doc", ["arquitectura", "hallazgos", "readme", "datos_laboratorio"])
def test_leer_cada_documento(doc: str) -> None:
    r = H.leer_documento(doc)
    assert r.get("texto"), f"{doc} vino vacio: {r.get('error')}"
    assert r["caracteres"] > 200


@pytest.mark.verde
def test_los_angulos_vienen_con_incerteza() -> None:
    for c in H.resumen_por_condicion("tapa")["condiciones"]:
        if c["angulo_grados"]:
            assert c["angulo_grados"]["incerteza"] > 0


# --------------------------------------------------------------------------
# ROJO
# --------------------------------------------------------------------------


@pytest.mark.rojo
def test_objeto_invalido_devuelve_error_y_la_lista_de_validos() -> None:
    r = H.resumen_por_condicion("ladrillo")
    assert "error" in r
    assert set(r["validos"]) == {"tapa", "esponja", "jabon"}


@pytest.mark.rojo
def test_corrida_inexistente_sugiere_parecidas() -> None:
    r = H.detalle_corrida("Tapa 9Libros Video9.mp4")
    assert "error" in r
    assert "parecidas" in r


@pytest.mark.rojo
def test_corrida_parcial_encuentra_candidatas() -> None:
    r = H.detalle_corrida("Tapa 4Libros")
    assert "error" in r
    assert any("Tapa 4Libros" in n for n in r["parecidas"])


@pytest.mark.rojo
def test_documento_desconocido_no_lee_archivos_arbitrarios() -> None:
    """Importa por seguridad: el nombre viene del modelo, no de nosotros."""
    for intento in ("../../.env", "/etc/passwd", "secretos", ".env"):
        r = H.leer_documento(intento)
        assert "error" in r, f"leer_documento acepto '{intento}'"
        assert "texto" not in r


@pytest.mark.rojo
def test_comparar_hipotesis_con_combinacion_inexistente() -> None:
    r = H.comparar_hipotesis("tapa", "7libros")
    assert "error" in r
    assert "combinaciones" in r


@pytest.mark.rojo
def test_comparar_hipotesis_rechaza_el_angulo_critico() -> None:
    """Ahi el cuerpo recien arranca: no hay tramo acelerado que contrastar."""
    r = H.comparar_hipotesis("tapa", "angulo critico")
    assert "error" in r


@pytest.mark.rojo
def test_falta_de_cache_da_instruccion_accionable(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    """Sin resultados/ el modelo tiene que recibir que hay que correr lote.py,
    no una excepcion ni un numero inventado."""
    monkeypatch.setattr(H, "RESULTADOS", tmp_path / "no-existe")
    with pytest.raises(H.FaltanDatos) as exc:
        H.resumen_por_condicion()
    assert "lote.py" in str(exc.value)


@pytest.mark.rojo
def test_estado_del_proyecto_degrada_sin_cache(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    """Esta es la que el modelo llama primero: no puede explotar."""
    monkeypatch.setattr(H, "RESULTADOS", tmp_path / "no-existe")
    r = H.estado_del_proyecto()
    assert r["disponible"] is False
    assert "lote.py" in r["motivo"]


# --------------------------------------------------------------------------
# AMARILLO
# --------------------------------------------------------------------------


@pytest.mark.amarillo
def test_las_condiciones_sin_datos_dicen_None_y_no_un_cero() -> None:
    """Un cero se puede confundir con 'midio cero'. Tiene que ser None."""
    for c in H.resumen_por_condicion()["condiciones"]:
        if c["n_confiables"] < 2:
            assert c["aceleracion_m_s2"] is None, f"{c['objeto']}/{c['condicion']}"


@pytest.mark.amarillo
def test_el_angulo_critico_se_marca_como_no_aplica() -> None:
    """No es una falla de medicion: esos videos no sirven para aceleracion."""
    criticas = [
        c for c in H.resumen_por_condicion()["condiciones"] if c["condicion"] == "angulo critico"
    ]
    assert len(criticas) == 3
    for c in criticas:
        assert c["no_aplica"], f"{c['objeto']} no explica por que no aplica"
        assert not c["descartadas"], "no deberia listar descartes en una condicion que no aplica"


@pytest.mark.amarillo
def test_las_corridas_descartadas_dicen_el_motivo() -> None:
    r = H.listar_corridas()
    descartadas = [c for c in r["corridas"] if not c["confiable"]]
    assert descartadas, "no hay descartes: revisar si el filtro dejo de funcionar"
    for c in descartadas:
        assert c["motivo_descarte"], f"{c['archivo']} descartada sin motivo"


@pytest.mark.amarillo
def test_el_jabon_sigue_sin_datos_confiables() -> None:
    """Limitacion conocida y documentada. Si este test falla es buena noticia:
    quiere decir que se arreglo el tracker y hay que actualizar hallazgos.md."""
    r = H.resumen_por_condicion("jabon")
    con_datos = [c for c in r["condiciones"] if c["aceleracion_m_s2"]]
    assert not con_datos, (
        "el jabon ahora mide: actualizar hallazgos.md y el prompt de sistema"
    )


@pytest.mark.amarillo
def test_estado_del_proyecto_lista_las_limitaciones() -> None:
    r = H.estado_del_proyecto()
    assert len(r["limitaciones_conocidas"]) >= 3
    assert any("jabon" in s.lower() for s in r["limitaciones_conocidas"])


@pytest.mark.amarillo
def test_la_contradiccion_de_la_tapa_se_reporta() -> None:
    r = H.comparar_hipotesis("tapa", "4libros")
    assert r["hipotesis_desliza"]["contradiccion"], (
        "ya no se denuncia que mu_d > mu_e para la tapa"
    )


@pytest.mark.amarillo
def test_ninguna_respuesta_es_demasiado_grande_para_el_contexto() -> None:
    """Un resultado gigante quema contexto y plata. 40 kB es el techo sano."""
    for funcion in (H.estado_del_proyecto, H.resumen_por_condicion, H.listar_corridas,
                    H.datos_del_laboratorio, H.inventario_videos):
        tam = serializable(funcion())
        assert tam < 40_000, f"{funcion.__name__} devuelve {tam} caracteres"
