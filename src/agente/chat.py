"""Chat del agente por consola.

    python src/agente/chat.py
    python src/agente/chat.py --proveedor gemini
    python src/agente/chat.py --pregunta "la tapa rueda o desliza?"

Misma capa que la pestania "Chat IA" del visor: las mismas herramientas y el
mismo prompt. Sirve para probar sin abrir la ventana y para comparar
proveedores con el mismo set de preguntas.
"""

from __future__ import annotations

import argparse
import sys

from llm import ErrorProveedor, crear


def _mostrar(r) -> None:  # noqa: ANN001
    if r.error:
        print(f"\n[error] {r.error}\n")
        return
    print(f"\n{r.texto}\n")
    if r.herramientas_usadas:
        vistas: list[str] = []
        for h in r.herramientas_usadas:
            if h not in vistas:
                vistas.append(h)
        detalle = "datos consultados: " + ", ".join(vistas)
    else:
        detalle = "sin consultar datos (conocimiento general)"
    print(f"  [{detalle} | {r.tokens_entrada}+{r.tokens_salida} tokens]\n")


def main() -> None:
    p = argparse.ArgumentParser(description="Chat con IA sobre el proyecto")
    p.add_argument("--proveedor", choices=["claude", "gemini"], help="por defecto, el que tenga clave")
    p.add_argument("--pregunta", help="una sola pregunta y sale (para probar o scriptear)")
    args = p.parse_args()

    try:
        conv = crear(args.proveedor)
    except ErrorProveedor as e:
        print(f"\n{e}\n")
        raise SystemExit(1)

    print(f"Chat del agente - {conv.nombre_proveedor} ({conv.modelo})")

    if args.pregunta:
        _mostrar(conv.preguntar(args.pregunta))
        return

    print("Escribi tu pregunta. 'salir' para terminar, 'reiniciar' para borrar el historial.\n")
    while True:
        try:
            pregunta = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not pregunta:
            continue
        if pregunta.lower() in {"salir", "exit", "quit"}:
            break
        if pregunta.lower() in {"reiniciar", "reset"}:
            conv.reiniciar()
            print("  [historial borrado]\n")
            continue
        _mostrar(conv.preguntar(pregunta))


if __name__ == "__main__":
    sys.exit(main())
