"""Captura de secuencias desde el stream de la ESP32-CAM (P5-09). Ver datos/DOMINIO.md."""

from .stream import (
    Captura,
    Cuadro,
    StreamDefectuoso,
    capturar,
    dimensiones_jpeg,
    huecos_excedidos,
    jpeg_completo,
    leer_partes,
    motivo_rechazo,
)

__all__ = [
    "Captura",
    "Cuadro",
    "StreamDefectuoso",
    "capturar",
    "dimensiones_jpeg",
    "huecos_excedidos",
    "jpeg_completo",
    "leer_partes",
    "motivo_rechazo",
]
