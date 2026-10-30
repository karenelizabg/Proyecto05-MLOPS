"""Manifiesto del conjunto de evaluación (P5-11): una fila por cuadro.

Junta lo que deja la captura (`datos/cuadros/<secuencia>/captura.jsonl`, P5-09) con las
anotaciones (`datos/anotaciones.jsonl`, formato v1 de config/anotaciones/, P5-10). El estado
esperado y las zonas ocupadas se calculan de las cajas anotadas con la misma definición de zonas
que usa la política del grupo B (`config/control/politica.yaml`), para que no haya dos reglas.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from control.config import ZONAS, ConfigPolitica, cargar_config_politica
from control.politica import zonas_ocupadas
from metricas.evaluacion import validar_anotaciones

RAIZ = Path(__file__).resolve().parents[2]
SPLIT = "evaluacion"  # D-06: no hubo ajuste; todo el conjunto es evaluación.
PROCEDENCIA = "ESP32-CAM del carro, python -m captura (P5-09)"
PATRON_ARCHIVO = re.compile(r"[A-Za-z0-9._-]+\.jpg")  # un nombre suelto, sin carpetas


class ErrorManifiesto(Exception):
    """Faltan datos para armar el manifiesto."""

    def __init__(self, errores: list[str]):
        super().__init__("\n".join(errores))
        self.errores = errores


def leer_jsonl(ruta: Path) -> list[Any]:
    texto = ruta.read_text(encoding="utf-8")  # NOSONAR (S8707)
    return [json.loads(linea) for linea in texto.splitlines() if linea.strip()]


def ruta_relativa(ruta: Path, raiz: Path) -> str | None:
    """`ruta` ya resuelta (enlaces incluidos), relativa a `raiz`; None si queda fuera de ella."""
    try:
        return ruta.resolve().relative_to(raiz.resolve()).as_posix()
    except ValueError:
        return None


def zonas_de(anotacion: Mapping[str, Any], config: ConfigPolitica) -> list[str]:
    """Zonas que ocupan los objetos anotados, en el orden izq, centro, der."""
    objetos = anotacion["objetos"]
    if not objetos:
        return []
    # Las cajas anotadas son la verdad: cuentan todas sus clases y con confianza 1.
    cambios = {
        "clases_obstaculo": frozenset(o["class_id"] for o in objetos),
        "umbral_confianza": 0.0,
    }
    config_anotadas = ConfigPolitica(**{**vars(config), **cambios})
    evento = {
        "status": "ok",
        "image_width": anotacion["image_width"],
        "bbox_format": "xyxy",
        "detections": [
            {"class_id": o["class_id"], "confidence": 1.0, "bbox": o["bbox"]} for o in objetos
        ],
    }
    ocupadas = zonas_ocupadas(evento, config_anotadas)
    return [z for z in ZONAS if z in ocupadas]


def fila(
    captura: Mapping[str, Any],
    anotacion: Mapping[str, Any],
    ruta: str,
    config: ConfigPolitica,
) -> dict[str, Any]:
    zonas = zonas_de(anotacion, config)
    return {
        "frame_id": captura["frame_id"],
        "sequence_id": captura["sequence_id"],
        "t_relativo_ms": captura["t_capture_ms"],
        "ruta": ruta,
        "sha256": captura["sha256"],
        "image_width": captura["image_width"],
        "image_height": captura["image_height"],
        "split": SPLIT,
        "estado_esperado": "obstaculo" if anotacion["objetos"] else "despejado",
        "objetos": len(anotacion["objetos"]),
        "zonas_ocupadas": zonas,
        "procedencia": PROCEDENCIA,
        "hueco_intencional": False,
    }


def _fila_de_captura(
    captura: Mapping[str, Any],
    registro: Path,
    anotacion: Mapping[str, Any] | None,
    raiz: Path,
    config: ConfigPolitica,
) -> dict[str, Any]:
    frame, archivo = captura["frame_id"], captura["archivo"]
    if anotacion is None:
        raise ErrorManifiesto([f"{frame}: el cuadro no tiene anotación"])
    if not isinstance(archivo, str) or not PATRON_ARCHIVO.fullmatch(archivo):
        raise ErrorManifiesto([f"{frame}: archivo {archivo!r} no es un nombre de cuadro válido"])
    relativa = ruta_relativa(registro.parent / archivo, raiz)
    if relativa is None:
        raise ErrorManifiesto([f"{frame}: el cuadro queda fuera de la raíz del repo"])
    return fila(captura, anotacion, relativa, config)


def construir(
    cuadros: Path,
    anotaciones: list[dict[str, Any]],
    raiz: Path = RAIZ,
    config: ConfigPolitica | None = None,
) -> list[dict[str, Any]]:
    """Una fila por cuadro capturado, en orden de secuencia y de captura.

    Lanza `ErrorManifiesto` si una anotación no es válida (cajas fuera de la imagen o `frame_id`
    repetido, entre otras: las zonas se calculan de ellas), si un cuadro no tiene anotación o una
    anotación no tiene cuadro: los despejados también se anotan (con `objetos: []`), así que debe
    haber una de cada uno. También si un `frame_id` se repite en la captura, o si `archivo` no es
    un nombre suelto o el cuadro queda fuera de `raiz`, por ejemplo por un enlace simbólico: el
    manifiesto lleva rutas relativas para que su hash no dependa de la computadora.
    """
    errores = validar_anotaciones(anotaciones)
    if errores:
        raise ErrorManifiesto(errores)
    config = config or cargar_config_politica()
    por_frame = {a["frame_id"]: a for a in anotaciones}
    filas, vistos = [], set()
    for registro in sorted(cuadros.glob("*/captura.jsonl")):
        for captura in leer_jsonl(registro):
            frame = captura["frame_id"]
            if frame in vistos:
                errores.append(f"{frame}: frame_id repetido en la captura")
                continue
            vistos.add(frame)
            try:
                filas.append(
                    _fila_de_captura(captura, registro, por_frame.get(frame), raiz, config)
                )
            except ErrorManifiesto as exc:
                errores += exc.errores
    errores += [
        f"{f}: la anotación no tiene cuadro capturado" for f in sorted(set(por_frame) - vistos)
    ]
    if errores:
        raise ErrorManifiesto(errores)
    return filas
