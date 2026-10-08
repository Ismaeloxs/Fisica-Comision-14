# Repositorio de la comision 14 del proyecto de fisica 1

## Herramientas Utilizadas
* **Python 3.14**
* **NumPy 2.5.3**
* **SciPy 1.18.1**
* **OpenCV 5.0.0**
* **Ultralytics YOLO 11**

## Guía de Instalación

### 1. Clonar el repositorio
Clonar el repo con
```bash
git clone https://github.com/Ismaeloxs/Fisica-Comision-14.git
cd Fisica-Comision-14
```
### 2. Activar entorno
En la carpeta del repo ejecutar
```bash
python -m venv .venv
```
Y luego
```bash
.venv\Scripts\activate -> HACERLO SIEMPRE QUE CIERRES CONSOLA
```
### 3. Activar entorno
Activar entorno con
```bash
pip install -r requirements.txt
```

### 4. Probar OpenCv
Para probar que OpenCv funciona correctamente pone un video en /videos con nombre prueba.mp4 y luego ejecuta
```bash
python src/test_OpenCv.py
```
Con esto se abre una ventana que ejecuta el video. Ctrl + c en consola para cerrar video. 

### 4. Probar YOLO
Para probar que YOLO funciona correctamente ejecuta
```bash
python src/test_YOLO.py
```
Deberia ejecutarse la misma ventana mostrando el mismo video pero esta vez con informacion acerca de lo que la ia ve.
