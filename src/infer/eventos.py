"""Publicación JSONL de un evento A→B v1 validado por cada JPEG."""

from __future__ import annotations

import json
import math
import re
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import cv2

from contrato.validador import validar_evento, validar_flujo

from .detector import DetectorJPEG, ErrorImagenJPEG, ErrorSalidaInvalida

_ID = re.compile(r"[A-Za-z0-9._-]{1,64}\Z")
_JPEG = {".jpg", ".jpeg"}
_MENSAJES_ERROR = {
    "unreadable_image": "no se pudo leer o decodificar el JPEG",
    "invalid_output": "salida inválida del detector",
    "detector_exception": "falló la ejecución del detector",
}


class ErrorRunInfer(ValueError):
    """Parámetros o evento incompatibles con el contrato v1."""


def _archivos(entrada: Path) -> tuple[list[Path], bool]:
    if entrada.is_dir():
        archivos = sorted(
            (p for p in entrada.iterdir() if p.is_file() and p.suffix.lower() in _JPEG),
            key=lambda p: p.name,
        )
        if not archivos:
            raise ErrorRunInfer(f"no hay JPEG en el directorio {entrada}")
        return archivos, True
    if entrada.suffix.lower() not in _JPEG:
        raise ErrorRunInfer("la entrada debe ser un JPEG o un directorio de JPEG")
    return [entrada], False  # El JPEG ausente produce unreadable_image por cuadro.


def _capturas(
    tiempos: Sequence[float] | None, cantidad: int, directorio: bool
) -> list[float] | None:
    if tiempos is None:
        if directorio:
            raise ErrorRunInfer("un directorio requiere --capture-ms por cada JPEG")
        return None
    if len(tiempos) != cantidad:
        raise ErrorRunInfer("--capture-ms debe aparecer exactamente una vez por JPEG")
    anterior = -1.0
    salida = []
    for valor in tiempos:
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise ErrorRunInfer("--capture-ms debe ser un número")
        numero = float(valor)
        if not math.isfinite(numero) or numero < 0 or numero <= anterior:
            raise ErrorRunInfer(
                "--capture-ms debe ser finito, no negativo y estrictamente creciente"
            )
        salida.append(numero)
        anterior = numero
    return salida


def _dimensiones_legibles(ruta: Path) -> tuple[int, int] | None:
    """Recupera dimensiones para un error posterior a la decodificación."""
    try:
        imagen = cv2.imread(str(ruta), cv2.IMREAD_COLOR)
    except cv2.error:
        return None
    if imagen is None or imagen.ndim != 3 or imagen.shape[0] < 1 or imagen.shape[1] < 1:
        return None
    alto, ancho = imagen.shape[:2]
    return ancho, alto


def _evento_base(
    run_id: str,
    sequence_id: str,
    frame_id: str,
    captura: float,
    emision: float,
    detector: DetectorJPEG,
) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "run_id": run_id,
        "sequence_id": sequence_id,
        "frame_id": frame_id,
        "t_capture_ms": captura,
        "t_emit_ms": emision,
        "image_width": None,
        "image_height": None,
        "model_sha256": detector.cargado.model_sha256,
        "config_sha256": detector.config.config_sha256,
        "status": "error",
        "bbox_format": "xyxy",
        "bbox_unit": "px",
        "detections": [],
    }


