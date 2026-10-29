# Arquitectura del agente — Fuerza de rozamiento (Grupo 14)

## 1. Qué tenemos que entregar

Somos el **agente** del movimiento 1 (fuerza de rozamiento). El Grupo 3 monta el
experimento, filma y mide a mano con Tracker. Nosotros construimos el programa que
hace lo mismo automáticamente, y **nos comparamos contra su medición**: sus datos son
el patrón de referencia, no una validación opcional.

Salidas obligatorias según la consigna:

1. Tabla `(t, x, y, σx, σy)` por corrida.
2. `v(t)` y `a(t)`, crudas y filtradas, comparadas entre sí.
3. Coeficiente de rozamiento dinámico **μ por regresión sobre varios ángulos** (un μ
   de una sola medición no cuenta).
4. Comparación de μ entre materiales.
5. Diagrama de cuerpo libre para plano horizontal y plano inclinado.
6. Chequeo físico: ¿el cuerpo desliza o rueda?
7. Todo número con unidad e incerteza propagada.
8. Sección de limitaciones.

## 2. Principio rector

> **El núcleo que produce números es determinista. El LLM nunca calcula.**

Dos razones, ambas de la consigna:

- Todo número necesita una incerteza **propagable**. Un número que sale de un modelo
  de lenguaje no tiene una fuente de error que puedas rastrear.
- "Lo probamos y anduvo bien" no es un resultado. Correr el pipeline dos veces sobre
  el mismo video tiene que dar exactamente lo mismo.

El LLM entra en cuatro lugares acotados, ninguno en el camino del número:

| Rol | Qué hace | Por qué no rompe el principio |
|---|---|---|
| **Bootstrap** | Mira el frame 0 y propone: dónde está el bloque, dónde la regla, ángulo aproximado | El humano confirma; la medición la hace OpenCV |
| **Triage** | Revisa 3 frames por corrida y marca "movido / reflejo / sale de cuadro" | Solo descarta corridas, no mide |
| **Preguntas** | Responde en lenguaje natural **llamando funciones Python** | Los números salen de las funciones, no del modelo |
| **Redacción** | Arma el borrador del informe desde `resultados/` | Texto, no números |

## 3. Etapas

Cada etapa lee de disco y escribe a disco. Esto no es ceremonia: es lo que permite
re-correr el análisis sin volver a trackear (y trackear es lo lento), comparar crudo
vs filtrado, y que cinco personas trabajen en etapas distintas sin pisarse.

```
videos/corrida_01.mp4
       │
       ├─[1] calibrar ──────→ datos/calibracion/corrida_01.json   (px/m, fps real, θ)
       │
       └─[2] trackear ──────→ datos/crudo/corrida_01.csv          (t, x_px, y_px, σ)
                                     │
                [3] procesar ────────┴───→ datos/procesado/corrida_01.csv  (x_m, v, a + σ)
                                     │
                [4] ajustar ─────────┴───→ resultados/corrida_01.json      (a ± σ)
                                     │
   todas las corridas → [5] regresión ───→ resultados/global.json          (μ ± σ)
                                     │
                       [6] reportar ──────→ informe/ (gráficos + texto)
                                     │
                       [7] preguntar ─────→ CLI interactiva (capa LLM)
```

## 4. Estructura de carpetas

```
src/agente/
  __init__.py
  cli.py              # punto de entrada: agente calibrar|trackear|procesar|...
  calibracion.py      # [1] px/m, fps real, ángulo del plano
  tracking/
    base.py           # interfaz Tracker -> (frame, x_px, y_px, σx, σy, conf)
    aruco.py          #     implementación A
    color.py          #     implementación B
    csrt.py           #     implementación C
  senal.py            # [3] suavizado, derivadas, propagación
  ajuste.py           # [4][5] cuadrados mínimos, μ, incertezas
  fisica.py           # modelos: a(θ,μ), desliza-vs-rueda, cuerpo libre
  reporte.py          # [6] gráficos y tablas
  llm/
    base.py           #     interfaz del proveedor (ver §7)
    claude.py
    gemini.py
    herramientas.py   #     las funciones que el modelo puede llamar
datos/                # artefactos intermedios (en .gitignore salvo ejemplos)
resultados/
informe/
tests/
docs/
```

## 5. Contratos de datos

**Esto es lo más importante de todo el documento.** Si los contratos están bien, cada
uno puede escribir su etapa sin coordinarse. Si están mal, nada encaja.

### `datos/calibracion/corrida_NN.json`

```json
{
  "corrida": 1,
  "material": "madera",
  "superficie": "melamina",
  "px_por_m": 842.3,
  "sigma_px_por_m": 4.1,
  "metodo_espacial": "aruco_50mm",
  "fps_real": 59.94,
  "sigma_fps": 0.02,
  "metodo_temporal": "cronometro_en_cuadro",
  "angulo_rad": 0.2618,
  "sigma_angulo_rad": 0.0035,
  "metodo_angulo": "pose_aruco_plano"
}
```

