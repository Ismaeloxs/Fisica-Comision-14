# Hallazgos de la primera pasada sobre los videos

> Estado al 31/10/2026. Complementa [arquitectura.md](arquitectura.md).
> Todo lo de acá es reproducible: `python src/agente/medir.py "<video>.mp4"`.

## Resumen en una línea

El pipeline mide bien la **tapa** en dos de los tres ángulos. Para los otros dos
objetos todavía no mide de forma confiable. Y los números de la tapa **no son
compatibles con deslizamiento puro**, que es el modelo que la consigna asume por
defecto.

## 1. Lo que ya funciona

| Pieza | Estado | Dónde |
|---|---|---|
| Datos del laboratorio extraídos | ✅ | [datos/referencia/laboratorio.json](datos/referencia/laboratorio.json) |
| Ángulos con incerteza propagada | ✅ | [src/agente/referencia.py](src/agente/referencia.py) |
| Inventario de los 61 videos | ✅ | [src/agente/inventario.py](src/agente/inventario.py) |
| Calibración espacial + eje de la rampa | ✅ | [src/agente/calibracion.py](src/agente/calibracion.py) |
| Seguimiento por color | ⚠️ solo tapa y esponja | [src/agente/tracking.py](src/agente/tracking.py) |
| Ajuste de aceleración | ✅ | [src/agente/cinematica.py](src/agente/cinematica.py) |
| Chequeo desliza-vs-rueda | ✅ | [src/agente/fisica.py](src/agente/fisica.py) |

### Los videos son mejores de lo que esperábamos

61 videos, todos **1920×1080 a 120 fps**, y los 120 fps son **reales**: se
verificaron leyendo el timestamp de cada cuadro y ninguno tiene framerate
variable. Se puede usar `t = cuadro/120` sin corrección. Era el riesgo silencioso
número uno y no se materializó.

### Los ángulos estaban escondidos

