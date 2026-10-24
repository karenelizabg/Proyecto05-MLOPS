"""Valida archivos de eventos: `python -m contrato <archivo.json|archivo.jsonl> [...]`.

Salida: 0 si todo cumple el contrato, 1 si hay eventos inválidos, 2 si un archivo no se
puede leer.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .validador import leer_eventos, validar_evento, validar_flujo


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m contrato", description=__doc__)
    parser.add_argument("archivos", nargs="+", type=Path)
    args = parser.parse_args(argv)

    codigo = 0
    for ruta in args.archivos:
        try:
            eventos = leer_eventos(ruta)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"{ruta}: no se pudo leer ({exc})", file=sys.stderr)
            return 2

        errores = [
            f"{ruta}: evento {n}: {msg}"
            for n, ev in enumerate(eventos, start=1)
            for msg in validar_evento(ev)
        ]
        errores += [f"{ruta}: {msg}" for msg in validar_flujo(eventos)]

        if errores:
            print("\n".join(errores), file=sys.stderr)
            codigo = 1
        else:
            print(f"{ruta}: OK ({len(eventos)} eventos)")
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
