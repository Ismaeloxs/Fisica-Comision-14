# Cómo usar el agente

Guía práctica: qué hace cada pieza, qué hay que configurar y qué comandos correr.

- Para **por qué** está diseñado así → [arquitectura.md](arquitectura.md)
- Para **qué dio hasta ahora** y qué sigue pendiente → [hallazgos.md](hallazgos.md)

---

## 1. Qué hace el agente

Somos el Grupo 14 (Línea III) del movimiento 1, fuerza de rozamiento. El Grupo 3
filma el experimento y lo mide a mano con Tracker; nosotros hacemos lo mismo
automáticamente a partir del video, y nos comparamos contra su medición.

La entrada es un video de un objeto deslizando por un plano inclinado. La salida
es la aceleración de esa corrida con su incerteza, el diagnóstico de si el
cuerpo desliza o rueda, las fuerzas del diagrama de cuerpo libre y el CSV con
la serie temporal completa (`t, x, y, s, v, a`, crudas y filtradas).

```
   datos/referencia/laboratorio.json          datos/agente/angulos.json
    (mediciones manuales Grupo 3)             (ángulos medidos por el agente)
                   │                                       │
              referencia.py                        angulos_agente.py
         ángulos θ ± σ, μ_e, masas           θ por video + θ_c de los 3 objetos
                   └───────────────────┬───────────────────┘
                                       ▼
 video.mp4 ──► calibracion.py ──► tracking.py ──► cinematica.py ──► fisica.py
                     │                 │               │                │
               papel rosa         centroide del    ajuste de       ¿desliza
               → px/cm            objeto cuadro    s(t)=s0+v0t     o rueda?
               → eje de la        a cuadro, y      +at²/2          → μ_d, DCL
                 rampa            ventana útil     → a ± σ         → CSV serie
```

Cada módulo hace una cosa y se puede leer solo:

| Archivo | Qué hace |
|---|---|
| [`inventario.py`](src/agente/inventario.py) | Sondea los 61 videos: resolución, fps y si el framerate es real o variable (VFR). Se corre una vez. |
| [`referencia.py`](src/agente/referencia.py) | Lee las mediciones a mano del Grupo 3 (`laboratorio.json`) y deriva ángulos y μ estático, propagando incertezas. |
| [`angulo_critico.py`](src/agente/angulo_critico.py) | Analiza los videos de **ángulo crítico** (donde la rampa se levanta a mano): mide θ(t) cuadro a cuadro, detecta el arranque y compara contra el Grupo 3. También trae `--validar` para contrastar el ángulo en imagen contra la regla. |
| [`angulos_agente.py`](src/agente/angulos_agente.py) | Calcula **una sola vez** todos los ángulos medidos por el agente (2, 3 y 4 libros + ángulo crítico de los 3 objetos) y los guarda en `datos/agente/angulos.json` para no recalcularlos en cada corrida. |
| [`calibracion.py`](src/agente/calibracion.py) | Del papel rosa de 7,5 cm saca la escala px/cm y el eje de la rampa para proyectar la trayectoria. |
| [`tracking.py`](src/agente/tracking.py) | Sigue el objeto por color (tapa, esponja y jabón), proyecta la trayectoria sobre el eje y recorta la ventana donde realmente desliza. |
| [`cinematica.py`](src/agente/cinematica.py) | Ajusta s(t) por cuadrados mínimos (aceleración con error) y calcula v(t) y a(t) por diferencias finitas, crudas y filtradas (Savitzky-Golay). |
| [`fisica.py`](src/agente/fisica.py) | Compara la aceleración medida contra deslizamiento y contra rodadura, calcula el diagrama de cuerpo libre y dictamina. |
| [`medir.py`](src/agente/medir.py) | Orquesta todo lo anterior para una corrida y exporta el CSV de la serie temporal en `resultados/series/`. Es el motor: lo usan tanto la consola como la ventana. |
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
`scipy` y `uncertainties` (más `matplotlib` para los gráficos). El resto
(`torch`, `ultralytics`) viene de la prueba inicial con YOLO y hoy no lo usa
ningún módulo del agente.

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
que da exactamente los mismos números (y también guarda el CSV de cada corrida
en `resultados/series/`).

