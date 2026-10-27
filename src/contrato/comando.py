"""Validador del contrato de comando B → adaptador (v1).

`validar_comando` comprueba un comando contra el esquema JSON y contra las reglas que
el esquema no puede expresar: números finitos y orden de los tiempos. Reutiliza el validador
cacheado de `validador.py`.

NaN e infinito no existen en JSON, pero en Python son `float` y pasan los rangos del esquema
(toda comparación con NaN es falsa). Por eso se revisan antes que el esquema.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .validador import RAIZ, _donde, _validador

RUTA_ESQUEMA_COMANDO = RAIZ / "config" / "contrato" / "comando.v1.schema.json"
CAMPOS_NUMERICOS = ("speed", "steering", "t_decision_ms", "t_command_ms", "valid_until_ms")


def validar_comando(comando: Any, ruta_esquema: Path = RUTA_ESQUEMA_COMANDO) -> list[str]:
    """Devuelve los errores del comando; lista vacía si cumple el contrato."""
    no_finitos = _no_finitos(comando)
    if no_finitos:
        return no_finitos
    fallos = sorted(
        _validador(ruta_esquema).iter_errors(comando),
        key=lambda e: [str(p) for p in e.absolute_path],
    )
    if fallos:
        return [f"{_donde(e)}: {e.message}" for e in fallos]
    return _reglas_semanticas(comando)


def _no_finitos(comando: Any) -> list[str]:
    if not isinstance(comando, dict):
        return []
    return [
        f"{campo}: debe ser un número finito"
        for campo in CAMPOS_NUMERICOS
        if isinstance(comando.get(campo), float) and not math.isfinite(comando[campo])
    ]


def _reglas_semanticas(comando: dict[str, Any]) -> list[str]:
    errores: list[str] = []
    if comando["t_command_ms"] < comando["t_decision_ms"]:
        errores.append("t_command_ms: no puede ser anterior a t_decision_ms")
    if comando["valid_until_ms"] < comando["t_command_ms"]:
        errores.append("valid_until_ms: no puede ser anterior a t_command_ms")
    return errores