### `datos/crudo/corrida_NN.csv`

```
frame,t_s,x_px,y_px,sigma_x_px,sigma_y_px,confianza
```

`t_s = frame / fps_real`. `sigma_*_px` sale de la repetibilidad medida del tracker
(§8), **no** de un número inventado. `confianza` permite descartar frames malos aguas
abajo sin perderlos.

### `datos/procesado/corrida_NN.csv`

```
t_s,sigma_t,x_m,sigma_x,y_m,sigma_y,x_filt,v,sigma_v,a,sigma_a
```

Se guardan **crudo y filtrado en el mismo archivo** — el paso 5 de la consigna pide
compararlos explícitamente.

### `resultados/corrida_NN.json`

```json
{
  "corrida": 1, "material": "madera", "angulo_rad": 0.2618,
  "aceleracion": {"valor": -2.41, "sigma": 0.08, "unidad": "m/s^2"},
  "metodo": "ajuste_cuadratico_x(t)",
  "chi2_reducido": 1.14, "n_puntos": 87,
  "ventana_analizada_s": [0.42, 1.88],
  "descartada": false, "motivo_descarte": null
}
```

### `resultados/global.json`

μ por material con su incerteza, los parámetros de la regresión, y el contraste contra
el Grupo 3.

## 6. Decisiones por módulo

### [1] Calibración

Tres cosas que se miden, no se suponen:

- **Espacial (px/m):** patrón de tamaño conocido **en el plano del movimiento**, no
  contra el fondo. Si usamos ArUco, sale del propio marcador.
- **Temporal (fps real):** `cv2.CAP_PROP_FPS` **miente**, y los celulares graban a
  framerate variable. Hay que verificarlo filmando un cronómetro o un LED. Si el video
  es VFR, hay que leer los timestamps por frame, no asumir `frame/fps`.
  *Este es el error más fácil de no notar y el que más daño hace.*
- **Ángulo del plano:** si el marcador está en el bloque, la pose de ArUco nos lo da
  por corrida. Si no, se mide a mano y se carga en el JSON.

### [2] Tracking

**`yolo11n.pt` es COCO: no tiene una clase "bloque de madera".** `model.track()` sobre
el bloque va a fallar o va a ser inestable. Opciones:

| | Método | Precisión | Esfuerzo | Nota |
|---|---|---|---|---|
| A | **ArUco** (`cv2.aruco`) | sub-pixel | bajo | Da además escala, ángulo **y rotación**. Requiere pegarle el marcador al bloque |
| B | Umbral HSV + centroide | ~1 px | bajo | Depende de iluminación controlada |
| C | `cv2.TrackerCSRT` + ROI | ~2 px | bajo | El análogo semiautomático a Tracker |
| D | YOLO fine-tuneado | caja, no sub-pixel | alto | Solo si A–C fallan |

**Propuesta: A como principal, C como control.** Correr los dos y comparar *es*
contenido del informe. Todos implementan la misma interfaz `base.Tracker`, así que
cambiar es una línea en la CLI.

Beneficio lateral de ArUco: como da la **orientación** del marcador, el chequeo
"¿desliza o rueda?" pasa de ser una suposición a una medición — si el ángulo del
marcador cambia monótonamente, está rodando.

### [3] Señal

Orden que pide la consigna: filtrar posición → derivar → filtrar velocidad → derivar →
filtrar aceleración. Savitzky-Golay como método principal (preserva los picos mejor
que la media móvil), con la ventana y el orden **como parámetros reportados**, no
hardcodeados. Guardar siempre la versión cruda al lado.

### [4][5] Ajuste y μ

Por corrida: ajuste cuadrático de `x(t)` → la aceleración sale del coeficiente, con su
error del ajuste. Es más estable que promediar la `a(t)` derivada dos veces.

Para μ, sobre plano inclinado:

```
a = g·(sen θ − μ·cos θ)
```

reordenando para que la regresión sea lineal:

```
g·sen θ − a  =  μ · (g·cos θ)
       y     =  μ ·      x          → recta por el origen, pendiente = μ
```

Cada corrida es un punto `(x, y)`. La pendiente de la regresión es μ, y el error de la
pendiente es σ_μ. **Esto es lo que la consigna pide cuando dice "regresión sobre varios
ángulos".** Un gráfico de esos puntos con la recta ajustada es probablemente la figura
central del informe.

En plano horizontal, `a = −μ·g` directo, promediado sobre corridas; sirve como control
independiente del valor obtenido por regresión.

## 7. La capa LLM

Un solo punto de contacto, detrás de una interfaz:

```python
# src/agente/llm/base.py
class ProveedorLLM(Protocol):
    def preguntar(self, pregunta: str, herramientas: list[Herramienta]) -> str: ...
```

