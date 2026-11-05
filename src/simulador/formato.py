"""Único punto del simulador que conoce el protocolo PC → carro (docs/carro/protocolo.md).

El resto de `simulador` importa de aquí y no de `carro.protocolo`. Si el protocolo sube de
versión, solo se toca este archivo. Las reglas (sesión, secuencia, rangos, paro automático,
techo de PWM) son las de `Placa`, el modelo de referencia del firmware: el simulador no las
repite, las envuelve en un socket. Del lado de la PC, el puente de la matriz de fallos usa el
emisor de P5-20 (`Emisor`), también desde aquí.
"""

from __future__ import annotations

from carro.emisor import Emisor
from carro.protocolo import (
    MINIMO_PWM,
    PUERTO,
    TECHO_PWM,
    TOPE_VIGENCIA_MS,
    Orden,
    Placa,
    Respuesta,
    codificar_respuesta,
)

__all__ = [
    "MINIMO_PWM",
    "PUERTO",
    "TECHO_PWM",
    "TOPE_VIGENCIA_MS",
    "Emisor",
    "Orden",
    "Placa",
    "Respuesta",
    "codificar_respuesta",
    "frenar",
    "orden_de_comando",
]


def frenar(placa: Placa) -> None:
    """Apaga los motores como al perder el WiFi (`WiFi.status() != WL_CONNECTED`).

    El protocolo pide frenar de inmediato en ese caso, pero `Placa` no lo modela porque no
    tiene red. Es la única regla del firmware que el simulador agrega por fuera.
    """
    placa._frenar()


def orden_de_comando(emisor: Emisor, comando: dict, vigencia_ms: int) -> Orden:
    """La siguiente orden del emisor para un comando del contrato (`comando.v1`).

    `action` es la acción, `speed` la velocidad y `steering` el giro (negativo = izquierda),
    igual que en la tabla de campos de docs/carro/protocolo.md. La vigencia no puede pasar del
    tope de la placa.
    """
    return emisor.orden(
        comando["action"],
        float(comando["speed"]),
        float(comando["steering"]),
        min(int(vigencia_ms), TOPE_VIGENCIA_MS),
    )
