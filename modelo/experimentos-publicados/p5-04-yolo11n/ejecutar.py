"""Prueba exploratoria de YOLO11n; no produce eventos del contrato v1."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import statistics
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
import torchvision
import ultralytics
from ultralytics import YOLO


EXPECTED_MODEL_SHA256 = "0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1"
MODEL_URL = "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt"
SETTINGS = {"device": "cpu", "imgsz": 640, "conf": 0.25, "iou": 0.7, "batch": 1}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def percentile_linear(values: list[float], percentage: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentage / 100
    low = math.floor(position)
    high = math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    images = sorted(args.images.glob("*.jpg"))
    if len(images) != 29:
        raise SystemExit(f"Se esperaban 29 JPEG; se encontraron {len(images)}")
    actual_model_sha256 = sha256(args.weights)
    if actual_model_sha256 != EXPECTED_MODEL_SHA256:
        raise SystemExit("El SHA-256 del checkpoint no coincide con el esperado")

    torch.set_num_threads(1)
    manifest = []
    for path in images:
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None or image.shape[:2] != (480, 640):
            raise SystemExit(f"JPEG ilegible o tamaño distinto de 640x480: {path}")
        manifest.append(
            {
                "archivo": path.name,
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
                "ancho": 640,
                "alto": 480,
                "grupo_nombre": path.name.split("_", 1)[0],
            }
        )

    config = {
        "proposito": "Prueba tecnica de seleccion P5-04; no evaluacion final ni benchmark P5-15",
        "fuente_fotos": str(args.images.resolve()),
        "camara": "ESP32-CAM real del carrito (declarado por el usuario; no consta en registro.csv)",
        "modelo": "YOLO11n",
        "checkpoint": str(args.weights.resolve()),
        "checkpoint_url": MODEL_URL,
        "checkpoint_release": "v8.3.0",
        "checkpoint_sha256": actual_model_sha256,
        "checkpoint_bytes": args.weights.stat().st_size,
        "licencia": "Ultralytics declara AGPL-3.0 para codigo y modelos; revisar antes de adoptar",
        "parametros": SETTINGS,
        "torch_threads": torch.get_num_threads(),
        "versiones": {
            "python": sys.version.split()[0],
            "ultralytics": ultralytics.__version__,
            "torch": torch.__version__,
            "torchvision": torchvision.__version__,
            "numpy": np.__version__,
            "opencv": cv2.__version__,
        },
        "hardware": {
            "sistema": platform.platform(),
            "arquitectura": platform.machine(),
            "procesador": platform.processor(),
        },
        "medicion": "wall_ms incluye lectura y llamadas a predict; speed de Ultralytics separa preprocesamiento, inferencia y posprocesamiento. Primera imagen separada.",
    }

    load_start = time.perf_counter()
    model = YOLO(str(args.weights))
    load_ms = (time.perf_counter() - load_start) * 1000
    if not model.names:
        raise SystemExit("El modelo cargó sin catálogo de clases")

    per_image = []
    detections = []
    invalid = []
    for item in manifest:
        path = args.images / item["archivo"]
        start = time.perf_counter()
        result = model.predict(
            source=str(path),
            device="cpu",
            imgsz=640,
            conf=0.25,
            iou=0.7,
            batch=1,
            verbose=False,
            save=False,
        )[0]
        wall_ms = (time.perf_counter() - start) * 1000
        height, width = result.orig_shape
        if (height, width) != (480, 640):
            invalid.append(f"{path.name}: orig_shape={result.orig_shape}")
        classes = []
        for index, box in enumerate(result.boxes):
            class_id = int(box.cls.item())
            confidence = float(box.conf.item())
            x1, y1, x2, y2 = [float(x) for x in box.xyxy[0].tolist()]
            class_name = result.names.get(class_id, "<id desconocido>")
            problems = []
            if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                problems.append("confianza invalida")
            if not all(math.isfinite(v) for v in (x1, y1, x2, y2)):
                problems.append("coordenadas no finitas")
            elif not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
                problems.append("caja fuera de limites o degenerada")
            if class_name == "<id desconocido>":
                problems.append("class_id desconocido")
            if problems:
                invalid.append(f"{path.name} deteccion {index}: {', '.join(problems)}")
            classes.append(class_name)
            detections.append(
                {
                    "archivo": path.name,
                    "indice": index,
                    "class_id": class_id,
                    "class_name": class_name,
                    "confidence": confidence,
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "validacion": "; ".join(problems) or "ok",
                }
            )
        per_image.append(
            {
                "archivo": path.name,
                "sha256": item["sha256"],
                "grupo_nombre": item["grupo_nombre"],
                "ancho": width,
                "alto": height,
                "detecciones": len(result.boxes),
                "clases_detectadas": ";".join(classes),
                "preprocess_ms": result.speed["preprocess"],
                "inference_ms": result.speed["inference"],
                "postprocess_ms": result.speed["postprocess"],
                "wall_ms": wall_ms,
            }
        )

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "configuracion.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_csv(args.output / "manifiesto.csv", list(manifest[0]), manifest)
    write_csv(args.output / "por_imagen.csv", list(per_image[0]), per_image)
    write_csv(
        args.output / "detecciones.csv",
        ["archivo", "indice", "class_id", "class_name", "confidence", "x1", "y1", "x2", "y2", "validacion"],
        detections,
    )
    steady = per_image[1:]
    summary = {
        "load_ms": load_ms,
        "first_image": per_image[0]["archivo"],
        "first_image_wall_ms": per_image[0]["wall_ms"],
        "first_image_inference_ms": per_image[0]["inference_ms"],
        "subsequent_images": len(steady),
        "inference_ms": {
            "min": min(row["inference_ms"] for row in steady),
            "median": statistics.median(row["inference_ms"] for row in steady),
            "p95_linear": percentile_linear([row["inference_ms"] for row in steady], 95),
            "max": max(row["inference_ms"] for row in steady),
        },
        "wall_ms": {
            "min": min(row["wall_ms"] for row in steady),
            "median": statistics.median(row["wall_ms"] for row in steady),
            "p95_linear": percentile_linear([row["wall_ms"] for row in steady], 95),
            "max": max(row["wall_ms"] for row in steady),
        },
        "invalid_results": invalid,
    }
    (args.output / "latencia_resumen.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if invalid:
        raise SystemExit("Hay detecciones invalidas: revisar latencia_resumen.json")


if __name__ == "__main__":
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
    main()
