# Cómo usar el agente

Guía práctica: qué hace cada pieza, qué hay que configurar y qué comandos correr.

- Para **por qué** está diseñado así → [arquitectura.md](arquitectura.md)
- Para **qué dio hasta ahora** y qué está roto → [hallazgos.md](hallazgos.md)

---

## 1. Qué hace el agente

Somos el Grupo 14 (Línea III) del movimiento 1, fuerza de rozamiento. El Grupo 3
filma el experimento y lo mide a mano con Tracker; nosotros hacemos lo mismo
automáticamente a partir del video, y nos comparamos contra su medición.

La entrada es un video de un objeto deslizando por un plano inclinado. La salida
es la aceleración de esa corrida con su incerteza, más el diagnóstico de si el
cuerpo desliza o rueda.

```
                       datos/referencia/laboratorio.json
                        (lo que midió a mano el Grupo 3)
                                      │
                                 referencia.py
                           ángulos θ ± σ,  μ_e = tan(θ_c)
                                      │
                                      ▼
 video.mp4 ──► calibracion.py ──► tracking.py ──► cinematica.py ──► fisica.py
                     │                 │               │                │
               papel rosa         centroide del    ajuste de       ¿desliza
               → px/cm            objeto cuadro    s(t)=s0+v0t     o rueda?
               → eje de la        a cuadro, y      +at²/2
                 rampa            ventana útil     → a ± σ
```

Cada módulo hace una cosa y se puede leer solo:

| Archivo | Qué hace |
|---|---|
| [`inventario.py`](src/agente/inventario.py) | Sondea los 61 videos: resolución, fps y si el framerate es real o variable (VFR). Se corre una vez. |
| [`referencia.py`](src/agente/referencia.py) | Lee las mediciones a mano del Grupo 3 y deriva ángulos y μ estático, propagando incertezas. |
| [`calibracion.py`](src/agente/calibracion.py) | Del papel rosa de 7,5 cm saca la escala px/cm y el eje de la rampa. |
| [`tracking.py`](src/agente/tracking.py) | Sigue el objeto por color, proyecta la trayectoria sobre el eje y recorta la ventana donde realmente desliza. |
| [`cinematica.py`](src/agente/cinematica.py) | Ajusta s(t) por cuadrados mínimos y saca la aceleración con el error del ajuste. |
| [`fisica.py`](src/agente/fisica.py) | Compara la aceleración medida contra deslizamiento y contra rodadura, y dictamina. |
| [`medir.py`](src/agente/medir.py) | Orquesta todo lo anterior para una corrida. Es el motor: lo usan tanto la consola como la ventana. |
| [`visor.py`](src/agente/visor.py) | Ventana tkinter. No calcula nada propio: llama a `medir.py` y se ocupa solo de mostrar. |

**Regla del proyecto:** ningún número viaja sin incerteza. Todo lo que calcula
el núcleo sale como `ufloat` (valor ± σ) del paquete `uncertainties`.

---

## 2. Preparar el entorno

Una sola vez, parado en la carpeta del repo:

```bash
python -m venv .venv
```

Activar el entorno (**hay que hacerlo cada vez que abrís una consola nueva**):

```bash
.venv\Scripts\activate
```

Instalar las dependencias:

```bash
pip install -r requirements.txt
```

De todo lo que instala, el agente usa cuatro cosas: `opencv-python`, `numpy`,
`scipy` y `uncertainties`. El resto (`torch`, `ultralytics`) viene de la prueba
inicial con YOLO y hoy no lo usa ningún módulo del agente.

---

## 3. Dónde van los videos

Los videos **no están en el repo** — pesan cerca de 1 GB y `.gitignore` los
excluye. Cada uno los tiene localmente, así que lo único que el agente necesita
saber es dónde los pusiste.

Los busca solo, en este orden, y se queda con la primera carpeta que exista:

1. `videos/Videos Proyecto mp4 120fps/` ← **la convención del grupo**
2. `src/Fuerza de Rozamiento-videos/Fuerza de Rozamiento/Videos Proyecto mp4 120fps/`

