"""Manifiesto y verificación del conjunto de evaluación (P5-11). Ver datos/DOMINIO.md."""

from .manifiesto import ErrorManifiesto, construir, zonas_de
from .verificacion import conteo, excepciones_de_hueco, verificar

__all__ = [
    "ErrorManifiesto",
    "construir",
    "conteo",
    "excepciones_de_hueco",
    "verificar",
    "zonas_de",
]
