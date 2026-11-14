"""El entorno de ejecucion.

Existe por un error real: correr `python src/agente/visor.py` sin activar el
venv usaba el Python del sistema, que tenia las dependencias viejas pero no las
nuevas, y el visor entero se caia por un import de la capa de chat.

Dos lecciones, una por test:
  - que las dependencias declaradas esten instaladas donde se corre;
  - que una dependencia opcional que falta no pueda voltear la aplicacion.
"""

from __future__ import annotations

import importlib
import re
import sys
import tkinter as tk
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]

# nombre en requirements.txt -> modulo que se importa
MODULO = {
    "opencv-python": "cv2",
    "python-dateutil": "dateutil",
    "python-dotenv": "dotenv",
    "google-genai": "google.genai",
    "pillow": "PIL",
    "pyyaml": "yaml",
    "ultralytics-thop": "thop",
    "nvidia-ml-py": "pynvml",
    "polars-runtime-32": "polars",
    "ultralytics-platform": "ultralytics",
    "typing-extensions": "typing_extensions",
}

# Paquetes que son dependencias indirectas y no se importan a mano.
NO_SE_IMPORTAN = {
    "anyio", "certifi", "charset-normalizer", "contourpy", "cycler", "filelock",
    "fonttools", "fsspec", "h11", "httpcore", "httpx", "httpx2", "idna",
    "kiwisolver", "markupsafe", "mpmath", "packaging", "psutil", "pyparsing",
    "setuptools", "six", "sympy", "tzdata", "urllib3", "jinja2", "networkx",
    "nvidia-ml-py", "polars-runtime-32", "ultralytics-platform",
    "ultralytics-thop", "torch", "torchvision", "polars", "ultralytics",
}


def paquetes_declarados() -> list[str]:
    texto = (RAIZ / "requirements.txt").read_text(encoding="utf-8")
    nombres = []
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        nombres.append(re.split(r"[=<>!~\[]", linea)[0].strip().lower())
    return nombres


# --------------------------------------------------------------------------
# VERDE
# --------------------------------------------------------------------------


@pytest.mark.verde
def test_los_modulos_del_agente_importan() -> None:
    for nombre in ("referencia", "inventario", "calibracion", "tracking",
                   "cinematica", "fisica", "medir", "lote"):
        importlib.import_module(nombre)


@pytest.mark.verde
def test_requirements_no_tiene_duplicados() -> None:
    nombres = paquetes_declarados()
    repetidos = {n for n in nombres if nombres.count(n) > 1}
    assert not repetidos, f"declarados dos veces: {repetidos}"


@pytest.mark.verde
def test_requirements_esta_pinneado() -> None:
    """Cinco personas con la misma version evitan 'en mi maquina anda'."""
    texto = (RAIZ / "requirements.txt").read_text(encoding="utf-8")
    for linea in texto.splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#"):
            assert "==" in linea, f"sin version fija: {linea}"


@pytest.mark.verde
def test_las_dependencias_nuevas_estan_declaradas() -> None:
    """Si alguien instala un paquete y se olvida de requirements.txt, al
    siguiente que clone el repo le va a pasar el mismo error del visor."""
    declarados = set(paquetes_declarados())
    for p in ("anthropic", "google-genai", "python-dotenv", "uncertainties",
              "opencv-python", "scipy", "numpy", "matplotlib"):
        assert p in declarados, f"falta {p} en requirements.txt"


# --------------------------------------------------------------------------
# ROJO
# --------------------------------------------------------------------------


@pytest.mark.rojo
def test_todo_lo_declarado_se_puede_importar_en_este_interprete() -> None:
    """EL test del error que paso. Si falla, se esta corriendo el Python
    equivocado: activar el venv e instalar requirements.txt."""
    faltan = []
    for paquete in paquetes_declarados():
        if paquete in NO_SE_IMPORTAN:
            continue
        modulo = MODULO.get(paquete, paquete.replace("-", "_"))
        try:
            importlib.import_module(modulo)
        except ImportError:
            faltan.append(f"{paquete} (import {modulo})")
    assert not faltan, (
        "faltan paquetes en "
        f"{sys.executable}:\n  " + "\n  ".join(faltan) +
        "\n\nSi es el Python del sistema, desde la carpeta del repo:\n"
        "    .venv\\Scripts\\activate\n    pip install -r requirements.txt"
    )


