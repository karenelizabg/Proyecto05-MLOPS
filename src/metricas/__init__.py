"""Métricas de detección (P5-13): TP/FP/FN, precisión, recall y F1 a IoU 0.50."""

from .calculo import UMBRAL_IOU, Conteo, Objeto, Par, Prediccion, emparejar, iou, metricas
from .evaluacion import EntradaInvalida, Resultado, evaluar, validar_anotaciones

__all__ = [
    "UMBRAL_IOU",
    "Conteo",
    "EntradaInvalida",
    "Objeto",
    "Par",
    "Prediccion",
    "Resultado",
    "emparejar",
    "evaluar",
    "iou",
    "metricas",
    "validar_anotaciones",
]