Si los descomprimís en `videos/`, no hay nada que configurar: los comandos de
la sección siguiente andan tal cual están escritos. La segunda ubicación está
sostenida para no romperle el repo a quien ya los tenga ahí.

Solo si los tenés en otro lado hace falta `--carpeta`, que pisa la búsqueda.
`RUTA/A/TUS/VIDEOS` es un marcador: reemplazalo por tu ruta real, porque tal
cual está escrito el comando corta con `No existe la carpeta`.

```bash
python src/agente/inventario.py --carpeta "RUTA/A/TUS/VIDEOS"
```

### Los nombres de archivo importan

El agente deduce objeto, ángulo y repetición del nombre. El formato es:

```
<Objeto> <N>Libros Video<n>.mp4        p. ej.  Tapa 4Libros Video1.mp4
<Objeto> Angulo Critico Video<n>.mp4   p. ej.  Jabon Angulo Critico Video2.mp4
```

con `<Objeto>` ∈ `Tapa`, `Esponja`, `Jabon` (sin tilde). Un archivo que no
matchee queda afuera del inventario y `medir.py` lo rechaza con
`Nombre no interpretable`. Usá la carpeta `Videos Proyecto mp4 120fps`, que ya
está nombrada así; las carpetas `Objeto 1. Ángulo 1` y compañía tienen los
mismos videos con los nombres originales del celular (`IMG_4060.mov`) y el
agente no los entiende.

---

## 4. Los comandos

### La ventana (lo más cómodo)

```bash
python src/agente/visor.py
```

No reemplaza nada: por dentro llama a las mismas funciones que la consola, así
que da exactamente los mismos números.

A la izquierda está la lista de videos, con filtros por objeto y por condición.
**Medir corrida** (o doble click sobre el nombre) mide el seleccionado y tarda
unos 6 segundos. **Medir todo el grupo filtrado** mide todos los que quedaron en
la lista, uno por uno, mostrando el avance abajo.

| Pestaña | Qué muestra |
|---|---|
| **Resumen** | Los números en cuatro tarjetas — calibración, seguimiento, cinemática, física — y el veredicto en un cartel de color con sus advertencias. |
| **Gráficos** | s(t) con el ajuste encima, los residuos contra la banda de ±σ, y v(t) y a(t) crudas contra filtradas. La comparación crudo-vs-filtrado que pide la consigna, hecha. |
| **Trayectoria** | Un cuadro del video con las detecciones dibujadas: en verde lo que entra al ajuste, en blanco lo descartado, y el eje sobre el que se proyecta s(t). Es la forma rápida de confirmar que el tracker siguió el objeto y no un reflejo o un libro. |
| **Lote** | Una fila por repetición y, abajo, la dispersión entre ellas con su gráfico. Esa dispersión es el número honesto del experimento; el error del ajuste individual es entre tres y seis veces menor. |
| **Texto** | El mismo informe que imprime la consola, para copiar y pegar. |

Un video que falla no corta nada: sale un cartel con el motivo, y dentro de un
lote queda como fila roja mientras el resto sigue.

### Ver los datos del laboratorio

No toca videos, sirve para chequear que el entorno quedó bien:

```bash
python src/agente/referencia.py
```

```
ANGULOS DEL PLANO
  angulo_1 (4 libros apilados): 34.353 +/- 0.190 grados
  angulo_2 (3 libros apilados): 24.624 +/- 0.163 grados
  angulo_3 (2 libros apilados): 20.196 +/- 0.154 grados

COEFICIENTE ESTATICO (del angulo critico)
  tapa     : theta_c = 16.32 +/- 0.15 grados -> mu_e = 0.2927+/-0.0028
  esponja  : theta_c = 14.20 +/- 0.14 grados -> mu_e = 0.2530+/-0.0027
  jabon    : theta_c = 17.89 +/- 0.15 grados -> mu_e = 0.3227+/-0.0029
```

### Inventariar los videos

