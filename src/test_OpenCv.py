import cv2


def main():
    video = cv2.VideoCapture("videos/prueba.mp4")

    if not video.isOpened():
        print("No se pudo abrir el video")
        return

    while True:
        ret, frame = video.read()

        if not ret:
            break

        cv2.imshow("Video", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    video.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()