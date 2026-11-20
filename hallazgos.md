# Hallazgos del agente sobre los 61 videos (v2)

> Estado al 20/11/2026 (rama `angulo-critico`). Complementa [arquitectura.md](arquitectura.md) y [COMO_USARLO.md](COMO_USARLO.md).
> Todo lo de acá es reproducible con `python src/agente/angulos_agente.py --ver` y `python src/agente/medir.py "<video>.mp4"`.

## Resumen en una línea

Con el nuevo perfil HSV del jabón y los ángulos medidos directamente por el
agente (`datos/agente/angulos.json`), el pipeline mide **43 de los 45 videos con
libros y los 16 videos de ángulo crítico** de los tres objetos. El hallazgo
central de esta versión es que **el jabón da un $\mu_d \approx 0,38$ constante en
los tres ángulos cuando se usan los ángulos del agente**, y que la paradoja
generalizada de $\mu_d > \mu_e$ en los tres objetos se explica por sesgos
experimentales concretos (espesor de la tabla, altura de 4 libros y vibraciones
del montaje manual del ángulo crítico), no porque todos los cuerpos rueden.

---

## 1. Qué cambió respecto de la v1 (31/10/2026)

| Pieza | v1 | v2 (ahora) | Dónde |
|---|---|---|---|
| Seguimiento del **jabón** | ❌ Roto (0/5 en 3 libros, 3 aceleraciones negativas en 4 libros) | ✅ **15/15 videos con libros** (100 % cobertura en 2 y 3 libros; 6 % dispersión en 3 libros) | [`tracking.py`](src/agente/tracking.py) |
| Videos de **ángulo crítico** | ❌ Fallaban todos en calibración | ✅ **16/16 medidos** (tapa, esponja y jabón) | [`angulo_critico.py`](src/agente/angulo_critico.py) |
| **Ángulos del agente** cacheados | ❌ Solo se usaban los de la regla (Grupo 3) | ✅ Calculados una vez y guardados en JSON; selector `agente` / `laboratorio` en consola y visor | [`angulos_agente.py`](src/agente/angulos_agente.py), [`datos/agente/angulos.json`](datos/agente/angulos.json) |
| Exportación de tabla `(t, x, y, σ, s, v, a)` | ❌ Solo resumen JSON en consola | ✅ CSV automático por corrida en `resultados/series/` | [`medir.py`](src/agente/medir.py), [`visor.py`](src/agente/visor.py) |
| Interfaz gráfica (`visor.py`) | ❌ No existía en v1 | ✅ Con selector de fuente de ángulos, gráficos crudo vs. filtrado, overlay de trayectoria y lote | [`visor.py`](src/agente/visor.py) |

El cambio clave en el jabón vino de ajustar su rango HSV con el muestreo
compartido por el otro grupo (`[14, 95, 105] → [21, 157, 246]`): el rango
anterior (`H ≥ 18`, `S ≤ 120`) cortaba al jabón real (`H ≈ 15–19`, `S ≈ 128–164`)
y dejaba entrar la pared blanca (`S ≈ 30`).

---

## 2. Ángulos medidos por el agente vs. regla del Grupo 3

El agente mide el ángulo del canto de madera de la rampa (PCA) corregido por el
giro de cámara (bordes verticales del termo). Todo quedó cacheado en
[`datos/agente/angulos.json`](datos/agente/angulos.json):

### Plano inclinado fijo (45 videos, 15 por condición)

| Condición | Regla Grupo 3 (`asin(h/42)`) | Agente (imagen) | Diferencia |
|---|---:|---:|---:|
| **4 libros** | $34,35 \pm 0,19^\circ$ | $32,57 \pm 0,42^\circ$ | $-1,79^\circ$ |
| **3 libros** | $24,62 \pm 0,16^\circ$ | $23,72 \pm 0,20^\circ$ | $-0,91^\circ$ |
| **2 libros** | $20,20 \pm 0,15^\circ$ | $20,83 \pm 0,33^\circ$ | $+0,63^\circ$ |

*(Recta de contraste: $\theta_{\text{imagen}} = 0,842\,\theta_{\text{regla}} + 3,47^\circ$.)*

### Ángulo crítico ($\mu_e = \tan\theta_c$, 16 videos)

| Objeto | $\theta_c$ Grupo 3 | $\mu_e$ Grupo 3 | $\theta_c$ Agente | $\mu_e$ Agente | Criterio y videos |
|---|---:|---:|---:|---:|---|
| **Tapa** | $16,32 \pm 0,15^\circ$ | $0,2927 \pm 0,0028$ | $12,99 \pm 0,27^\circ$ | $0,2306 \pm 0,0050$ | 5/5, deslizamiento (`> 1 cm/s`) |
| **Esponja** | $14,20 \pm 0,14^\circ$ | $0,2530 \pm 0,0027$ | $12,61 \pm 0,33^\circ$ | $0,2236 \pm 0,0061$ | 5/5, corrimiento lento (`> 0,3 cm`) |
| **Jabón** | $17,89 \pm 0,15^\circ$ | $0,3227 \pm 0,0029$ | $12,87 \pm 0,54^\circ$ | $0,2285 \pm 0,0101$ | 6/6 (2 deslizamiento + 4 corrimiento lento) |

