# El chat con IA

Pestania "Chat IA" del visor, y tambien `python src/agente/chat.py` por consola.
Sirve para preguntar sobre los videos, los calculos, la fisica del problema o
que hacer con lo que falta.

## Como se configura

El chat es lo unico del proyecto que necesita una clave de API. El resto del
visor (medir, graficos, lote) funciona sin nada de esto.

La configuracion va en un archivo `.env` en la raiz del repo, que **no se
versiona**: cada integrante arma el suyo.

```bash
copy .env.ejemplo .env     # Windows
cp .env.ejemplo .env       # bash
```

y se completa la clave adentro. `llm/base.py` lo carga solo, asi que vale igual
desde el visor y desde la consola. Una variable exportada en la terminal le
gana al archivo, util para probar otra clave sin editarlo.

Hay dos proveedores. **Uno solo alcanza.**

### Gemini (tiene nivel gratuito)

```
AGENTE_LLM=gemini
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3.5-flash
GEMINI_FALLBACK_MODEL=gemini-3.1-flash-lite
```

La clave se saca en <https://aistudio.google.com/apikey>.

Conviene nombrar un modelo concreto y no un alias `-latest`: los alias apuntan
al mas popular y se saturan. Si el modelo configurado no existe para la clave,
el chat lo avisa y lista los disponibles.

`GEMINI_FALLBACK_MODEL` es el respaldo para cuando el principal devuelve **503
por saturacion**: se rearma el chat conservando el historial, se reintenta una
sola vez, y la respuesta avisa que la contesto el respaldo. No es teorico —
paso en la primera prueba.

### Claude

```
AGENTE_LLM=claude
ANTHROPIC_API_KEY=sk-ant-...
```

La clave se saca en <https://console.anthropic.com/settings/keys>. No tiene
nivel gratuito, pero una pregunta cuesta centavos.

Si no se define `AGENTE_LLM`, se usa el proveedor que tenga clave. Si no hay
ninguna, la pestania se muestra deshabilitada con estas instrucciones y el
resto del visor sigue andando.

## Antes de usarlo: generar el cache

El chat lee los resultados ya medidos, no mide videos en vivo (cada corrida
tarda segundos y una pregunta puede tocar las 61). Hay que correr una vez:

```bash
python src/agente/lote.py
```

Eso deja `resultados/corridas.json` y `resultados/global.json`. Si falta,
las herramientas lo dicen en vez de inventar.

Hay que volver a correrlo cada vez que se cambie el pipeline de medicion.

## Como esta hecho

```
chat_ui.py / chat.py        la interfaz (pestania del visor / consola)
      |
llm/base.py                 interfaz comun + prompt de sistema
      |-- llm/proveedor_claude.py    SDK anthropic, tool runner
      |-- llm/proveedor_gemini.py    SDK google-genai, automatic function calling
      |
llm/herramientas.py         las funciones que el modelo puede llamar
      |
resultados/*.json           lo que produjo el pipeline determinista
```

`llm/herramientas.py` no importa ningun SDK: las mismas ocho funciones las
exponen los dos proveedores. Cambiar de proveedor es cambiar una variable de
entorno.

### La regla que hace que esto sea defendible

**El modelo no calcula.** Cuando necesita un numero del experimento llama a una
funcion de Python, que lo lee de `resultados/`, que lo produjo el pipeline
deterministico. El modelo interpreta y redacta; los numeros no son suyos.

Esto importa por la consigna: todo numero lleva incerteza propagada, y una
incerteza solo se puede propagar si se sabe de donde salio el numero. Un valor
inventado por un modelo de lenguaje no tiene esa trazabilidad.

Por eso **debajo de cada respuesta se lista que herramientas se llamaron**. Si
el chat afirma una aceleracion y la linea de abajo dice "sin consultar datos",
se la invento y no hay que creerle.

### Las herramientas

| Funcion | Para que |
|---|---|
| `estado_del_proyecto` | Panorama: que mide bien y que esta roto |
| `resumen_por_condicion` | Tabla principal: a, dispersion, mu, factor de inercia |
| `datos_del_laboratorio` | Lo que midio el Grupo 3: angulos, masas, calibracion |
| `listar_corridas` | Las corridas con filtros, y cuales se descartaron |
| `detalle_corrida` | Todos los numeros de un video |
| `comparar_hipotesis` | El chequeo desliza-vs-rueda que pide la consigna |
| `inventario_videos` | Resolucion, fps real, duraciones |
| `leer_documento` | arquitectura.md, hallazgos.md, README, datos del lab |

Agregar una herramienta es escribir una funcion en `llm/herramientas.py` y
sumarla a la lista `HERRAMIENTAS` del final. El esquema que ve el modelo sale
de la firma y del docstring, asi que **el docstring no es decorativo**: si
miente, el modelo llama mal a la funcion.

## Que esperar

Preguntas que contesta bien:

- "Como viene el proyecto, que anda y que no"
- "La tapa rueda o desliza, justificado con los numeros"
- "Por que se descartaron las corridas del jabon"
- "Explicame el diagrama de cuerpo libre" (de teoria, sin herramientas)
- "Que le tendriamos que pedir al Grupo 3"

Lo que **no** hace:

- No mira los videos. No tiene vision: lee los resultados del pipeline. Si la
  pregunta es "¿se ve girar la tapa?", la respuesta hay que verla en la
  pestania Trayectoria o abriendo el video.
- No corrige el pipeline solo. Puede decir que el tracker del jabon falla y por
  que, pero arreglarlo es codigo.
- No inventa los datos que faltan. Si una condicion no tiene corridas
  confiables, lo dice.
