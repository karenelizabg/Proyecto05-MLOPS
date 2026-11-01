"""Repite el benchmark CPU de P5-05 sin descargar pesos ni modificar imágenes."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import time
from importlib.metadata import version
from pathlib import Path

import numpy as np
import torch

from infer.config import cargar_config_detector
from infer.detector import DetectorJPEG
from infer.pesos import cargar_pesos


def _guardar_resultado(ruta: Path, datos: dict) -> None:
    """Crea un JSON nuevo sin truncar destinos existentes ni seguir un enlace final."""
    contenido = json.dumps(datos, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    try:
        with ruta.open("x", encoding="utf-8") as archivo:
            archivo.write(contenido)
    except FileExistsError as exc:
        raise SystemExit(f"benchmark: la salida ya existe: {ruta}") from exc
    except OSError as exc:
        raise SystemExit(f"benchmark: no se pudo crear la salida {ruta}: {exc}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    config = cargar_config_detector()
    inicio = time.perf_counter()
    cargado = cargar_pesos(args.weights, config)
    carga_ms = (time.perf_counter() - inicio) * 1000
    inicio = time.perf_counter()
    detector = DetectorJPEG(cargado, config)
    construccion_ms = (time.perf_counter() - inicio) * 1000
    hilos_tras_setup = torch.get_num_threads()
    inicio = time.perf_counter()
    detector.calentar()
    calentamiento_sintetico_ms = (time.perf_counter() - inicio) * 1000
    hilos_tras_calentamiento = torch.get_num_threads()
    inicio = time.perf_counter()
    for _ in range(10):
        detector.inferir(args.image)
    calentamiento_jpeg_ms = (time.perf_counter() - inicio) * 1000

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
        "machine": {
            "os": platform.platform(),
            "architecture": platform.machine(),
            "cpu": platform.processor(),
        },
        "python": platform.python_version(),
        "runtime": {
            nombre: version(nombre)
            for nombre in ("ultralytics", "torch", "torchvision", "opencv-python", "numpy")
        },
        "torch_threads": config.torch_threads,
        "torch_threads_configured": config.torch_threads,
        "torch_threads_after_setup": hilos_tras_setup,
        "torch_threads_after_warmup": hilos_tras_calentamiento,
        "torch_threads_effective": torch.get_num_threads(),
        "preparation_ms": {
            "verified_weights_load": carga_ms,
            "detector_setup": construccion_ms,
            "synthetic_predictor_warmup": calentamiento_sintetico_ms,
            "jpeg_warmup_10_runs": calentamiento_jpeg_ms,
        },
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
            "preparation_ms": (
                "Separada de las 50 inferencias medidas; incluye carga, setup, "
                "calentamiento sintético y 10 JPEG"
            ),
        },
        "stats": {nombre: resumen(valores) for nombre, valores in series.items()},
        "samples_ms": series,
    }
    _guardar_resultado(args.output, datos)
    print(json.dumps(datos["stats"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
