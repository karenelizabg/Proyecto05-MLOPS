"""CLI de inferencia JPEG: ``python -m infer``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from .config import RUTA_CONFIG_DETECTOR, cargar_config_detector
from .detector import DetectorJPEG
from .eventos import ejecutar_run
from .pesos import cargar_pesos


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m infer", description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="JPEG o directorio plano de JPEG")
    parser.add_argument("--config", type=Path, default=RUTA_CONFIG_DETECTOR)
    parser.add_argument(
        "--weights", required=True, type=Path, help="checkpoint .pt local verificado"
    )
    parser.add_argument(
        "--output", required=True, type=Path, help="archivo .jsonl o carpeta de salida"
    )
    parser.add_argument("--run-id", required=True, help="ID del run, hasta 64 caracteres seguros")
    parser.add_argument("--sequence-id", help="ID de secuencia; obligatorio para directorios")
    parser.add_argument(
        "--capture-ms",
        action="append",
        type=float,
        help="captura relativa al run en ms; repetir una vez por JPEG, en orden de nombre",
    )
    args = parser.parse_args(argv)
    try:
        config = cargar_config_detector(args.config)
        detector = DetectorJPEG(cargar_pesos(args.weights, config), config)
        salida, cuadros, errores = ejecutar_run(
            detector,
            args.input,
            args.output,
            run_id=args.run_id,
            sequence_id=args.sequence_id,
            capture_ms=args.capture_ms,
        )
    except Exception as exc:
        print(f"infer: {exc}", file=sys.stderr)
        return 2
    print(f"{salida}: {cuadros} cuadros, {errores} errores")
    return 1 if errores else 0


if __name__ == "__main__":
    raise SystemExit(main())
