"""Ensayo P5-04 de SSDLite320 en CPU; no implementa el contrato v1."""

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
import torch
import torchvision
from torchvision.models.detection import (
    SSDLite320_MobileNet_V3_Large_Weights,
    ssdlite320_mobilenet_v3_large,
)


EXPECTED_SHA256 = "a79551df90c79834bcd3bb3845ef9d966b5449a3a9b2833ae8404778ca5d65d2"
WEIGHTS_URL = "https://download.pytorch.org/models/ssdlite320_mobilenet_v3_large_coco-a79551df.pth"
CONFIDENCE = 0.25


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
    p = (len(values) - 1) * 0.95
    low, high = math.floor(p), math.ceil(p)
    return {
        "min": values[0],
        "median": statistics.median(values),
        "p95_linear": values[low] + (values[high] - values[low]) * (p - low),
        "max": values[-1],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", required=True, type=Path)
    parser.add_argument("--weights", required=True, type=Path)
    parser.add_argument("--yolo-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if sha256(args.weights) != EXPECTED_SHA256:
        raise SystemExit("SHA-256 del checkpoint diferente del esperado")
    with args.yolo_manifest.open(encoding="utf-8", newline="") as source:
        earlier = {row["archivo"]: row for row in csv.DictReader(source)}
    images = sorted(args.images.glob("*.jpg"))
    if len(images) != 29 or len(earlier) != 29 or {p.name for p in images} != set(earlier):
        raise SystemExit("El conjunto no coincide con las 29 fotos de YOLO11n")
    manifest = []
    for path in images:
        digest = sha256(path)
        if digest != earlier[path.name]["sha256"]:
            raise SystemExit(f"La foto cambió: {path.name}")
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None or image.shape[:2] != (480, 640):
            raise SystemExit(f"JPEG ilegible o resolución incorrecta: {path.name}")
        manifest.append({
            "archivo": path.name, "sha256": digest, "bytes": path.stat().st_size,
            "ancho": 640, "alto": 480, "grupo_nombre": path.name.split("_", 1)[0],
        })

    torch.set_num_threads(1)
    categories = SSDLite320_MobileNet_V3_Large_Weights.COCO_V1.meta["categories"]
    start = time.perf_counter()
    # No automatic weight/backbone download: construct architecture, then load local state_dict.
    model = ssdlite320_mobilenet_v3_large(
        weights=None, weights_backbone=None,
        score_thresh=0.001, nms_thresh=0.55,
        detections_per_img=300, topk_candidates=300,
    )
    state = torch.load(args.weights, map_location="cpu", weights_only=True)
    model.load_state_dict(state, strict=True)
    model.to(torch.device("cpu"))
    model.eval()
    load_ms = (time.perf_counter() - start) * 1000

    per_image, detections, invalid = [], [], []
    with torch.inference_mode():
        for item in manifest:
            path = args.images / item["archivo"]
            total_start = time.perf_counter()
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            tensor = torch.from_numpy(rgb.copy()).permute(2, 0, 1).float().div_(255.0)
            preprocess_ms = (time.perf_counter() - total_start) * 1000

            forward_start = time.perf_counter()
            output = model([tensor])[0]
            forward_ms = (time.perf_counter() - forward_start) * 1000

            post_start = time.perf_counter()
            found = []
            for index, (box, label, score) in enumerate(zip(
                output["boxes"], output["labels"], output["scores"], strict=True
            )):
                confidence = float(score.item())
                if confidence < CONFIDENCE:
                    continue
                class_id = int(label.item())
                class_name = categories[class_id] if 0 <= class_id < len(categories) else "<id desconocido>"
                x1, y1, x2, y2 = [float(value) for value in box.tolist()]
                problems = []
                if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                    problems.append("confianza invalida")
                if not all(math.isfinite(v) for v in (x1, y1, x2, y2)):
                    problems.append("coordenadas no finitas")
                elif not (0 <= x1 < x2 <= 640 and 0 <= y1 < y2 <= 480):
                    problems.append("caja fuera de limites o degenerada")
                if class_name in ("<id desconocido>", "N/A", "__background__"):
                    problems.append("clase no valida")
                if problems:
                    invalid.append(f"{path.name} #{index}: {', '.join(problems)}")
                found.append(class_name)
                detections.append({
                    "archivo": path.name, "indice": index, "class_id": class_id,
                    "class_name": class_name, "confidence": confidence,
                    "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                    "validacion": "; ".join(problems) or "ok",
                })
            postprocess_ms = (time.perf_counter() - post_start) * 1000
            wall_ms = (time.perf_counter() - total_start) * 1000
            per_image.append({
                "archivo": path.name, "sha256": item["sha256"],
                "grupo_nombre": item["grupo_nombre"], "ancho": 640, "alto": 480,
                "detecciones": len(found), "clases_detectadas": ";".join(found),
                "preprocess_ms": preprocess_ms, "inference_ms": forward_ms,
                "postprocess_ms": postprocess_ms, "wall_ms": wall_ms,
            })

    config = {
        "proposito": "Prueba técnica de selección P5-04; no benchmark P5-15",
        "fuente_fotos": str(args.images.resolve()),
        "camara": "ESP32-CAM real del carrito (declarado por el usuario)",
        "modelo": "torchvision.models.detection.ssdlite320_mobilenet_v3_large",
        "pesos": "SSDLite320_MobileNet_V3_Large_Weights.COCO_V1",
        "checkpoint": str(args.weights.resolve()), "checkpoint_url": WEIGHTS_URL,
        "checkpoint_sha256": EXPECTED_SHA256, "checkpoint_bytes": args.weights.stat().st_size,
        "licencia_codigo": "BSD-3-Clause (torchvision)",
        "licencia_pesos": "No especificada de forma independiente en metadatos COCO_V1; verificar condiciones de dataset y uso antes de adoptar",
        "parametros": {
            "device": "cpu", "batch": 1, "native_size": [320, 320],
            "report_confidence": CONFIDENCE, "internal_score_thresh": 0.001,
            "internal_nms_iou": 0.55, "topk_candidates": 300,
            "detections_per_img": 300,
        },
        "torch_threads": torch.get_num_threads(),
        "versiones": {"python": sys.version.split()[0], "torch": torch.__version__,
                     "torchvision": torchvision.__version__, "numpy": np.__version__,
                     "opencv": cv2.__version__},
        "hardware": {"sistema": platform.platform(), "arquitectura": platform.machine(),
                     "procesador": platform.processor(), "equipo": "MacBook Air Apple M3, 8 núcleos, 16 GB RAM"},
        "medicion": "preprocess_ms=lectura JPEG+RGB+tensor; inference_ms=model([tensor]) incluye resize interno 320x320, backbone, cabezal, NMS y remapeo de cajas; postprocess_ms=filtrado >=0.25 y CSV; wall_ms=todo. Primera imagen separada.",
    }
    steady = per_image[1:]
    summary = {
        "load_ms": load_ms,
        "first_image": per_image[0]["archivo"],
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
        raise SystemExit("Resultados inválidos; consultar latencia_resumen.json")


if __name__ == "__main__":
    main()
