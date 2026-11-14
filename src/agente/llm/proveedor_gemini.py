"""Proveedor de chat con la API de Gemini (SDK oficial `google-genai`).

Alternativa a proveedor_claude.py. Expone exactamente las mismas herramientas
de herramientas.py y el mismo prompt de sistema, asi que las respuestas se
pueden comparar entre proveedores con el mismo set de preguntas.

El SDK de Google hace "automatic function calling": se le pasan las funciones
de Python directas y el SDK deduce el esquema, las ejecuta y realimenta el
resultado. Es el equivalente al tool runner de Anthropic.

El modelo se toma de GEMINI_MODEL porque los nombres de modelo de Google
cambian seguido; si el que esta configurado no existe, listar_modelos() dice
cuales hay disponibles con esa clave.
"""

from __future__ import annotations

import os

from google import genai
from google.genai import errors as gerrors
from google.genai import types

from . import herramientas
from .base import Conversacion, ErrorProveedor, RegistroHerramientas, RespuestaChat, SISTEMA

MODELO_POR_DEFECTO = "gemini-2.5-pro"
MAX_LLAMADAS_HERRAMIENTAS = 12


def _clave() -> str:
    clave = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not clave:
        raise ErrorProveedor(
            "Falta la clave de Gemini. Conseguila en https://aistudio.google.com/apikey "
            "y exportala como GEMINI_API_KEY."
        )
    return clave


def listar_modelos() -> list[str]:
    """Modelos disponibles para la clave configurada. Util si el modelo no existe."""
    cliente = genai.Client(api_key=_clave())
    nombres = []
    for m in cliente.models.list():
        acciones = getattr(m, "supported_actions", None) or []
        if not acciones or "generateContent" in acciones:
            nombres.append(m.name or "")
    return [n for n in nombres if n]


class ConversacionGemini(Conversacion):
    nombre_proveedor = "Gemini"

    def __init__(self) -> None:
        self.modelo = os.environ.get("GEMINI_MODEL", MODELO_POR_DEFECTO)
        # Respaldo para cuando el modelo principal esta saturado (503). Se
        # reintenta una sola vez y se avisa en la respuesta: si el chat contesta
        # con otro modelo del que dice la barra de estado, hay que saberlo.
        self.modelo_respaldo = os.environ.get("GEMINI_FALLBACK_MODEL") or None
        self._usando_respaldo = False
        try:
            self.cliente = genai.Client(api_key=_clave())
        except ErrorProveedor:
            raise
        except Exception as e:  # noqa: BLE001
            raise ErrorProveedor(f"No se pudo crear el cliente de Gemini: {e}") from e
        self.registro = RegistroHerramientas()
        self._config = types.GenerateContentConfig(
            system_instruction=SISTEMA,
            # Las mismas funciones que usa Claude, envueltas para registrar que
            # se ejecuto. El SDK de Google deduce el esquema de la firma y el
            # docstring, que functools.wraps conserva.
            tools=self.registro.envolver_todas(herramientas.HERRAMIENTAS),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                maximum_remote_calls=MAX_LLAMADAS_HERRAMIENTAS,
            ),
        )
        self._abrir_chat()

    def _abrir_chat(self, modelo: str | None = None) -> None:
        self.chat = self.cliente.chats.create(
            model=modelo or self.modelo, config=self._config
        )

    def reiniciar(self) -> None:
        self._usando_respaldo = False
        self._abrir_chat()

    def _reabrir_en_respaldo(self) -> bool:
        """Rearma el chat sobre el modelo de respaldo, conservando el historial."""
        if not self.modelo_respaldo or self._usando_respaldo:
            return False
        historial = list(self.chat.get_history()) if hasattr(self.chat, "get_history") else []
        self.chat = self.cliente.chats.create(
            model=self.modelo_respaldo, config=self._config, history=historial
        )
        self._usando_respaldo = True
        return True

    def preguntar(self, texto: str) -> RespuestaChat:
        aviso_respaldo = ""
        self.registro.limpiar()
        try:
            respuesta = self.chat.send_message(texto)
        except gerrors.ServerError as e:
            # 503 = modelo saturado. Es lo que motiva GEMINI_FALLBACK_MODEL.
            if getattr(e, "code", None) == 503 and self._reabrir_en_respaldo():
                try:
                    respuesta = self.chat.send_message(texto)
                    aviso_respaldo = (
                        f"\n\n[El modelo {self.modelo} estaba saturado (503); "
                        f"esta respuesta la dio {self.modelo_respaldo}.]"
                    )
                except gerrors.APIError as e2:
                    return RespuestaChat(
                        texto="",
                        error=(
                            f"Tanto {self.modelo} como el respaldo "
                            f"{self.modelo_respaldo} fallaron: {e2}"
                        ),
                    )
            else:
                return RespuestaChat(texto="", error=f"Error del servidor de Gemini: {e}")
        except gerrors.ClientError as e:
            if "not found" in str(e).lower() or getattr(e, "code", None) == 404:
                try:
                    disponibles = ", ".join(listar_modelos()[:8])
                except Exception:  # noqa: BLE001
                    disponibles = "no se pudieron listar"
                return RespuestaChat(
                    texto="",
                    error=(
                        f"El modelo '{self.modelo}' no existe para esta clave. "
                        f"Configura GEMINI_MODEL con alguno de: {disponibles}"
                    ),
                )
            if getattr(e, "code", None) == 429:
                return RespuestaChat(
                    texto="", error="Limite de velocidad de Gemini alcanzado. Esperar y reintentar."
                )
            return RespuestaChat(texto="", error=f"Error de Gemini: {e}")
        except gerrors.APIError as e:
            return RespuestaChat(texto="", error=f"Error de la API de Gemini: {e}")

        uso = respuesta.usage_metadata
        return RespuestaChat(
            texto=(respuesta.text or "").strip() + aviso_respaldo,
            herramientas_usadas=list(self.registro.llamadas),
            tokens_entrada=(uso.prompt_token_count or 0) if uso else 0,
            tokens_salida=(uso.candidates_token_count or 0) if uso else 0,
        )