El `.docx` del Grupo 3 tiene los títulos ("Cálculo del valor del ángulo para 4
libros apilados:") **sin valores**. Los valores estaban en cuatro fotos de
anotaciones a mano embebidas en el documento. Extraídos y verificados: nuestras
cuentas reproducen los ángulos manuscritos al cuarto decimal, lo que confirma que
la hipotenusa de 42 cm aplica a los tres casos.

| Condición | Altura | Ángulo |
|---|---|---|
| 4 libros | 23,7 cm | 34,353 ± 0,190° |
| 3 libros | 17,5 cm | 24,624 ± 0,163° |
| 2 libros | 14,5 cm | 20,196 ± 0,154° |

Coeficiente estático del ángulo crítico, μ_e = tan(θ_c):

| Objeto | Masa | θ crítico | μ_e |
|---|---|---|---|
| Tapa | 5 g | 16,32 ± 0,15° | **0,2927 ± 0,0028** |
| Esponja | 3 g | 14,20 ± 0,14° | **0,2530 ± 0,0027** |
| Jabón | 116 g | 17,89 ± 0,15° | **0,3227 ± 0,0029** |

## 2. Resultados de la primera medición completa

Aceleración media por condición, con la **dispersión entre repeticiones**:

| Objeto | Condición | n | a [m/s²] | dispersión | confiable |
|---|---|---|---|---|---|
| Tapa | 4 libros | 5 | 2,287 ± 0,204 | 8,9 % | ✅ |
| Tapa | 3 libros | 5 | 1,280 ± 0,127 | 9,9 % | ✅ |
| Tapa | 2 libros | 4 | 0,430 ± 0,267 | 62 % | ❌ |
| Esponja | 4 libros | 5 | 1,111 ± 0,234 | 21 % | ⚠️ |
| Esponja | 3 libros | 5 | 0,148 ± 0,076 | 51 % | ❌ |
| Esponja | 2 libros | 0 | — | — | ❌ |
| Jabón | 4 libros | 2 | 2,111 ± 0,089 | 4,2 % | ❌ (3 de 5 corridas dieron aceleración negativa) |
| Jabón | 3 libros | 0 | — | — | ❌ |
| Jabón | 2 libros | 5 | 0,036 ± 0,027 | 77 % | ❌ |

**La dispersión entre repeticiones es el número honesto, no el error del ajuste.**
Cada ajuste individual da ±0,06 m/s² (≈3 %), pero repetir la misma condición da
9 %. El ajuste solo mide cuán parabólica es una trayectoria, no cuán repetible es
el experimento.

## 3. El hallazgo que cambia la física: la tapa no desliza

La consigna pide μ dinámico por regresión asumiendo deslizamiento:
`a = g(senθ − μ cosθ)`. Si eso vale, **μ tiene que dar lo mismo en los tres
ángulos**. Y si en cambio rueda sin deslizar, `a = g senθ/(1 + I/mR²)`, lo
constante tiene que ser `1 + I/mR²`.

| Condición | θ | a medida | μ si desliza | 1+I/mR² si rueda |
|---|---|---|---|---|
| 4 libros | 34,35° | 2,287 ± 0,204 | 0,401 ± 0,026 | 2,42 ± 0,22 |
| 3 libros | 24,62° | 1,280 ± 0,127 | 0,315 ± 0,015 | 3,19 ± 0,32 |
| 2 libros | 20,20° | 0,430 ± 0,267 | 0,321 ± 0,029 | 7,88 ± 4,89 |

**Ninguna de las dos constantes se mantiene.** Y además:

> Los tres μ dan **mayores** que el μ_e = 0,2927 medido por ángulo crítico. El
> rozamiento dinámico no puede superar al estático. La hipótesis de
> deslizamiento puro queda descartada, no por gusto sino por contradicción.

Tiene sentido físico: la tapa es un tapón de botella apoyado sobre su canto, o
sea un cilindro que puede rodar.

Un modelo mixto (rueda con resistencia a la rodadura),
`a = (g senθ − c_r g cosθ)/(1 + I/mR²)`, ajustado a los dos ángulos confiables da
c_r = 0,226 ± 0,064 e I/mR² = 0,622 ± 0,339 — valores plausibles para un tapón
(entre disco macizo 0,5 y cilindro hueco 1,0). **Pero son dos parámetros
ajustados a dos datos: cero grados de libertad, no está validado.** Para
testearlo hace falta el tercer ángulo midiendo bien.

### Qué implica para el proyecto

El entregable "μ dinámico por regresión" **no se puede producir para la tapa** sin
antes resolver si rueda o desliza. Opciones:

1. Mirar los videos cuadro a cuadro y ver si gira. Es directo y gratis.
2. Pedirle al Grupo 3 que repita con la tapa pegada/trabada para que no pueda
   rodar, o apoyada sobre su cara plana.
3. Reportar la rodadura como el resultado, que es un resultado legítimo y además
   es literalmente el "chequeo físico" que la consigna exige para este
   movimiento.

**Ojo con el ángulo crítico:** si la tapa rueda, el ángulo al que arranca a
moverse no mide μ estático, mide resistencia a la rodadura. Los μ_e de la tabla
de arriba quedarían mal interpretados para ese objeto.

## 4. Lo que no funciona todavía

### El tracker del jabón está roto
Crema pálido sobre pared blanca y regla de madera: el umbral de color no lo
separa del fondo. Da cobertura 80-88 % y aceleraciones negativas. Era el objeto
que había marcado como difícil en la arquitectura. **Necesita otro método**:
`cv2.TrackerCSRT` sembrado con una ROI, o diferencia de cuadros (la escena es
estática salvo el objeto y la mano, así que la resta de fondo debería aislarlo
limpio para los tres objetos).

### Las ventanas de los ángulos chicos son malas
A 2 libros el objeto casi no acelera y recorre pocos centímetros, así que quedan
pocos puntos y mucha dispersión. Puede que esos videos simplemente no sirvan para
medir aceleración, y haya que decirlo en limitaciones.

### El σ de posición está subestimado
Se mide con el cuerpo quieto (0,44 mm), pero en movimiento hay desenfoque que
corre el centroide. El χ² reducido da ~40, o sea que el error real es ~6 veces el
estimado. Hay que medir σ también en movimiento.

### El control cruzado de escala no cierra
La escala sale del papel rosa: 27,07 ± 0,54 px/cm. Contrastada contra la regla de
42 cm da ~22 px/cm, 23 % menos. La regla es cota inferior (sus extremos quedan
ocultos: arriba el papel, abajo contra la mesa), así que la discrepancia es
esperable en signo, pero **23 % es mucho**. Dos argumentos a favor del papel:

- El recorrido medido con la escala del papel da 30,5 cm, consistente con una
  rampa de 42 cm donde el papel ocupa los primeros 7,5 cm.
- El tamaño aparente de la tapa varía solo ±6 % a lo largo del recorrido, o sea
  que la perspectiva aporta ~±3 % de escala, no 23 %.

Aun así conviene **pedirle al Grupo 3 una foto con una regla apoyada sobre el
plano**, que resolvería esto en un minuto.

## 5. La inconsistencia de los ángulos

Los saltos de altura no son uniformes:

- 2 → 3 libros: **+3,0 cm**
- 3 → 4 libros: **+6,2 cm**

Si los libros son de espesor parecido, uno de los tres valores está mal. El
manuscrito de 4 libros dice "altura = 15 + 8,7 = 23,7", una suma que los otros
dos no tienen. Con solo tres puntos en la regresión, un ángulo equivocado
desplaza la pendiente directamente.

**Pregunta concreta para el Grupo 3:** ¿cómo midieron la altura en cada caso, y
qué es el "15 + 8,7"?

## 6. Preguntas para el Grupo 3

1. ¿Qué es el "15 + 8,7 = 23,7" del cálculo de 4 libros? (ver §5)
2. ¿La tapa rodó o deslizó? ¿Lo vieron al filmar?
3. ¿Tienen una foto con una regla apoyada sobre el plano del movimiento? (ver §4)
4. ¿Con qué balanza pesaron? Con 3 g y σ = 0,5 g la masa de la esponja tiene 17 %
   de error. (No afecta μ, pero sí cualquier cálculo de fuerzas.)
5. ¿Reportan incertezas propias? Las de `laboratorio.json` son **asumidas por
   nosotros** y hay que confirmarlas.

## 7. Próximos pasos sugeridos

1. Resolver la pregunta rueda-vs-desliza mirando los videos. Bloquea la física.
2. Reemplazar el tracker por diferencia de cuadros, que debería servir para los
   tres objetos de una.
3. Medir σ de posición en movimiento, no solo en reposo.
4. Recién ahí, la regresión de μ sobre los ángulos y la comparación entre
   materiales.
