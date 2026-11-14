"""Capa de chat: interfaz, registro de herramientas y esquemas.

Nada de esto llama a una API. Lo que se prueba es la plomeria: que los esquemas
salgan bien de las firmas, que el registro de herramientas no mienta y que la
eleccion de proveedor respete el entorno.

El unico test que gasta cuota esta marcado `red` y no corre por defecto.
"""

from __future__ import annotations

import pytest

from llm import base, herramientas
from llm.base import RegistroHerramientas


@pytest.fixture
def entorno_limpio(monkeypatch) -> None:  # noqa: ANN001
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "GEMINI_API_KEY",
              "GOOGLE_API_KEY", "AGENTE_LLM"):
        monkeypatch.delenv(k, raising=False)


# --------------------------------------------------------------------------
# VERDE
# --------------------------------------------------------------------------


@pytest.mark.verde
def test_el_registro_anota_lo_que_se_ejecuta() -> None:
    r = RegistroHerramientas()
    envuelta = r.envolver(herramientas.inventario_videos)
    envuelta()
    envuelta()
    assert r.llamadas == ["inventario_videos", "inventario_videos"]


@pytest.mark.verde
def test_envolver_conserva_nombre_docstring_y_firma() -> None:
    """De ahi sale el esquema que ve el modelo: si se pierde, el modelo queda
    ciego a los parametros."""
    import inspect

    r = RegistroHerramientas()
    for original in herramientas.HERRAMIENTAS:
        envuelta = r.envolver(original)
        assert envuelta.__name__ == original.__name__
        assert envuelta.__doc__ == original.__doc__
        assert inspect.signature(envuelta) == inspect.signature(original)


@pytest.mark.verde
def test_los_esquemas_de_claude_tienen_los_parametros_correctos() -> None:
    from llm.proveedor_claude import _envolver

    esquemas = {t.to_dict()["name"]: t.to_dict() for t in _envolver(RegistroHerramientas())}
    assert len(esquemas) == len(herramientas.HERRAMIENTAS)

    esperado = {
        "detalle_corrida": {"archivo"},
        "comparar_hipotesis": {"objeto", "condicion"},
        "leer_documento": {"nombre"},
        "estado_del_proyecto": set(),
        "inventario_videos": set(),
    }
    for nombre, requeridos in esperado.items():
        req = set(esquemas[nombre]["input_schema"].get("required", []))
        assert req == requeridos, f"{nombre}: requeridos {req}, esperados {requeridos}"


@pytest.mark.verde
def test_toda_herramienta_lleva_descripcion_para_el_modelo() -> None:
    from llm.proveedor_claude import _envolver

    for t in _envolver(RegistroHerramientas()):
        d = t.to_dict()
        assert len(d.get("description") or "") > 40, f"{d['name']} sin descripcion util"


@pytest.mark.verde
def test_el_prompt_de_sistema_tiene_las_reglas_que_importan() -> None:
    p = base.SISTEMA.lower()
    assert "nunca calcules un numero" in p, "falta la regla de no inventar numeros"
    assert "incerteza" in p
    assert "dispersion entre repeticiones" in p
    assert "rueda" in p, "falta el hallazgo de la rodadura de la tapa"
    assert "jabon" in p, "falta avisar que el seguimiento del jabon esta roto"


@pytest.mark.verde
def test_crear_elige_por_variable_de_entorno(monkeypatch, entorno_limpio) -> None:  # noqa: ANN001
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("AGENTE_LLM", "gemini")
    conv = base.crear()
    assert conv.nombre_proveedor == "Gemini"


@pytest.mark.verde
def test_crear_elige_el_que_tenga_clave_si_no_se_especifica(monkeypatch, entorno_limpio) -> None:  # noqa: ANN001
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert base.crear().nombre_proveedor == "Gemini"


@pytest.mark.verde
def test_respuesta_chat_tiene_valores_por_defecto() -> None:
    r = base.RespuestaChat(texto="hola")
    assert r.herramientas_usadas == []
    assert r.tokens_entrada == 0 and r.error is None


# --------------------------------------------------------------------------
# ROJO
# --------------------------------------------------------------------------


@pytest.mark.rojo
def test_sin_credenciales_explica_como_configurar(entorno_limpio) -> None:  # noqa: ANN001
    with pytest.raises(base.ErrorProveedor) as exc:
        base.crear()
    mensaje = str(exc.value)
    assert "ANTHROPIC_API_KEY" in mensaje and "GEMINI_API_KEY" in mensaje


@pytest.mark.rojo
def test_proveedor_desconocido_falla(entorno_limpio) -> None:  # noqa: ANN001
    with pytest.raises(base.ErrorProveedor) as exc:
        base.crear("chatgpt")
    assert "chatgpt" in str(exc.value)


