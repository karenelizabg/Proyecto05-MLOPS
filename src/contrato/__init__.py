"""Contratos de percepción A → B y de comando B → adaptador. Ver config/contrato/CONTRATO.md."""

from .comando import RUTA_ESQUEMA_COMANDO, validar_comando
from .validador import RUTA_ESQUEMA, leer_eventos, validar_evento, validar_flujo

__all__ = [
    "RUTA_ESQUEMA",
    "RUTA_ESQUEMA_COMANDO",
    "leer_eventos",
    "validar_comando",
    "validar_evento",
    "validar_flujo",
]