A la izquierda está la lista de videos, con filtros por **Objeto** y
**Condición**, más el selector **Ángulos** para elegir si la física usa los
ángulos medidos por el `agente` (`datos/agente/angulos.json`, por defecto) o
los del `laboratorio` (`datos/referencia/laboratorio.json`, Grupo 3).

**Medir corrida** (o doble click sobre el nombre) mide el seleccionado y tarda
unos 6 segundos. **Medir todo el grupo filtrado** mide todos los que quedaron en
la lista, uno por uno, mostrando el avance abajo.

| Pestaña | Qué muestra |
|---|---|
| **Resumen** | Los números en tarjetas — calibración, seguimiento, cinemática, física (indicando de dónde salieron θ y μ_e), diagrama de cuerpo libre — y el veredicto en un cartel de color con sus advertencias. |
| **Gráficos** | s(t) con el ajuste encima, los residuos contra la banda de ±σ, y v(t) y a(t) crudas contra filtradas. La comparación crudo-vs-filtrado que pide la consigna, hecha. |
| **Trayectoria** | Un cuadro del video con las detecciones dibujadas: en verde lo que entra al ajuste, en blanco lo descartado, y el eje sobre el que se proyecta s(t). Es la forma rápida de confirmar que el tracker siguió el objeto y no un reflejo o un libro. |
| **Lote** | Arranca vacía: se llena cuando apretás **Medir todo el grupo filtrado**, con una fila por repetición y, abajo, la dispersión entre ellas con su gráfico. Esa dispersión es el número honesto del experimento; el error del ajuste individual es entre tres y seis veces menor. Las corridas cuya ventana útil quedó demasiado corta (menos de 25 puntos o menos de 10 cm de recorrido) salen en amarillo. |
| **Texto** | El mismo informe que imprime la consola, para copiar y pegar. |

Un video que falla no corta nada: sale un cartel con el motivo, y dentro de un
lote queda como fila roja mientras el resto sigue.

### Ver los ángulos guardados del agente (o recalcularlos)

El archivo [`datos/agente/angulos.json`](datos/agente/angulos.json) ya viene
generado en el repo para que nadie tenga que esperar varios minutos. Para ver
lo guardado:

```bash
python src/agente/angulos_agente.py --ver
```

Solo si cambian los videos o el detector hace falta regenerarlo:

```bash
python src/agente/angulos_agente.py                 # recalcula libros + críticos
python src/agente/angulos_agente.py --solo-libros   # solo 2/3/4 libros (~1 min)
python src/agente/angulos_agente.py --solo-criticos # solo ángulos críticos (~5 min)
```

### Analizar los videos de ángulo crítico y validar la geometría

Los videos de `Angulo Critico` no pasan por `medir.py` (porque la rampa gira
durante toda la toma). Se analizan con su propio script, que guarda un `.csv`,
un `.png` por video y el `resumen.json` en `resultados/angulo_critico/`:

```bash
python src/agente/angulo_critico.py                 # todos los de ángulo crítico
python src/agente/angulo_critico.py --objeto jabon  # solo un objeto
python src/agente/angulo_critico.py --validar       # compara ángulo en imagen vs regla (2/3/4 libros)
```

### Ver los datos del laboratorio (Grupo 3)

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

### Medir una corrida desde consola

Este es el comando principal:

```bash
python src/agente/medir.py "Tapa 4Libros Video1.mp4"
```

Opciones útiles:

- `--angulos agente` *(por defecto)* o `--angulos laboratorio`: elige si la
  física usa los ángulos de `datos/agente/angulos.json` o los del Grupo 3.
