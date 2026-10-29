"""Captura una secuencia del stream de la ESP32-CAM y guarda sus cuadros tal como llegan.

Uso:
    python -m captura --url http://192.168.0.32:81/stream --secuencia S01 [--cuadros 12] \
        [--cada-ms 200] [--salida datos/cuadros] [--sin-pausa]

Escribe en SALIDA/SECUENCIA/: un JPEG por cuadro (`S01_f0001.jpg`, ...), `captura.jsonl` (un
cuadro por línea: frame_id, tiempo relativo de recepción, SHA-256, bytes y tamaño) y, si algo
del stream no sirvió, `rechazados/` con esos bytes y el motivo en el nombre (P5-12 puede usar un
JPEG truncado real). Los nombres no llevan la clase ni el caso.

Salida: 0 si se capturaron todos los cuadros sin huecos mayores al máximo, 1 si faltan cuadros o
hay huecos (la secuencia se vuelve a filmar), 2 si no se pudo conectar o la carpeta ya existe.

El máximo de hueco sale de `validez_orden_ms` en config/control/plazos.yaml. Las rutas las elige
quien corre el comando; por eso las escrituras llevan `NOSONAR (S8707)`, como en `python -m
metricas`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import yaml

from .stream import Captura, capturar, huecos_mayores, leer_partes

RAIZ = Path(__file__).resolve().parents[2]
RUTA_PLAZOS = RAIZ / "config" / "control" / "plazos.yaml"
PATRON_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")  # el mismo del contrato


def _max_hueco_ms() -> int:
    plazos = yaml.safe_load(RUTA_PLAZOS.read_text(encoding="utf-8"))
    return int(plazos["validez_orden_ms"])


def _guardar(captura: Captura, carpeta: Path, secuencia: str) -> None:
    carpeta.mkdir(parents=True)  # NOSONAR (S8707)
    filas = []
    for n, cuadro in enumerate(captura.cuadros, start=1):
        frame_id = f"{secuencia}_f{n:04d}"
        (carpeta / f"{frame_id}.jpg").write_bytes(cuadro.datos)  # NOSONAR (S8707)
        filas.append(
            {
                "frame_id": frame_id,
                "sequence_id": secuencia,
                "archivo": f"{frame_id}.jpg",
                "t_capture_ms": cuadro.t_ms,
                "sha256": cuadro.sha256,
                "bytes": len(cuadro.datos),
                "image_width": cuadro.ancho,
                "image_height": cuadro.alto,
            }
        )
    texto = "".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas)
    (carpeta / "captura.jsonl").write_text(texto, encoding="utf-8")  # NOSONAR (S8707)
    if captura.rechazados:
        rechazados = carpeta / "rechazados"
        rechazados.mkdir()  # NOSONAR (S8707)
        for n, (motivo, datos) in enumerate(captura.rechazados, start=1):
            (rechazados / f"{n:03d}_{motivo}.bin").write_bytes(datos)  # NOSONAR (S8707)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m captura",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--url", required=True, help="Stream MJPEG, p. ej. http://IP:81/stream.")
    parser.add_argument("--secuencia", required=True, help="sequence_id, p. ej. S01.")
    parser.add_argument("--cuadros", type=int, default=12, help="Cuántos cuadros (12).")
    parser.add_argument("--cada-ms", type=int, default=200, help="Separación mínima (200 ms).")
    parser.add_argument("--salida", type=Path, default=Path("datos/cuadros"))
    parser.add_argument("--ancho", type=int, default=640)
    parser.add_argument("--alto", type=int, default=480)
    parser.add_argument(
        "--descartar", type=int, default=2, help="Cuadros viejos del búfer que se tiran (2)."
    )
    parser.add_argument("--sin-pausa", action="store_true", help="No esperar Enter para empezar.")
    args = parser.parse_args(argv)

    if not PATRON_ID.match(args.secuencia):
        parser.error("--secuencia solo admite letras, números, '.', '_' y '-' (hasta 64)")
    if args.cuadros < 1 or args.cada_ms < 1:
        parser.error("--cuadros y --cada-ms deben ser al menos 1")
    url = urllib.parse.urlsplit(args.url)
    if url.scheme not in ("http", "https") or not url.hostname:
        parser.error("--url debe ser http(s)://IP:puerto/stream")
    carpeta = args.salida / args.secuencia
    if carpeta.exists():
        print(f"{carpeta.as_posix()} ya existe: bórrala o usa otra secuencia", file=sys.stderr)
        return 2
    maximo = _max_hueco_ms()

    if not args.sin_pausa:
        input(f"Secuencia {args.secuencia}: Enter para empezar a capturar...")
    try:
        # La URL la da quien corre el comando (la cámara en su red); solo se acepta http(s).
        with urllib.request.urlopen(args.url, timeout=10) as respuesta:  # NOSONAR (S8703)
            captura = capturar(
                leer_partes(respuesta),
                reloj_ms=lambda: time.monotonic_ns() / 1e6,
                cuadros=args.cuadros,
                cada_ms=args.cada_ms,
                tamano=(args.ancho, args.alto),
                descartar=args.descartar,
            )
    except OSError as exc:
        print(f"no se pudo leer el stream {args.url}: {exc}", file=sys.stderr)
        return 2

    if not captura.cuadros:
        print("no llegó ningún cuadro válido; no se guardó nada", file=sys.stderr)
        return 1
    _guardar(captura, carpeta, args.secuencia)

    cuadros = captura.cuadros
    duracion = cuadros[-1].t_ms
    print(
        f"{len(cuadros)} cuadros en {duracion} ms "
        f"({datetime.now().isoformat(timespec='seconds')}) -> {carpeta.as_posix()}/"
    )
    if captura.duplicados or captura.rechazados:
        print(f"descartados: {captura.duplicados} duplicados, {len(captura.rechazados)} rechazados")

    problemas = []
    if len(cuadros) < args.cuadros:
        problemas.append(f"solo {len(cuadros)} de {args.cuadros} cuadros (el stream se cortó)")
    problemas += [
        f"hueco de {hueco} ms antes de {args.secuencia}_f{i + 1:04d} (máximo {maximo})"
        for i, hueco in huecos_mayores(cuadros, maximo)
    ]
    for problema in problemas:
        print(f"advertencia: {problema}", file=sys.stderr)
    if problemas:
        print("vuelve a filmar la secuencia (borra la carpeta primero)", file=sys.stderr)
    return 1 if problemas else 0


if __name__ == "__main__":
    raise SystemExit(main())
