"""Interfaz comun de los proveedores de chat y el prompt de sistema.

El resto del proyecto no sabe si atras hay Claude o Gemini: habla con
Conversacion.preguntar(). Cambiar de proveedor es cambiar una variable de
entorno, no tocar codigo.
"""

from __future__ import annotations

import abc
import os
from dataclasses import dataclass, field
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[3]


def _cargar_env_simple(archivo: Path) -> None:
    """Lector minimo de .env, para cuando python-dotenv no esta instalado.

    Un .env es "CLAVE=valor" con comentarios: no justifica que falte un paquete
    y el proyecto no arranque. python-dotenv se usa si esta (maneja casos raros
    como valores multilinea); si no, alcanza con esto.
    """
    if not archivo.is_file():
        return
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        clave = clave.strip()
        valor = valor.strip().strip('"').strip("'")
        # override=False: una variable ya exportada en la terminal le gana al
        # archivo, que es lo que se espera al probar otra clave sin editarlo.
        if clave and clave not in os.environ:
            os.environ[clave] = valor


# Python no lee .env por su cuenta. Se carga aca, en el modulo que elige el
# proveedor, para que valga igual desde la consola y desde el visor sin que
# cada entrada tenga que acordarse.
try:
    from dotenv import load_dotenv

    load_dotenv(_RAIZ / ".env", override=False)
except ImportError:
    _cargar_env_simple(_RAIZ / ".env")


@dataclass
class RespuestaChat:
    texto: str
    herramientas_usadas: list[str] = field(default_factory=list)
    tokens_entrada: int = 0
    tokens_salida: int = 0
    error: str | None = None


# El prompt de sistema es la pieza que mantiene honesto al chat. Las dos reglas
# que importan: que no invente numeros (que los pida a las herramientas) y que
# no esconda los problemas del proyecto, porque la consigna exige una seccion
# de limitaciones y un chat complaciente la vacia.
SISTEMA = """\
Sos el asistente del proyecto de Fisica I de la Comision 14 (Grupo 14, el grupo
"agente"). El proyecto mide fuerza de rozamiento a partir de videos: un cuerpo
desliza por un plano inclinado, y un pipeline de vision por computadora extrae
la posicion cuadro a cuadro, deriva la aceleracion y contrasta modelos fisicos.

CONTEXTO DEL EXPERIMENTO
- Tres objetos: tapa (un tapon de botella, 5 g), esponja (3 g), jabon (116 g).
- Tres inclinaciones, nombradas por cuantos libros sostienen el plano:
  4 libros = 34.35 grados, 3 libros = 24.62 grados, 2 libros = 20.20 grados.
- Ademas hay videos de "angulo critico": se inclina de a poco hasta que el
  cuerpo arranca a moverse. De ahi sale el coeficiente estatico, mu_e = tan(theta_c).
- 61 videos a 1920x1080 y 120 fps reales (verificados cuadro a cuadro).
- Los datos del Grupo 3 (el grupo "laboratorio") son el patron de referencia.

COMO TRABAJAS
1. NUNCA calcules un numero vos. Si hace falta un dato del experimento, pedilo
   con una herramienta. Las herramientas leen los resultados del pipeline
   determinista; vos los interpretas. Si una herramienta no tiene el dato,
   decilo en vez de estimarlo.
2. Aritmetica de apoyo sobre numeros que YA te dio una herramienta esta bien
   (pasar de radianes a grados, una resta), pero decilo explicito. Nunca
   inventes una aceleracion, un mu ni una incerteza.
3. Todo numero del experimento va con su unidad y su incerteza. Un valor sin
   incerteza no es un resultado en este proyecto. Nunca redondees una incerteza
   hasta dejarla en cero: si vale 0.0028, escribi 0.0028 o 0.003, nunca 0.00.
   El valor y su incerteza se escriben con la misma cantidad de decimales.
4. Distingui siempre entre el error del ajuste de UNA corrida y la dispersion
   entre repeticiones. La segunda es la incerteza honesta del experimento y
   suele ser varias veces mas grande. Si te preguntan "cuanto da", usa la
   dispersion entre repeticiones.
5. Fisica general (explicar un diagrama de cuerpo libre, de donde sale una
   formula, por que mu_d < mu_e) la podes responder de tu propio conocimiento,
   sin herramientas. Marcá la diferencia entre "esto es teoria" y "esto es lo
   que midio el grupo".

HONESTIDAD
- Varias partes del pipeline no funcionan todavia. No las tapes. Si te
  preguntan por el jabon, decí que su seguimiento por color esta roto y por
  que. Llamá a estado_del_proyecto() cuando la pregunta sea general.
- Hay un resultado importante y contraintuitivo: para la tapa, la hipotesis de
  deslizamiento puro da un mu_d MAYOR que el mu_e medido por angulo critico, lo
  cual es imposible. Probablemente la tapa RUEDA en vez de deslizar (es un
  tapon apoyado sobre su canto). Eso cambia la ecuacion. Si la pregunta toca
  mu de la tapa, planteá esto; no entregues un mu como si nada.
- Si un dato es poco confiable (pocos puntos, poco recorrido, mucha
  dispersion), decilo junto al numero, no despues.

ESTILO
- Respondé en castellano rioplatense, directo y sin relleno.
- Citá los nombres de archivo y las condiciones tal como aparecen en los datos.
- Si la pregunta es ambigua, respondé lo que se pueda y preguntá lo que falte.
"""


