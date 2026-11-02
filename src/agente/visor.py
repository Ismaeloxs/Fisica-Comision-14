"""Ventana para usar el agente sin la linea de comandos.

    python src/agente/visor.py

No calcula nada por su cuenta: llama a medir.analizar_corrida(), que es el
mismo camino que usa la CLI. Lo unico que agrega es como se muestra.

Tres cosas que la consola no puede dar:

  - El ajuste y los residuos graficados. Un chi2 de 41 es un numero; ver los
    residuos ordenados en una curva en vez de dispersos muestra enseguida que
    el problema no es ruido sino que al modelo le falta algo.
  - La trayectoria dibujada sobre el cuadro. Es la unica forma rapida de
    confirmar que el tracker siguio el objeto y no un reflejo o un libro.
  - El lote por condicion con la dispersion entre repeticiones, que es el
    numero honesto del experimento y no el error del ajuste individual.

El trabajo pesado corre en un hilo aparte: tkinter no es thread-safe, asi que
el hilo solo deja resultados en una cola y la ventana los recoge con after().
"""

from __future__ import annotations

import math
import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

import cv2
import matplotlib
import numpy as np

matplotlib.use("TkAgg")

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from inventario import CARPETA_VIDEOS, parsear_nombre  # noqa: E402
from medir import ErrorMedicion, analizar_corrida, informe_texto  # noqa: E402

FONDO = "#f4f4f6"
TARJETA = "#ffffff"
BORDE = "#d6d6dc"
TEXTO = "#1d1d22"
TENUE = "#6a6a76"
ACENTO = "#2563cb"

# Color del cartel del veredicto segun que dictamino la fisica.
COLOR_VEREDICTO = {
    "deslizamiento compatible": ("#e8f5ec", "#1d6b38"),
    "deslizamiento descartado": ("#fdeaea", "#a62121"),
    "ambiguo": ("#fdf4e3", "#8a5a10"),
    "rodadura": ("#e9f0fb", "#1c4f9c"),
}

# Una medicion completa lee todos los cuadros del video. Sirve para avisar
# cuanto va a tardar un lote antes de largarlo.
SEGUNDOS_POR_VIDEO = 6
# Debajo de esto la corrida aporta poco: la ventana util quedo demasiado corta
# para que el ajuste cuadratico signifique algo.
MIN_PUNTOS_CONFIABLE = 25
MIN_RECORRIDO_CM = 10.0

OBJETOS = ["todos", "tapa", "esponja", "jabon"]
CONDICIONES = ["todas", "4libros", "3libros", "2libros", "angulo critico"]


def _color_veredicto(veredicto: str) -> tuple[str, str]:
    for clave, colores in COLOR_VEREDICTO.items():
        if clave in veredicto:
            return colores
    return (TARJETA, TEXTO)


@dataclass
class Medida:
    """Lo que el hilo de trabajo le devuelve a la ventana."""

    corrida: Any
    cuadro_rgb: np.ndarray | None
    error: str | None = None
    nombre: str = ""