**Dos observaciones directas de los videos de ángulo crítico:**

1. **La esponja y parte del jabón no arrancan de golpe:** en los 5 videos de
   esponja y en 4 de los 6 de jabón el objeto nunca supera `1 cm/s`; se corre
   despacio (*creep* / *stick-slip*) mientras se levanta la tabla a pulso.
2. **La rampa en el video nunca llega al ángulo anotado con la regla:** en la
   tapa llega a $12,9\text{--}14,7^\circ$ (vs. $16,3^\circ$), en la esponja a
   $11,6\text{--}13,6^\circ$ (vs. $14,2^\circ$) y en el jabón a
   $11,5\text{--}15,2^\circ$ (vs. $17,9^\circ$). Al trazar manualmente la
   geometría sobre un cuadro se ve la causa principal: **la tabla tiene ~1 cm de
   espesor** y se midió la altura desde la mesa hasta la cara superior
   dividiendo por $42\text{ cm}$ sin descontar ese espesor. Restar ~1 cm a
   $h_c = 10,3\text{ cm}$ (esponja) lleva $14,2^\circ$ a **$12,8^\circ$**,
   coincidiendo con el agente ($12,6^\circ$).

---

## 3. Resultados dinámicos sobre los 45 videos con libros

Aceleración media y $\mu_d$ asumiendo deslizamiento puro, reportando la
**dispersión entre repeticiones** (el error honesto del experimento, no el error
del ajuste individual):

| Objeto | Condición | Medidos | Cortas\* | $a$ [m/s²] | Disp. $a$ | $\mu_d$ (áng. agente) | $\mu_d$ (áng. lab) |
|---|---|---:|---:|---:|---:|---:|---:|
| **Tapa** | 4 libros | 5/5 | 1 | $2,287 \pm 0,204$ | 9 % | $0,3657 \pm 0,0228$ | $0,4011 \pm 0,0252$ |
| **Tapa** | 3 libros | 5/5 | 0 | $1,280 \pm 0,127$ | 10 % | $0,2980 \pm 0,0143$ | $0,3149 \pm 0,0142$ |
| **Tapa** | 2 libros | 4/6 | 0 | $0,430 \pm 0,267$ | 62 % | $0,3342 \pm 0,0333$ | $0,3212 \pm 0,0291$ |
| **Esponja** | 4 libros | 5/5 | 0 | $1,111 \pm 0,234$ | 21 % | $0,5027 \pm 0,0230$ | $0,5464 \pm 0,0289$ |
| **Esponja** | 3 libros | 5/5 | 0 | $0,148 \pm 0,076$ | 51 % | $0,4224 \pm 0,0085$ | $0,4417 \pm 0,0085$ |
| **Esponja** | 2 libros | 4/4 | 0 | $-0,014 \pm 0,019$ | 143 % | $0,3852 \pm 0,0027$ | $0,3693 \pm 0,0021$ |
| **Jabón** | 4 libros | 5/5 | 3 | $1,909 \pm 0,459$ | 24 % | $0,4054 \pm 0,0539$ | $0,4478 \pm 0,0567$ |
| **Jabón** | 3 libros | 5/5 | 0 | $0,574 \pm 0,035$ | **6 %** | $0,3748 \pm 0,0092$ | $0,3940 \pm 0,0039$ |
| **Jabón** | 2 libros | 5/5 | 0 | $0,017 \pm 0,010$ | 58 % | $0,3764 \pm 0,0087$ | $0,3660 \pm 0,0011$ |

*\*Corridas con ventana útil corta (< 25 puntos o < 10 cm de recorrido), marcadas en amarillo en el visor.*

### Qué destaca de esta tabla

1. **El jabón cierra consistente en los tres ángulos cuando se usan los ángulos del agente:**
   - Con ángulos del agente: $\mu_d = 0,405 \pm 0,054$ (4 libros), **$0,375 \pm 0,009$** (3 libros), **$0,376 \pm 0,009$** (2 libros). Los tres son compatibles entre sí dentro de $1\,\sigma$.
   - Con ángulos del laboratorio: $\mu_d$ sube sistemáticamente con el ángulo ($0,366 \to 0,394 \to 0,448$), lo cual refleja el sesgo en las alturas anotadas (en especial el salto anómalo de $+6,2\text{ cm}$ en 4 libros).
2. **La esponja no acelera en 2 libros ($a \approx 0$) y apenas baja en 3 libros ($a = 0,15\text{ m/s}^2$):**
   Esto implica un coeficiente de rozamiento efectivo cercano a $\tan(21\text{--}24^\circ) \approx 0,38\text{--}0,44$ sobre la rampa firme.