- `--csv ruta.csv`: elige dónde guardar la serie temporal (por defecto se
  guarda automáticamente en `resultados/series/<Nombre_del_Video>.csv` con
  `frame, t_s, x_px, y_px, sigma_x_px, sigma_y_px, x_m, y_m, sigma_x_m, sigma_y_m, s_m, sigma_s_m, s_filtrada_m, v_cruda_m_s, v_filtrada_m_s, a_cruda_m_s2, a_filtrada_m_s2`).
- `--json salida.json`: además guarda el resumen numérico en JSON.

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

El **eje de la rampa** sale del papel rosa y sirve únicamente para proyectar la
trayectoria 2D a una coordenada `s(t)` a lo largo del plano. El ángulo que se
usa después en las ecuaciones de física se imprime en el bloque `FISICA` (sale
del canto de madera guardado en `datos/agente/angulos.json` o de la regla del
Grupo 3, según `--angulos`). El **control con rampa** contrasta la escala
contra los 42 cm de la tabla; es cota inferior porque los extremos quedan
tapados.

```
SEGUIMIENTO
  cobertura         = 100% (127/127)
  sigma de posicion = 1.20 px = 0.44 mm (medido con el cuerpo quieto)
  ventana util      = cuadros 45-102 (58 puntos, 0.47 s)
  fin de la ventana = deja la rampa en el indice 105 (umbral 12.0 px)
  recorrido         = 30.5 cm
```

**Cobertura** es en cuántos cuadros se encontró el objeto. Si baja de 50 % el
comando aborta. La **ventana útil** recorta dos tramos que no son deslizamiento:
el principio (la mano sostiene el cuerpo) y el final (el cuerpo deja la rampa y
cae a la mesa).

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
amplifica el ruido y a 120 fps la derivada segunda cruda queda dominada por él.
La incerteza tiene dos partes que se informan por separado: el error del ajuste
y el error de la escala px/cm. La línea de **diferencias finitas** está para
compararla contra el ajuste, como pide la consigna.

> **El χ² reducido alto es un problema conocido, no un detalle.** Significa que
> el σ de posición medido con el cuerpo quieto subestima el ruido real en
> movimiento (desenfoque y cambio de forma de la mancha). El error de `a` igual
> ya sale escalado con los residuos del ajuste.

```
FISICA
  angulo del plano de: agente: canto de la rampa en este video (sigma = dispersion entre 15 videos de 4libros)
  mu estatico de:      agente: angulo critico, deslizamiento (> 1 cm/s), promedio de 5 videos (sigma = dispersion / raiz de n)
  angulo del plano     = 33.23 +/- 0.42 grados
  a medida             = 2.237+/-0.062 m/s^2
  ...
  HIPOTESIS A - desliza:
    mu_dinamico        = 0.3825+/-0.0119
    mu_estatico (ref.) = 0.2306+/-0.0050   (debe cumplirse mu_d < mu_e)
  ...
  VEREDICTO: deslizamiento descartado
```

Acá el agente informa explícitamente qué fuente de ángulos se usó, confronta la
aceleración medida contra deslizamiento (`a = g(senθ − μcosθ)`) y rodadura sin
deslizar (`a = g senθ/(1 + I/mR²)`), y calcula las fuerzas del diagrama de
cuerpo libre (`P, N, P senθ, f`, más el control `f/N`). Al final imprime la ruta
del CSV exportado (`-> CSV serie temporal: resultados/series/...csv`).

---

## 6. Qué se puede ajustar y dónde

