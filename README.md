# Fisica-Comision-14

git clone https://github.com/TU-USUARIO/agente-rozamiento.git
cd agente-rozamiento

Actiar entorno
python -m venv .venv
.venv\Scripts\activate ->  hacerlo siempre que cierres consola

pip install -r requirements.txt

Para probar que OpenCv funciona correctamente pone un video en /videos con nombre prueba.mp4 y luego ejecuta "python src/test_OpenCv.py", con esto se abre una ventana que ejecuta el video. Ctrl + c en consola para cerrar video. 

Para probar que YOLO funciona correctamente ejecuta "python src/test_YOLO.py" y deberia ejecutarse la ventana mostrando el mismo video pero esta vez con informacion acerca de lo que la ia ve.