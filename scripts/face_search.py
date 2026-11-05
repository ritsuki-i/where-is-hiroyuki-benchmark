"""Local face detection and reference matching using OpenCV YuNet and SFace."""
from pathlib import Path
import time

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]

def detect_faces(image_path):
    detector_path = ROOT / 'models/yunet.onnx'
    if not detector_path.exists():
        raise RuntimeError('YuNetモデルがありません。READMEの準備手順を確認してください')
    detector = cv2.FaceDetectorYN.create(str(detector_path), '', (320, 320), 0.6, 0.3, 5000)
    image = cv2.imdecode(np.fromfile(str(image_path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError('画像を読み込めません')
    detector.setInputSize((image.shape[1], image.shape[0]))
    _, faces = detector.detect(image)
    return image, [] if faces is None else sorted(faces, key=lambda f: (float(f[1]), float(f[0])))


def search(image_path, reference_path):
    start = time.perf_counter()
    detector_path = ROOT / 'models/yunet.onnx'
    recognizer_path = ROOT / 'models/sface.onnx'
    if not detector_path.exists() or not recognizer_path.exists():
        raise RuntimeError('顔モデルがありません。READMEの準備手順を確認してください')
    detector = cv2.FaceDetectorYN.create(str(detector_path), '', (320, 320), 0.6, 0.3, 5000)
    recognizer = cv2.FaceRecognizerSF.create(str(recognizer_path), '')

    def detect(path):
        image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError('画像を読み込めません')
        detector.setInputSize((image.shape[1], image.shape[0]))
        _, faces = detector.detect(image)
        return image, [] if faces is None else faces

    ref, refs = detect(reference_path)
    if len(refs) == 0:
        raise RuntimeError('参照画像から顔を検出できませんでした')
    ref_face = max(refs, key=lambda f: f[2] * f[3])
    ref_feature = recognizer.feature(recognizer.alignCrop(ref, ref_face))
    image, faces = detect(image_path)
    if len(faces) == 0:
        return {'box': None, 'confidence': None, 'candidates': 0, 'seconds': time.perf_counter()-start}
    scored = [(float(recognizer.match(ref_feature, recognizer.feature(recognizer.alignCrop(image, f)), cv2.FaceRecognizerSF_FR_COSINE)), f) for f in faces]
    similarity, face = max(scored, key=lambda item: item[0])
    x, y, w, h = map(float, face[:4])
    width, height = image.shape[1], image.shape[0]
    box = [max(0, x/width), max(0, y/height), min(1, (x+w)/width), min(1, (y+h)/height)]
    return {'box': box, 'confidence': similarity, 'candidates': len(faces), 'seconds': time.perf_counter()-start}
