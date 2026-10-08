import cv2
from ultralytics import YOLO
import numpy as np
import scipy


def main():
    print("Agente de fuerza de rozamiento")
    print(f"NumPy: {np.__version__}")
    print(f"SciPy: {scipy.__version__}")
    print(f"OpenCV: {cv2.__version__}")

    model = YOLO("models/yolo11n.pt")

    print("YOLO cargado correctamente")


if __name__ == "__main__":
    main()