def _leer_cuadro(corrida) -> np.ndarray | None:
    """Un cuadro del medio de la ventana util, para dibujarle la trayectoria."""
    indice = int(corrida.frames[(corrida.i0 + corrida.i1) // 2])
    cap = cv2.VideoCapture(str(corrida.ruta))
    cap.set(cv2.CAP_PROP_POS_FRAMES, indice)
    ok, cuadro = cap.read()
    cap.release()
    return cv2.cvtColor(cuadro, cv2.COLOR_BGR2RGB) if ok else None


def angulo_trayectoria(c) -> float:
    """Direccion que siguio el objeto, medida de la trayectoria misma.

    Sirve de control del eje que salio del papel rosa: si los dos angulos no
    coinciden, la proyeccion s(t) esta tomada sobre un eje equivocado.
    """
    x = np.array([d.x_px for d in c.tray.detecciones])[c.i0 : c.i1]
    y = np.array([d.y_px for d in c.tray.detecciones])[c.i0 : c.i1]
    puntos = np.column_stack([x - x.mean(), y - y.mean()])
    _, _, vt = np.linalg.svd(puntos, full_matrices=False)
    u = vt[0] if vt[0][0] >= 0 else -vt[0]
    return math.atan2(u[1], u[0])


def _medir_en_hilo(ruta: Path) -> Medida:
    try:
        corrida = analizar_corrida(ruta)
    except ErrorMedicion as e:
        return Medida(None, None, error=str(e), nombre=ruta.name)
    except Exception as e:  # el tracker puede romper de formas variadas
        return Medida(None, None, error=f"{type(e).__name__}: {e}", nombre=ruta.name)
    return Medida(corrida, _leer_cuadro(corrida), nombre=ruta.name)


class MarcoScrollable(ttk.Frame):
    """Marco con scroll vertical. El contenido se cuelga de .interior.

    Hace falta porque el resumen no entra en pantallas chicas: en un portatil
    de 768 px de alto las tarjetas se cortan y el cartel del veredicto, que es
    la conclusion, queda abajo del borde sin que nada lo avise.
    """

    def __init__(self, padre):
        super().__init__(padre)
        self._lienzo = tk.Canvas(self, background=FONDO, highlightthickness=0)
        barra = ttk.Scrollbar(self, orient="vertical", command=self._lienzo.yview)
        self.interior = ttk.Frame(self._lienzo, padding=12)
        self._ventana = self._lienzo.create_window((0, 0), window=self.interior, anchor="nw")
        self._lienzo.configure(yscrollcommand=barra.set)
        self._lienzo.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")

        self.interior.bind(
            "<Configure>",
            lambda _e: self._lienzo.configure(scrollregion=self._lienzo.bbox("all")),
        )
        self._lienzo.bind(
            "<Configure>", lambda e: self._lienzo.itemconfigure(self._ventana, width=e.width)
        )
        # La rueda se engancha solo mientras el puntero esta encima, si no se
        # roba el scroll de las otras pestanias.
        self._lienzo.bind("<Enter>", lambda _e: self._lienzo.bind_all("<MouseWheel>", self._rueda))
        self._lienzo.bind("<Leave>", lambda _e: self._lienzo.unbind_all("<MouseWheel>"))

    def _rueda(self, evento) -> None:
        self._lienzo.yview_scroll(-evento.delta // 120, "units")

    def limpiar(self) -> None:
        for hijo in self.interior.winfo_children():
            hijo.destroy()
        self._lienzo.yview_moveto(0.0)


class Tarjeta(ttk.Frame):
    """Un bloque de pares etiqueta-valor, con titulo."""

    def __init__(self, padre, titulo: str):
        super().__init__(padre, style="Tarjeta.TFrame", padding=(14, 10, 14, 12))
        ttk.Label(self, text=titulo.upper(), style="Titulo.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        self.columnconfigure(1, weight=1)
        self._fila = 1

    def agregar(self, etiqueta: str, valor: str, destacado: bool = False) -> None:
        ttk.Label(self, text=etiqueta, style="Tenue.TLabel").grid(
            row=self._fila, column=0, sticky="w", padx=(0, 16), pady=2
        )
        estilo = "Grande.TLabel" if destacado else "Valor.TLabel"
        ttk.Label(self, text=valor, style=estilo).grid(
            row=self._fila, column=1, sticky="e", pady=2
        )
        self._fila += 1

    def nota(self, texto: str, color: str = TENUE) -> None:
        etiqueta = ttk.Label(self, text=texto, style="Tenue.TLabel", wraplength=330)
        etiqueta.configure(foreground=color)
        etiqueta.grid(row=self._fila, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self._fila += 1


class Visor(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Agente de fuerza de rozamiento - Grupo 14")
        ancho = min(1360, self.winfo_screenwidth() - 80)
        alto = min(880, self.winfo_screenheight() - 120)
        self.geometry(f"{ancho}x{alto}")
        self.minsize(900, 560)
        self.configure(background=FONDO)

        self.carpeta = CARPETA_VIDEOS
        self.cola: queue.Queue = queue.Queue()
        self.corrida_actual = None
        self.resultados_lote: list[Medida] = []
        self.trabajando = False

        self._estilos()
        self._armar()
        self._refrescar_lista()
        self.after(100, self._revisar_cola)

    # ------------------------------------------------------------------ estilo

    def _estilos(self) -> None:
        estilo = ttk.Style(self)
        estilo.theme_use("clam")
        estilo.configure("TFrame", background=FONDO)
        estilo.configure("Tarjeta.TFrame", background=TARJETA, relief="solid", borderwidth=1)
        estilo.configure("TLabel", background=FONDO, foreground=TEXTO)
        estilo.configure(
            "Titulo.TLabel", background=TARJETA, foreground=TENUE, font=("Segoe UI", 8, "bold")
        )
        estilo.configure(
            "Valor.TLabel", background=TARJETA, foreground=TEXTO, font=("Consolas", 10)
        )
        estilo.configure(
            "Grande.TLabel", background=TARJETA, foreground=ACENTO, font=("Consolas", 15, "bold")
        )
        estilo.configure(
            "Tenue.TLabel", background=TARJETA, foreground=TENUE, font=("Segoe UI", 9)
        )
        estilo.configure("Barra.TLabel", background=FONDO, foreground=TENUE)
        estilo.configure("TButton", font=("Segoe UI", 9))
        estilo.configure("Accion.TButton", font=("Segoe UI", 9, "bold"))
        estilo.map("Accion.TButton", background=[("active", "#dce7f8")])
        estilo.configure("Treeview", font=("Consolas", 9), rowheight=23)
        estilo.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    # ------------------------------------------------------------------ layout

    def _armar(self) -> None:
        barra = ttk.Frame(self, padding=(12, 10))
        barra.pack(fill="x")
        self.var_carpeta = tk.StringVar(value=str(self.carpeta))
        ttk.Label(barra, text="Carpeta de videos:", style="Barra.TLabel").pack(side="left")
        ttk.Label(barra, textvariable=self.var_carpeta, style="Barra.TLabel").pack(
            side="left", padx=(6, 12)
        )
        ttk.Button(barra, text="Cambiar...", command=self._elegir_carpeta).pack(side="left")

        cuerpo = ttk.Frame(self, padding=(12, 0, 12, 8))
        cuerpo.pack(fill="both", expand=True)

        self._panel_izquierdo(cuerpo)
        self._panel_derecho(cuerpo)
        self._barra_estado()

    def _panel_izquierdo(self, padre) -> None:
        panel = ttk.Frame(padre, width=300)
        panel.pack(side="left", fill="y", padx=(0, 12))
        panel.pack_propagate(False)

        filtros = ttk.Frame(panel)
        filtros.pack(fill="x", pady=(0, 8))
        self.var_objeto = tk.StringVar(value="todos")
        self.var_condicion = tk.StringVar(value="todas")
        for texto, var, valores in (
            ("Objeto", self.var_objeto, OBJETOS),
            ("Condicion", self.var_condicion, CONDICIONES),
        ):
            fila = ttk.Frame(filtros)
            fila.pack(fill="x", pady=2)
            ttk.Label(fila, text=texto, width=10).pack(side="left")
            combo = ttk.Combobox(fila, textvariable=var, values=valores, state="readonly")
            combo.pack(side="left", fill="x", expand=True)
            combo.bind("<<ComboboxSelected>>", lambda _e: self._refrescar_lista())

        self.lista = tk.Listbox(
            panel,
            font=("Consolas", 9),
            background=TARJETA,
            foreground=TEXTO,
            selectbackground=ACENTO,
            selectforeground="white",
            highlightthickness=1,
            highlightbackground=BORDE,
            borderwidth=0,
            activestyle="none",
        )
        self.lista.pack(fill="both", expand=True)
        self.lista.bind("<Double-Button-1>", lambda _e: self._medir_seleccionado())

        botones = ttk.Frame(panel)
        botones.pack(fill="x", pady=(8, 0))
        self.boton_medir = ttk.Button(
            botones, text="Medir corrida", style="Accion.TButton", command=self._medir_seleccionado
        )
        self.boton_medir.pack(fill="x", pady=(0, 4))
        self.boton_lote = ttk.Button(
            botones, text="Medir todo el grupo filtrado", command=self._medir_lote
        )
        self.boton_lote.pack(fill="x")

    def _panel_derecho(self, padre) -> None:
        self.pestanias = ttk.Notebook(padre)
        self.pestanias.pack(side="left", fill="both", expand=True)

        self.tab_resumen = ttk.Frame(self.pestanias)
        self.tab_graficos = ttk.Frame(self.pestanias)
        self.tab_trayectoria = ttk.Frame(self.pestanias)
        self.tab_lote = ttk.Frame(self.pestanias, padding=12)
        self.tab_texto = ttk.Frame(self.pestanias)

        self.pestanias.add(self.tab_resumen, text="  Resumen  ")
        self.resumen = MarcoScrollable(self.tab_resumen)
        self.resumen.pack(fill="both", expand=True)
        self.pestanias.add(self.tab_graficos, text="  Graficos  ")
        self.pestanias.add(self.tab_trayectoria, text="  Trayectoria  ")
        self.pestanias.add(self.tab_lote, text="  Lote  ")
        self.pestanias.add(self.tab_texto, text="  Texto  ")

        self.fig_graficos = Figure(figsize=(9, 6.6), dpi=96, facecolor=FONDO)
        self.canvas_graficos = FigureCanvasTkAgg(self.fig_graficos, master=self.tab_graficos)
        self.canvas_graficos.get_tk_widget().pack(fill="both", expand=True)

        self.fig_tray = Figure(figsize=(9, 6.6), dpi=96, facecolor=FONDO)
        self.canvas_tray = FigureCanvasTkAgg(self.fig_tray, master=self.tab_trayectoria)
        self.canvas_tray.get_tk_widget().pack(fill="both", expand=True)

        self.texto = tk.Text(
            self.tab_texto,
            font=("Consolas", 9),
            background=TARJETA,
            foreground=TEXTO,
            borderwidth=0,
            wrap="none",
            padx=12,
            pady=10,
        )
        self.texto.pack(fill="both", expand=True)
        self.texto.configure(state="disabled")

        self._armar_lote()
        self._mensaje_inicial()

    def _armar_lote(self) -> None:
        columnas = ("video", "n", "recorrido", "a", "chi2", "mu", "veredicto")
        titulos = {
            "video": "Video",
            "n": "Puntos",
            "recorrido": "Recorrido",
            "a": "a [m/s2]",
            "chi2": "chi2 red",
            "mu": "mu si desliza",
            "veredicto": "Veredicto",
        }
        anchos = {"video": 210, "n": 60, "recorrido": 90, "a": 130, "chi2": 80, "mu": 120}

        self.tabla = ttk.Treeview(
            self.tab_lote, columns=columnas, show="headings", height=9
        )
        for col in columnas:
            self.tabla.heading(col, text=titulos[col])
            self.tabla.column(
                col,
                width=anchos.get(col, 190),
                anchor="w" if col in ("video", "veredicto") else "e",
            )
        self.tabla.pack(fill="x")
        self.tabla.tag_configure("error", foreground="#a62121")
        self.tabla.tag_configure("flojo", background="#fdf4e3")

        self.resumen_lote = ttk.Label(
            self.tab_lote, text="", style="Barra.TLabel", font=("Segoe UI", 10)
        )
        self.resumen_lote.pack(fill="x", pady=(10, 6))

        self.fig_lote = Figure(figsize=(9, 3.4), dpi=96, facecolor=FONDO)
        self.canvas_lote = FigureCanvasTkAgg(self.fig_lote, master=self.tab_lote)
        self.canvas_lote.get_tk_widget().pack(fill="both", expand=True)

    def _mensaje_lote_vacio(self) -> None:
        """La tabla vacia no se explica sola: sin esto parece que algo fallo."""
        n = len(getattr(self, "videos", []))
        if not n:
            self.resumen_lote.configure(text="No hay videos en la lista para medir.")
            return
        segundos = SEGUNDOS_POR_VIDEO * n
        cuanto = f"{segundos} s" if segundos < 90 else f"~{round(segundos / 60)} min"
        self.resumen_lote.configure(
            text=(
                f"Todavia no corriste ningun lote. El boton "
                f"'Medir todo el grupo filtrado' mide los {n} videos de la lista "
                f"y tarda {cuanto}; las filas van apareciendo a medida que terminan."
            )
        )

    def _barra_estado(self) -> None:
        barra = ttk.Frame(self, padding=(12, 6))
        barra.pack(fill="x", side="bottom")
        self.var_estado = tk.StringVar(value="Listo")
        ttk.Label(barra, textvariable=self.var_estado, style="Barra.TLabel").pack(side="left")
        self.progreso = ttk.Progressbar(barra, mode="indeterminate", length=180)
        self.progreso.pack(side="right")

    def _mensaje_inicial(self) -> None:
        self.resumen.limpiar()
        marco = ttk.Frame(self.resumen.interior)
        marco.pack(expand=True)
        ttk.Label(
            marco,
            text="Elegi un video de la lista y apreta 'Medir corrida'.",
            font=("Segoe UI", 12),
        ).pack()
        ttk.Label(
            marco,
            text="Doble click sobre el nombre hace lo mismo.",
            foreground=TENUE,
        ).pack(pady=(6, 0))

    # ------------------------------------------------------------------ lista

    def _videos_filtrados(self) -> list[Path]:
        if not self.carpeta.is_dir():
            return []
        objeto, condicion = self.var_objeto.get(), self.var_condicion.get()
        elegidos = []
        for ruta in sorted(self.carpeta.glob("*.mp4")):
            partes = parsear_nombre(ruta)
            if partes is None:
                continue
            obj, cond, _ = partes
            if objeto != "todos" and obj != objeto:
                continue
            if condicion != "todas" and cond != condicion:
                continue
            elegidos.append(ruta)
        return elegidos

    def _refrescar_lista(self) -> None:
        self.lista.delete(0, tk.END)
        self.videos = self._videos_filtrados()
        for ruta in self.videos:
            self.lista.insert(tk.END, f" {ruta.stem}")
        if not self.videos:
            aviso = (
                "No hay videos en la carpeta"
                if self.carpeta.is_dir()
                else "La carpeta no existe"
            )
            self.var_estado.set(f"{aviso}: {self.carpeta}")
        else:
            self.lista.selection_set(0)
            self.var_estado.set(f"{len(self.videos)} videos en la lista")
        if not self.resultados_lote:
            self._mensaje_lote_vacio()

    def _elegir_carpeta(self) -> None:
        elegida = filedialog.askdirectory(
            title="Carpeta con los videos", initialdir=str(self.carpeta)
        )
        if elegida:
            self.carpeta = Path(elegida)
            self.var_carpeta.set(str(self.carpeta))
            self._refrescar_lista()

    # ------------------------------------------------------------------ medir

    def _ocupar(self, ocupado: bool, mensaje: str = "") -> None:
        self.trabajando = ocupado
        estado = "disabled" if ocupado else "normal"
        self.boton_medir.configure(state=estado)
        self.boton_lote.configure(state=estado)
        if ocupado:
            self.progreso.start(12)
            self.var_estado.set(mensaje)
        else:
            self.progreso.stop()

    def _medir_seleccionado(self) -> None:
        if self.trabajando:
            return
        seleccion = self.lista.curselection()
        if not seleccion:
            messagebox.showinfo("Sin seleccion", "Elegi un video de la lista.")
            return
        ruta = self.videos[seleccion[0]]
        self._ocupar(True, f"Midiendo {ruta.name} ...")

        def trabajo() -> None:
            self.cola.put(("corrida", _medir_en_hilo(ruta)))

        threading.Thread(target=trabajo, daemon=True).start()

    def _medir_lote(self) -> None:
        if self.trabajando:
            return
        rutas = list(self.videos)
        if not rutas:
            messagebox.showinfo("Sin videos", "El filtro no deja ningun video.")
            return
        if len(rutas) > 20:
            minutos = round(SEGUNDOS_POR_VIDEO * len(rutas) / 60)
            seguir = messagebox.askyesno(
                "Lote largo",
                f"Vas a medir {len(rutas)} videos. Va a tardar unos "
                f"{minutos} minutos.\n\n"
                "Podes achicarlo filtrando por objeto y condicion. Seguir igual?",
            )
            if not seguir:
                return
        self.resultados_lote = []
        self.tabla.delete(*self.tabla.get_children())
        self.resumen_lote.configure(text="")
        self.fig_lote.clear()
        self.canvas_lote.draw()
        self.pestanias.select(self.tab_lote)
        self._ocupar(True, f"Midiendo {len(rutas)} videos ...")

        def trabajo() -> None:
            for i, ruta in enumerate(rutas, 1):
                self.cola.put(("progreso", f"Midiendo {i}/{len(rutas)}: {ruta.name}"))
                self.cola.put(("lote_fila", _medir_en_hilo(ruta)))
            self.cola.put(("lote_fin", None))

        threading.Thread(target=trabajo, daemon=True).start()

    def _revisar_cola(self) -> None:
        try:
            while True:
                clase, carga = self.cola.get_nowait()
                if clase == "progreso":
                    self.var_estado.set(carga)
                elif clase == "corrida":
                    self._mostrar_corrida(carga)
                elif clase == "lote_fila":
                    self._agregar_fila_lote(carga)
                elif clase == "lote_fin":
                    self._cerrar_lote()
        except queue.Empty:
            pass
        self.after(100, self._revisar_cola)

    # ------------------------------------------------------------- una corrida

    def _mostrar_corrida(self, medida: Medida) -> None:
        self._ocupar(False)
        if medida.error:
            self.var_estado.set(f"{medida.nombre}: {medida.error}")
            messagebox.showerror("No se pudo medir", f"{medida.nombre}\n\n{medida.error}")
            return

        self.corrida_actual = medida.corrida
        self._pintar_resumen(medida.corrida)
        self._pintar_graficos(medida.corrida)
        self._pintar_trayectoria(medida.corrida, medida.cuadro_rgb)
        self._pintar_texto(medida.corrida)
        self.pestanias.select(self.tab_resumen)
        self.var_estado.set(f"{medida.nombre}: a = {medida.corrida.aceleracion:.3f} m/s^2")

    def _pintar_resumen(self, c) -> None:
        self.resumen.limpiar()

        encabezado = ttk.Frame(self.resumen.interior)
        encabezado.pack(fill="x", pady=(0, 10))
        ttk.Label(encabezado, text=c.ruta.stem, font=("Segoe UI", 15, "bold")).pack(side="left")
        ttk.Label(
            encabezado,
            text=f"   {c.objeto} · {c.condicion} · repeticion {c.repeticion}",
            foreground=TENUE,
            font=("Segoe UI", 10),
        ).pack(side="left", pady=(5, 0))

        grilla = ttk.Frame(self.resumen.interior)
        grilla.pack(fill="both", expand=True)
        grilla.columnconfigure(0, weight=1, uniform="col")
        grilla.columnconfigure(1, weight=1, uniform="col")

        cal = Tarjeta(grilla, "Calibracion")
        cal.agregar("escala", f"{c.cal.px_por_cm:.2f} px/cm")
        cal.agregar("papel rosa", f"{c.cal.largo_papel_px:.1f} px = 7.5 cm")
        cal.agregar("eje de la rampa", f"{math.degrees(c.cal.angulo_rampa_rad):.2f}°")
        if c.chequeo_escala.get("disponible"):
            cal.agregar(
                "control con la tabla",
                f"{c.chequeo_escala['px_por_cm_rampa']:.2f} px/cm "
                f"({c.chequeo_escala['discrepancia_relativa']:+.1%})",
            )
            cal.nota("El control es cota inferior: los extremos de la tabla quedan tapados.")
        desvio = math.degrees(c.cal.angulo_rampa_rad - angulo_trayectoria(c))
        cal.agregar("eje de la trayectoria", f"{math.degrees(angulo_trayectoria(c)):.2f}° ({desvio:+.2f}°)")
        cal.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 10))

        seg = Tarjeta(grilla, "Seguimiento")
        seg.agregar(
            "cobertura",
            f"{c.tray.cobertura:.0%} ({len(c.tray.detecciones)}/{c.tray.n_frames})",
        )
        seg.agregar("sigma de posicion", f"{c.sigma_px:.2f} px = {1000 * c.sigma_s_m:.2f} mm")
        seg.agregar(
            "ventana util",
            f"cuadros {int(c.frames[c.i0])}-{int(c.frames[c.i1 - 1])} ({len(c.t)} pts)",
        )
        seg.agregar("duracion", f"{c.duracion_s:.2f} s")
        seg.agregar("recorrido", f"{c.recorrido_cm:.1f} cm")
        seg.nota(f"Fin de la ventana: {c.motivo_fin}")
        seg.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 10))

        cin = Tarjeta(grilla, "Cinematica")
        cin.agregar("aceleracion", f"{c.aceleracion:.3f} m/s²", destacado=True)
        rel = c.cal.px_por_cm.s / c.cal.px_por_cm.n
        cin.agregar(
            "  de donde sale el error",
            f"ajuste {c.cin.aceleracion.s:.3f} + escala {abs(c.cin.aceleracion.n) * rel:.3f}",
        )
        cin.agregar("velocidad inicial", f"{c.cin.v_inicial:.3f} m/s")
        cin.agregar("residuo RMS", f"{1000 * c.cin.residuo_rms:.2f} mm")
        cin.agregar("chi2 reducido", f"{c.cin.chi2_reducido:.2f}")
        cin.agregar(
            "a por diferencias", f"{np.median(c.cin.a_filtrada):.3f} m/s² (mediana filtrada)"
        )
        if c.cin.chi2_reducido > 5:
            cin.nota(
                "chi2 muy por encima de 1: el sigma de posicion esta subestimado "
                "(se mide con el cuerpo quieto, pero en movimiento hay desenfoque).",
                "#8a5a10",
            )
        cin.grid(row=1, column=0, sticky="nsew", padx=(0, 6))

        fis = Tarjeta(grilla, "Fisica")
        if c.diagnostico is None:
            fis.agregar("angulo", "variable durante la toma")
            fis.nota(
                "Es una corrida de angulo critico: el plano se levanta mientras se "
                "filma, asi que no hay un theta fijo con el que calcular mu dinamico."
            )
        else:
            d = c.diagnostico
            fis.agregar(
                "angulo del plano",
                f"{math.degrees(d.theta.n):.2f} ± {math.degrees(d.theta.s):.2f}°",
            )
            fis.agregar("g sen(theta)", f"{d.a_sin_rozamiento.n:.3f} m/s²")
            fis.agregar("mu dinamico si desliza", f"{d.mu_d_si_desliza:.4f}")
            if d.mu_e_referencia is not None:
                fis.agregar("mu estatico (referencia)", f"{d.mu_e_referencia:.4f}")
            mejor = min(d.predicciones_rodando.items(), key=lambda kv: kv[1][1])
            fis.agregar(
                "mejor hipotesis de rodadura",
                f"{mejor[0]}: {mejor[1][0].n:.3f} m/s² ({mejor[1][1]:.1f}σ)",
            )
        fis.grid(row=1, column=1, sticky="nsew", padx=(6, 0))

        libre = Tarjeta(grilla, "Diagrama de cuerpo libre")
        libre.agregar("masa", f"{1000 * c.masa_kg.n:.0f} ± {1000 * c.masa_kg.s:.0f} g")
        if c.diagnostico is None or c.diagnostico.fuerzas is None:
            libre.nota(
                "Las fuerzas necesitan un theta fijo. En una corrida de angulo critico "
                "el plano se levanta mientras se filma, asi que no hay uno."
            )
        else:
            f = c.diagnostico.fuerzas
            for etiqueta, fuerza in (
                ("peso  P = m·g", f.peso),
                ("normal  N = P·cosθ", f.normal),
                ("paralela  P·senθ", f.paralela),
                ("rozamiento  f = m(g·senθ − a)", f.rozamiento),
            ):
                libre.agregar(etiqueta, f"{1000 * fuerza.n:.2f} ± {1000 * fuerza.s:.2f} mN")
            libre.agregar("control  f / N", f"{f.mu_de_fuerzas.n:.4f}")
            libre.nota(
                "f/N no depende de la masa: se simplifica. Que de igual que el mu dinamico "
                "de arriba es el control de que el planteo de fuerzas cierra. La incerteza "
                "de las fuerzas la domina la masa, que esta medida al gramo."
            )
        libre.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(10, 0))

        if c.diagnostico is not None:
            fondo, frente = _color_veredicto(c.diagnostico.veredicto)
            cartel = tk.Frame(self.resumen.interior, background=fondo, highlightthickness=0)
            cartel.pack(fill="x", pady=(12, 0))
            tk.Label(
                cartel,
                text=f"VEREDICTO: {c.diagnostico.veredicto}",
                background=fondo,
                foreground=frente,
                font=("Segoe UI", 11, "bold"),
                anchor="w",
                padx=14,
                pady=8,
            ).pack(fill="x")
            for aviso in c.diagnostico.advertencias:
                tk.Label(
                    cartel,
                    text=f"⚠  {aviso}",
                    background=fondo,
                    foreground=frente,
                    font=("Segoe UI", 9),
                    anchor="w",
                    justify="left",
                    wraplength=980,
                    padx=14,
                ).pack(fill="x", pady=(0, 8))

    def _pintar_graficos(self, c) -> None:
        self.fig_graficos.clear()
        ejes = self.fig_graficos.subplots(2, 2)
        for fila in ejes:
            for eje in fila:
                eje.set_facecolor("white")
                eje.grid(alpha=0.25, linewidth=0.6)

        t = c.t - c.t[0]
        coef = np.polyfit(t, c.s_m, 2)
        ajuste = np.polyval(coef, t)

        pos = ejes[0][0]
        pos.plot(t, 100 * c.s_m, ".", color=ACENTO, markersize=5, label="medido")
        pos.plot(t, 100 * ajuste, "-", color="#d1495b", linewidth=1.6, label="ajuste cuadratico")
        pos.set_ylabel("s [cm]")
        pos.set_title("Posicion sobre el plano", fontsize=10)
        pos.legend(fontsize=8, framealpha=0.9)

        res = ejes[0][1]
        residuos = 1000 * (c.s_m - ajuste)
        res.axhline(0, color=TENUE, linewidth=0.8)
        res.plot(t, residuos, ".-", color="#7b5ea7", markersize=4, linewidth=0.8)
        res.axhspan(
            -1000 * c.sigma_s_m, 1000 * c.sigma_s_m, color=TENUE, alpha=0.18, label="± sigma"
        )
        res.set_ylabel("residuo [mm]")
        res.set_title(
            f"Residuos del ajuste  (chi2 red = {c.cin.chi2_reducido:.1f})", fontsize=10
        )
        res.legend(fontsize=8, framealpha=0.9)

        vel = ejes[1][0]
        vel.plot(t, c.cin.v_cruda, color=TENUE, linewidth=0.7, alpha=0.65, label="cruda")
        vel.plot(t, c.cin.v_filtrada, color=ACENTO, linewidth=1.8, label="filtrada")
        vel.set_ylabel("v [m/s]")
        vel.set_xlabel("t [s]")
        vel.set_title("Velocidad", fontsize=10)
        vel.legend(fontsize=8, framealpha=0.9)

        ace = ejes[1][1]
        ace.plot(t, c.cin.a_cruda, color=TENUE, linewidth=0.7, alpha=0.5, label="cruda")
        ace.plot(t, c.cin.a_filtrada, color=ACENTO, linewidth=1.8, label="filtrada")
        ace.axhline(
            c.aceleracion.n,
            color="#d1495b",
            linewidth=1.6,
            linestyle="--",
            label=f"ajuste = {c.aceleracion.n:.3f}",
        )
        ace.fill_between(
            t,
            c.aceleracion.n - c.aceleracion.s,
            c.aceleracion.n + c.aceleracion.s,
            color="#d1495b",
            alpha=0.15,
        )
        # La derivada segunda cruda se va a escalas que aplastan todo lo demas.
        margen = max(3 * abs(c.aceleracion.n), 2.0)
        ace.set_ylim(c.aceleracion.n - margen, c.aceleracion.n + margen)
        ace.set_ylabel("a [m/s²]")
        ace.set_xlabel("t [s]")
        ace.set_title("Aceleracion", fontsize=10)
        ace.legend(fontsize=8, framealpha=0.9)

        self.fig_graficos.suptitle(c.ruta.stem, fontsize=11, y=0.985)
        self.fig_graficos.tight_layout(rect=(0, 0, 1, 0.96))
        self.canvas_graficos.draw()

    def _pintar_trayectoria(self, c, cuadro_rgb) -> None:
        self.fig_tray.clear()
        eje = self.fig_tray.add_subplot(111)
        if cuadro_rgb is not None:
            eje.imshow(cuadro_rgb)

        x = np.array([d.x_px for d in c.tray.detecciones])
        y = np.array([d.y_px for d in c.tray.detecciones])

        eje.plot(x, y, ".", color="white", markersize=3, alpha=0.55, label="detecciones")
        eje.plot(
            x[c.i0 : c.i1],
            y[c.i0 : c.i1],
            ".",
            color="#36d399",
            markersize=5,
            label="ventana analizada",
        )
        eje.plot(x[c.i0], y[c.i0], "o", color="#36d399", markersize=11, markeredgecolor="black")
        eje.plot(
            x[c.i1 - 1], y[c.i1 - 1], "s", color="#f87272", markersize=11, markeredgecolor="black"
        )

        # Eje sobre el que se proyecta s(t). Se ancla en el primer punto
        # analizado y no en el papel rosa: dibujado desde el papel se aleja de
        # la trayectoria por el desplazamiento perpendicular entre los dos, y
        # parece un error de angulo que no existe.
        u = c.cal.versor_rampa
        largo = float(np.hypot(x[c.i1 - 1] - x[c.i0], y[c.i1 - 1] - y[c.i0]))
        ancla = np.array([x[c.i0], y[c.i0]]) - u * 0.08 * largo
        fin = ancla + u * 1.16 * largo
        desvio = math.degrees(c.cal.angulo_rampa_rad - angulo_trayectoria(c))
        eje.plot(
            [ancla[0], fin[0]],
            [ancla[1], fin[1]],
            "--",
            color="#fbbd23",
            linewidth=1.2,
            alpha=0.9,
            label=(
                f"eje de proyeccion: {math.degrees(c.cal.angulo_rampa_rad):.1f}° "
                f"(trayectoria {desvio:+.1f}°)"
            ),
        )

        eje.set_title(
            f"{c.ruta.stem}  —  verde: lo que se analiza   blanco: lo descartado",
            fontsize=10,
        )
        eje.legend(fontsize=8, loc="lower left", framealpha=0.85)
        eje.set_xticks([])
        eje.set_yticks([])
        self.fig_tray.tight_layout()
        self.canvas_tray.draw()

    def _pintar_texto(self, c) -> None:
        self.texto.configure(state="normal")
        self.texto.delete("1.0", tk.END)
        self.texto.insert("1.0", informe_texto(c))
        self.texto.configure(state="disabled")

    # ------------------------------------------------------------------- lote

    def _agregar_fila_lote(self, medida: Medida) -> None:
        self.resultados_lote.append(medida)
        if medida.error:
            self.tabla.insert(
                "", tk.END, values=(medida.nombre, "", "", "", "", "", medida.error), tags=("error",)
            )
            return
        c = medida.corrida
        mu = c.diagnostico.mu_d_si_desliza if c.diagnostico else None
        floja = len(c.t) < MIN_PUNTOS_CONFIABLE or c.recorrido_cm < MIN_RECORRIDO_CM
        self.tabla.insert(
            "",
            tk.END,
            tags=("flojo",) if floja else (),
            values=(
                c.ruta.stem,
                len(c.t),
                f"{c.recorrido_cm:.1f} cm",
                f"{c.aceleracion.n:.3f} ± {c.aceleracion.s:.3f}",
                f"{c.cin.chi2_reducido:.1f}",
                f"{mu.n:.4f}" if mu else "-",
                c.diagnostico.veredicto if c.diagnostico else "angulo critico",
            ),
        )

    def _cerrar_lote(self) -> None:
        self._ocupar(False)
        buenas = [m.corrida for m in self.resultados_lote if m.corrida is not None]
        fallidas = len(self.resultados_lote) - len(buenas)

        if not buenas:
            self.resumen_lote.configure(text=f"Ninguna corrida se pudo medir ({fallidas} fallaron)")
            self.var_estado.set("Lote terminado sin resultados")
            return

        aceleraciones = np.array([c.aceleracion.n for c in buenas])
        media = float(np.mean(aceleraciones))
        # La dispersion ENTRE repeticiones es el numero honesto del experimento.
        # El error del ajuste individual solo dice cuan parabolica es una
        # trayectoria, no cuan repetible es la medicion.
        dispersion = float(np.std(aceleraciones, ddof=1)) if len(aceleraciones) > 1 else 0.0
        relativa = dispersion / abs(media) if media else float("inf")

        texto = (
            f"a = {media:.3f} ± {dispersion:.3f} m/s²   "
            f"(dispersion entre {len(buenas)} repeticiones: {relativa:.0%})"
        )
        if fallidas:
            texto += f"   —  {fallidas} corrida(s) no se pudieron medir"
        flojas = [
            c
            for c in buenas
            if len(c.t) < MIN_PUNTOS_CONFIABLE or c.recorrido_cm < MIN_RECORRIDO_CM
        ]
        if flojas:
            texto += (
                f"   —  {len(flojas)} en amarillo: ventana demasiado corta, "
                f"conviene mirarlas antes de promediar"
            )
        self.resumen_lote.configure(text=texto)

        self.fig_lote.clear()
        eje = self.fig_lote.add_subplot(111)
        eje.set_facecolor("white")
        eje.grid(alpha=0.25, linewidth=0.6)
        indices = np.arange(1, len(buenas) + 1)
        eje.errorbar(
            indices,
            aceleraciones,
            yerr=[c.aceleracion.s for c in buenas],
            fmt="o",
            color=ACENTO,
            capsize=4,
            label="cada corrida (error del ajuste)",
        )
        eje.axhline(media, color="#d1495b", linewidth=1.5, label=f"media = {media:.3f}")
        eje.fill_between(
            [0.5, len(buenas) + 0.5],
            media - dispersion,
            media + dispersion,
            color="#d1495b",
            alpha=0.15,
            label=f"dispersion = {dispersion:.3f}",
        )
        eje.set_xlim(0.5, len(buenas) + 0.5)
        eje.set_xticks(indices)
        eje.set_xticklabels([c.ruta.stem.split()[-1] for c in buenas], fontsize=8)
        eje.set_ylabel("a [m/s²]")
        eje.set_title(
            "La barra de cada punto es el error del ajuste; la banda, la dispersion real",
            fontsize=10,
        )
        eje.legend(fontsize=8, framealpha=0.9)
        self.fig_lote.tight_layout()
        self.canvas_lote.draw()
        self.var_estado.set(f"Lote terminado: {len(buenas)} corridas medidas")


def main() -> None:
    Visor().mainloop()


if __name__ == "__main__":
    main()
