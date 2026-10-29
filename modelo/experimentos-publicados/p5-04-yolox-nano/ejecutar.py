"""Experimento P5-04 de YOLOX-Nano ONNX en CPU, sin contrato de producción."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import statistics
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort


EXPECTED_MODEL_SHA256 = "c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d"
MODEL_URL = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx"
SOURCE_COMMIT = "e1052df71842031413f6030723c3607b839c80ce"
COCO_CLASSES = (
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
    "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
    "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
    "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier",
    "toothbrush",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save_csv(path: Path, rows: list[dict], columns: list[str] | None = None) -> None:
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=columns or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def metrics(values: list[float]) -> dict[str, float]:
    values = sorted(values)
    position = (len(values) - 1) * 0.95
    low, high = math.floor(position), math.ceil(position)
    return {
        "min": values[0],
        "median": statistics.median(values),
        "p95_linear": values[low] + (values[high] - values[low]) * (position - low),
        "max": values[-1],
    }


def nms(boxes: np.ndarray, scores: np.ndarray, threshold: float) -> list[int]:
    """NMS por clase del demo_utils.py oficial de 0.1.1rc0 (+1 píxel en área)."""
    x1, y1, x2, y2 = boxes.T
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size:
        index = int(order[0])
        keep.append(index)
        xx1 = np.maximum(x1[index], x1[order[1:]])
        yy1 = np.maximum(y1[index], y1[order[1:]])
        xx2 = np.minimum(x2[index], x2[order[1:]])
        yy2 = np.minimum(y2[index], y2[order[1:]])
        width = np.maximum(0.0, xx2 - xx1 + 1)
        height = np.maximum(0.0, yy2 - yy1 + 1)
        intersection = width * height
        overlap = intersection / (areas[index] + areas[order[1:]] - intersection)
        order = order[np.where(overlap <= threshold)[0] + 1]
    return keep


def decode(raw: np.ndarray, ratio: float) -> tuple[np.ndarray, np.ndarray]:
    """Decodificación de YOLOX-Nano, strides 8/16/32, a cajas originales xyxy."""
    predictions = raw.copy()
    grids, expanded_strides = [], []
    for stride in (8, 16, 32):
        cells = 416 // stride
        yv, xv = np.meshgrid(np.arange(cells), np.arange(cells), indexing="ij")
        grids.append(np.stack((xv, yv), axis=2).reshape(1, -1, 2))
        expanded_strides.append(np.full((1, cells * cells, 1), stride))
    grid = np.concatenate(grids, axis=1)
    stride = np.concatenate(expanded_strides, axis=1)
    predictions[..., :2] = (predictions[..., :2] + grid) * stride
    predictions[..., 2:4] = np.exp(predictions[..., 2:4]) * stride
    decoded = predictions[0]
    centers, sizes = decoded[:, :2], decoded[:, 2:4]
    boxes = np.concatenate((centers - sizes / 2, centers + sizes / 2), axis=1) / ratio
    scores = decoded[:, 4:5] * decoded[:, 5:]
    return boxes, scores


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", required=True, type=Path)
    parser.add_argument("--weights", required=True, type=Path)
    parser.add_argument("--yolo-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    assert len(COCO_CLASSES) == 80
    assert [COCO_CLASSES[i] for i in (24, 26, 28, 39, 41, 56)] == [
        "backpack", "handbag", "suitcase", "bottle", "cup", "chair"
    ]
    model_sha256 = sha256(args.weights)
    if model_sha256 != EXPECTED_MODEL_SHA256:
        raise SystemExit("SHA-256 del checkpoint diferente del esperado")
    with args.yolo_manifest.open(encoding="utf-8", newline="") as source:
        earlier = {row["archivo"]: row for row in csv.DictReader(source)}
    images = sorted(args.images.glob("*.jpg"))
    if len(images) != 29 or len(earlier) != 29 or {p.name for p in images} != set(earlier):
        raise SystemExit("Las imágenes no son el mismo conjunto de 29 fotografías")
    manifest = []
    for path in images:
        digest = sha256(path)
        if digest != earlier[path.name]["sha256"]:
            raise SystemExit(f"La fotografía cambió: {path.name}")
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None or image.shape != (480, 640, 3):
            raise SystemExit(f"JPEG ilegible o resolución incorrecta: {path.name}")
        manifest.append({
            "archivo": path.name, "sha256": digest, "bytes": path.stat().st_size,
            "ancho": 640, "alto": 480, "grupo_nombre": path.name.split("_", 1)[0],
        })

    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    load_start = time.perf_counter()
    session = ort.InferenceSession(str(args.weights), sess_options=options,
                                   providers=["CPUExecutionProvider"])
    load_ms = (time.perf_counter() - load_start) * 1000
    if session.get_providers() != ["CPUExecutionProvider"]:
        raise SystemExit("La sesión no utiliza únicamente CPUExecutionProvider")
    input_info = session.get_inputs()
    output_info = session.get_outputs()
    if ([(x.shape, x.type) for x in input_info] != [([1, 3, 416, 416], "tensor(float)")]
            or [(x.shape, x.type) for x in output_info] != [([1, 3549, 85], "tensor(float)")]):
        raise SystemExit("Las formas ONNX difieren de la prueba mínima")

    per_image, detections, invalid = [], [], []
    for item in manifest:
        path = args.images / item["archivo"]
        wall_start = time.perf_counter()
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        ratio = min(416 / image.shape[0], 416 / image.shape[1])
        resized = cv2.resize(image, (int(640 * ratio), int(480 * ratio)),
                             interpolation=cv2.INTER_LINEAR)
        padded = np.full((416, 416, 3), 114, dtype=np.uint8)
        padded[:resized.shape[0], :resized.shape[1]] = resized
        tensor = np.ascontiguousarray(padded.transpose(2, 0, 1)[None], dtype=np.float32)
        preprocess_ms = (time.perf_counter() - wall_start) * 1000

        run_start = time.perf_counter()
        raw = session.run(None, {input_info[0].name: tensor})[0]
        inference_ms = (time.perf_counter() - run_start) * 1000
        if raw.shape != (1, 3549, 85) or raw.dtype != np.float32:
            raise SystemExit(f"Salida inesperada: {path.name}, {raw.shape}, {raw.dtype}")
        if not np.isfinite(raw).all():
            invalid.append(f"{path.name}: salida cruda no finita")
            continue

        post_start = time.perf_counter()
        boxes, scores = decode(raw, ratio)
        found = []
        for class_id, class_name in enumerate(COCO_CLASSES):
            class_scores = scores[:, class_id]
            mask = class_scores >= 0.25
            if not mask.any():
                continue
            valid_boxes, valid_scores = boxes[mask], class_scores[mask]
            for index in nms(valid_boxes, valid_scores, 0.45):
                xyxy = [float(value) for value in valid_boxes[index]]
                confidence = float(valid_scores[index])
                problems = []
                if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                    problems.append("confianza inválida")
                if not all(math.isfinite(v) for v in xyxy):
                    problems.append("coordenadas no finitas")
                elif not (0 <= xyxy[0] < xyxy[2] <= 640 and 0 <= xyxy[1] < xyxy[3] <= 480):
                    problems.append("caja fuera de límites o degenerada")
                if problems:
                    invalid.append(f"{path.name} clase {class_id}: {', '.join(problems)}")
                found.append({
                    "archivo": path.name, "class_id": class_id,
                    "class_name": class_name, "confidence": confidence,
                    "x1": xyxy[0], "y1": xyxy[1], "x2": xyxy[2], "y2": xyxy[3],
                    "validacion": "; ".join(problems) or "ok",
                })
        found.sort(key=lambda row: row["confidence"], reverse=True)
        for index, row in enumerate(found):
            detections.append({"indice": index, **row})
        postprocess_ms = (time.perf_counter() - post_start) * 1000
        wall_ms = (time.perf_counter() - wall_start) * 1000
        per_image.append({
            "archivo": path.name, "sha256": item["sha256"], "grupo_nombre": item["grupo_nombre"],
            "ancho": 640, "alto": 480, "detecciones": len(found),
            "clases_detectadas": ";".join(row["class_name"] for row in found),
            "preprocess_ms": preprocess_ms, "inference_ms": inference_ms,
            "postprocess_ms": postprocess_ms, "wall_ms": wall_ms,
        })

    if len(per_image) != 29:
        raise SystemExit(f"Solo se registraron {len(per_image)} imágenes; errores: {invalid}")
    config = {
        "proposito": "Prueba preliminar P5-04; no benchmark oficial P5-15",
        "camara": "ESP32-CAM real del carrito (declarado por el usuario)",
        "fuente_fotos": str(args.images.resolve()),
        "modelo": "YOLOX-Nano ONNX", "release": "0.1.1rc0", "source_commit": SOURCE_COMMIT,
        "checkpoint": str(args.weights.resolve()), "checkpoint_url": MODEL_URL,
        "checkpoint_sha256": model_sha256, "checkpoint_bytes": args.weights.stat().st_size,
        "licencia_codigo": "Apache-2.0 (YOLOX)",
        "licencia_pesos": "Condiciones independientes no verificadas; no inferir Apache-2.0",
        "parametros": {
            "providers": session.get_providers(), "batch": 1, "input_size": [416, 416],
            "letterbox": "arriba-izquierda", "padding": 114, "channels": "BGR CHW float32",
            "normalization": "none", "decode_strides": [8, 16, 32],
            "score": "objectness * class_probability", "report_confidence_gte": 0.25,
            "nms": "por clase, NumPy YOLOX 0.1.1rc0", "nms_iou": 0.45,
            "intra_op_threads": 1, "inter_op_threads": 1,
        },
        "entrada": {"name": input_info[0].name, "shape": input_info[0].shape,
                    "type": input_info[0].type},
        "salida": {"name": output_info[0].name, "shape": output_info[0].shape,
                   "type": output_info[0].type},
        "versiones": {"python": sys.version.split()[0], "onnxruntime": ort.__version__,
                     "numpy": np.__version__, "opencv": cv2.__version__},
        "hardware": {"sistema": platform.platform(), "arquitectura": platform.machine(),
                     "equipo": "MacBook Air Apple M3, 8 núcleos, 16 GB RAM"},
        "medicion": "preprocess_ms: JPEG+letterbox+CHW; inference_ms: session.run; postprocess_ms: decode+filtro+NMS; wall_ms: todo. Primera imagen separada.",
        "discrepancia_historica": "El ejemplo ONNX en el commit de release normaliza, pero las notas 0.1.1rc0 indican que los pesos nuevos dejan de normalizar; la documentación oficial posterior enlaza el mismo asset y usa preprocesamiento sin normalización. La prueba mínima visual de taza fue coherente con esta ruta.",
    }
    steady = per_image[1:]
    summary = {
        "load_ms": load_ms, "first_image": per_image[0]["archivo"],
        "first_image_ms": {key: per_image[0][key] for key in
                           ("preprocess_ms", "inference_ms", "postprocess_ms", "wall_ms")},
        "subsequent_images": len(steady),
        **{key: metrics([row[key] for row in steady]) for key in
           ("preprocess_ms", "inference_ms", "postprocess_ms", "wall_ms")},
        "invalid_results": invalid,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "configuracion.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n")
    (args.output / "latencia_resumen.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    save_csv(args.output / "manifiesto.csv", manifest)
    save_csv(args.output / "por_imagen.csv", per_image)
    save_csv(args.output / "detecciones.csv", detections, [
        "archivo", "indice", "class_id", "class_name", "confidence",
        "x1", "y1", "x2", "y2", "validacion",
    ])
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"imagenes={len(per_image)} detecciones={len(detections)}")
    if invalid:
        raise SystemExit("Se registraron resultados inválidos; revisar latencia_resumen.json")


if __name__ == "__main__":
    main()
