"""Resultados por cuadro y trazabilidad completa de una corrida (P5-14, E6).

Uso:
    python -m trazabilidad construir --corrida resultados/<run>/ --anotaciones anotaciones.jsonl \
        --salida resultados/<run>/trazabilidad/ [--model-sha256 HASH] [--config-sha256 HASH] \
        [--secuencia S01 ...]
    python -m trazabilidad recalcular resultados/<run>/trazabilidad/
    python -m trazabilidad cuadro resultados/<run>/trazabilidad/ FRAME_ID

`construir` une la corrida de `python -m control` con las anotaciones y escribe en `--salida`:
- `por_cuadro.jsonl`: una línea por cuadro con el evento del detector, la anotación, TP/FP/FN,
  la decisión y el comando de B y los errores con su motivo (ver `trazabilidad/union.py`).
- `ordenes_sin_cuadro.jsonl`: las órdenes de B sin cuadro (reloj, emergencia, rearme, cierre).
- `errores_sin_cuadro.jsonl`: los errores de B que no son de un cuadro (p. ej. `orden_vencida`).
- `resumen.json`: las métricas de P5-13, los conteos por secuencia, los hashes del detector y de
  B, el SHA-256 de cada entrada y de cada archivo escrito, y las advertencias.

`--secuencia` (repetible) une solo las anotaciones de esas secuencias, para una corrida que no
cubre todo el conjunto; los eventos de la corrida tienen que ser de esas secuencias.

`recalcular` lee solo los tres `.jsonl` que escribió `construir` y vuelve a producir las cifras de
`resumen.json`. `cuadro` muestra un cuadro de punta a punta: del `frame_id` al comando.

Salida de `construir`: 0 sin advertencias, 1 con advertencias, 2 si una entrada no se puede leer
o unir (no se escribe nada). De `recalcular`: 0 si da las mismas cifras, 1 si alguna difiere o un
archivo cambió, 2 si no se puede leer. De `cuadro`: 0 si lo encontró, 1 si no.

Todo se escribe con fin de línea LF, y cada SHA-256 se calcula sobre el texto con LF: un archivo
que Git saca con CRLF, o una corrida de `control` escrita en Windows, da el mismo hash.

Las rutas las elige quien corre el comando. Por eso las lecturas y escrituras con esas rutas
llevan `NOSONAR (S8707)`, como en `python -m metricas`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from control.__main__ import NOMBRE_DETECCIONES, NOMBRE_RUN
from metricas.evaluacion import validar_anotaciones

from .union import (
    ARCHIVOS_CORRIDA,
    construir,
    leer_corrida,
    leer_jsonl,
    recalcular,
)

POR_CUADRO = "por_cuadro.jsonl"
ORDENES = "ordenes_sin_cuadro.jsonl"
ERRORES = "errores_sin_cuadro.jsonl"
SALIDAS = (POR_CUADRO, ORDENES, ERRORES)
RESUMEN = "resumen.json"
CIFRAS = ("metricas", "conteo_por_cuadro", "conteos", "detector")


def _sha256(ruta: Path) -> str:
    """SHA-256 del texto con fin de línea LF, para que no dependa del sistema ni de Git."""
    datos = ruta.read_bytes().replace(b"\r\n", b"\n")  # NOSONAR (S8707)
    return hashlib.sha256(datos).hexdigest()


def _escribir(ruta: Path, texto: str) -> None:
    ruta.write_text(texto, encoding="utf-8", newline="\n")  # NOSONAR (S8707)


def _hash_hex(valor: str) -> str:
    if len(valor) != 64 or not set(valor) <= set("0123456789abcdef"):
        raise argparse.ArgumentTypeError("debe tener 64 caracteres hex en minúsculas")
    return valor


def _jsonl(filas: list[Any]) -> str:
    return "".join(json.dumps(f, ensure_ascii=False, allow_nan=False) + "\n" for f in filas)


def _construir(args: argparse.Namespace) -> int:
    try:
        corrida = leer_corrida(args.corrida)
        anotaciones = leer_jsonl(args.anotaciones) if args.anotaciones else None
        if args.secuencia:
            anotaciones = _de_las_secuencias(anotaciones, corrida, args.secuencia)
        filas, cifras, advertencias = construir(
            corrida, anotaciones, args.model_sha256, args.config_sha256
        )
    except (OSError, ValueError) as exc:  # ValueError incluye JSONDecodeError y ErrorTrazabilidad
        print(f"no se une: {exc}", file=sys.stderr)
        return 2
    if args.salida.exists() and (  # NOSONAR (S8707)
        not args.salida.is_dir() or any(args.salida.iterdir())  # NOSONAR (S8707)
    ):
        print(f"no se une: {args.salida.as_posix()} no es una carpeta vacía", file=sys.stderr)
        return 2

    args.salida.mkdir(parents=True, exist_ok=True)  # NOSONAR (S8707)
    _escribir(args.salida / POR_CUADRO, _jsonl(filas))
    _escribir(args.salida / ORDENES, _jsonl(cifras.pop("ordenes_sin_cuadro")))
    _escribir(args.salida / ERRORES, _jsonl(cifras.pop("errores_sin_cuadro")))
    entradas = {n: _sha256(args.corrida / n) for n in (*ARCHIVOS_CORRIDA, NOMBRE_RUN)}
    resumen = {
        "version": 1,
        "corrida": {
            "run_id": filas[0]["run_id"] if filas else None,
            "archivos": entradas,
            "config_b": corrida[NOMBRE_RUN].get("config"),
        },
        "anotaciones": (
            {
                "archivo": args.anotaciones.name,
                "sha256": _sha256(args.anotaciones),
                "secuencias": sorted(args.secuencia) if args.secuencia else None,
            }
            if args.anotaciones
            else None
        ),
        "esperado": {"model_sha256": args.model_sha256, "config_sha256": args.config_sha256},
        "archivos": {n: _sha256(args.salida / n) for n in SALIDAS},
        **cifras,
        "advertencias": advertencias,
    }
    texto = json.dumps(resumen, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    _escribir(args.salida / RESUMEN, texto)

    metricas = cifras["metricas"]
    if metricas:
        micro = metricas["micro"]
        print(f"TP={micro['tp']} FP={micro['fp']} FN={micro['fn']} F1={micro['f1']:.4f}")
    print(f"{len(filas)} cuadros, {len(cifras['conteos']['errores'])} errores registrados")
    for advertencia in advertencias:
        print(f"advertencia: {advertencia}", file=sys.stderr)
    print(f"resultados en {args.salida.as_posix()}/")
    return 1 if advertencias else 0


def _recalcular(args: argparse.Namespace) -> int:
    try:
        resumen = json.loads((args.carpeta / RESUMEN).read_text(encoding="utf-8"))  # NOSONAR
        filas = leer_jsonl(args.carpeta / POR_CUADRO)
        ordenes = leer_jsonl(args.carpeta / ORDENES)
        errores = leer_jsonl(args.carpeta / ERRORES)
        esperado = resumen["esperado"]
        faltan = [c for c in CIFRAS if c not in resumen]
        if faltan:
            raise ValueError(f"a {RESUMEN} le faltan {faltan}")
        cifras = recalcular(
            filas, ordenes, errores, esperado["model_sha256"], esperado["config_sha256"]
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"no se recalcula: {exc}", file=sys.stderr)
        return 2

    diferencias = [
        f"{n} cambió: su SHA-256 no es el de resumen.json"
        for n in SALIDAS
        if _sha256(args.carpeta / n) != resumen.get("archivos", {}).get(n)
    ]
    diferencias += [f"{c} no coincide con resumen.json" for c in CIFRAS if cifras[c] != resumen[c]]
    for diferencia in diferencias:
        print(f"diferencia: {diferencia}", file=sys.stderr)
    if diferencias:
        return 1
    print(f"el recálculo desde {POR_CUADRO} da las mismas cifras que {RESUMEN}")
    return 0


def _de_las_secuencias(
    anotaciones: list[Any] | None, corrida: dict[str, Any], secuencias: list[str]
) -> list[Any]:
    """Las anotaciones de esas secuencias; los eventos tienen que ser de ellas."""
    if anotaciones is None:
        raise ValueError("--secuencia elige anotaciones: falta --anotaciones")
    # Antes de filtrar, todo el archivo: una fila inválida o repetida no se salta en silencio.
    problemas = validar_anotaciones(anotaciones)
    if problemas:
        raise ValueError(f"las anotaciones no son válidas: {'; '.join(problemas[:5])}")
    elegidas = set(secuencias)
    anotadas = {a["sequence_id"] for a in anotaciones}
    if elegidas - anotadas:
        raise ValueError(f"no hay anotaciones de {sorted(elegidas - anotadas)}")
    fuera = sorted(
        {e.get("sequence_id") for e in corrida[NOMBRE_DETECCIONES] if isinstance(e, dict)}
        - elegidas,
        key=str,
    )
    if fuera:
        raise ValueError(f"la corrida tiene eventos de {fuera}, que no están en --secuencia")
    return [a for a in anotaciones if a["sequence_id"] in elegidas]


def _cuadro(args: argparse.Namespace) -> int:
    try:
        filas = leer_jsonl(args.carpeta / POR_CUADRO)
    except (OSError, ValueError) as exc:
        print(f"no se lee: {exc}", file=sys.stderr)
        return 2
    encontradas = [f for f in filas if f["frame_id"] == args.frame_id]
    if not encontradas:
        print(f"{args.frame_id}: no está en {POR_CUADRO}", file=sys.stderr)
        return 1
    for fila in encontradas:
        print(json.dumps(fila, ensure_ascii=False, indent=2))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m trazabilidad",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    unir = sub.add_parser("construir", help="une una corrida cuadro por cuadro")
    unir.add_argument("--corrida", type=Path, required=True, help="carpeta de python -m control")
    unir.add_argument("--anotaciones", type=Path, help="anotaciones v1 (P5-10)")
    unir.add_argument("--salida", type=Path, required=True, help="carpeta nueva o vacía")
    unir.add_argument("--model-sha256", type=_hash_hex, help="SHA-256 de los pesos congelados")
    unir.add_argument("--config-sha256", type=_hash_hex, help="SHA-256 de la config congelada")
    unir.add_argument(
        "--secuencia",
        action="append",
        help="une solo las anotaciones de esta secuencia (repetible)",
    )
    unir.set_defaults(funcion=_construir)

    rehacer = sub.add_parser("recalcular", help="rehace las cifras desde por_cuadro.jsonl")
    rehacer.add_argument("carpeta", type=Path)
    rehacer.set_defaults(funcion=_recalcular)

    uno = sub.add_parser("cuadro", help="muestra un cuadro de punta a punta")
    uno.add_argument("carpeta", type=Path)
    uno.add_argument("frame_id")
    uno.set_defaults(funcion=_cuadro)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return args.funcion(args)


if __name__ == "__main__":
    raise SystemExit(main())
