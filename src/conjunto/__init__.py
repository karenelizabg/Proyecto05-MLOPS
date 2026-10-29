"""Manifiesto y verificación del conjunto de evaluación (P5-11). Ver datos/DOMINIO.md."""

from .manifiesto import ErrorManifiesto, construir, zonas_de
from .verificacion import conteo, verificar

__all__ = ["ErrorManifiesto", "construir", "conteo", "verificar", "zonas_de"]
