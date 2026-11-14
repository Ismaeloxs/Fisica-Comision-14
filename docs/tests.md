# Tests

```bash
.venv\Scripts\activate
pip install -r requirements.txt
pytest
```

162 tests. Los de video necesitan los archivos del laboratorio y se saltean
solos si faltan; los de red no corren salvo que se pidan.

## Las tres categorias

| Marca | Que verifica | Cuantos |
|---|---|---|
| 🟢 `verde` | Camino feliz: funciona y da el numero correcto | 72 |
| 🔴 `rojo` | Entrada mala o datos faltantes dan error claro, nunca rompen ni inventan | 49 |
| 🟡 `amarillo` | Degradado: filtros de calidad, advertencias fisicas, limitaciones documentadas | 39 |

```bash
pytest -m verde
pytest -m "rojo or amarillo"
pytest -m video          # pipeline completo sobre videos reales (lento)
pytest -m red            # llama a la API y gasta cuota
```

## Que hay en cada archivo

| Archivo | Cubre |
|---|---|
| `test_referencia.py` | Angulos y mu estatico derivados de los datos del Grupo 3 |
| `test_cinematica.py` | Ajuste y derivacion, contra datos sinteticos de respuesta conocida |
| `test_fisica.py` | Deslizamiento, rodadura, cuerpo libre y el diagnostico entre hipotesis |
| `test_lote.py` | Filtros de calidad y agregacion por condicion |
| `test_herramientas.py` | Las 8 funciones que el modelo puede llamar |
| `test_llm.py` | Esquemas, registro de herramientas y eleccion de proveedor |
| `test_entorno.py` | Dependencias instaladas y degradacion sin ellas |
| `test_integracion.py` | Pipeline completo sobre un video real |

## Dos decisiones de diseno

**La cinematica se prueba con datos sinteticos.** Se genera `s(t)` con una
aceleracion conocida de antemano y se verifica que el ajuste la recupere. Con un
video real no hay con que comparar: no se sabe cual es la respuesta correcta.

**Varios tests amarillos documentan limitaciones, no exigen que anden.** Por
ejemplo `test_el_jabon_sigue_sin_datos_confiables` o
`test_el_chi2_delata_que_el_sigma_esta_subestimado`. **Si esos fallan es buena
noticia**: quiere decir que alguien arreglo el problema, y lo que hay que hacer
es actualizar `hallazgos.md` y borrar el test.

## Tres bugs reales que encontraron

1. **`_leer_json` rompia al armar su propio mensaje de error.** Usaba
   `relative_to(RAIZ)`, que lanza `ValueError` si la ruta cae fuera del repo.
   El manejo de errores era el que fallaba.
2. **Una dependencia opcional faltante volteaba el visor entero.** El import de
   la capa de IA estaba fuera del `try`, asi que un `ModuleNotFoundError`
   mataba la aplicacion al abrirse en vez de deshabilitar la pestania del chat.
3. **La afirmacion de que la perspectiva aportaba ~±3 % estaba mal.** El area
   del cuerpo cae con la velocidad (correlacion −0,65): es desenfoque de
   movimiento, no perspectiva, y las dos cosas estan confundidas. Corregido en
   `hallazgos.md`.

## El test que hay que mirar primero cuando algo no anda

`test_entorno.py::test_todo_lo_declarado_se_puede_importar_en_este_interprete`

Si falla, se esta corriendo el Python equivocado. Es el error mas facil de
cometer: `python src/agente/visor.py` sin activar el venv usa el Python del
sistema, que puede tener algunas dependencias y no otras.
