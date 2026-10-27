"""Validador del contrato de percepción A → B (v1).

`validar_evento` comprueba un evento contra el esquema JSON y contra las reglas que
el esquema no puede expresar (caja dentro de la imagen, tiempo coherente).
`validar_flujo` añade las reglas que dependen de varios eventos: IDs únicos, tiempo
monótono por secuencia y un solo modelo y configuración por run.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

RAIZ = Path(__file__).resolve().parents[2]
RUTA_ESQUEMA = RAIZ / "config" / "contrato" / "percepcion.v1.schema.json"

# Tolerancia para comparar píxeles en coma flotante.
_TOL = 1e-6


@lru_cache(maxsize=None)
def _validador(ruta: Path) -> Draft202012Validator:
    esquema = json.loads(ruta.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(esquema)
    return Draft202012Validator(esquema)


def _donde(error: Any) -> str:
    return "/".join(str(p) for p in error.absolute_path) or "(evento)"


def _numeros_no_finitos(valor: Any, ruta: str = "", activos: set[int] | None = None) -> list[str]:
    """Encuentra números no finitos y ciclos antes de comparar rangos, cajas o tiempos."""
    if (isinstance(valor, float) and not math.isfinite(valor)) or (
        isinstance(valor, Decimal) and not valor.is_finite()
    ):
        return [f"{ruta or '(evento)'}: debe ser un número finito"]
    if not isinstance(valor, (dict, list)):
        return []

    if activos is None:
        activos = set()
    identidad = id(valor)
    if identidad in activos:
        return [f"{ruta or '(evento)'}: estructura cíclica no permitida"]

    activos.add(identidad)
    try:
        if isinstance(valor, dict):
            return [
                error
                for clave, hijo in valor.items()
                for error in _numeros_no_finitos(
                    hijo, f"{ruta}/{clave}" if ruta else str(clave), activos
                )
            ]
        return [
            error
            for indice, hijo in enumerate(valor)
            for error in _numeros_no_finitos(
                hijo, f"{ruta}/{indice}" if ruta else str(indice), activos
            )
        ]
    finally:
        activos.remove(identidad)


def validar_evento(evento: Any, ruta_esquema: Path = RUTA_ESQUEMA) -> list[str]:
    """Devuelve los errores del evento; lista vacía si cumple el contrato."""
    errores_numericos = _numeros_no_finitos(evento)
    if errores_numericos:
        return errores_numericos
    fallos = sorted(
        _validador(ruta_esquema).iter_errors(evento),
        key=lambda e: [str(p) for p in e.absolute_path],
    )
    if fallos:
        return [f"{_donde(e)}: {e.message}" for e in fallos]
    return _reglas_semanticas(evento)


def _reglas_semanticas(evento: dict[str, Any]) -> list[str]:
    errores: list[str] = []
    if evento["t_emit_ms"] < evento["t_capture_ms"]:
        errores.append("t_emit_ms: no puede ser anterior a t_capture_ms")

    ancho, alto = evento["image_width"], evento["image_height"]
    for i, det in enumerate(evento["detections"]):
        a, b, c, d = det["bbox"]
        if evento["bbox_format"] == "xyxy":
            x1, y1, x2, y2 = a, b, c, d
        else:
            x1, y1, x2, y2 = a, b, a + c, b + d
        donde = f"detections/{i}/bbox"
        if x2 <= x1 or y2 <= y1:
            errores.append(f"{donde}: la caja debe tener ancho y alto positivos")
        if x2 > ancho + _TOL or y2 > alto + _TOL:
            errores.append(f"{donde}: la caja sale de la imagen ({ancho}x{alto})")
    return errores


def validar_flujo(eventos: Iterable[Any]) -> list[str]:
    """Reglas entre eventos. Los eventos que no cumplen el contrato por sí solos se omiten
    aquí (ya los reporta `validar_evento`)."""
    errores: list[str] = []
    frames: set[tuple[str, str]] = set()
    ultimo_t: dict[tuple[str, str], float] = {}
    por_run: dict[str, tuple[str, str, str]] = {}

    for n, ev in enumerate(eventos, start=1):
        if validar_evento(ev):
            continue
        run, secuencia, frame = ev["run_id"], ev["sequence_id"], ev["frame_id"]

        if (run, frame) in frames:
            errores.append(f"evento {n}: frame_id {frame!r} repetido en el run {run!r}")
        frames.add((run, frame))

        clave = (run, secuencia)
        if clave in ultimo_t and ev["t_capture_ms"] <= ultimo_t[clave]:
            errores.append(
                f"evento {n}: t_capture_ms ({ev['t_capture_ms']}) no crece respecto al "
                f"cuadro anterior de la secuencia {secuencia!r} ({ultimo_t[clave]})"
            )
        ultimo_t[clave] = ev["t_capture_ms"]

        firma = (ev["model_sha256"], ev["config_sha256"], ev["bbox_format"])
        if por_run.setdefault(run, firma) != firma:
            errores.append(
                f"evento {n}: el run {run!r} cambia de modelo, configuración o bbox_format"
            )
    return errores


def leer_eventos(ruta: Path) -> list[Any]:
    """Lee un .json (objeto o lista de objetos) o un .jsonl (un evento por línea)."""
    texto = ruta.read_text(encoding="utf-8")
    if ruta.suffix == ".jsonl":
        return [json.loads(linea) for linea in texto.splitlines() if linea.strip()]
    dato = json.loads(texto)
    return dato if isinstance(dato, list) else [dato]
