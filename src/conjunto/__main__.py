"""Manifiesto y verificación del conjunto de evaluación (P5-11).

Uso:
    python -m conjunto manifiesto [--cuadros datos/cuadros] \
        [--anotaciones datos/anotaciones.jsonl] [--salida datos/manifiesto.jsonl] [--sobrescribir]
    python -m conjunto verificar [--manifiesto datos/manifiesto.jsonl] \
        [--anotaciones datos/anotaciones.jsonl] [--sha256 HASH_CONGELADO]
    python -m conjunto hojas --salida CARPETA_NUEVA [--cuadros datos/cuadros] \
        [--anotaciones datos/anotaciones.jsonl]

`manifiesto` junta la captura (P5-09) y las anotaciones (P5-10) en una fila por cuadro. Si
`--salida` ya existe, aunque sea un enlace roto, no la toca, salvo con `--sobrescribir`: puede
ser el manifiesto congelado. Con `--sobrescribir` se reemplaza la ruta, sin seguir enlaces.
`verificar` es el `verify_dataset` del ticket: revisa mínimos de E3, cuadros únicos, hashes,
`split`, huecos menores que `validez_orden_ms` y anotaciones, e imprime el SHA-256 del manifiesto
para congelarlo. Con `--sha256` además exige que el manifiesto sea el congelado. Cada
`hueco_intencional` sale como aviso por stderr, con su cuadro y su hueco, y la última línea dice
`OK con N excepciones`. La regla es cero excepciones, salvo las que apruebe el PM A en #13.
`hojas` es la revisión visual de P5-10: dibuja las cajas sobre los cuadros, una hoja PNG por
secuencia a resolución completa, y avisa por stderr de cada caja repetida entre cuadros.

Salida: 0 si todo cumple, 1 si alguna regla se rompe, 2 si una entrada no se puede leer o la salida
no se puede escribir.
Las rutas las elige quien corre el comando; por eso las lecturas y escrituras llevan
`NOSONAR (S8707)`, como en `python -m metricas`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
from collections.abc import Sequence
from pathlib import Path

from .hojas import cajas_repetidas, escribir_hojas
from .manifiesto import RAIZ, ErrorManifiesto, construir, leer_jsonl
from .verificacion import conteo, excepciones_de_hueco, verificar

RUTA_CLASES = RAIZ / "modelo" / "clases.json"


def _clases() -> set[int] | None:
    """`class_id` de modelo/clases.json (P5-04), o None si todavía no existe."""
    if not RUTA_CLASES.exists():
        return None
    return {c["class_id"] for c in json.loads(RUTA_CLASES.read_text(encoding="utf-8"))}


def _escribir(salida: Path, texto: str, sobrescribir: bool) -> None:
    """Escribe en un temporal y lo publica en `salida`: un error no deja un manifiesto a medias.

    El temporal lleva un nombre impredecible y se crea con `x`, que falla si ya existe: no sigue un
    enlace preparado de antemano ni pisa otro archivo. Publicar tampoco sigue enlaces: `link` falla
    si `salida` apareció mientras tanto (también un enlace roto) y `replace` cambia la ruta misma.
    `newline` fija el fin de línea: si no, en Windows el SHA-256 del archivo no sería el impreso.
    """
    temporal = salida.with_name(f".{salida.name}.{secrets.token_hex(8)}.parcial")
    archivo = temporal.open("x", encoding="utf-8", newline="\n")  # NOSONAR (S8707)
    try:
        with archivo:
            archivo.write(texto)
        if sobrescribir:
            temporal.replace(salida)  # NOSONAR (S8707)
        else:
            os.link(temporal, salida)  # NOSONAR (S8707)
    finally:
        temporal.unlink(missing_ok=True)  # NOSONAR (S8707)


def _manifiesto(args: argparse.Namespace) -> int:
    ya_existe = f"{args.salida.as_posix()} ya existe: usa --sobrescribir"
    if os.path.lexists(args.salida) and not args.sobrescribir:
        print(ya_existe, file=sys.stderr)
        return 2
    try:
        anotaciones = leer_jsonl(args.anotaciones)
        filas = construir(args.cuadros, anotaciones, args.raiz)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"no se pudo leer una entrada: {exc}", file=sys.stderr)
        return 2
    except ErrorManifiesto as exc:
        print("\n".join(exc.errores), file=sys.stderr)
        return 1
    texto = "".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas)
    try:
        _escribir(args.salida, texto, args.sobrescribir)
    except FileExistsError:
        print(ya_existe, file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"no se pudo escribir el manifiesto: {exc}", file=sys.stderr)
        return 2
    sha = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    print(f"{len(filas)} cuadros -> {args.salida.as_posix()} (SHA-256 {sha})")
    return 0


def _verificar(args: argparse.Namespace) -> int:
    try:
        datos = args.manifiesto.read_bytes()  # NOSONAR (S8707)
        filas = leer_jsonl(args.manifiesto)
        anotaciones = leer_jsonl(args.anotaciones)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"no se pudo leer una entrada: {exc}", file=sys.stderr)
        return 2

    clases = _clases()
    errores = verificar(filas, anotaciones, args.raiz, clases=clases)
    sha = hashlib.sha256(datos).hexdigest()
    if args.sha256 and sha != args.sha256:
        errores.append(f"el manifiesto cambió: SHA-256 {sha}, el congelado es {args.sha256}")

    total = conteo(filas) if all("estado_esperado" in f for f in filas) else {}
    print(", ".join(f"{k}: {v}" for k, v in total.items()))
    print(f"SHA-256 del manifiesto: {sha}")
    if clases is None:
        print("aviso: no existe modelo/clases.json; no se revisaron los class_id", file=sys.stderr)
    for error in errores:
        print(f"error: {error}", file=sys.stderr)
    excepciones = [] if errores else excepciones_de_hueco(filas)
    for excepcion in excepciones:
        print(f"aviso: {excepcion}; requiere aprobación del PM A en #13", file=sys.stderr)
    print("NO cumple" if errores else f"OK con {len(excepciones)} excepciones")
    return 1 if errores else 0


def _hojas(args: argparse.Namespace) -> int:
    try:
        if args.salida.exists() and (  # NOSONAR (S8707)
            not args.salida.is_dir() or any(args.salida.iterdir())  # NOSONAR (S8707)
        ):
            raise OSError(f"{args.salida.as_posix()} no es una carpeta vacía")
        anotaciones = leer_jsonl(args.anotaciones)
        args.salida.mkdir(parents=True, exist_ok=True)  # NOSONAR (S8707)
        hojas = escribir_hojas(anotaciones, args.cuadros, args.salida)
    except (OSError, ValueError, KeyError) as exc:  # PIL lanza OSError con un JPEG ilegible
        print(f"no se pudieron armar las hojas: {exc}", file=sys.stderr)
        return 2
    for aviso in cajas_repetidas(anotaciones):
        print(f"aviso: {aviso}", file=sys.stderr)
    print(f"{len(hojas)} hojas en {args.salida.as_posix()}/")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")  # acentos legibles en la consola de Windows
    parser = argparse.ArgumentParser(
        prog="python -m conjunto",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--raiz",
        type=Path,
        default=RAIZ,
        help="Raíz del repo: las rutas del manifiesto son relativas a ella.",
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("manifiesto", help="Arma el manifiesto desde la captura y las anotaciones.")
    p.add_argument("--cuadros", type=Path, default=Path("datos/cuadros"))
    p.add_argument("--anotaciones", type=Path, default=Path("datos/anotaciones.jsonl"))
    p.add_argument("--salida", type=Path, default=Path("datos/manifiesto.jsonl"))
    p.add_argument("--sobrescribir", action="store_true", help="Reemplaza --salida si ya existe.")

    v = sub.add_parser("verificar", help="verify_dataset: revisa el conjunto antes de congelar.")
    v.add_argument("--manifiesto", type=Path, default=Path("datos/manifiesto.jsonl"))
    v.add_argument("--anotaciones", type=Path, default=Path("datos/anotaciones.jsonl"))
    v.add_argument("--sha256", help="SHA-256 congelado del manifiesto.")

    h = sub.add_parser("hojas", help="Dibuja las cajas sobre los cuadros para revisarlas a ojo.")
    h.add_argument("--salida", type=Path, required=True, help="Carpeta nueva o vacía.")
    h.add_argument("--cuadros", type=Path, default=Path("datos/cuadros"))
    h.add_argument("--anotaciones", type=Path, default=Path("datos/anotaciones.jsonl"))

    args = parser.parse_args(argv)
    comandos = {"manifiesto": _manifiesto, "verificar": _verificar, "hojas": _hojas}
    return comandos[args.comando](args)


if __name__ == "__main__":
    raise SystemExit(main())
