"""Las funciones que el modelo de lenguaje puede llamar.

Este modulo no sabe que proveedor se usa: son funciones de Python normales que
devuelven diccionarios serializables. Los adaptadores (claude.py, gemini.py) las
exponen cada uno a su manera.

El principio del proyecto: **el modelo no calcula**. Pregunta, y los numeros
salen de aca, que a su vez los lee de resultados/ y datos/, producidos por el
pipeline determinista. Una respuesta del chat es auditable porque se puede
mirar que funciones llamo y comparar con el JSON.

Las docstrings y los nombres de parametros NO son decorativos: de ahi sale el
esquema de la herramienta que ve el modelo. Si una docstring miente, el modelo
llama mal a la funcion.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[3]
RESULTADOS = RAIZ / "resultados"
DATOS = RAIZ / "datos"

OBJETOS_VALIDOS = ("tapa", "esponja", "jabon")
CONDICIONES_VALIDAS = ("4libros", "3libros", "2libros", "angulo critico")

DOCUMENTOS = {
    "arquitectura": RAIZ / "arquitectura.md",
    "hallazgos": RAIZ / "hallazgos.md",
    "readme": RAIZ / "README.md",
    "datos_laboratorio": DATOS / "referencia" / "laboratorio.json",
}


class FaltanDatos(RuntimeError):
    """El cache de resultados no existe todavia."""


def _mostrar(ruta: Path) -> str:
    """Ruta relativa al repo si se puede, si no el nombre.

    relative_to() lanza ValueError cuando la ruta cae fuera del repo, asi que
    usarla directo hacia que el propio mensaje de error rompiera.
    """
    try:
        return str(ruta.relative_to(RAIZ))
    except ValueError:
        return ruta.name


def _leer_json(ruta: Path) -> Any:
    if not ruta.is_file():
        raise FaltanDatos(
            f"Falta {_mostrar(ruta)}. Hay que correr primero: "
            f"python src/agente/lote.py"
        )
    return json.loads(ruta.read_text(encoding="utf-8"))


def _corridas() -> list[dict]:
    return _leer_json(RESULTADOS / "corridas.json")


def _global() -> dict:
    return _leer_json(RESULTADOS / "global.json")


def _vu(par: list | None) -> dict | None:
    """Convierte [valor, sigma] en algo que el modelo lea sin confundirse."""
    if not par:
        return None
    return {"valor": round(par[0], 5), "incerteza": round(par[1], 5)}


# --------------------------------------------------------------------------
# Herramientas
# --------------------------------------------------------------------------


def estado_del_proyecto() -> dict:
    """Panorama del proyecto: que mide bien el agente y que no.

    Empezar por aca cuando la pregunta es general ("como viene esto",
    "que falta", "que problemas hay"). Devuelve el conteo de corridas
    confiables y la lista de que esta roto, con el motivo.
    """
    try:
        g = _global()
        corridas = _corridas()
    except FaltanDatos as e:
        return {"disponible": False, "motivo": str(e)}

    por_condicion = []
    for c in g["condiciones"]:
        por_condicion.append(
            {
                "objeto": c["objeto"],
                "condicion": c["condicion"],
                "confiables": f"{c['n_confiables']} de {c['n_videos']}",
                "no_aplica": c.get("no_aplica"),
                "aceleracion_m_s2": (
                    {
                        "valor": round(c["aceleracion_media"], 4),
                        "error_de_la_media": round(c["error_de_la_media"], 4),
                        "dispersion_entre_repeticiones": round(
                            c["dispersion_entre_repeticiones"], 4
                        ),
                    }
                    if c["aceleracion_media"] is not None
                    else None
                ),
            }
        )

    errores: dict[str, int] = {}
    for f in corridas:
        if f.get("motivo_descarte"):
            clave = f["motivo_descarte"].split(":")[0][:70]
            errores[clave] = errores.get(clave, 0) + 1

    return {
        "disponible": True,
        "totales": g["totales"],
        "por_condicion": por_condicion,
        "motivos_de_descarte": errores,
        "limitaciones_conocidas": [
            "El seguimiento del jabon por umbral de color no funciona: es crema "
            "palido sobre pared blanca y regla de madera.",
            "A 2 libros el cuerpo recorre pocos centimetros y quedan pocos puntos "
            "para el ajuste.",
            "El sigma de posicion se mide con el cuerpo quieto y subestima el error "
            "en movimiento (hay desenfoque). El chi2 reducido sale alto por eso.",
            "La escala px/cm sale del papel rosa de 7,5 cm. El control contra la "
            "regla de 42 cm no cierra, pero la regla es cota inferior porque sus "
            "extremos quedan ocultos.",
        ],
    }


def resumen_por_condicion(objeto: str | None = None) -> dict:
    """Aceleracion media y dispersion por objeto y condicion, mas mu y el contraste rueda-vs-desliza.

    Es la tabla principal de resultados. Incluye, por cada condicion con datos:
    la aceleracion media, el error de la media, la dispersion entre
    repeticiones, el angulo del plano, el mu dinamico que saldria si el cuerpo
    deslizara, y el factor 1+I/mR2 que saldria si rodara sin deslizar.

    Args:
        objeto: filtra por un objeto ("tapa", "esponja" o "jabon"). Si se omite, devuelve todos.
    """
    g = _global()
    condiciones = g["condiciones"]
    if objeto:
        objeto = objeto.strip().lower()
        if objeto not in OBJETOS_VALIDOS:
            return {"error": f"objeto desconocido '{objeto}'", "validos": list(OBJETOS_VALIDOS)}
        condiciones = [c for c in condiciones if c["objeto"] == objeto]

    salida = []
    for c in condiciones:
        salida.append(
            {
                "objeto": c["objeto"],
                "condicion": c["condicion"],
                "n_confiables": c["n_confiables"],
                "n_videos": c["n_videos"],
                "aceleracion_m_s2": _vu(
                    [c["aceleracion_media"], c["error_de_la_media"]]
                    if c["aceleracion_media"] is not None
                    else None
                ),
                "dispersion_entre_repeticiones_m_s2": (
                    round(c["dispersion_entre_repeticiones"], 4)
                    if c.get("dispersion_entre_repeticiones")
                    else None
                ),
                "angulo_grados": _vu(c.get("angulo_grados")),
                "mu_d_si_desliza": _vu(c.get("mu_d_si_desliza")),
                "factor_inercia_si_rueda": _vu(c.get("factor_inercia_si_rueda")),
                "descartadas": c["archivos_descartados"],
                "no_aplica": c.get("no_aplica"),
            }
        )
    return {"condiciones": salida, "objetos": g["objetos"]}


def datos_del_laboratorio() -> dict:
    """Lo que midio a mano el Grupo 3: angulos, masas, angulos criticos y calibracion.

    Son los datos de entrada del agente, no resultados nuestros. Incluye los
    tres angulos del plano con su incerteza, la masa de cada objeto, la altura
    a la que arranca el movimiento (de donde sale el mu estatico) y el patron
    de calibracion espacial.
    """
    ref = _leer_json(DATOS / "referencia" / "laboratorio.json")
    g = None
    try:
        g = _global()
    except FaltanDatos:
        pass

    hip = ref["geometria"]["hipotenusa_cm"]
    angulos = {}
    for clave, a in ref["angulos"].items():
        if clave.startswith("_"):
            continue
        angulos[clave] = {
            "descripcion": a["descripcion"],
            "altura_cm": a["altura_cm"],
            "grados": round(math.degrees(math.asin(a["altura_cm"] / hip)), 4),
        }

    return {
        "fuente": ref["_fuente"],
        "hipotenusa_del_plano_cm": hip,
        "calibracion_espacial": ref["calibracion_espacial"],
        "fps_declarado": ref["fps_declarado"],
        "angulos": angulos,
        "nota_angulos": ref["angulos"].get("_nota"),
        "objetos": {
            o["nombre"]: {
                "masa_g": o["masa_g"],
                "sigma_masa_g": o["sigma_masa_g"],
                "altura_inicio_movimiento_cm": o["altura_inicio_movimiento_cm"],
            }
            for o in ref["objetos"].values()
        },
        "mu_estatico_derivado": (g or {}).get("objetos"),
        "criterio_de_incertezas": ref["sigmas_asumidos"],
    }


def listar_corridas(
    objeto: str | None = None,
    condicion: str | None = None,
    solo_confiables: bool = False,
) -> dict:
    """Lista las corridas medidas, con su aceleracion y si son confiables.

    Args:
        objeto: filtra por objeto ("tapa", "esponja", "jabon").
        condicion: filtra por condicion ("4libros", "3libros", "2libros", "angulo critico").
        solo_confiables: si es True, deja afuera las corridas descartadas.
    """
    filas = _corridas()
    if objeto:
        filas = [f for f in filas if f["objeto"] == objeto.strip().lower()]
    if condicion:
        filas = [f for f in filas if f["condicion"] == condicion.strip().lower()]
    if solo_confiables:
        filas = [f for f in filas if f["confiable"]]

    return {
        "n": len(filas),
        "corridas": [
            {
                "archivo": f["archivo"],
                "objeto": f["objeto"],
                "condicion": f["condicion"],
                "repeticion": f["repeticion"],
                "aceleracion_m_s2": _vu(f["aceleracion"]),
                "n_puntos": f["n_puntos"],
                "recorrido_cm": round(f["recorrido_cm"], 2),
                "confiable": f["confiable"],
                "motivo_descarte": f.get("motivo_descarte"),
            }
            for f in filas
        ],
    }


def detalle_corrida(archivo: str) -> dict:
    """Todos los numeros de una corrida: calibracion, seguimiento, ajuste, fuerzas y veredicto.

    Args:
        archivo: nombre del video, por ejemplo "Tapa 4Libros Video1.mp4".
    """
    filas = _corridas()
    archivo = archivo.strip()
    exacta = [f for f in filas if f["archivo"].lower() == archivo.lower()]
    if not exacta:
        parecidas = [f["archivo"] for f in filas if archivo.lower() in f["archivo"].lower()]
        return {
            "error": f"no existe la corrida '{archivo}'",
            "parecidas": parecidas[:10],
        }
    return exacta[0]


def comparar_hipotesis(objeto: str, condicion: str) -> dict:
    """Contrasta la aceleracion medida contra deslizamiento puro y contra rodadura.

    Este es el chequeo que pide la consigna ("verificar si el cuerpo desliza o
    rueda, porque cambia la ecuacion"). Devuelve, para la condicion pedida:
    la aceleracion medida, g*sen(theta) que seria sin rozamiento, el mu que
    haria falta si deslizara, el mu estatico medido por angulo critico (que es
    una cota superior para el dinamico), y la aceleracion que predice cada
    geometria rodando.

    Args:
        objeto: "tapa", "esponja" o "jabon".
        condicion: "4libros", "3libros" o "2libros". El angulo critico no sirve
            para este contraste porque ahi el cuerpo todavia no se mueve.
    """
    g = _global()
    objeto, condicion = objeto.strip().lower(), condicion.strip().lower()
    match = [
        c for c in g["condiciones"] if c["objeto"] == objeto and c["condicion"] == condicion
    ]
    if not match:
        return {
            "error": f"no hay datos para {objeto} / {condicion}",
            "combinaciones": [f"{c['objeto']} / {c['condicion']}" for c in g["condiciones"]],
        }
    c = match[0]
    if c["aceleracion_media"] is None:
        return {
            "error": "esa condicion no tiene corridas confiables, no se puede contrastar",
            "n_videos": c["n_videos"],
            "descartadas": c["archivos_descartados"],
        }
    if "angulo_grados" not in c:
        return {"error": "el angulo critico no sirve para contrastar hipotesis de movimiento"}

    G = 9.81
    theta = math.radians(c["angulo_grados"][0])
    a = c["aceleracion_media"]
    sigma_a = c["error_de_la_media"]
    a_libre = G * math.sin(theta)

    rodando = {}
    for nombre, inercia in (
        ("aro o cilindro hueco (I = mR^2)", 1.0),
        ("disco o cilindro macizo (I = mR^2/2)", 0.5),
        ("esfera maciza (I = 2mR^2/5)", 0.4),
    ):
        pred = a_libre / (1.0 + inercia)
        rodando[nombre] = {
            "aceleracion_predicha_m_s2": round(pred, 4),
            "sigmas_de_diferencia": round(abs(a - pred) / sigma_a, 2) if sigma_a else None,
        }

    mu_d = _vu(c["mu_d_si_desliza"])
    mu_e = g["objetos"].get(objeto, {}).get("mu_estatico")
    contradiccion = None
    if mu_d and mu_e and mu_d["valor"] > mu_e[0]:
        contradiccion = (
            f"mu_d = {mu_d['valor']:.3f} saldria MAYOR que mu_e = {mu_e[0]:.3f}. "
            f"El rozamiento dinamico no puede superar al estatico, asi que la "
            f"hipotesis de deslizamiento puro no se sostiene para este caso."
        )

    return {
        "objeto": objeto,
        "condicion": condicion,
        "angulo_grados": _vu(c["angulo_grados"]),
        "aceleracion_medida_m_s2": _vu([a, sigma_a]),
        "n_corridas": c["n_confiables"],
        "hipotesis_desliza": {
            "a_sin_rozamiento_m_s2": round(a_libre, 4),
            "mu_dinamico_necesario": mu_d,
            "mu_estatico_medido": _vu(mu_e),
            "contradiccion": contradiccion,
        },
        "hipotesis_rueda": {
            "factor_1_mas_I_sobre_mR2_medido": _vu(c.get("factor_inercia_si_rueda")),
            "predicciones": rodando,
            "nota": (
                "Si el cuerpo rueda sin deslizar, el factor medido tiene que dar "
                "el mismo numero en los tres angulos, y entre 1.4 y 2.0 para un "
                "cilindro. Conviene pedir resumen_por_condicion y comparar."
            ),
        },
    }


def inventario_videos() -> dict:
    """Caracteristicas tecnicas de los 61 videos: resolucion, fps real, duracion.

    Sirve para preguntas sobre la filmacion, no sobre la fisica. Incluye la
    verificacion de framerate: los 120 fps declarados por el Grupo 3 se
    comprobaron leyendo el timestamp de cada cuadro.
    """
    filas = _leer_json(DATOS / "inventario.json")
    resoluciones = sorted({f"{f['ancho']}x{f['alto']}" for f in filas})
    fps_medidos = [f["fps_medido"] for f in filas if f.get("fps_medido")]
    duraciones = sorted(f["duracion_s"] for f in filas)
    vfr = [f["archivo"] for f in filas if f.get("es_vfr")]

    combos: dict[str, int] = {}
    for f in filas:
        combos[f"{f['objeto']} / {f['condicion']}"] = (
            combos.get(f"{f['objeto']} / {f['condicion']}", 0) + 1
        )

    return {
        "n_videos": len(filas),
        "resoluciones": resoluciones,
        "fps_declarado_por_contenedor": sorted({f["fps_declarado"] for f in filas}),
        "fps_medido_de_timestamps": {
            "min": min(fps_medidos) if fps_medidos else None,
            "max": max(fps_medidos) if fps_medidos else None,
        },
        "videos_con_framerate_variable": len(vfr),
        "nota_fps": (
            "Cero videos con framerate variable: los 120 fps son reales y se "
            "puede usar t = cuadro/120 sin corregir."
        ),
        "duracion_s": {
            "min": duraciones[0],
            "mediana": duraciones[len(duraciones) // 2],
            "max": duraciones[-1],
        },
        "repeticiones_por_condicion": combos,
    }


def leer_documento(nombre: str) -> dict:
    """Devuelve el texto de un documento del proyecto.

    Usar cuando la pregunta es sobre decisiones de diseno, limitaciones
    documentadas o la consigna, no sobre numeros.

    Args:
        nombre: uno de "arquitectura", "hallazgos", "readme", "datos_laboratorio".
    """
    nombre = nombre.strip().lower()
    if nombre not in DOCUMENTOS:
        return {"error": f"documento desconocido '{nombre}'", "validos": list(DOCUMENTOS)}
    ruta = DOCUMENTOS[nombre]
    if not ruta.is_file():
        return {"error": f"el archivo {ruta.name} no existe en el repo"}
    texto = ruta.read_text(encoding="utf-8")
    return {"documento": nombre, "archivo": ruta.name, "caracteres": len(texto), "texto": texto}


# Orden estable: el esquema de herramientas forma parte del prefijo cacheado,
# asi que no debe cambiar entre llamadas.
HERRAMIENTAS = [
    estado_del_proyecto,
    resumen_por_condicion,
    datos_del_laboratorio,
    listar_corridas,
    detalle_corrida,
    comparar_hipotesis,
    inventario_videos,
    leer_documento,
]
