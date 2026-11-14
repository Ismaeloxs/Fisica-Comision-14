"""Pestania de chat con IA para el visor.

Se arma como un widget suelto (PanelChat) para que visor.py solo tenga que
agregarlo al Notebook, y para poder probarlo solo con `python chat_ui.py`.

Dos cosas que importan en la implementacion:

  - La llamada al modelo tarda segundos y puede llamar varias herramientas en
    el medio, asi que corre en un hilo aparte. tkinter no es thread-safe: el
    hilo deja la respuesta en una cola y la ventana la recoge con after().
  - Debajo de cada respuesta se muestra que herramientas se llamaron. No es
    decoracion: es lo que hace auditable la respuesta. Si el modelo dice un
    numero sin haber llamado ninguna herramienta, lo invento.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk

FONDO = "#f4f4f6"
TARJETA = "#ffffff"
BORDE = "#d6d6dc"
TEXTO = "#1d1d22"
TENUE = "#6a6a76"
ACENTO = "#2563cb"
ERROR = "#c0392b"

SUGERENCIAS = [
    "Como viene el proyecto? Que anda y que no?",
    "La tapa rueda o desliza? Justifica con los numeros.",
    "Que coeficiente de rozamiento da cada objeto?",
    "Por que falla el seguimiento del jabon?",
    "Explicame el diagrama de cuerpo libre en el plano inclinado.",
    "Cuales corridas se descartaron y por que?",
]


class PanelChat(ttk.Frame):
    """Chat con el modelo, con historial y aviso de herramientas usadas."""

    def __init__(self, padre: tk.Misc) -> None:
        super().__init__(padre)
        self.cola: queue.Queue = queue.Queue()
        self.conversacion = None
        self.pensando = False
        self._construir()
        self._revisar_cola()
        self._conectar()

    # ------------------------------------------------------------------
    # armado
    # ------------------------------------------------------------------
    def _construir(self) -> None:
        barra = ttk.Frame(self, padding=(12, 10, 12, 6))
        barra.pack(fill="x")

        self.etiqueta_estado = ttk.Label(barra, text="Conectando...", foreground=TENUE)
        self.etiqueta_estado.pack(side="left")

        ttk.Button(barra, text="Reiniciar", command=self._reiniciar).pack(side="right")

        cuerpo = ttk.Frame(self, padding=(12, 0, 12, 0))
        cuerpo.pack(fill="both", expand=True)

        self.texto = tk.Text(
            cuerpo,
            wrap="word",
            font=("Segoe UI", 10),
            background=TARJETA,
            foreground=TEXTO,
            borderwidth=1,
            relief="solid",
            padx=14,
            pady=12,
            spacing1=2,
            spacing3=6,
            state="disabled",
            cursor="arrow",
        )
        barra_v = ttk.Scrollbar(cuerpo, orient="vertical", command=self.texto.yview)
        self.texto.configure(yscrollcommand=barra_v.set)
        barra_v.pack(side="right", fill="y")
        self.texto.pack(side="left", fill="both", expand=True)

        self.texto.tag_configure("usuario", foreground=ACENTO, font=("Segoe UI", 10, "bold"))
        self.texto.tag_configure("agente", foreground=TEXTO)
        self.texto.tag_configure(
            "meta", foreground=TENUE, font=("Consolas", 8), spacing1=0, spacing3=10
        )
        self.texto.tag_configure("error", foreground=ERROR, font=("Segoe UI", 10))
        self.texto.tag_configure("aviso", foreground=TENUE, font=("Segoe UI", 9, "italic"))

        chips = ttk.Frame(self, padding=(12, 8, 12, 0))
        chips.pack(fill="x")
        ttk.Label(chips, text="Para arrancar:", foreground=TENUE).pack(anchor="w")
        grilla = ttk.Frame(chips)
        grilla.pack(fill="x", pady=(4, 0))
        for i, s in enumerate(SUGERENCIAS):
            b = ttk.Button(
                grilla,
                text=s if len(s) <= 46 else s[:43] + "...",
                command=lambda t=s: self._usar_sugerencia(t),
            )
            b.grid(row=i // 2, column=i % 2, sticky="ew", padx=(0, 6), pady=2)
        grilla.columnconfigure(0, weight=1)
        grilla.columnconfigure(1, weight=1)

        entrada = ttk.Frame(self, padding=(12, 8, 12, 12))
        entrada.pack(fill="x")
        self.campo = tk.Text(
            entrada,
            height=3,
            wrap="word",
            font=("Segoe UI", 10),
            background=TARJETA,
            foreground=TEXTO,
            borderwidth=1,
            relief="solid",
            padx=8,
            pady=6,
        )
        self.campo.pack(side="left", fill="both", expand=True)
        # Enter manda, Shift+Enter hace salto de linea.
        self.campo.bind("<Return>", self._al_apretar_enter)
        self.campo.bind("<Shift-Return>", lambda e: None)

        self.boton = ttk.Button(entrada, text="Preguntar", command=self._enviar)
        self.boton.pack(side="left", fill="y", padx=(8, 0))

    # ------------------------------------------------------------------
    # conexion
    # ------------------------------------------------------------------
    def _conectar(self) -> None:
        # El import va adentro del try a proposito. El chat es una funcion
        # opcional del visor y no tiene que poder voltearlo: si falta una
        # dependencia de la capa de IA, esta pestania se deshabilita sola y
        # medir, graficar y el lote siguen funcionando. Tenerlo afuera hacia
        # que un ModuleNotFoundError matara la aplicacion entera al abrirse.
        try:
            from llm import ErrorProveedor, crear

            # crear() importa el modulo del proveedor elegido, asi que un
            # paquete faltante puede aparecer aca y no en el import de arriba.
            self.conversacion = crear()
        except ImportError as e:
            self.etiqueta_estado.configure(text="Falta una dependencia", foreground=ERROR)
            self._escribir_aviso(
                f"No se pudo cargar la capa de IA: falta el paquete '{e.name}'.\n\n"
                "Seguramente estas corriendo el Python del sistema en vez del "
                "entorno del proyecto. Desde la carpeta del repo:\n\n"
                "    .venv\\Scripts\\activate\n"
                "    pip install -r requirements.txt\n\n"
                "El resto del visor funciona igual: esto solo afecta al chat."
            )
            self._deshabilitar()
            return
        except ErrorProveedor as e:
            self.etiqueta_estado.configure(text="Sin proveedor configurado", foreground=ERROR)
            self._escribir_aviso(
                f"{e}\n\n"
                "El resto del visor funciona igual: el chat es lo unico que "
                "necesita una clave de API."
            )
            self._deshabilitar()
            return
        except Exception as e:  # noqa: BLE001
            self.etiqueta_estado.configure(text="Error al conectar", foreground=ERROR)
            self._escribir_aviso(f"No se pudo iniciar el chat: {type(e).__name__}: {e}")
            self._deshabilitar()
            return

        self.etiqueta_estado.configure(
            text=f"{self.conversacion.nombre_proveedor} - {self.conversacion.modelo}",
            foreground=TENUE,
        )
        self._escribir_aviso(
            "Preguntale lo que quieras sobre el proyecto: los videos, los "
            "calculos, la fisica, o que hacer con lo que falta.\n"
            "Los numeros los saca de resultados/ llamando funciones del "
            "pipeline, no los inventa. Debajo de cada respuesta vas a ver "
            "cuales llamo."
        )

    def _deshabilitar(self) -> None:
        """Apaga la entrada del chat dejando el resto del visor intacto."""
        self.boton.state(["disabled"])
        self.campo.configure(state="disabled")
        for hijo in self.winfo_children():
            for nieto in hijo.winfo_children():
                if isinstance(nieto, ttk.Button) and nieto is not self.boton:
                    nieto.state(["disabled"])

    # ------------------------------------------------------------------
    # escribir en el panel
    # ------------------------------------------------------------------
    def _append(self, texto: str, tag: str) -> None:
        self.texto.configure(state="normal")
        self.texto.insert("end", texto, tag)
        self.texto.configure(state="disabled")
        self.texto.see("end")

    def _escribir_aviso(self, texto: str) -> None:
        self._append(f"{texto}\n\n", "aviso")

    # ------------------------------------------------------------------
    # enviar y recibir
    # ------------------------------------------------------------------
    def _al_apretar_enter(self, evento):  # noqa: ANN001
        self._enviar()
        return "break"  # evita que Enter inserte el salto de linea

    def _usar_sugerencia(self, texto: str) -> None:
        if self.pensando:
            return
        self.campo.delete("1.0", "end")
        self.campo.insert("1.0", texto)
        self._enviar()

    def _enviar(self) -> None:
        if self.pensando or self.conversacion is None:
            return
        pregunta = self.campo.get("1.0", "end").strip()
        if not pregunta:
            return
        self.campo.delete("1.0", "end")

        self._append(f"Vos\n", "usuario")
        self._append(f"{pregunta}\n\n", "agente")

        self.pensando = True
        self.boton.state(["disabled"])
        self.etiqueta_estado.configure(text="Pensando y consultando los datos...")

        hilo = threading.Thread(target=self._trabajar, args=(pregunta,), daemon=True)
        hilo.start()

    def _trabajar(self, pregunta: str) -> None:
        """Corre en el hilo de fondo. No toca ningun widget."""
        try:
            respuesta = self.conversacion.preguntar(pregunta)
        except Exception as e:  # noqa: BLE001
            self.cola.put(("error", f"{type(e).__name__}: {e}"))
            return
        self.cola.put(("respuesta", respuesta))

    def _revisar_cola(self) -> None:
        try:
            while True:
                clase, carga = self.cola.get_nowait()
                if clase == "error":
                    self._append(f"Fallo la consulta: {carga}\n\n", "error")
                else:
                    self._mostrar(carga)
                self.pensando = False
                self.boton.state(["!disabled"])
                if self.conversacion is not None:
                    self.etiqueta_estado.configure(
                        text=f"{self.conversacion.nombre_proveedor} - {self.conversacion.modelo}",
                        foreground=TENUE,
                    )
        except queue.Empty:
            pass
        self.after(120, self._revisar_cola)

    def _mostrar(self, r) -> None:  # noqa: ANN001
        if r.error:
            self._append(f"{r.error}\n\n", "error")
            return

        self._append("Agente\n", "usuario")
        self._append(f"{r.texto}\n", "agente")

        if r.herramientas_usadas:
            vistas: list[str] = []
            for h in r.herramientas_usadas:
                if h not in vistas:
                    vistas.append(h)
            detalle = "datos consultados: " + ", ".join(vistas)
        else:
            detalle = "sin consultar datos (respuesta de conocimiento general)"
        costo = f" | {r.tokens_entrada}+{r.tokens_salida} tokens"
        self._append(f"{detalle}{costo}\n\n", "meta")

    def _reiniciar(self) -> None:
        if self.pensando or self.conversacion is None:
            return
        self.conversacion.reiniciar()
        self.texto.configure(state="normal")
        self.texto.delete("1.0", "end")
        self.texto.configure(state="disabled")
        self._escribir_aviso("Historial borrado.")


def main() -> None:
    raiz = tk.Tk()
    raiz.title("Chat del agente - Grupo 14")
    raiz.geometry("900x700")
    raiz.configure(background=FONDO)
    estilo = ttk.Style(raiz)
    try:
        estilo.theme_use("clam")
    except tk.TclError:
        pass
    estilo.configure("TFrame", background=FONDO)
    estilo.configure("TLabel", background=FONDO, foreground=TEXTO)
    PanelChat(raiz).pack(fill="both", expand=True)
    raiz.mainloop()


if __name__ == "__main__":
    main()