```bash
python src/agente/inventario.py
```

Escribe `datos/inventario.csv` y `datos/inventario.json`. Lee el timestamp de
cada cuadro de los 61 videos para verificar que el framerate sea real: tarda
alrededor de un minuto. Con `--rapido` solo lee los metadatos del contenedor y
termina en segundos, pero **saltea justamente la verificación que importa**.

Ya está corrido y dio: 61 videos, todos 1920×1080 a 120 fps, y los 120 fps son
reales — ninguno es VFR. Se puede usar `t = cuadro/120` sin corrección.

### Medir una corrida

Este es el comando principal:

```bash
python src/agente/medir.py "Tapa 4Libros Video1.mp4"
```

Con `--json salida.json` además guarda el resultado en un archivo en vez de solo
imprimirlo.

---

## 5. Cómo leer la salida de `medir.py`

Esta es la salida real de la corrida de arriba, por bloques:

```
CALIBRACION
  eje de la rampa   = 31.46 grados
  papel rosa        = 203.0 px para 7.5 cm
  escala            = 27.07+/-0.54 px/cm
  control con rampa = 21.98 px/cm (discrepancia +23.2%, cota inferior)
```

El **eje de la rampa** sale del papel rosa, no de detectar rectas en la imagen
(el borde de la mesa aparece a ~13° y contaminaba el promedio). Da 31,46° contra
los 34,35° medidos con regla. La explicación más probable es la perspectiva —
la cámara no está perfectamente perpendicular al plano — pero no está
cuantificada todavía, así que el ángulo que se usa para la física es el de la
regla, no el de la imagen. El **control con rampa** contrasta la
escala contra los 42 cm de la tabla; es solo cota inferior porque los extremos
de la tabla quedan tapados. Ese +23 % todavía no está explicado del todo
(ver [hallazgos.md §4](hallazgos.md)).

```
SEGUIMIENTO
  cobertura         = 100% (127/127)
  sigma de posicion = 1.20 px = 0.44 mm (medido con el cuerpo quieto)
  ventana util      = cuadros 45-102 (58 puntos, 0.47 s)
  fin de la ventana = deja la rampa en el indice 105 (umbral 12.0 px)
  recorrido         = 30.5 cm
```

**Cobertura** es en cuántos cuadros se encontró el objeto. Si baja de 50 % el
comando aborta: el perfil de color no sirve para ese video. La **ventana útil**
recorta dos tramos que no son deslizamiento: el principio, donde la mano todavía
sostiene el cuerpo, y el final, donde el cuerpo ya se cayó de la rampa a la mesa.
El corte del final se detecta por la distancia perpendicular al eje, que es
constante mientras el cuerpo está apoyado y se dispara cuando se despega.

```
CINEMATICA
  a (ajuste)        = 2.237+/-0.062 m/s^2
     del ajuste 0.043 + de la escala 0.045
  v inicial         = 0.120+/-0.011 m/s
  residuo RMS       = 2.77 mm   max 7.81 mm
  chi2 reducido     = 41.23
  a por diferencias = 2.362 m/s^2 (mediana, filtrada)
```

La aceleración sale del **ajuste cuadrático**, no de derivar dos veces: derivar
amplifica el ruido y a 120 fps la derivada segunda queda dominada por él. La
incerteza tiene dos partes que se informan por separado: el error del ajuste y
el error de la escala px/cm. La línea de **diferencias finitas** está para
compararla contra el ajuste, como pide la consigna.

> **El χ² reducido de 41 es un problema conocido, no un detalle.** Significa que
> el σ de posición está subestimado unas 6 veces: se mide con el cuerpo quieto,
> pero en movimiento el desenfoque corre el centroide. Está anotado como
> pendiente en [hallazgos.md §4](hallazgos.md).

```
FISICA
  HIPOTESIS A - desliza:
    mu_dinamico        = 0.4073+/-0.0087
    mu_estatico (ref.) = 0.2927+/-0.0028   (debe cumplirse mu_d < mu_e)
  ...
  VEREDICTO: deslizamiento descartado
```

