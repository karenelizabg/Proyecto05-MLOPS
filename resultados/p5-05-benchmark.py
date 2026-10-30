"""Repite el benchmark CPU de P5-05 sin descargar pesos ni modificar imágenes."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
from importlib.metadata import version
from pathlib import Path

import numpy as np

from infer.config import cargar_config_detector
from infer.detector import DetectorJPEG
from infer.pesos import cargar_pesos


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    config = cargar_config_detector()
    cargado = cargar_pesos(args.weights, config)
    detector = DetectorJPEG(cargado, config)
    for _ in range(10):
        detector.inferir(args.image)

    series: dict[str, list[float]] = {
        "detector_total_ms": [],
        "forward_ms": [],
        "preprocess_ms": [],
        "postprocess_ms": [],
    }
    for _ in range(50):
        resultado = detector.inferir(args.image)
        speed = detector.predictor.results[0].speed
        series["detector_total_ms"].append(resultado.elapsed_ms)
        series["forward_ms"].append(speed["inference"])
        series["preprocess_ms"].append(speed["preprocess"])
        series["postprocess_ms"].append(speed["postprocess"])

    def resumen(valores: list[float]) -> dict[str, float]:
        return {
            "mean": statistics.mean(valores),
            "median": statistics.median(valores),
            "p95_linear": float(np.percentile(valores, 95)),
            "min": min(valores),
            "max": max(valores),
        }

    datos = {
        "machine": {"os": platform.platform(), "cpu": platform.processor()},
        "python": platform.python_version(),
        "runtime": {
            nombre: version(nombre)
            for nombre in ("ultralytics", "torch", "torchvision", "opencv-python", "numpy")
        },
        "torch_threads": config.torch_threads,
        "device": "cpu",
        "image": args.image.name,
        "image_sha256": hashlib.sha256(args.image.read_bytes()).hexdigest(),
        "image_width": resultado.width,
        "image_height": resultado.height,
        "tensor_shape": resultado.tensor_shape,
        "warmup_runs": 10,
        "measured_runs": 50,
        "model_sha256": cargado.model_sha256,
        "config_sha256": config.config_sha256,
        "method": {
            "detector_total_ms": "DetectorJPEG.inferir: JPEG + predictor + validación, sin carga",
            "forward_ms": "Ultralytics Results.speed[inference]: forward del modelo",
            "percentile": "NumPy percentile(method=linear) 95",
        },
        "stats": {nombre: resumen(valores) for nombre, valores in series.items()},
        "samples_ms": series,
    }
    args.output.write_text(
        json.dumps(datos, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(datos["stats"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
