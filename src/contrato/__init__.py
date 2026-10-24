"""Contrato de percepción A → B. Ver config/contrato/CONTRATO.md."""

from .validador import RUTA_ESQUEMA, leer_eventos, validar_evento, validar_flujo

__all__ = ["RUTA_ESQUEMA", "leer_eventos", "validar_evento", "validar_flujo"]