Acá el agente confronta la aceleración medida contra las dos hipótesis que
predicen cosas distintas: deslizar (`a = g(senθ − μcosθ)`) y rodar sin deslizar
(`a = g senθ/(1 + I/mR²)`). El criterio no es a ojo: compara a cuántos σ queda
cada predicción, y si el μ dinámico sale **mayor** que el μ estático medido por
ángulo crítico, la hipótesis de deslizamiento es insostenible — el rozamiento
dinámico no puede superar al estático.

Para la tapa pasa exactamente eso, y es el hallazgo central hasta ahora:
probablemente **rueda**, no desliza. Está desarrollado en
[hallazgos.md §3](hallazgos.md).

---

## 6. Qué se puede ajustar y dónde

| Qué | Dónde | Nota |
|---|---|---|
| Medidas del laboratorio (alturas, masas, hipotenusa, σ) | [`datos/referencia/laboratorio.json`](datos/referencia/laboratorio.json) | Único lugar donde se tocan. Los ángulos se **derivan**, no se escriben a mano. |
| Rangos HSV de cada objeto | `PERFILES` en [`tracking.py`](src/agente/tracking.py) | Los umbrales salieron de muestrear el objeto en el cuadro 0, no son arbitrarios. |
| Color y tamaño del papel de calibración | `HSV_ROSA_*`, `LARGO_PAPEL_CM` en [`calibracion.py`](src/agente/calibracion.py) | |
| Carpetas donde se buscan los videos | `CARPETAS_POSIBLES` en [`inventario.py`](src/agente/inventario.py) | Se usa la primera que exista. `--carpeta` la pisa. Ver §3. |
| fps | `FPS = 120.0` en [`medir.py`](src/agente/medir.py) | **Está fijo en el código**, no lo toma del inventario. Vale porque los 61 videos son CFR a 120 fps, pero si entra un video de otra cámara hay que cambiarlo acá. |
| Gravedad | `G = 9.81` en [`fisica.py`](src/agente/fisica.py) | |

---

## 7. Errores que vas a ver y qué significan

| Mensaje | Qué pasó |
|---|---|
| `No existe la carpeta: ...` | No hay videos en ninguna de las carpetas conocidas, o el `--carpeta` que pasaste apunta a donde no hay. Ver §3. |
| `No existe: <ruta>` | El nombre del video está mal escrito. Las mayúsculas y los espacios cuentan. |
| `Nombre no interpretable: ...` | El archivo no sigue la convención de nombres. Ver §3. |
| `No se encontro el papel rosa de calibracion` | Pasa con **todos los videos de ángulo crítico**: la rampa se mueve durante la toma y el papel queda fuera de donde el detector lo busca. Esos videos todavía no se pueden medir con este pipeline. |
| `Cobertura del tracker demasiado baja (NN%)` | El perfil de color no separa el objeto del fondo. Es el caso del jabón: crema pálido sobre pared blanca. Ver [hallazgos.md §4](hallazgos.md). |

En la ventana estos mismos errores salen en un cartel y no cortan la
aplicación; dentro de un lote quedan como fila roja y el resto de las
repeticiones sigue midiéndose.

---

## 8. Estado actual

Lo que anda, con una corrida verificada punta a punta:

- Tapa y esponja en 4 y 3 libros: miden bien y de forma repetible.
- Ángulos, μ estático e incertezas: completos y verificados contra las cuentas
  manuscritas del Grupo 3.
- Inventario: los 61 videos sondeados, 120 fps confirmados como reales.

Lo que todavía no:

- **El jabón.** El tracker por color no lo agarra.
- **Los videos de ángulo crítico.** Fallan en calibración.
- **2 libros.** El objeto casi no acelera y la dispersión entre repeticiones
  llega al 62 %.
- **μ dinámico por regresión**, que es el entregable central. Está bloqueado
  hasta resolver si la tapa rueda o desliza.

El detalle de cada punto, con números, está en [hallazgos.md](hallazgos.md).
