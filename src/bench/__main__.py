"""Benchmark del detector en CPU: 10 calentamientos + 100 ejecuciones válidas (P5-15, E7).

Uso:
    python -m bench --entradas datos/cuadros/ --salida mediciones/<run>/ --equipo "<PEND-05>" \
        --detector paquete.modulo [--opcion clave=valor ...] \
        --model-sha256 HASH --config-sha256 HASH [--config-control config/control/]

`--detector falso` usa el detector de prueba del arnés. Con el real, `paquete.modulo` expone
`crear(**opciones)` (ver `bench/detector.py`).

`--model-sha256` y `--config-sha256` son obligatorios: sin ellos no se sabe si se midió la
configuración congelada. Para probar el arnés sin hashes está `--prueba`, que lo deja anotado y
nunca sale con 0. La etapa de B usa `plazos.yaml` y `politica.yaml` de `--config-control`, y sus
SHA-256 quedan registrados en `procedencia.config_b`. B no tiene todavía una referencia congelada
con qué compararlos, así que se registran pero no cuentan como procedencia comprobada (esa es
la del detector, en `procedencia.detector`).

En modo oficial el detector debe tener archivo de pesos: el arnés calcula su SHA-256 y lo compara.
Un detector sin pesos, como el falso, solo se mide con `--prueba`.

Escribe en la carpeta de salida, que debe no existir o estar vacía:
- `ejecuciones.csv`: una fila por ejecución válida, calentamientos marcados (`fase`).
- `fallos.csv`: las ejecuciones fallidas, aparte; no entran en p50/p95.
- `resumen.json`: p50/p95/máximo por etapa, hardware, runtime, pesos, procedencia y advertencias.

Salida: 0 si el benchmark está completo y sin advertencias; 1 si se midió pero hay advertencias
(detector falso, modo de prueba, equipo sin declarar, en batería) o quedó incompleto por fallos;
2 si no se puede medir así (configuración distinta de la congelada, hashes sin indicar, entradas,
configuración de B o argumentos inválidos). Con 2 no se escribe nada.

Las rutas las elige quien corre el comando y pueden estar en cualquier carpeta. Por eso las
lecturas y escrituras con esas rutas llevan `NOSONAR (S8707)`, como en `python -m control`.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from control.__main__ import CARPETA_CONFIG

from .arnes import (
    CALENTAMIENTOS,
    ETAPAS,
    MAX_FALLOS,
    MINIMO_MEDICIONES,
    PERIODO_MS,
    ErrorBench,
    EtapaPolitica,
    cargar_entradas,
    energia,
    hardware,
    medir,
    resumir_etapas,
    runtime,
    ruta_publicable,
    sha256_archivo,
    verificar_procedencia,
)
from .detector import DetectorFalso

EXTENSIONES = (".jpg", ".jpeg", ".png")
COLUMNAS_EJECUCIONES = ["intento", "fase", "entrada_id", *ETAPAS, "detecciones", "accion"]
COLUMNAS_FALLOS = ["intento", "fase", "entrada_id", "etapa", "error", "mensaje"]


def _rutas_de_entrada(entradas: Sequence[Path]) -> list[Path]:
    """Archivos tal cual, y de cada carpeta sus imágenes en orden de nombre."""
    rutas: list[Path] = []
    for entrada in entradas:
        if entrada.is_dir():  # NOSONAR (S8707)
            rutas += sorted(p for p in entrada.iterdir() if p.suffix.lower() in EXTENSIONES)
        else:
            rutas.append(entrada)
    return rutas


def _opciones(pares: Sequence[str]) -> dict[str, Any]:
    """`clave=valor` → {clave: valor}, con el valor leído como YAML (números, listas, ...)."""
    opciones = {}
    for par in pares:
        clave, igual, valor = par.partition("=")
        if not igual or not clave:
            raise ErrorBench(f"--opcion {par!r}: se espera clave=valor")
        opciones[clave] = yaml.safe_load(valor)
    return opciones


def _crear_detector(nombre: str, opciones: dict[str, Any]) -> Any:
    modulo = "bench.detector" if nombre == "falso" else nombre
    try:
        return importlib.import_module(modulo).crear(**opciones)
    except (ImportError, AttributeError, TypeError, ValueError) as exc:
        raise ErrorBench(f"no se pudo crear el detector {nombre!r}: {exc}") from exc


def _escribir_csv(ruta: Path, filas: list[dict[str, Any]], columnas: list[str]) -> None:
    with ruta.open("w", encoding="utf-8", newline="") as archivo:  # NOSONAR (S8707)
        escritor = csv.DictWriter(archivo, fieldnames=columnas, lineterminator="\n")
        escritor.writeheader()
        escritor.writerows(filas)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m bench",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--entradas", type=Path, nargs="+", required=True, help="Imágenes o carpetas."
    )
    parser.add_argument("--salida", type=Path, required=True, help="Carpeta vacía de resultados.")
    parser.add_argument("--detector", default="falso", help="'falso' o el módulo con crear().")
    parser.add_argument("--opcion", action="append", default=[], help="clave=valor para crear().")
    parser.add_argument("--model-sha256", help="SHA-256 de los pesos congelados.")
    parser.add_argument("--config-sha256", help="SHA-256 de la configuración congelada.")
    parser.add_argument("--equipo", help="Máquina declarada (PEND-05), p. ej. 'laptop de A3'.")
    parser.add_argument(
        "--mediciones", type=int, default=MINIMO_MEDICIONES, help="Ejecuciones válidas (>= 100)."
    )
    parser.add_argument("--max-fallos", type=int, default=MAX_FALLOS, help="Fallos tolerados.")
    parser.add_argument("--sin-politica", action="store_true", help="No medir la etapa de B.")
    parser.add_argument(
        "--config-control",
        type=Path,
        default=CARPETA_CONFIG,
        help="Carpeta con plazos.yaml y politica.yaml de B.",
    )
    parser.add_argument(
        "--prueba", action="store_true", help="Probar el arnés sin hashes (nunca sale con 0)."
    )
    return parser


def _revisar_argumentos(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.mediciones < MINIMO_MEDICIONES:
        parser.error(f"--mediciones debe ser al menos {MINIMO_MEDICIONES}")
    if args.max_fallos < 0:
        parser.error("--max-fallos no puede ser negativo")
    for nombre in ("model_sha256", "config_sha256"):
        opcion = f"--{nombre.replace('_', '-')}"
        valor = getattr(args, nombre)
        if valor is None and not args.prueba:
            parser.error(f"falta {opcion}: sin él no se rechaza una configuración distinta")
        if valor is not None and not (len(valor) == 64 and set(valor) <= set("0123456789abcdef")):
            parser.error(f"{opcion} debe tener 64 caracteres hex en minúsculas")
    salida = args.salida
    if salida.exists() and (not salida.is_dir() or any(salida.iterdir())):  # NOSONAR (S8707)
        parser.error(f"{salida} no está vacía: usa una carpeta nueva para no mezclar corridas")


def _advertencias(args: argparse.Namespace, detector: Any, corriente: str) -> list[str]:
    advertencias = []
    if args.prueba:
        advertencias.append("modo de prueba (--prueba): no es la medición del entregable")
    if isinstance(detector, DetectorFalso):
        advertencias.append("detector falso: prueba el arnés, no es la medición del entregable")
    if not args.equipo:
        advertencias.append("no se declaró el equipo (--equipo, PEND-05)")
    if corriente == "bateria":
        advertencias.append("el equipo está en batería: la frecuencia puede bajar; conéctalo")
    if args.sin_politica:
        advertencias.append("sin la etapa de política/adaptador: el total no incluye a B")
    return advertencias


def _resumen(
    args: argparse.Namespace,
    detector: Any,
    procedencia: dict[str, Any],
    entradas: list[Any],
    medicion: Any,
    corriente: str,
    advertencias: list[str],
) -> dict[str, Any]:
    return {
        "version": 1,
        "estado": "completo" if medicion.completa else "incompleto",
        "equipo": args.equipo,
        "hardware": hardware(),
        "energia": corriente,
        "runtime": runtime(detector),
        "procedencia": procedencia,
        "protocolo": {
            "calentamientos": CALENTAMIENTOS,
            "mediciones": args.mediciones,
            "max_fallos": args.max_fallos,
            "prueba": args.prueba,
            "reloj": "time.perf_counter_ns",
            "percentil": "lineal: posición (n - 1) * q, interpolando entre vecinos",
            "incluye": (
                "preprocesamiento, inferencia, posprocesamiento, armar y validar el evento, "
                "y política/adaptador de B"
            ),
            "excluye": [
                "leer y decodificar la imagen",
                "carga del modelo",
                "pausas de reproducción",
            ],
            "total": "tiempo de pared de cada ejecución, del preprocesamiento al comando de B",
            "entradas_en_ciclo": True,
            "periodo_etiqueta_ms": PERIODO_MS,
            "con_politica": not args.sin_politica,
        },
        "entradas": {e.entrada_id: e.sha256 for e in entradas},
        "conteos": {
            "calentamientos": sum(1 for e in medicion.ejecuciones if e["fase"] == "calentamiento"),
            "mediciones": sum(1 for e in medicion.ejecuciones if e["fase"] == "medicion"),
            "fallos": len(medicion.fallos),
        },
        "etapas": resumir_etapas(medicion.ejecuciones),
        "advertencias": advertencias,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    _revisar_argumentos(parser, args)

    with tempfile.TemporaryDirectory(prefix="bench-politica-") as temporal:
        try:
            detector = _crear_detector(args.detector, _opciones(args.opcion))
            del_detector, advertencias = verificar_procedencia(
                detector, args.model_sha256, args.config_sha256, args.prueba
            )
            entradas = cargar_entradas(detector, _rutas_de_entrada(args.entradas))
            politica = None
            if not args.sin_politica:
                politica = EtapaPolitica(Path(temporal), args.config_control)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            print(f"no se mide: {exc}", file=sys.stderr)
            return 2
        procedencia = {"detector": del_detector, "config_b": None}
        if politica is not None:
            procedencia["config_b"] = {
                "carpeta": ruta_publicable(args.config_control),
                **politica.archivos,
                "comparada_con_referencia": False,
                "nota": "registrada; B no tiene una referencia congelada con qué compararla",
            }
        medicion = medir(
            detector, entradas, politica, CALENTAMIENTOS, args.mediciones, args.max_fallos
        )

    corriente = energia()
    advertencias = _advertencias(args, detector, corriente) + advertencias
    if not medicion.completa:
        advertencias.append(
            f"incompleto: {len(medicion.fallos)} fallos, más de los {args.max_fallos} tolerados"
        )

    args.salida.mkdir(parents=True, exist_ok=True)  # NOSONAR (S8707)
    ruta_ejecuciones, ruta_fallos = args.salida / "ejecuciones.csv", args.salida / "fallos.csv"
    _escribir_csv(ruta_ejecuciones, medicion.ejecuciones, COLUMNAS_EJECUCIONES)
    _escribir_csv(ruta_fallos, medicion.fallos, COLUMNAS_FALLOS)
    resumen = _resumen(args, detector, procedencia, entradas, medicion, corriente, advertencias)
    resumen["archivos"] = {
        "ejecuciones.csv": sha256_archivo(ruta_ejecuciones),
        "fallos.csv": sha256_archivo(ruta_fallos),
    }
    texto = json.dumps(resumen, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    (args.salida / "resumen.json").write_text(texto, encoding="utf-8")  # NOSONAR (S8707)

    etapas = resumen["etapas"]
    if "total_ms" in etapas:
        total = etapas["total_ms"]
        print(
            f"total: p50={total['p50']:.2f} ms p95={total['p95']:.2f} ms "
            f"máx={total['maximo']:.2f} ms"
            f" | {resumen['conteos']['mediciones']} mediciones, {len(medicion.fallos)} fallos"
        )
    for advertencia in advertencias:
        print(f"advertencia: {advertencia}", file=sys.stderr)
    print(f"resultados en {args.salida.as_posix()}/")
    return 1 if advertencias else 0


if __name__ == "__main__":
    raise SystemExit(main())
