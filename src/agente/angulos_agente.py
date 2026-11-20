"""Angulos medidos por el agente, calculados UNA vez y guardados en disco.

    python src/agente/angulos_agente.py                  # calcula todo y guarda
    python src/agente/angulos_agente.py --solo-libros    # rapido (~1 min)
    python src/agente/angulos_agente.py --solo-criticos  # lento (~5 min)
    python src/agente/angulos_agente.py --ver            # muestra lo guardado

Resultado: datos/agente/angulos.json. medir.py lo lee y, si existe, usa estos
angulos para la fisica en vez de los de laboratorio.json (Grupo 3). Si no
existe, o falta un dato, cae a laboratorio.json y lo avisa.

QUE SE MIDE
  - Angulo del plano en las corridas con libros (2, 3 y 4 libros): el canto de
    madera de la rampa en los primeros cuadros de CADA video, cuando el objeto
    todavia esta sostenido y la rampa se ve entera (angulo_critico.recta_rampa,
    corregido por el giro de la camara). Se guarda el angulo de cada video y
    el promedio por condicion.
      - Para la fisica de una corrida se usa el angulo de ESE video.
      - Su incerteza es la dispersion entre los videos de la misma condicion:
        la rampa con los mismos libros es la misma, asi que lo que varia de un
        video a otro es error de medicion (giro de camara, ruido de la recta).
  - Angulo critico de cada objeto (-> mu_e = tan theta_c): con
    angulo_critico.medir_video sobre los videos "Angulo Critico". Se promedian
    las repeticiones que deslizaron; la incerteza es la dispersion / sqrt(n),
    porque mu_e es una propiedad del material, no de una corrida.
      - El JABON se excluye a proposito: su perfil de color no se separa bien
        en esos videos y el agente no detecta el arranque. Para el jabon se
        sigue usando el dato del Grupo 3, y queda marcado.

LIMITACION
El angulo es el APARENTE en la imagen (proyeccion). La validacion contra los
angulos de la regla (angulo_critico.py --validar) dio diferencias de -1,8,
-0,9 y +0,6 grados para 4, 3 y 2 libros. No se sabe cual de los dos esta mas
cerca del real: la regla tiene sus propios problemas (espesor de la tabla,
altura de 4 libros sospechosa), y la imagen tiene perspectiva.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from uncertainties import ufloat, umath
from uncertainties.core import Variable

import angulo_critico as ac
from inventario import CARPETA_VIDEOS, parsear_nombre

RAIZ = Path(__file__).resolve().parents[2]
ARCHIVO = RAIZ / "datos" / "agente" / "angulos.json"
VERSION = 1

CONDICIONES = ("4libros", "3libros", "2libros")
# Objetos cuyo angulo critico mide el agente.
OBJETOS_CRITICO = ("tapa", "esponja", "jabon")
CUADROS_LIBROS = 30  # primeros cuadros de cada video (el objeto todavia quieto)


# ---------------------------------------------------------------- lectura


@dataclass
class AngulosAgente:
    datos: dict

    @property
    def generado(self) -> str:
        return self.datos.get("_generado", "?")

    def angulo_rad(self, archivo: str, condicion: str) -> Variable | None:
        """Angulo del plano para esa corrida, o None si no esta medido."""
        cond = self.datos.get("condiciones", {}).get(condicion)
        if not cond:
            return None
        sigma = math.radians(cond["sigma_grados"])
        propio = cond.get("por_video", {}).get(archivo)
        valor = propio if propio is not None else cond["theta_grados"]
        return ufloat(math.radians(valor), sigma)

    def descripcion_angulo(self, archivo: str, condicion: str) -> str:
        cond = self.datos["condiciones"][condicion]
        if archivo in cond.get("por_video", {}):
            return (
                f"agente: canto de la rampa en este video "
                f"(sigma = dispersion entre {cond['n']} videos de {condicion})"
            )
        return f"agente: promedio de {cond['n']} videos de {condicion} (este video no se midio)"

    def mu_estatico(self, objeto: str) -> Variable | None:
        """mu_e = tan(theta_c) medido por el agente, o None si no lo mide."""
        c = self.datos.get("criticos", {}).get(objeto)
        if not c or c.get("fuente") != "agente":
            return None
        th = ufloat(math.radians(c["theta_c_grados"]), math.radians(c["sigma_grados"]))
        return umath.tan(th)

    def descripcion_mu_e(self, objeto: str) -> str:
        c = self.datos["criticos"][objeto]
        crit = f", {c['criterio']}" if c.get("criterio") else ""
        return (
            f"agente: angulo critico{crit}, promedio de {c['n']} videos "
            f"(sigma = dispersion / raiz de n)"
        )


_cache: tuple[float, AngulosAgente | None] | None = None


def cargar(archivo: Path = ARCHIVO) -> AngulosAgente | None:
    """Lee el archivo guardado. None si no existe (hay que correr este script).

    Se recuerda en memoria y se relee solo si el archivo cambio.
    """
    global _cache
    if not archivo.is_file():
        return None
    mtime = archivo.stat().st_mtime
    if _cache is not None and _cache[0] == mtime:
        return _cache[1]
    datos = json.loads(archivo.read_text(encoding="utf-8"))
    if datos.get("_version") != VERSION:
        return None
    obj = AngulosAgente(datos)
    _cache = (mtime, obj)
    return obj


# ---------------------------------------------------------------- calculo


def angulo_video_libros(ruta: Path, n_cuadros: int = CUADROS_LIBROS) -> float | None:
    """Angulo aparente del canto de la rampa (grados) en un video con libros."""
    cap = cv2.VideoCapture(str(ruta))
    angs, giro = [], None
    try:
        for _ in range(n_cuadros):
            ok, fr = cap.read()
            if not ok:
                break
            fr = cv2.resize(fr, None, fx=ac.ESCALA, fy=ac.ESCALA, interpolation=cv2.INTER_AREA)
            if giro is None:
                giro = ac.giro_camara(fr)
            r = ac.recta_rampa(cv2.cvtColor(fr, cv2.COLOR_BGR2HSV))
            if r is not None:
                angs.append(r[0])
    finally:
        cap.release()
    if len(angs) < 5:
        return None
    return math.degrees(float(np.median(angs)) - (giro or 0.0))


def calcular_libros(carpeta: Path) -> dict:
    from referencia import cargar as cargar_referencia

    ref = cargar_referencia()
    clave_lab = {"4libros": "angulo_1", "3libros": "angulo_2", "2libros": "angulo_3"}
    salida = {}
    for cond in CONDICIONES:
        por_video = {}
        for ruta in sorted(carpeta.glob("*.mp4")):
            partes = parsear_nombre(ruta)
            if partes is None or partes[1] != cond:
                continue
            a = angulo_video_libros(ruta)
            print(f"  {ruta.name:32s} {'-' if a is None else f'{a:6.2f} grados'}", flush=True)
            if a is not None:
                por_video[ruta.name] = round(a, 4)
        if not por_video:
            print(f"  [!] {cond}: ningun video medido")
            continue
        vals = np.array(list(por_video.values()))
        regla = math.degrees(ref.angulo_rad(clave_lab[cond]).n)
        salida[cond] = {
            "theta_grados": float(vals.mean()),
            "sigma_grados": float(vals.std(ddof=1)) if len(vals) > 1 else 0.5,
            "n": len(vals),
            "regla_grupo3_grados": regla,
            "por_video": por_video,
        }
        print(
            f"  => {cond}: {vals.mean():.2f} +/- {salida[cond]['sigma_grados']:.2f} grados "
            f"({len(vals)} videos)   regla Grupo 3: {regla:.2f}\n",
            flush=True,
        )
    return salida


def calcular_criticos(carpeta: Path, paso: int = 2) -> dict:
    from referencia import cargar as cargar_referencia

    ref = cargar_referencia()
    salida = {}
    for objeto in ("tapa", "esponja", "jabon"):
        o = next(x for x in ref.objetos.values() if x.nombre == objeto)
        th_lab = o.angulo_critico(ref.hipotenusa_cm)
        base = {
            "theta_c_grupo3_grados": math.degrees(th_lab.n),
            "sigma_grupo3_grados": math.degrees(th_lab.s),
        }
        if objeto not in OBJETOS_CRITICO:
            salida[objeto] = {
                **base,
                "fuente": "laboratorio",
                "motivo": "el agente no detecta el arranque del jabon (perfil de color)",
            }
            print(f"  {objeto}: se usa el dato del Grupo 3 (excluido del agente)")
            continue

        por_video, criterios, fallas = {}, set(), {}
        for ruta in sorted(carpeta.glob(f"{objeto.capitalize()} Angulo Critico Video*.mp4")):
            m = ac.PATRON.match(ruta.name)
            if not m or m.group("dup"):
                continue
            print(f"  midiendo {ruta.name} ...", flush=True)
            r = ac.medir_video(ruta, objeto, paso, graficar=True)
            if r.theta_c_grados is not None:
                por_video[ruta.name] = round(r.theta_c_grados, 4)
                criterios.add("deslizamiento (> 1 cm/s)")
                print(f"     theta_c = {r.theta_c_grados:.2f} grados (deslizamiento)")
            elif r.theta_corrimiento_grados is not None:
                por_video[ruta.name] = round(r.theta_corrimiento_grados, 4)
                criterios.add("corrimiento (> 0.3 cm)")
                print(f"     theta_c = {r.theta_corrimiento_grados:.2f} grados (corrimiento lento)")
            else:
                fallas[ruta.name] = r.error
                print(f"     sin movimiento: {r.error}")
        if not por_video:
            salida[objeto] = {**base, "fuente": "laboratorio", "motivo": "ningun video se movio", "fallas": fallas}
            continue
        vals = np.array(list(por_video.values()))
        n = len(vals)
        disp = float(vals.std(ddof=1)) if n > 1 else 0.5
        salida[objeto] = {
            **base,
            "fuente": "agente",
            "criterio": " + ".join(sorted(criterios)),
            "theta_c_grados": float(vals.mean()),
            "sigma_grados": disp / math.sqrt(n),
            "dispersion_grados": disp,
            "n": n,
            "mu_e": math.tan(math.radians(vals.mean())),
            "por_video": por_video,
            "fallas": fallas,
        }
        print(
            f"  => {objeto}: theta_c = {vals.mean():.2f} +/- {disp / math.sqrt(n):.2f} grados "
            f"({n} videos, dispersion {disp:.2f})   Grupo 3: {math.degrees(th_lab.n):.2f}\n",
            flush=True,
        )
    return salida


def guardar(libros: dict | None, criticos: dict | None, archivo: Path = ARCHIVO) -> None:
    """Escribe el archivo. Si solo se recalculo una parte, conserva la otra."""
    previo = {}
    if archivo.is_file():
        try:
            previo = json.loads(archivo.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previo = {}
    datos = {
        "_version": VERSION,
        "_generado": datetime.now().isoformat(timespec="seconds"),
        "_nota": (
            "Generado por src/agente/angulos_agente.py. NO editar a mano: volver a "
            "correr el script. Angulos aparentes en la imagen, en grados."
        ),
        "condiciones": libros if libros is not None else previo.get("condiciones", {}),
        "criticos": criticos if criticos is not None else previo.get("criticos", {}),
    }
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")


def mostrar(a: AngulosAgente | None) -> None:
    if a is None:
        print(f"No hay angulos guardados en {ARCHIVO}. Correr este script.")
        return
    print(f"Angulos del agente (generado {a.generado})\n")
    print(f"{'condicion':10s} {'agente':>16s} {'regla G3':>9s} {'dif':>7s}")
    for cond, c in a.datos.get("condiciones", {}).items():
        dif = c["theta_grados"] - c["regla_grupo3_grados"]
        print(
            f"{cond:10s} {c['theta_grados']:7.2f} +/- {c['sigma_grados']:.2f} "
            f"{c['regla_grupo3_grados']:9.2f} {dif:+7.2f}   ({c['n']} videos)"
        )
    print(f"\n{'objeto':10s} {'theta_c agente':>18s} {'mu_e':>7s} {'theta_c G3':>11s}  fuente")
    for obj, c in a.datos.get("criticos", {}).items():
        if c.get("fuente") == "agente":
            print(
                f"{obj:10s} {c['theta_c_grados']:9.2f} +/- {c['sigma_grados']:.2f} "
                f"{c['mu_e']:7.4f} {c['theta_c_grupo3_grados']:11.2f}  agente ({c['n']} videos)"
            )
        else:
            print(
                f"{obj:10s} {'-':>18s} {'-':>7s} {c['theta_c_grupo3_grados']:11.2f}  "
                f"laboratorio ({c.get('motivo', '')})"
            )


def main() -> None:
    p = argparse.ArgumentParser(description="Calcula y guarda los angulos medidos por el agente")
    p.add_argument("--carpeta", type=Path, default=CARPETA_VIDEOS)
    p.add_argument("--solo-libros", action="store_true")
    p.add_argument("--solo-criticos", action="store_true")
    p.add_argument("--paso", type=int, default=2, help="angulo critico: 1 de cada N cuadros")
    p.add_argument("--ver", action="store_true", help="solo mostrar lo guardado")
    args = p.parse_args()

    if args.ver:
        mostrar(cargar())
        return

    libros = criticos = None
    if not args.solo_criticos:
        print("ANGULO DEL PLANO EN LAS CORRIDAS CON LIBROS")
        libros = calcular_libros(args.carpeta)
    if not args.solo_libros:
        print("ANGULO CRITICO")
        criticos = calcular_criticos(args.carpeta, args.paso)
    guardar(libros, criticos)
    print(f"\n-> {ARCHIVO}\n")
    mostrar(cargar())


if __name__ == "__main__":
    main()
