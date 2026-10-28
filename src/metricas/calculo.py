"""Emparejamiento y métricas de detección (P5-13). Funciones puras: no leen ni escriben archivos.

Regla de emparejamiento, por cuadro: las predicciones se recorren de mayor a menor confianza y
cada una toma la caja real **aún libre** de su misma clase con mayor IoU, si ese IoU es ≥ 0.50.
Cada caja real se usa una sola vez. Lo que no se empareja es FP (predicción) o FN (objeto real);
una clase equivocada deja 1 FP y 1 FN.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

UMBRAL_IOU = 0.5

Caja = tuple[float, float, float, float]


@dataclass(frozen=True)
class Prediccion:
    class_id: int
    confidence: float
    caja: Caja


@dataclass(frozen=True)
class Objeto:
    class_id: int
    caja: Caja


@dataclass(frozen=True)
class Par:
    """Una línea del detalle: un TP (predicción + objeto), un FP o un FN."""

    tipo: str  # "TP", "FP" o "FN"
    class_id: int
    confidence: float | None = None
    iou: float | None = None
    caja_predicha: Caja | None = None
    caja_real: Caja | None = None


@dataclass(frozen=True)
class Conteo:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def __add__(self, otro: Conteo) -> Conteo:
        return Conteo(self.tp + otro.tp, self.fp + otro.fp, self.fn + otro.fn)


def a_xyxy(bbox: Sequence[float], formato: str) -> Caja:
    a, b, c, d = (float(v) for v in bbox)
    if formato == "xyxy":
        return (a, b, c, d)
    if formato == "xywh":
        return (a, b, a + c, b + d)
    raise ValueError(f"bbox_format desconocido: {formato!r}")


def iou(a: Caja, b: Caja) -> float:
    ancho = min(a[2], b[2]) - max(a[0], b[0])
    alto = min(a[3], b[3]) - max(a[1], b[1])
    if ancho <= 0 or alto <= 0:
        return 0.0
    interseccion = ancho * alto
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - interseccion
    return interseccion / union


def emparejar(
    predicciones: Sequence[Prediccion], reales: Sequence[Objeto], umbral_iou: float = UMBRAL_IOU
) -> list[Par]:
    """Empareja uno a uno las predicciones con los objetos reales de un cuadro."""
    pares: list[Par] = []
    libres = list(range(len(reales)))
    # sorted es estable: con la misma confianza manda el orden en que llegaron.
    for p in sorted(predicciones, key=lambda p: -p.confidence):
        mejor, mejor_iou = _libre_de_mayor_iou(p, reales, libres)
        if mejor is not None and mejor_iou >= umbral_iou:
            libres.remove(mejor)
            pares.append(Par("TP", p.class_id, p.confidence, mejor_iou, p.caja, reales[mejor].caja))
        else:
            # Para un FP se anota el mejor IoU que tuvo con un objeto libre de su clase (o nada).
            pares.append(Par("FP", p.class_id, p.confidence, mejor_iou, p.caja))
    pares.extend(Par("FN", reales[j].class_id, caja_real=reales[j].caja) for j in libres)
    return pares


def _libre_de_mayor_iou(
    p: Prediccion, reales: Sequence[Objeto], libres: list[int]
) -> tuple[int | None, float | None]:
    """El objeto libre de la clase de `p` con mayor IoU; (None, None) si no queda ninguno."""
    candidatos = [
        (iou(p.caja, reales[j].caja), j) for j in libres if reales[j].class_id == p.class_id
    ]
    if not candidatos:
        return None, None
    # Con el mismo IoU gana el primero en la lista de objetos.
    mejor_iou, mejor = max(candidatos, key=lambda c: (c[0], -c[1]))
    return mejor, mejor_iou


def contar(pares: Iterable[Par]) -> Conteo:
    tipos = [p.tipo for p in pares]
    return Conteo(tipos.count("TP"), tipos.count("FP"), tipos.count("FN"))


def _proporcion(numerador: int, denominador: int) -> Fraction | None:
    return Fraction(numerador, denominador) if denominador else None


def metricas(conteo: Conteo) -> dict[str, Any]:
    """P/R/F1. Con denominador cero vale 0 y el nombre queda en `sin_soporte`."""
    tp, fp, fn = conteo.tp, conteo.fp, conteo.fn
    valores = {
        "precision": _proporcion(tp, tp + fp),
        "recall": _proporcion(tp, tp + fn),
        "f1": _proporcion(2 * tp, 2 * tp + fp + fn),
    }
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        **{nombre: float(v or 0) for nombre, v in valores.items()},
        "sin_soporte": [nombre for nombre, v in valores.items() if v is None],
    }


def puntaje_1_4(conteo: Conteo) -> float:
    """`floor(12 * F1) / 2`, con F1 como fracción exacta: 12 * 0.75 da 9 y no 8.999…"""
    f1 = _proporcion(2 * conteo.tp, 2 * conteo.tp + conteo.fp + conteo.fn) or Fraction(0)
    return math.floor(12 * f1) / 2