Dos implementaciones (`claude.py`, `gemini.py`), elegibles por variable de entorno. El
resto del código no sabe cuál está activa.

**El modelo no recibe los CSV ni calcula nada.** Recibe la lista de funciones que puede
llamar:

```python
coeficiente_rozamiento(material)        -> {valor, sigma, n_corridas, metodo}
aceleracion_corrida(n)                  -> {valor, sigma, chi2_red}
listar_corridas(material=None)          -> [...]
comparar_con_laboratorio(magnitud)      -> {nuestro, grupo3, diferencia, sigmas}
serie_temporal(n, magnitud)             -> [...]
```

El modelo decide qué llamar y redacta la respuesta; los números salen de las funciones.
Ventaja concreta: toda respuesta es auditable — se puede loggear qué funciones llamó.

Esto nos deja probar los dos proveedores con el mismo set de preguntas y reportarlo.
Costo estimado de la capa: unos centavos por pregunta en cualquiera de los dos.

## 8. Incertezas

El riesgo acá es inventar los σ. Las tres fuentes se **miden**:

| Fuente | Cómo se mide |
|---|---|
| σ del centroide | Trackear N frames de un bloque **quieto** → la dispersión del resultado |
| σ de px/m | Repetir la calibración k veces / tamaño conocido del patrón |
| σ de t | Del fps real y su verificación; si el video es VFR, de los timestamps |

Propagación con el paquete `uncertainties` (la consigna lo nombra). Faltan en
`requirements.txt`: `uncertainties`, `lmfit`.

**Regla del proyecto:** ninguna función del núcleo devuelve un `float` pelado. Devuelve
valor + incerteza, o una estructura que la lleve. Esto va al `CLAUDE.md`.

## 9. Validación contra el Grupo 3

Es la métrica del proyecto, así que se automatiza como cualquier otra etapa:

1. Les pedimos su export de Tracker en el mismo formato `(t, x, y, σx, σy)`.
2. `comparar.py` alinea las series y reporta: RMS de la diferencia en posición,
   diferencia en `a` por corrida, diferencia en μ expresada **en cuántos σ**.
3. El criterio de acuerdo se fija **antes** de mirar los resultados. Propuesta:
   compatible si `|Δ| < 2σ_combinado`. Discutir.

## 10. Lo que el agente NO va a hacer

La consigna exige sección de limitaciones. Candidatos que ya sabemos:

- No corrige perspectiva si la cámara no está perpendicular (salvo que agreguemos
  homografía — ver decisión 4).
- No detecta si el bloque rebota o vibra; asume deslizamiento plano.
- No sirve si el bloque sale de cuadro o se ocluye.
- No mide la masa ni el ángulo sin que se los demos (salvo vía ArUco).
- Degrada con sombras duras, reflejos y fondo no uniforme.

## 11. Decisiones abiertas

Esto es lo que hay que debatir:

1. **¿ArUco o seguimos con detección natural?** ArUco es mucho más robusto pero obliga
   al Grupo 3 a pegarle un marcador al bloque. **Hay que preguntarles ya**, antes de que
   filmen — si filman sin marcador, la decisión está tomada por omisión.
2. **¿Cuántas corridas y cuántos ángulos?** La consigna dice 5–20 corridas. Para la
   regresión de μ hacen falta al menos 4–5 ángulos distintos. ¿Cuántos materiales?
3. **¿Quién hace qué?** Somos 5 y las etapas son independientes por diseño: calibración,
   tracking, señal+ajuste, capa LLM, informe+validación.
4. **¿Homografía sí o no?** Corrige perspectiva pero agrega complejidad y una fuente de
   error más. Propuesta: no, y exigir cámara perpendicular en el setup.
5. **¿Claude o Gemini?** Ver §7. Propuesta: la interfaz primero, decidir después.
6. **Criterio de acuerdo con el Grupo 3** (§9): ¿2σ?
7. **¿Interfaz?** CLI alcanza para el informe. Una UI web es lindo pero es alcance extra.

## 12. Fases

| Fase | Qué | Criterio de terminado |
|---|---|---|
| 0 | Hablar con el Grupo 3: marcador, formato, fps | Acuerdo escrito en este repo |
| 1 | `CLAUDE.md` + contratos de datos + esqueleto de módulos | `agente --help` corre |
| 2 | **Vertical slice**: un video → μ con incerteza | Un número defendible |
| 3 | Segundo tracker + comparación | Tabla de los dos métodos |
| 4 | Lote: todas las corridas, regresión, validación vs Grupo 3 | `global.json` completo |
| 5 | Capa LLM | Preguntas respondidas vía tool calling |
| 6 | Informe | Entregable |

La fase 2 es la que importa. Hasta que no exista **un** número con incerteza que se
pueda comparar contra el Grupo 3, todo lo demás es andamiaje.