@pytest.mark.rojo
def test_el_chat_sin_su_dependencia_no_voltea_el_visor(monkeypatch) -> None:  # noqa: ANN001
    """Era el bug: el import de llm estaba fuera del try y un
    ModuleNotFoundError mataba la aplicacion al abrirse."""
    import chat_ui

    real = importlib.import_module

    def importar_fallando(nombre, *args, **kwargs):  # noqa: ANN001, ANN202
        if nombre == "llm" or nombre.startswith("llm."):
            raise ImportError("simulado", name="google")
        return real(nombre, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", importar_fallando)
    monkeypatch.setitem(sys.modules, "llm", None)  # fuerza el ImportError

    raiz = tk.Tk()
    raiz.withdraw()
    try:
        panel = chat_ui.PanelChat(raiz)  # no tiene que levantar excepcion
        assert panel.conversacion is None
        assert "disabled" in panel.boton.state()
        aviso = panel.texto.get("1.0", "end")
        assert "activate" in aviso or "dependencia" in aviso.lower()
    finally:
        raiz.destroy()


@pytest.mark.rojo
def test_el_env_se_lee_sin_python_dotenv(tmp_path: Path) -> None:
    """El lector minimo tiene que cubrir el caso de que falte el paquete."""
    from llm.base import _cargar_env_simple

    archivo = tmp_path / ".env"
    archivo.write_text(
        "# comentario\n"
        "VACIO=\n"
        'CON_COMILLAS="valor"\n'
        "CON_ESPACIOS =  otro  \n"
        "SIN_IGUAL\n"
        "\n"
        "NORMAL=ok\n",
        encoding="utf-8",
    )
    import os

    for k in ("VACIO", "CON_COMILLAS", "CON_ESPACIOS", "NORMAL", "SIN_IGUAL"):
        os.environ.pop(k, None)
    _cargar_env_simple(archivo)
    assert os.environ["CON_COMILLAS"] == "valor"
    assert os.environ["CON_ESPACIOS"] == "otro"
    assert os.environ["NORMAL"] == "ok"
    assert "SIN_IGUAL" not in os.environ
    for k in ("VACIO", "CON_COMILLAS", "CON_ESPACIOS", "NORMAL"):
        os.environ.pop(k, None)


@pytest.mark.rojo
def test_el_env_no_pisa_una_variable_ya_exportada(tmp_path: Path) -> None:
    from llm.base import _cargar_env_simple
    import os

    os.environ["PRUEBA_PISAR"] = "de la terminal"
    archivo = tmp_path / ".env"
    archivo.write_text("PRUEBA_PISAR=del archivo\n", encoding="utf-8")
    _cargar_env_simple(archivo)
    assert os.environ["PRUEBA_PISAR"] == "de la terminal"
    os.environ.pop("PRUEBA_PISAR", None)


@pytest.mark.rojo
def test_env_inexistente_no_rompe(tmp_path: Path) -> None:
    from llm.base import _cargar_env_simple

    _cargar_env_simple(tmp_path / "no-existe")  # no debe lanzar


# --------------------------------------------------------------------------
# AMARILLO
# --------------------------------------------------------------------------


@pytest.mark.amarillo
def test_el_env_real_no_se_versiona() -> None:
    """Una clave commiteada es un incidente, no un bug."""
    import subprocess

    r = subprocess.run(
        ["git", "check-ignore", ".env"], cwd=RAIZ, capture_output=True, text=True
    )
    assert r.returncode == 0, ".env NO esta en .gitignore"


@pytest.mark.amarillo
def test_hay_plantilla_de_env_sin_secretos() -> None:
    plantilla = RAIZ / ".env.ejemplo"
    assert plantilla.is_file(), "falta .env.ejemplo para que el grupo arme el suyo"
    texto = plantilla.read_text(encoding="utf-8")
    assert "GEMINI_API_KEY" in texto
    # La plantilla no puede traer una clave de verdad
    for linea in texto.splitlines():
        if "API_KEY=" in linea and not linea.strip().startswith("#"):
            valor = linea.split("=", 1)[1].strip()
            assert not valor, f"la plantilla tiene un valor cargado: {linea}"


@pytest.mark.amarillo
def test_los_videos_no_se_versionan() -> None:
    """Son casi 1 GB: un `git add .` descuidado arruina el repo."""
    import subprocess

    r = subprocess.run(
        ["git", "check-ignore", "src/Fuerza de Rozamiento-videos/Fuerza de Rozamiento/"
         "Videos Proyecto mp4 120fps/Tapa 4Libros Video1.mp4"],
        cwd=RAIZ, capture_output=True, text=True,
    )
    assert r.returncode == 0, "los .mp4 no estan ignorados"
