"""Mide todas las corridas una vez y deja los resultados en disco.

    python src/agente/lote.py

Existe por dos razones:

  - El chat no puede medir videos en vivo: cada corrida tarda unos segundos y
    una pregunta puede tocar las 61. Con el cache, responder es leer un JSON.
  - La dispersion entre repeticiones, que es la incerteza honesta del
    experimento, solo se puede calcular mirando todas las repeticiones juntas.

Salidas:
  resultados/corridas.json  una entrada por video medido (o por el que fallo)
  resultados/global.json    agregado por objeto y condicion
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any

from inventario import CARPETA_VIDEOS, parsear_nombre
from medir import ErrorMedicion, analizar_corrida, resumen_dict
from referencia import cargar as cargar_referencia

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = RAIZ / "resultados"

CONDICION_A_ANGULO = {"4libros": "angulo_1", "3libros": "angulo_2", "2libros": "angulo_3"}

# Una corrida con muy pocos puntos o muy poco recorrido no mide aceleracion:
# el ajuste cuadratico se apoya en demasiado poco. Se guarda igual, marcada.
MIN_PUNTOS = 15
MIN_RECORRIDO_CM = 3.0


def _confiable(r: dict) -> tuple[bool, str]:
    if r.get("error"):
        return False, r["error"]
    if r["n_puntos"] < MIN_PUNTOS:
        return False, f"solo {r['n_puntos']} puntos en el ajuste (minimo {MIN_PUNTOS})"
    if r["recorrido_cm"] < MIN_RECORRIDO_CM:
        return False, f"recorrido de {r['recorrido_cm']:.1f} cm (minimo {MIN_RECORRIDO_CM})"
    if r["aceleracion"][0] <= 0:
        return False, "aceleracion no positiva: el seguimiento fallo"
    if r["cobertura"] < 0.9:
        return False, f"el tracker solo encontro el objeto en el {r['cobertura']:.0%} de los cuadros"
    return True, ""


def medir_todo(carpeta: Path) -> list[dict]:
    archivos = sorted(carpeta.glob("*.mp4"))
    filas: list[dict] = []
    for i, ruta in enumerate(archivos, 1):
        if parsear_nombre(ruta) is None:
            continue
        print(f"  [{i:>2}/{len(archivos)}] {ruta.name}", flush=True)
        try:
            fila = resumen_dict(analizar_corrida(ruta))
            fila["error"] = None
        except (ErrorMedicion, Exception) as e:  # noqa: BLE001 - queremos registrar cualquier falla
            objeto, condicion, repeticion = parsear_nombre(ruta)
            fila = {
                "archivo": ruta.name,
                "objeto": objeto,
                "condicion": condicion,
                "repeticion": repeticion,
                "error": f"{type(e).__name__}: {e}",
                "n_puntos": 0,
                "recorrido_cm": 0.0,
                "cobertura": 0.0,
                "aceleracion": [0.0, 0.0],
            }
        ok, motivo = _confiable(fila)
        fila["confiable"] = ok
        fila["motivo_descarte"] = motivo or None
        filas.append(fila)
    return filas


def agregar(filas: list[dict]) -> dict[str, Any]:
    """Agrupa por objeto y condicion y calcula la dispersion entre repeticiones."""
    ref = cargar_referencia()
    grupos: dict[tuple[str, str], list[dict]] = {}
    for f in filas:
        grupos.setdefault((f["objeto"], f["condicion"]), []).append(f)

    condiciones = []
    for (objeto, condicion), fs in sorted(grupos.items()):
        buenas = [f for f in fs if f["confiable"]]
        entrada: dict[str, Any] = {
            "objeto": objeto,
            "condicion": condicion,
            "n_videos": len(fs),
            "n_confiables": len(buenas),
            "archivos_descartados": [
                {"archivo": f["archivo"], "motivo": f["motivo_descarte"]}
                for f in fs
                if not f["confiable"]
            ],
        }

        # El angulo critico no se mide por aceleracion: en esos videos se
        # inclina el plano hasta que el cuerpo apenas arranca, asi que no hay
        # tramo de movimiento uniformemente acelerado para ajustar. El mu
        # estatico sale de la altura de inicio que midio el Grupo 3, no del
        # seguimiento. Marcarlo como "sin datos confiables" seria reportar una
        # falla que no existe.
        if condicion == "angulo critico":
            entrada["aceleracion_media"] = None
            entrada["no_aplica"] = (
                "El angulo critico no se analiza por aceleracion: el cuerpo recien "
                "arranca a moverse y no hay tramo acelerado para ajustar. El mu "
                "estatico de este objeto sale de la altura de inicio medida por el "
                "Grupo 3, que esta en datos_del_laboratorio()."
            )
            entrada["archivos_descartados"] = []
            condiciones.append(entrada)
            continue

        if len(buenas) >= 2:
            acs = [f["aceleracion"][0] for f in buenas]
            media = statistics.mean(acs)
            desvio = statistics.stdev(acs)

            # Dispersion exactamente cero entre mediciones independientes no es
            # precision: es senal de que algo esta repetido (el mismo video dos
            # veces, o un cache que no se invalido). Se avisa en vez de emitir
            # un mu con incerteza cero, que contradice la regla del proyecto.
            if desvio == 0.0:
                entrada["sospecha"] = (
                    f"Las {len(buenas)} corridas dieron exactamente la misma "
                    f"aceleracion ({media:.6f} m/s^2). Entre mediciones "
                    f"independientes eso no pasa: revisar si hay videos "
                    f"duplicados o un cache viejo."
                )
            entrada["aceleracion_media"] = media
            # error de la media = dispersion / sqrt(n). La dispersion entre
            # repeticiones, no el error de cada ajuste, es la incerteza real.
            entrada["dispersion_entre_repeticiones"] = desvio
            entrada["error_de_la_media"] = desvio / math.sqrt(len(buenas))
            entrada["dispersion_relativa"] = desvio / media if media else None

            clave_ang = CONDICION_A_ANGULO.get(condicion)
            if clave_ang:
                from uncertainties import ufloat, umath

                theta = ref.angulo_rad(clave_ang)
                a = ufloat(media, desvio / math.sqrt(len(buenas)))
                g = 9.81
                mu = (g * umath.sin(theta) - a) / (g * umath.cos(theta))
                entrada["angulo_grados"] = [math.degrees(theta.n), math.degrees(theta.s)]
                entrada["mu_d_si_desliza"] = [mu.n, mu.s]
                # 1 + I/(mR^2) si en cambio rodara sin deslizar
                inercia = g * umath.sin(theta) / a
                entrada["factor_inercia_si_rueda"] = [inercia.n, inercia.s]
        else:
            entrada["aceleracion_media"] = None
            entrada["nota"] = "menos de 2 corridas confiables: no se puede dar dispersion"

        condiciones.append(entrada)

    objetos = {}
    for clave, obj in ref.objetos.items():
        mu_e = ref.mu_estatico(clave)
        objetos[obj.nombre] = {
            "clave": clave,
            "masa_kg": [obj.masa_kg.n, obj.masa_kg.s],
            "mu_estatico": [mu_e.n, mu_e.s],
            "angulo_critico_grados": [
                math.degrees(obj.angulo_critico(ref.hipotenusa_cm).n),
                math.degrees(obj.angulo_critico(ref.hipotenusa_cm).s),
            ],
        }

    return {
        "condiciones": condiciones,
        "objetos": objetos,
        "totales": {
            "videos": len(filas),
            "confiables": sum(1 for f in filas if f["confiable"]),
            "con_error": sum(1 for f in filas if f.get("error")),
        },
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Mide todas las corridas y cachea resultados")
    p.add_argument("--carpeta", type=Path, default=CARPETA_VIDEOS)
    p.add_argument("--salida", type=Path, default=SALIDA)
    args = p.parse_args()

    print(f"Midiendo {args.carpeta.name}/\n")
    filas = medir_todo(args.carpeta)
    glob = agregar(filas)

    args.salida.mkdir(parents=True, exist_ok=True)
    (args.salida / "corridas.json").write_text(
        json.dumps(filas, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (args.salida / "global.json").write_text(
        json.dumps(glob, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    t = glob["totales"]
    print(f"\n{t['videos']} videos | {t['confiables']} confiables | {t['con_error']} con error")
    print("\nPor condicion:")
    for c in glob["condiciones"]:
        if c["aceleracion_media"] is not None:
            print(
                f"  {c['objeto']:8s} {c['condicion']:15s} "
                f"a = {c['aceleracion_media']:.3f} +/- {c['error_de_la_media']:.3f} m/s^2 "
                f"(disp {c['dispersion_relativa']:.0%}, n={c['n_confiables']})"
            )
        else:
            print(f"  {c['objeto']:8s} {c['condicion']:15s} sin datos confiables")
    print(f"\n-> {args.salida / 'corridas.json'}")
    print(f"-> {args.salida / 'global.json'}")


if __name__ == "__main__":
    main()