@pytest.mark.rojo
def test_gemini_sin_clave_falla_con_el_link(monkeypatch, entorno_limpio) -> None:  # noqa: ANN001
    with pytest.raises(base.ErrorProveedor) as exc:
        base.crear("gemini")
    assert "aistudio" in str(exc.value)


@pytest.mark.rojo
def test_el_registro_se_limpia_entre_preguntas() -> None:
    """Si no, la segunda respuesta muestra las herramientas de la primera y la
    linea de auditoria deja de ser confiable."""
    r = RegistroHerramientas()
    r.envolver(herramientas.inventario_videos)()
    assert len(r.llamadas) == 1
    r.limpiar()
    assert r.llamadas == []


@pytest.mark.rojo
def test_el_registro_anota_aunque_la_herramienta_devuelva_error() -> None:
    """Una herramienta que devuelve {'error': ...} igual se ejecuto: tiene que
    figurar en la auditoria."""
    r = RegistroHerramientas()
    envuelta = r.envolver(herramientas.leer_documento)
    salida = envuelta("inexistente")
    assert "error" in salida
    assert r.llamadas == ["leer_documento"]


@pytest.mark.rojo
def test_una_herramienta_que_lanza_igual_queda_registrada() -> None:
    """El registro anota antes de ejecutar, asi que una excepcion no borra el
    rastro de que se intento."""
    def explota() -> None:
        """Herramienta de prueba que falla a proposito."""
        raise RuntimeError("boom")

    r = RegistroHerramientas()
    with pytest.raises(RuntimeError):
        r.envolver(explota)()
    assert r.llamadas == ["explota"]


# --------------------------------------------------------------------------
# AMARILLO
# --------------------------------------------------------------------------


@pytest.mark.amarillo
def test_el_orden_de_las_herramientas_es_estable() -> None:
    """El esquema de herramientas es parte del prefijo cacheado: si cambia de
    orden entre llamadas, el cache no sirve y cada pregunta cuesta de mas."""
    uno = [f.__name__ for f in herramientas.HERRAMIENTAS]
    dos = [f.__name__ for f in herramientas.HERRAMIENTAS]
    assert uno == dos
    assert uno[0] == "estado_del_proyecto", "la de panorama general va primera"


@pytest.mark.amarillo
def test_el_prompt_pide_no_redondear_la_incerteza_a_cero() -> None:
    """Salio de una respuesta real que mostro 'mu = 0.29 +/- 0.00'."""
    assert "0.00" in base.SISTEMA or "cero" in base.SISTEMA.lower()


@pytest.mark.amarillo
def test_el_prompt_no_es_tan_largo_como_para_pesar_en_cada_pregunta() -> None:
    """Va en todas las consultas. Mas de ~8 kB ya conviene recortarlo."""
    assert len(base.SISTEMA) < 8000, f"{len(base.SISTEMA)} caracteres"


@pytest.mark.amarillo
def test_gemini_toma_el_modelo_de_respaldo_del_entorno(monkeypatch, entorno_limpio) -> None:  # noqa: ANN001
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("GEMINI_MODEL", "modelo-principal")
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "modelo-respaldo")
    conv = base.crear("gemini")
    assert conv.modelo == "modelo-principal"
    assert conv.modelo_respaldo == "modelo-respaldo"


@pytest.mark.amarillo
def test_gemini_sin_respaldo_configurado_no_reintenta(monkeypatch, entorno_limpio) -> None:  # noqa: ANN001
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.delenv("GEMINI_FALLBACK_MODEL", raising=False)
    conv = base.crear("gemini")
    assert conv.modelo_respaldo is None
    assert conv._reabrir_en_respaldo() is False


# --------------------------------------------------------------------------
# RED (gasta cuota: pytest -m red)
# --------------------------------------------------------------------------


@pytest.mark.red
def test_pregunta_real_usa_herramientas_y_responde() -> None:
    conv = base.crear()
    r = conv.preguntar("Que aceleracion midio la tapa a 4 libros? Respondé en una linea.")
    assert not r.error, r.error
    assert r.texto
    assert r.herramientas_usadas, "contesto sin consultar los datos"
    assert "2.3" in r.texto or "2,3" in r.texto


@pytest.mark.red
def test_pregunta_de_teoria_no_consulta_datos() -> None:
    conv = base.crear()
    r = conv.preguntar(
        "Explicá en dos lineas por que el rozamiento dinamico no supera al estatico. "
        "No consultes los datos del grupo."
    )
    assert not r.error, r.error
    assert not r.herramientas_usadas