3. **La tapa sigue dando un $\mu_d$ ligeramente más alto en 4 libros que en 3 libros**, aunque la brecha se achica al pasar de los ángulos de la regla ($0,401$ vs. $0,315$) a los del agente ($0,366$ vs. $0,298$).

---

## 4. Por qué da $\mu_d > \mu_e$ en los tres objetos (revisión de v1)

En la v1 se había concluido que la tapa no deslizaba porque $\mu_d > \mu_e$. Al
medir los tres objetos completos, **$\mu_d > \mu_e$ ocurre también en el jabón y
la esponja**, que claramente no ruedan. Además, para la tapa una rodadura pura
requeriría $a \ge g\sin\theta / 2$ ($2,77\text{ m/s}^2$ en 4 libros y
$2,04\text{ m/s}^2$ en 3 libros), que es *mayor* que la aceleración medida
($2,29$ y $1,28\text{ m/s}^2$).

Por lo tanto, el problema principal **no es rodadura pura**, sino una
combinación de factores experimentales medibles:

1. **El ensayo manual de ángulo crítico subestima $\mu_e$:** en los videos se ve
   que la rampa se levanta a pulso apoyada sobre una tablita y un frasco
   cilíndrico. Las microvibraciones de la mano destraban los cuerpos (en especial
   la esponja de 3 g) a $\sim 13^\circ$ ($\mu_e \approx 0,22\text{--}0,25$),
   mientras que sobre la pila rígida de libros a $20^\circ$ la esponja y el
   jabón casi ni arrancan ($\mu \approx 0,38\text{--}0,44$).
2. **El ángulo de 4 libros del Grupo 3 está sobreestimado:** el salto de alturas
   es $+3,0\text{ cm}$ de 2 a 3 libros pero $+6,2\text{ cm}$ de 3 a 4 libros
   (`15 + 8,7 = 23,7 cm`). El agente mide $32,57^\circ$ en vez de $34,35^\circ$.
   Usar el ángulo del agente baja $\mu_d$ entre $0,02$ y $0,04$ y hace que el
   jabón quede constante en los tres ángulos.
3. **Posible sobreestimación de la escala `px/cm` del papel rosa:** da
   $27\text{--}29\text{ px/cm}$ frente a $\sim 22\text{ px/cm}$ del control con
   la regla de $42\text{ cm}$ (cota inferior). Si la escala real fuera menor,
   todas las aceleraciones subirían y todos los $\mu_d$ bajarían.
4. **La incerteza asumida en $\mu_e$ de laboratorio ($\pm 0,003$) es demasiado
   chica:** asume precisión de $1\text{ mm}$ levantando una rampa a mano, lo que
   infla artificialmente los "$\sigma$ de desacuerdo" en el veredicto.

---

## 5. Limitaciones abiertas (para la sección obligatoria del informe)

- **$\sigma$ de posición subestimado en `medir.py`:** se mide con el cuerpo
  quieto ($\sim 0,44\text{ mm}$ en la tapa), pero en movimiento el desenfoque y
  el cambio de forma de la mancha producen residuos de $\sim 2\text{--}3\text{ mm}$
  ($\chi^2_{\text{red}} \approx 40$). El error de $a$ igual sale escalado por
  los residuos en `np.polyfit(..., cov=True)`, pero el $\sigma$ reportado en los
  CSV refleja solo el piso estático del detector.
- **Ruido en aceleración cruda:** a $120\text{ fps}$, derivar dos veces divide
  por $\Delta t^2 = (1/120)^2$, amplificando $1\text{ mm}$ de ruido en posición
  a $\sim 9\text{ m/s}^2$ en `a_cruda`. Por eso el valor físico sale del ajuste
  cuadrático y `a_filtrada` usa Savitzky-Golay.
- **Ángulos aparentes:** `angulos_agente.py` mide la proyección en 2D sin
  homografía; depende de que la cámara esté perpendicular al plano.
- **Sin videos en superficie horizontal:** la consigna pide velocidad,
  aceleración y diagrama de cuerpo libre también en plano horizontal; el Grupo 3
  solo filmó plano inclinado y ángulo crítico.
- **Sin exports de Tracker del Grupo 3:** falta el contraste automático serie
  contra serie y $\mu_d$ contra $\mu_d$ frente a la medición humana.
- **Inconsistencia de alturas de 4 libros** (`15 + 8,7 = 23,7 cm`) y **foto de
  escala con regla sobre el plano**: siguen pendientes de confirmar con el Grupo 3.

---

## 6. Próximos pasos

1. Implementar la **regresión lineal global de $\mu_d$** ($g\sin\theta - a = \mu_d \cdot g\cos\theta$) sobre los tres ángulos para cada material, usando los ángulos del agente y comparando contra los del laboratorio.
2. Pedir al Grupo 3 sus **exports de Tracker** (para el contraste obligatorio), las aclaraciones sobre la altura de 4 libros y, si llegan, videos en **plano horizontal**.
3. Generar las figuras finales del informe desde los CSV de `resultados/series/` y `resultados/angulo_critico/`.