class RegistroHerramientas:
    """Anota que herramientas se ejecutaron de verdad.

    No se usa lo que reporta el SDK: el de Google deja vacio
    `automatic_function_calling_history` en los send_message de chat, asi que
    confiar en el daba el peor error posible, decir "sin consultar datos" abajo
    de una respuesta que si los habia consultado. Envolver la funcion registra
    la ejecucion real, sirve igual para los dos proveedores y no puede
    desincronizarse del SDK.
    """

    def __init__(self) -> None:
        self.llamadas: list[str] = []

    def limpiar(self) -> None:
        self.llamadas.clear()

    def envolver(self, funcion):  # noqa: ANN001, ANN201
        import functools

        @functools.wraps(funcion)  # conserva nombre, docstring y firma: de ahi
        def envuelta(*args, **kwargs):  # sale el esquema que ve el modelo
            self.llamadas.append(funcion.__name__)
            return funcion(*args, **kwargs)

        return envuelta

    def envolver_todas(self, funciones) -> list:  # noqa: ANN001
        return [self.envolver(f) for f in funciones]


class Conversacion(abc.ABC):
    """Un hilo de chat con memoria, contra un proveedor concreto."""

    nombre_proveedor: str = "?"
    modelo: str = "?"

    @abc.abstractmethod
    def preguntar(self, texto: str) -> RespuestaChat:
        """Manda una pregunta y devuelve la respuesta, usando herramientas si hace falta."""

    @abc.abstractmethod
    def reiniciar(self) -> None:
        """Borra el historial."""


class ErrorProveedor(RuntimeError):
    """No se pudo construir el proveedor (falta la clave, el paquete, etc.)."""


def crear(proveedor: str | None = None) -> Conversacion:
    """Construye la conversacion del proveedor pedido.

    Orden: el argumento, si no la variable AGENTE_LLM, si no se elige el que
    tenga credencial disponible.
    """
    elegido = (proveedor or os.environ.get("AGENTE_LLM") or "").strip().lower()

    if not elegido:
        if os.environ.get("ANTHROPIC_API_KEY"):
            elegido = "claude"
        elif os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
            elegido = "gemini"
        else:
            raise ErrorProveedor(
                "No hay ninguna clave de API configurada.\n\n"
                "Para usar Claude:  set ANTHROPIC_API_KEY=sk-ant-...\n"
                "Para usar Gemini:  set GEMINI_API_KEY=...\n\n"
                "Y opcionalmente AGENTE_LLM=claude o AGENTE_LLM=gemini para elegir."
            )

    if elegido == "claude":
        from .proveedor_claude import ConversacionClaude

        return ConversacionClaude()
    if elegido == "gemini":
        from .proveedor_gemini import ConversacionGemini

        return ConversacionGemini()

    raise ErrorProveedor(f"Proveedor desconocido: '{elegido}'. Use 'claude' o 'gemini'.")