| Qué | Dónde | Nota |
|---|---|---|
| Medidas manuales del laboratorio (alturas, masas, hipotenusa, σ) | [`datos/referencia/laboratorio.json`](datos/referencia/laboratorio.json) | Único lugar donde se tocan. Los ángulos del Grupo 3 se **derivan**, no se escriben a mano. |
| Ángulos medidos por el agente (caché) | [`datos/agente/angulos.json`](datos/agente/angulos.json) | Generado por `angulos_agente.py`. No editar a mano: volver a correr el script. |
| Fuente de ángulos por defecto (`agente` o `laboratorio`) | `FUENTE_ANGULOS_DEFAULT` en [`medir.py`](src/agente/medir.py) | También se puede cambiar en cada corrida con `--angulos` o desde el desplegable de `visor.py`. |
| Rangos HSV de cada objeto | `PERFILES` en [`tracking.py`](src/agente/tracking.py) y `OBJETOS_HSV` en [`angulo_critico.py`](src/agente/angulo_critico.py) | Incluye el rango calibrado del jabón `(14, 95, 105) → (21, 157, 246)`, que separa el jabón de la pared y del canto de madera. |
| Color y tamaño del papel de calibración | `HSV_ROSA_*`, `LARGO_PAPEL_CM` en [`calibracion.py`](src/agente/calibracion.py) | |
| Carpetas donde se buscan los videos | `CARPETAS_POSIBLES` en [`inventario.py`](src/agente/inventario.py) | Se usa la primera que exista. `--carpeta` la pisa. Ver §3. |
| fps | `FPS = 120.0` en [`medir.py`](src/agente/medir.py) y [`angulo_critico.py`](src/agente/angulo_critico.py) | Vale porque los 61 videos son CFR a 120 fps. |
| Gravedad | `G = 9.81` en [`fisica.py`](src/agente/fisica.py) | |

---

## 7. Errores que vas a ver y qué significan

| Mensaje | Qué pasó |
|---|---|
| `No existe la carpeta: ...` | No hay videos en ninguna de las carpetas conocidas, o el `--carpeta` que pasaste apunta a donde no hay. Ver §3. |
| `No existe: <ruta>` | El nombre del video está mal escrito. Las mayúsculas y los espacios cuentan. |
| `Nombre no interpretable: ...` | El archivo no sigue la convención de nombres. Ver §3. |
| `No se encontro el papel rosa de calibracion` | Pasa si pasás un video de **ángulo crítico** por `medir.py`: en esos videos la rampa arranca casi horizontal y el papel queda más abajo del corte superior. Esos videos se miden con `angulo_critico.py` / `angulos_agente.py`. |
| `Cobertura del tracker demasiado baja (NN%)` | El perfil de color no separó el objeto en al menos la mitad de los cuadros. Con el rango nuevo del jabón ya no ocurre en ninguno de los 45 videos con libros. |

En la ventana estos mismos errores salen en un cartel y no cortan la
aplicación; dentro de un lote quedan como fila roja y el resto de las
repeticiones sigue midiéndose.

---

## 8. Estado actual

Lo que anda de punta a punta:

- **Seguimiento de los 3 objetos** (tapa, esponja y jabón): el nuevo perfil HSV del jabón recuperó los 15 videos con libros (antes fallaban todos los de 3 libros y 3 de 5 en 4 libros).
- **Ángulos medidos por el agente** (`datos/agente/angulos.json`): los 45 videos con libros y los 16 videos de ángulo crítico (tapa, esponja y jabón) medidos y cacheados, con selector `agente` / `laboratorio` en consola y en `visor.py`.
- **Exportación automática de series temporales** en `resultados/series/*.csv` con `(t, x, y, σx, σy, s, v, a)` crudas y filtradas.
- **Inventario:** los 61 videos sondeados, 120 fps confirmados como reales.

Lo que todavía queda pendiente:

- **2 libros:** los objetos casi no aceleran (sobre todo esponja y jabón, con $a \approx 0,01\text{--}0,03\text{ m/s}^2$) y la dispersión relativa es alta.
- **Regresión global de μ dinámico** sobre los ángulos y comparación formal contra los exports de Tracker del Grupo 3.
- **Videos en superficie horizontal** (pedidos por la consigna; todavía no los filmaron).

El detalle completo con los números actualizados está en [hallazgos.md](hallazgos.md).
