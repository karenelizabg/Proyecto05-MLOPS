"""Captura de secuencias desde el stream de la ESP32-CAM (P5-09). Ver datos/DOMINIO.md."""

from .stream import (
    Captura,
    Cuadro,
    capturar,
    dimensiones_jpeg,
    huecos_mayores,
    jpeg_completo,
    leer_partes,
)

__all__ = [
    "Captura",
    "Cuadro",
    "capturar",
    "dimensiones_jpeg",
    "huecos_mayores",
    "jpeg_completo",
    "leer_partes",
]
