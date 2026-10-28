"""Calcula TP/FP/FN, precisión, recall y F1 a IoU 0.50 de un run del detector.

Uso:
    python -m metricas --detecciones run.jsonl --anotaciones anotaciones.jsonl --salida DIR \
        [--model-sha256 HASH] [--config-sha256 HASH]

Escribe en DIR: `por_cuadro.csv` (TP/FP/FN de cada cuadro), `detalle.csv` (cada emparejamiento)
y `resumen.json` (micro, por clase, criterio 1.4, procedencia y advertencias).

Salida: 0 si todo está en orden, 1 si se calcularon las métricas pero hay advertencias
(procedencia sin comprobar, cuadros sin predicción, mínimos de E3...), 2 si una entrada no se
puede leer o no cumple su formato.

Las rutas las elige quien corre el comando y pueden estar en cualquier carpeta (el evaluador usa
las suyas). Por eso las lecturas y escrituras con esas rutas llevan `NOSONAR (S8707)`, como en
`python -m control`: no hay una carpeta base contra la cual limitarlas.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from contrato import leer_eventos

from .evaluacion import EntradaInvalida, evaluar


def _sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()  # NOSONAR (S8707)


def _escribir_csv(ruta: Path, filas: list[dict[str, Any]], columnas: list[str]) -> None:
    with ruta.open("w", encoding="utf-8", newline="") as archivo:  # NOSONAR (S8707)
        escritor = csv.DictWriter(archivo, fieldnames=columnas, lineterminator="\n")
        escritor.writeheader()
        escritor.writerows(filas)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m metricas",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--detecciones", type=Path, required=True, help="Eventos del contrato v1.")
    parser.add_argument("--anotaciones", type=Path, required=True, help="Verdad de referencia.")
    parser.add_argument("--salida", type=Path, required=True, help="Carpeta de resultados.")
    parser.add_argument("--model-sha256", help="SHA-256 de los pesos congelados.")
    parser.add_argument("--config-sha256", help="SHA-256 de la configuración congelada.")
    args = parser.parse_args(argv)

    for nombre in ("model_sha256", "config_sha256"):
        valor = getattr(args, nombre)
        if valor is not None and not (len(valor) == 64 and set(valor) <= set("0123456789abcdef")):
            parser.error(f"--{nombre.replace('_', '-')} debe tener 64 caracteres hex en minúsculas")

    try:
        eventos = leer_eventos(args.detecciones)
        anotaciones = leer_eventos(args.anotaciones)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"no se pudo leer una entrada: {exc}", file=sys.stderr)
        return 2

    try:
        resultado = evaluar(anotaciones, eventos, args.model_sha256, args.config_sha256)
    except EntradaInvalida as exc:
        print("\n".join(exc.errores), file=sys.stderr)
        return 2

    resultado.resumen["entradas"] = {
        "detecciones": {"ruta": args.detecciones.as_posix(), "sha256": _sha256(args.detecciones)},
        "anotaciones": {"ruta": args.anotaciones.as_posix(), "sha256": _sha256(args.anotaciones)},
    }
    args.salida.mkdir(parents=True, exist_ok=True)  # NOSONAR (S8707)
    _escribir_csv(
        args.salida / "por_cuadro.csv",
        resultado.por_cuadro,
        ["frame_id", "sequence_id", "estado", "reales", "predichas", "tp", "fp", "fn"],
    )
    _escribir_csv(
        args.salida / "detalle.csv",
        resultado.detalle,
        ["frame_id", "tipo", "class_id", "confidence", "iou", "caja_predicha", "caja_real"],
    )
    resumen = json.dumps(resultado.resumen, ensure_ascii=False, indent=2) + "\n"
    (args.salida / "resumen.json").write_text(resumen, encoding="utf-8")  # NOSONAR (S8707)

    micro, criterio = resultado.resumen["micro"], resultado.resumen["criterio_1_4"]
    print(
        f"TP={micro['tp']} FP={micro['fp']} FN={micro['fn']} | P={micro['precision']:.4f} "
        f"R={micro['recall']:.4f} F1={micro['f1']:.4f} | 1.4: {criterio['puntaje_con_tope_e3']:g}/6"
    )
    for advertencia in resultado.advertencias:
        print(f"advertencia: {advertencia}", file=sys.stderr)
    print(f"resultados en {args.salida.as_posix()}/")
    return 1 if resultado.advertencias else 0


if __name__ == "__main__":
    raise SystemExit(main())
