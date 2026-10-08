from ultralytics import YOLO

model = YOLO("models/yolo11n.pt")

results = model.track(
    source="videos/prueba.mp4",
    show=True
)