def _evento_cuadro(
    detector: DetectorJPEG,
    ruta: Path,
    run_id: str,
    sequence_id: str,
    indice: int,
    frame_id: str,
    captura: float,
    transcurrido: Callable[[], float],
) -> dict[str, Any]:
    try:
        resultado = detector.inferir(ruta)
        if (
            resultado.model_sha256 != detector.cargado.model_sha256
            or resultado.config_sha256 != detector.config.config_sha256
        ):
            raise ErrorSalidaInvalida("los hashes del resultado cambiaron durante el run")
        evento = _evento_base(run_id, sequence_id, frame_id, captura, transcurrido(), detector)
        evento["image_width"] = resultado.width
        evento["image_height"] = resultado.height
        evento["status"] = "ok"
        evento["detections"] = [
            {"class_id": d.class_id, "confidence": d.confidence, "bbox": list(d.bbox)}
            for d in resultado.detections
        ]
        fallos = validar_evento(evento)
        if fallos:
            raise ErrorSalidaInvalida(
                "detecciones incompatibles con contrato v1: " + "; ".join(fallos)
            )
        try:
            json.dumps(evento, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ErrorSalidaInvalida(f"detecciones no serializables como JSON: {exc}") from exc
        return evento
    except Exception as exc:
        # Los errores del detector son eventos, nunca una vía libre ficticia.
        codigo = (
            "unreadable_image"
            if isinstance(exc, ErrorImagenJPEG)
            else "invalid_output"
            if isinstance(exc, ErrorSalidaInvalida)
            else "detector_exception"
        )
        dimensiones = None if codigo == "unreadable_image" else _dimensiones_legibles(ruta)
        if dimensiones is None and codigo != "unreadable_image":
            codigo = "unreadable_image"
        # El detalle y la ruta quedan en stderr local, nunca en el JSONL publicable.
        print(f"infer: cuadro {indice} ({ruta}): {type(exc).__name__}: {exc}", file=sys.stderr)
        evento = _evento_base(run_id, sequence_id, frame_id, captura, transcurrido(), detector)
        if dimensiones is not None:
            evento["image_width"], evento["image_height"] = dimensiones
        evento["error"] = {"code": codigo, "message": _MENSAJES_ERROR[codigo]}
        return evento


def _serializar_evento(evento: dict[str, Any], anteriores: Sequence[dict[str, Any]]) -> str:
    fallos = validar_evento(evento) + validar_flujo([*anteriores, evento])
    if fallos:
        raise ErrorRunInfer("evento incompatible con contrato v1: " + "; ".join(fallos))
    try:
        return json.dumps(evento, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ErrorRunInfer(f"evento no serializable como JSON estricto: {exc}") from exc


def ejecutar_run(
    detector: DetectorJPEG,
    entrada: Path,
    salida: Path,
    *,
    run_id: str,
    sequence_id: str | None = None,
    capture_ms: Sequence[float] | None = None,
    reloj: Callable[[], float] = time.monotonic,
    dormir: Callable[[float], None] = time.sleep,
) -> tuple[Path, int, int]:
    """Escribe JSONL validado; en directorios reproduce capturas explícitas."""
    if not isinstance(run_id, str) or _ID.fullmatch(run_id) is None:
        raise ErrorRunInfer("run_id debe cumplir [A-Za-z0-9._-]{1,64}")
    archivos, directorio = _archivos(Path(entrada))
    secuencia = (None if directorio else "independent") if sequence_id is None else sequence_id
    if secuencia is None or _ID.fullmatch(secuencia) is None:
        raise ErrorRunInfer("sequence_id válido es obligatorio para un directorio")
    tiempos = _capturas(capture_ms, len(archivos), directorio)
    frame_ids = [ruta.stem for ruta in archivos]
    if any(_ID.fullmatch(frame_id) is None for frame_id in frame_ids):
        raise ErrorRunInfer("cada frame_id debe cumplir [A-Za-z0-9._-]{1,64}")
    if len(set(frame_ids)) != len(frame_ids):
        raise ErrorRunInfer("frame_id repetido en el run")

    destino = Path(salida)
    if destino.suffix.lower() != ".jsonl":
        destino /= f"{run_id}.jsonl"
    detector.calentar()
    destino.parent.mkdir(parents=True, exist_ok=True)
    eventos: list[dict[str, Any]] = []
    origen = reloj()

    def transcurrido() -> float:
        return (reloj() - origen) * 1000

    errores = 0
    with destino.open("x", encoding="utf-8", newline="\n") as archivo:
        for indice, (ruta, frame_id) in enumerate(zip(archivos, frame_ids, strict=True), start=1):
            if tiempos is None:
                captura = transcurrido()  # Recepción del JPEG individual en este run.
            else:
                captura = tiempos[indice - 1]
                restante = captura - transcurrido()
                if restante > 0:
                    dormir(restante / 1000)
            evento = _evento_cuadro(
                detector, ruta, run_id, secuencia, indice, frame_id, captura, transcurrido
            )
            evento["t_emit_ms"] = transcurrido()
            linea = _serializar_evento(evento, eventos)
            archivo.write(linea + "\n")
            archivo.flush()
            eventos.append(evento)
            errores += evento["status"] == "error"
    return destino, len(eventos), errores
