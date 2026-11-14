"""Proveedor de chat con la API de Claude (SDK oficial `anthropic`).

Usa el tool runner del SDK: se le pasan las funciones de herramientas.py
decoradas con @beta_tool y el SDK se encarga del bucle pedido -> ejecutar
herramienta -> devolver resultado -> seguir, hasta que el modelo termina.

El esquema de cada herramienta lo deduce el decorador de la firma y el
docstring de la funcion, asi que las herramientas se definen una sola vez y en
un modulo que no depende de ningun proveedor.
"""

from __future__ import annotations

import anthropic
from anthropic import beta_tool

from . import herramientas
from .base import Conversacion, ErrorProveedor, RegistroHerramientas, RespuestaChat, SISTEMA

MODELO = "claude-opus-5-5"
MAX_TOKENS = 16000
# Tope de vueltas del bucle de herramientas. Una pregunta razonable usa 1 a 4;
# 12 deja margen para una comparacion entre objetos sin permitir un bucle infinito.
MAX_VUELTAS = 12


def _envolver(registro: RegistroHerramientas) -> list:
    """Aplica @beta_tool a cada funcion de herramientas.py.

    Se hace aca y no en herramientas.py para que ese modulo quede libre de
    cualquier SDK: el adaptador de Gemini envuelve las mismas funciones a su
    manera.
    """
    return [beta_tool(f) for f in registro.envolver_todas(herramientas.HERRAMIENTAS)]


class ConversacionClaude(Conversacion):
    nombre_proveedor = "Claude"
    modelo = MODELO

    def __init__(self) -> None:
        try:
            # Sin api_key explicita: el SDK resuelve ANTHROPIC_API_KEY, el token
            # de entorno o el perfil de `ant auth login`, en ese orden.
            self.cliente = anthropic.Anthropic()
        except Exception as e:  # noqa: BLE001
            raise ErrorProveedor(f"No se pudo crear el cliente de Anthropic: {e}") from e
        self.registro = RegistroHerramientas()
        self.tools = _envolver(self.registro)
        self.mensajes: list = []

    def reiniciar(self) -> None:
        self.mensajes = []

    def preguntar(self, texto: str) -> RespuestaChat:
        self.mensajes.append({"role": "user", "content": texto})
        self.registro.limpiar()
        entrada = salida = 0

        try:
            runner = self.cliente.beta.messages.tool_runner(
                model=MODELO,
                max_tokens=MAX_TOKENS,
                max_iterations=MAX_VUELTAS,
                system=[
                    # El prompt y la lista de herramientas son el prefijo estable
                    # de todas las consultas: cachearlo abarata cada pregunta.
                    {"type": "text", "text": SISTEMA, "cache_control": {"type": "ephemeral"}}
                ],
                tools=self.tools,
                messages=self.mensajes,
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
            )

            final = None
            for mensaje in runner:
                final = mensaje
                entrada += mensaje.usage.input_tokens or 0
                salida += mensaje.usage.output_tokens or 0

            if final is None:
                return RespuestaChat(texto="", error="El modelo no devolvio ninguna respuesta.")

            if final.stop_reason == "refusal":
                motivo = getattr(final.stop_details, "explanation", None) or "sin detalle"
                return RespuestaChat(
                    texto="",
                    herramientas_usadas=list(self.registro.llamadas),
                    error=f"El modelo rechazo la consulta ({motivo}).",
                )

            partes = [b.text for b in final.content if b.type == "text" and b.text]
            respuesta = "\n".join(partes).strip()

            if final.stop_reason == "max_tokens":
                respuesta += "\n\n[La respuesta se corto por limite de tokens.]"

            # El historial se guarda con el contenido completo, no solo el texto:
            # el runner ya dejo en self.mensajes los turnos de herramientas.
            self.mensajes.append({"role": "assistant", "content": final.content})

            return RespuestaChat(
                texto=respuesta,
                herramientas_usadas=list(self.registro.llamadas),
                tokens_entrada=entrada,
                tokens_salida=salida,
            )

        except anthropic.AuthenticationError:
            # El cliente se construye sin error aunque no haya clave, porque un
            # perfil de `ant auth login` tambien sirve. Por eso el problema de
            # credenciales recien aparece aca, en la primera consulta.
            return RespuestaChat(
                texto="",
                error=(
                    "Anthropic rechazo la credencial. Opciones:\n"
                    "  - Poner una clave:  set ANTHROPIC_API_KEY=sk-ant-...\n"
                    "    (se saca en https://console.anthropic.com/settings/keys)\n"
                    "  - O usar Gemini:    set GEMINI_API_KEY=...  y  set AGENTE_LLM=gemini"
                ),
            )
        except anthropic.RateLimitError as e:
            espera = e.response.headers.get("retry-after", "unos segundos")
            return RespuestaChat(
                texto="", error=f"Limite de velocidad alcanzado. Reintentar en {espera}."
            )
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                return RespuestaChat(
                    texto="", error=f"Error del servidor ({e.status_code}). Reintentar mas tarde."
                )
            return RespuestaChat(texto="", error=f"Error de la API: {e.message}")
        except anthropic.APIConnectionError:
            return RespuestaChat(texto="", error="No hay conexion con la API. Revisa la red.")
