"""Arnés de benchmark del detector (P5-15): calentamientos, mediciones por etapa y p50/p95."""

from .arnes import (
    CALENTAMIENTOS,
    ETAPAS,
    MINIMO_MEDICIONES,
    Entrada,
    ErrorBench,
    EtapaPolitica,
    FalloEjecucion,
    Medicion,
    cargar_entradas,
    ejecutar_una,
    medir,
    percentil,
    resumir_etapas,
    verificar_procedencia,
)
from .detector import Detector, DetectorFalso, FalloInyectado

__all__ = [
    "CALENTAMIENTOS",
    "ETAPAS",
    "MINIMO_MEDICIONES",
    "Detector",
    "DetectorFalso",
    "Entrada",
    "ErrorBench",
    "EtapaPolitica",
    "FalloEjecucion",
    "FalloInyectado",
    "Medicion",
    "cargar_entradas",
    "ejecutar_una",
    "medir",
    "percentil",
    "resumir_etapas",
    "verificar_procedencia",
]
