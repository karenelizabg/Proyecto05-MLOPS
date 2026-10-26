"""Política del grupo B: de un evento de percepción a una decisión.

T08 (#28): `zonas_ocupadas` dice en qué zonas (izquierda, centro, derecha) hay obstáculo.
Las decisiones AVANZAR / GIRAR / STOP (T09-T11) se construyen encima de esta función.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .config import ZONAS, ConfigPolitica


def caja_a_xyxy(bbox: Sequence[float], bbox_format: str) -> tuple[float, float, float, float]:
    """Convierte una caja del contrato a `(x1, y1, x2, y2)` en píxeles.

    `xyxy` = [x1, y1, x2, y2]; `xywh` = [x, y, ancho, alto] con (x, y) la esquina superior
    izquierda (origen arriba a la izquierda, x hacia la derecha; CONTRATO.md).
    """
    a, b, c, d = (float(v) for v in bbox)
    if bbox_format == "xyxy":
        return a, b, c, d
    if bbox_format == "xywh":
        return a, b, a + c, b + d
    raise ValueError(f"bbox_format desconocido: {bbox_format!r} (se espera 'xyxy' o 'xywh')")


def _zonas_de_caja(x1: float, x2: float, ancho: float, config: ConfigPolitica) -> set[str]:
    """Zonas que ocupa una caja horizontal [x1, x2] en una imagen de `ancho` píxeles."""
    # A ya recorta las cajas a la imagen; se recorta otra vez por seguridad.
    x1, x2 = max(0.0, min(x1, ancho)), max(0.0, min(x2, ancho))
    ancho_caja = x2 - x1
    ocupadas: set[str] = set()
    if ancho_caja <= 0:
        # El contrato exige ancho y alto positivos (validar_evento lo rechaza antes).
        return ocupadas
    for nombre in ZONAS:
        inicio, fin = config.zonas[nombre]
        z1, z2 = inicio * ancho, fin * ancho
        traslape = min(x2, z2) - max(x1, z1)
        if traslape > 0 and traslape / ancho_caja >= config.traslape_minimo:
            ocupadas.add(nombre)
    return ocupadas


def zonas_ocupadas(evento: Mapping[str, Any], config: ConfigPolitica) -> set[str]:
    """Devuelve el conjunto de zonas con obstáculo: subconjunto de {'izq', 'centro', 'der'}.

    - Solo cuentan detecciones con `class_id` en `clases_obstaculo` y
      `confidence >= umbral_confianza`. Se decide con `class_id`, nunca con `class_name`.
    - Los límites de zona se calculan con `image_width` DEL EVENTO, nunca con un ancho fijo.
    - Una caja ocupa una zona si la fracción de SU ancho que cae en la zona es
      `>= traslape_minimo`; una caja ancha puede ocupar dos o tres zonas.

    Solo tiene sentido con `status=ok`. Con `stale` o `error` lanza `ValueError` en vez de
    devolver un conjunto vacío, porque vacío significaría "vía libre" y el contrato dice
    que esos estados son STOP (reglas 2 y 4). Quien llama debe revisar el `status` antes.
    El evento debe venir ya validado con `contrato.validar_evento`.
    """
    status = evento.get("status")
    if status != "ok":
        raise ValueError(
            f"zonas_ocupadas solo acepta status='ok', llegó {status!r}: stale/error son STOP"
        )
    ancho = evento["image_width"]
    if not isinstance(ancho, (int, float)) or isinstance(ancho, bool) or ancho <= 0:
        raise ValueError(f"image_width inválido: {ancho!r}")

    formato = evento["bbox_format"]
    ocupadas: set[str] = set()
    for det in evento["detections"]:
        if det["class_id"] not in config.clases_obstaculo:
            continue
        if det["confidence"] < config.umbral_confianza:
            continue
        x1, _, x2, _ = caja_a_xyxy(det["bbox"], formato)
        ocupadas |= _zonas_de_caja(x1, x2, float(ancho), config)
    return ocupadas
