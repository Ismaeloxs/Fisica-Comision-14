"""Configuracion comun de los tests.

Los tests se clasifican con tres marcas:

    verde     camino feliz: tiene que funcionar y dar el numero correcto
    rojo      manejo de errores: entrada mala o datos faltantes tienen que dar
              un error claro, nunca romper ni devolver un numero inventado
    amarillo  degradado: funciona pero con reservas. Filtros de calidad,
              advertencias fisicas, datos poco confiables

    pytest -m verde
    pytest -m "rojo or amarillo"

Ademas:

    video     necesita los videos del laboratorio, que no estan en el repo
    red       llama a una API y gasta cuota: NO corre salvo que se pida
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
AGENTE = RAIZ / "src" / "agente"

# Los modulos del agente se importan por nombre plano (medir, fisica, ...),
# igual que cuando se corre `python src/agente/visor.py`.
for ruta in (str(AGENTE), str(RAIZ)):
    if ruta not in sys.path:
        sys.path.insert(0, ruta)


def pytest_configure(config: pytest.Config) -> None:
    for marca, ayuda in (
        ("verde", "camino feliz"),
        ("rojo", "manejo de errores"),
        ("amarillo", "casos degradados y advertencias"),
        ("video", "necesita los videos del laboratorio"),
        ("red", "llama a una API externa y gasta cuota"),
    ):
        config.addinivalue_line("markers", f"{marca}: {ayuda}")


def pytest_collection_modifyitems(config: pytest.Config, items: list) -> None:
    """Los tests de red no corren salvo que se pidan explicitamente."""
    if config.getoption("-m").strip() == "red":
        return
    saltar = pytest.mark.skip(reason="llama a una API real; correr con: pytest -m red")
    for item in items:
        if "red" in item.keywords:
            item.add_marker(saltar)


# --------------------------------------------------------------------------
# Rutas de datos
# --------------------------------------------------------------------------


@pytest.fixture(scope="session")
def raiz() -> Path:
    return RAIZ


@pytest.fixture(scope="session")
def carpeta_videos() -> Path:
    from inventario import CARPETA_VIDEOS

    return CARPETA_VIDEOS


@pytest.fixture(scope="session")
def un_video(carpeta_videos: Path) -> Path:
    """Un video conocido y bien medido, para los tests de integracion."""
    ruta = carpeta_videos / "Tapa 4Libros Video1.mp4"
    if not ruta.is_file():
        pytest.skip(f"falta {ruta.name}: los videos no se versionan")
    return ruta


@pytest.fixture(scope="session")
def hay_resultados(raiz: Path) -> bool:
    return (raiz / "resultados" / "global.json").is_file()


@pytest.fixture
def exige_resultados(hay_resultados: bool) -> None:
    if not hay_resultados:
        pytest.skip("falta el cache: correr primero `python src/agente/lote.py`")


@pytest.fixture(scope="session")
def referencia():
    from referencia import cargar

    return cargar()
