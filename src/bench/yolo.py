"""El detector de P5-05 (YOLO11n) con la forma que pide el arnés (P5-15).

    python -m bench --detector bench.yolo --opcion pesos=<ruta>/yolo11n.pt ...

Envuelve `infer.detector.DetectorJPEG` sin cambiar su configuración ni sus validaciones: el mismo
predictor, el mismo NMS y las mismas revisiones de la salida cruda y de las cajas finales. Solo
separa en etapas lo que `DetectorJPEG.inferir` hace de una vez, para cronometrarlas por separado:

- `leer`: decodifica el JPEG (no se cronometra, igual que en el arnés).
- `preprocesar`: letterbox a 640 y tensor BCHW (`predictor.preprocess`).
- `inferir`: la red (`predictor.inference`).
- `posprocesar`: revisión de la salida cruda, NMS, cajas a píxeles del cuadro original y filtro
  de clases (`predictor.postprocess` y `_extraer_detecciones`).

Al crearlo se llama a `DetectorJPEG.calentar()`, porque Ultralytics fija el tamaño de entrada en su
primera llamada. Esa llamada no cuenta: el arnés hace sus propios calentamientos.

Hilos: los fija `DetectorJPEG` con `torch_threads` de `config/detector.json`, que entra en el
`config_sha256`. No hay opción para cambiarlos aquí: una medición con otros hilos sería de otra
configuración con el mismo hash. Si después de calentar no son los de la configuración, falla.
"""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch

from infer.config import RUTA_CONFIG_DETECTOR, cargar_config_detector
from infer.detector import DetectorJPEG, ErrorSalidaInvalida, _extraer_detecciones
from infer.pesos import cargar_pesos

PAQUETES = ("ultralytics", "torch", "torchvision", "opencv-python", "numpy")


class DetectorYOLO:
    def __init__(self, pesos: Path, config: Path = RUTA_CONFIG_DETECTOR):
        self.ruta_pesos = Path(pesos)
        self.ruta_config = Path(config)
        configuracion = cargar_config_detector(self.ruta_config)
        self._detector = DetectorJPEG(cargar_pesos(self.ruta_pesos, configuracion), configuracion)
        self.model_sha256 = self._detector.cargado.model_sha256
        self.config_sha256 = configuracion.config_sha256
        self._predictor = self._detector.predictor
        self._tensor: torch.Tensor | None = None
        self.hilos_configurados = configuracion.torch_threads
        self._detector.calentar()
        if torch.get_num_threads() != self.hilos_configurados:
            raise ValueError(
                f"torch usa {torch.get_num_threads()} hilos y la configuración pide "
                f"{self.hilos_configurados}"
            )

    def descripcion(self) -> dict[str, Any]:
        return {
            "detector": "YOLO11n (P5-05, infer.detector.DetectorJPEG)",
            "config": self.ruta_config.name,
            "versiones": {p: version(p) for p in PAQUETES},
            "hilos_torch": torch.get_num_threads(),
            "hilos_configurados": self.hilos_configurados,
            "dispositivo": str(self._predictor.model.device),
        }

    def leer(self, ruta: Path) -> np.ndarray:
        try:
            imagen = cv2.imread(str(ruta), cv2.IMREAD_COLOR)
        except cv2.error as exc:
            # En Windows, Ultralytics cambia imread por imdecode, que truena con un archivo vacío.
            raise ValueError(f"{ruta} no se pudo decodificar: {exc}") from exc
        if imagen is None or imagen.ndim != 3 or imagen.shape[2] != 3:
            raise ValueError(f"{ruta} no es un JPEG legible")
        return imagen

    def dimensiones(self, imagen: np.ndarray) -> tuple[int, int]:
        alto, ancho = imagen.shape[:2]
        return ancho, alto

    def preprocesar(self, imagen: np.ndarray) -> torch.Tensor:
        with torch.inference_mode():
            # posprocesar necesita la forma del tensor tras el letterbox para regresar las cajas
            # a píxeles del cuadro original.
            self._tensor = self._predictor.preprocess([imagen])
        return self._tensor

    def inferir(self, tensor: torch.Tensor) -> Any:
        with torch.inference_mode():
            return self._predictor.inference(tensor)

    def posprocesar(self, salida: Any, imagen: np.ndarray) -> list[dict[str, Any]]:
        ancho, alto = self.dimensiones(imagen)
        with torch.inference_mode():
            resultados = self._predictor.postprocess(salida, self._tensor, [imagen])
        if len(resultados) != 1:
            raise ErrorSalidaInvalida("el predictor no devolvió exactamente un cuadro")
        detecciones = _extraer_detecciones(resultados[0], ancho, alto, self._detector.clases)
        return [
            {"class_id": d.class_id, "confidence": d.confidence, "bbox": list(d.bbox)}
            for d in detecciones
        ]


def crear(pesos: str, config: str | None = None) -> DetectorYOLO:
    return DetectorYOLO(Path(pesos), Path(config) if config else RUTA_CONFIG_DETECTOR)
