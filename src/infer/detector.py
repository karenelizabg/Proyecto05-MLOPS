"""Inferencia JPEG en CPU con validación anterior al NMS de Ultralytics 8.3.0."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
from ultralytics.models.yolo.detect.predict import DetectionPredictor

from .config import ConfigDetector
from .pesos import ModeloCargado

_COCO_NCLASES = 80


class ErrorImagenJPEG(ValueError):
    """El archivo no se puede decodificar como JPEG BGR válido."""


class ErrorSalidaInvalida(ValueError):
    """Una salida del modelo no puede convertirse en detecciones confiables."""

    code = "invalid_output"


@dataclass(frozen=True)
class Deteccion:
    class_id: int
    confidence: float
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class ResultadoJPEG:
    width: int
    height: int
    tensor_shape: tuple[int, int, int, int]
    detections: tuple[Deteccion, ...]
    elapsed_ms: float
    model_sha256: str
    config_sha256: str


def _validar_prediccion_cruda(preds: Any) -> None:
    """YOLO11n .pt: BCHW de cajas xywh y 80 puntajes, antes de NMS/clipping.

    ``preds`` es [tensor(1, 84, N), mapas auxiliares] en la ruta real del
    checkpoint. La forma tensor(1, 84, N) también se acepta para evitar depender
    de los mapas auxiliares, que no participan en las detecciones.
    """
    candidato = preds[0] if isinstance(preds, (list, tuple)) and preds else preds
    if (
        not isinstance(candidato, torch.Tensor)
        or candidato.ndim != 3
        or candidato.shape[0] != 1
        or candidato.shape[1] != 4 + _COCO_NCLASES
        or candidato.dtype != torch.float32
        or candidato.device.type != "cpu"
    ):
        raise ErrorSalidaInvalida("estructura cruda incompatible con YOLO11n COCO CPU/FP32")
    if not bool(torch.isfinite(candidato).all()):
        raise ErrorSalidaInvalida("predicción cruda contiene NaN o Infinity")
    cajas = candidato[:, :4, :]
    puntajes = candidato[:, 4:, :]
    if bool((cajas[:, 2:4, :] <= 0).any()):
        raise ErrorSalidaInvalida("ancho o alto crudo no positivo")
    # NMS convierte xywh a xyxy; una suma FP32 desbordada debe fallar aquí.
    mitad = cajas[:, 2:4, :] / 2
    if not bool(torch.isfinite(cajas[:, :2, :] - mitad).all()) or not bool(
        torch.isfinite(cajas[:, :2, :] + mitad).all()
    ):
        raise ErrorSalidaInvalida("geometría cruda desborda al convertir a xyxy")
    if bool(((puntajes < 0) | (puntajes > 1)).any()):
        raise ErrorSalidaInvalida("puntaje de clase crudo fuera de [0, 1]")


class PredictorValidado(DetectionPredictor):
    """Inserta la validación justo entre la red y el NMS nativo."""

    tensor_shape: tuple[int, int, int, int] | None = None

    def preprocess(self, im):
        tensor = super().preprocess(im)
        self.tensor_shape = tuple(tensor.shape)
        return tensor

    def postprocess(self, preds, img, orig_imgs):
        _validar_prediccion_cruda(preds)
        return super().postprocess(preds, img, orig_imgs)


def _extraer_detecciones(resultado: Any, width: int, height: int, clases: set[int]):
    """Valida las cajas finales antes de filtrar clases COCO fuera del dominio."""
    if resultado.boxes is None:
        raise ErrorSalidaInvalida("resultado sin matriz de cajas")
    datos = resultado.boxes.data
    if (
        not isinstance(datos, torch.Tensor)
        or datos.ndim != 2
        or datos.shape[1] != 6
        or not datos.is_floating_point()
    ):
        raise ErrorSalidaInvalida("matriz de detecciones incompatible")
    detecciones = []
    for fila in datos.tolist():
        if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in fila):
            raise ErrorSalidaInvalida("detección contiene NaN o Infinity")
        x1, y1, x2, y2, confianza, clase = fila
        if not 0 <= confianza <= 1:
            raise ErrorSalidaInvalida("confianza fuera de [0, 1]")
        if not clase.is_integer() or not 0 <= clase < _COCO_NCLASES:
            raise ErrorSalidaInvalida("class_id fuera del catálogo COCO")
        # scale_boxes de Ultralytics ya recorta; el clamp asegura límites ante
        # diferencias mínimas de representación sin aceptar una caja degenerada.
        x1, x2 = max(0.0, min(x1, width)), max(0.0, min(x2, width))
        y1, y2 = max(0.0, min(y1, height)), max(0.0, min(y2, height))
        if x2 <= x1 or y2 <= y1:
            raise ErrorSalidaInvalida("caja degenerada tras recortar a la imagen original")
        class_id = int(clase)
        if class_id in clases:
            detecciones.append(Deteccion(class_id, confianza, (x1, y1, x2, y2)))
    return tuple(detecciones)


class DetectorJPEG:
    """Reutiliza un predictor CPU; cada llamada recibe solo píxeles BGR del JPEG."""

    def __init__(self, cargado: ModeloCargado, config: ConfigDetector):
        if cargado.config_sha256 != config.config_sha256:
            raise ValueError("config_sha256 del modelo y la configuración no coinciden")
        self.cargado = cargado
        self.config = config
        self.clases = set(config.effective["postprocess"]["class_ids"])
        self._lock = threading.Lock()
        overrides = {
            **config.predict_kwargs(),
            "save": False,
            "save_txt": False,
            "save_crop": False,
            "show": False,
            "verbose": False,
        }
        self.predictor = PredictorValidado(overrides=overrides)
        self.predictor.setup_model(model=cargado.modelo.model, verbose=False)
        if self.predictor.model.device.type != "cpu" or self.predictor.model.fp16:
            raise ValueError("el predictor debe permanecer en CPU y FP32")

    def inferir(self, ruta: str | Path) -> ResultadoJPEG:
        """Decodifica el JPEG local y ejecuta la ruta nativa de predicción."""
        archivo = Path(ruta)
        if archivo.suffix.lower() not in {".jpg", ".jpeg"}:
            raise ErrorImagenJPEG("se requiere un archivo JPEG local")
        imagen = cv2.imread(str(archivo), cv2.IMREAD_COLOR)
        if (
            imagen is None
            or not isinstance(imagen, np.ndarray)
            or imagen.ndim != 3
            or imagen.shape[2] != 3
            or imagen.dtype != np.uint8
            or imagen.shape[0] < 1
            or imagen.shape[1] < 1
        ):
            raise ErrorImagenJPEG(f"no se pudo decodificar JPEG válido: {archivo}")
        height, width = imagen.shape[:2]
        with self._lock:
            self.predictor.tensor_shape = None
            inicio = time.perf_counter()
            resultados = self.predictor(source=imagen, stream=False)
            transcurrido = (time.perf_counter() - inicio) * 1000
            if len(resultados) != 1 or self.predictor.tensor_shape is None:
                raise ErrorSalidaInvalida("el predictor no devolvió exactamente un cuadro")
            resultado = resultados[0]
            if tuple(resultado.orig_shape) != (height, width):
                raise ErrorSalidaInvalida("dimensiones originales inconsistentes")
            detecciones = _extraer_detecciones(resultado, width, height, self.clases)
            return ResultadoJPEG(
                width=width,
                height=height,
                tensor_shape=self.predictor.tensor_shape,
                detections=detecciones,
                elapsed_ms=transcurrido,
                model_sha256=self.cargado.model_sha256,
                config_sha256=self.config.config_sha256,
            )
