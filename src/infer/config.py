"""Carga y hash de los parámetros efectivos de YOLO11n en CPU (P5-05).

Ultralytics 8.3.0, con un checkpoint .pt y batch 1, usa LetterBox(auto=True)
independientemente de ``rect``. Los valores no ajustables aquí se validan contra
ese comportamiento; ``imgsz``, umbrales y clases sí se pasan a ``predict``.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[2]
RUTA_CONFIG_DETECTOR = RAIZ / "config" / "detector.json"

_SHA_P5_04 = "0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1"
_VERSIONES = {
    "ultralytics": "8.3.0",
    "torch": "2.9.0",
    "torchvision": "0.24.0",
    "opencv-python": "4.11.0.86",
    "numpy": "1.26.4",
}
_MODELO = {"name": "YOLO11n", "backend": "pytorch_pt"}
_EJECUCION = {
    "device": "cpu",
    "dtype": "float32",
    "batch": 1,
    "torch_threads": 1,
    "augment": False,
}
_PREPROCESO = {
    "decoder": "cv2.imread_IMREAD_COLOR",
    "input_channels": "BGR",
    "model_channels": "RGB",
    "layout": "BCHW",
    "letterbox": "minimum_rectangle_auto",
    "stride": 32,
    "scale_fill": False,
    "scaleup": True,
    "center": True,
    "padding_value": 114,
    "interpolation": "cv2.INTER_LINEAR",
    "normalization_divisor": 255,
}
_POSPROCESO = {
    "agnostic_nms": False,
    "bbox_format": "xyxy",
    "bbox_unit": "px",
    "coordinates": "original",
    "clip_boxes": True,
}
_CLASES_APROBADAS = {39, 41}


class ErrorConfigDetector(ValueError):
    """Configuración incompatible con la ruta de predicción verificada de P5-04."""


@dataclass(frozen=True)
class ConfigDetector:
    """Configuración validada; los bytes canónicos no incluyen rutas ni artefactos."""

    _bytes_canonicos: bytes
    weights_path: Path
    expected_model_sha256: str

    @property
    def effective(self) -> dict[str, Any]:
        """Devuelve una copia, de modo que un consumidor no altere el hash."""
        return json.loads(self._bytes_canonicos)

    @property
    def config_sha256(self) -> str:
        return hashlib.sha256(self._bytes_canonicos).hexdigest()

    def predict_kwargs(self) -> dict[str, Any]:
        """Opciones que Ultralytics 8.3.0 sí usa en ``YOLO.predict``.

        ``torch.set_num_threads(config.torch_threads)`` debe ejecutarse antes de
        cargar/inferir; el paso 2 comprobará también backend .pt y stride 32.
        """
        efectivo = self.effective
        ejecucion = efectivo["execution"]
        pre = efectivo["preprocess"]
        post = efectivo["postprocess"]
        return {
            "device": ejecucion["device"],
            "half": ejecucion["dtype"] != "float32",
            "batch": ejecucion["batch"],
            "augment": ejecucion["augment"],
            "imgsz": pre["imgsz"],
            "conf": post["confidence"],
            "iou": post["nms_iou"],
            "agnostic_nms": post["agnostic_nms"],
            "max_det": post["max_det"],
            "classes": post["class_ids"],
        }

    @property
    def torch_threads(self) -> int:
        return self.effective["execution"]["torch_threads"]


def _claves(datos: Any, esperadas: set[str], seccion: str) -> dict[str, Any]:
    if not isinstance(datos, dict) or set(datos) != esperadas:
        raise ErrorConfigDetector(
            f"{seccion}: se requieren exactamente las claves {sorted(esperadas)}"
        )
    return datos


def _constantes(datos: dict[str, Any], esperados: dict[str, Any], seccion: str) -> None:
    for clave, esperado in esperados.items():
        valor = datos[clave]
        if type(valor) is not type(esperado) or valor != esperado:
            raise ErrorConfigDetector(f"{seccion}.{clave}: se requiere {esperado!r}")


def _numero_unitario(valor: Any, nombre: str) -> float:
    if (
        not isinstance(valor, (int, float))
        or isinstance(valor, bool)
        or not math.isfinite(valor)
        or not 0 <= valor <= 1
    ):
        raise ErrorConfigDetector(f"{nombre}: se requiere número finito entre 0 y 1")
    return float(valor)


def _entero_positivo(valor: Any, nombre: str) -> int:
    if type(valor) is not int or valor < 1:
        raise ErrorConfigDetector(f"{nombre}: se requiere entero positivo")
    return valor


def validar_config_detector(datos: Any, *, raiz: Path = RAIZ) -> ConfigDetector:
    """Valida estructura, runtime y combinaciones; normaliza los parámetros efectivos."""
    raiz_config = _claves(datos, {"artifacts", "effective"}, "config")
    artefactos = _claves(
        raiz_config["artifacts"], {"weights_path", "expected_model_sha256"}, "artifacts"
    )
    ruta = artefactos["weights_path"]
    if not isinstance(ruta, str) or not ruta.strip():
        raise ErrorConfigDetector("artifacts.weights_path: se requiere una ruta no vacía")
    sha = artefactos["expected_model_sha256"]
    if sha != _SHA_P5_04:
        raise ErrorConfigDetector("artifacts.expected_model_sha256: no coincide con P5-04")

    efectivo = _claves(
        raiz_config["effective"],
        {"model", "runtime", "execution", "preprocess", "postprocess"},
        "effective",
    )
    modelo = _claves(efectivo["model"], set(_MODELO), "model")
    _constantes(modelo, _MODELO, "model")
    runtime = _claves(efectivo["runtime"], set(_VERSIONES), "runtime")
    _constantes(runtime, _VERSIONES, "runtime")
    ejecucion = _claves(efectivo["execution"], set(_EJECUCION), "execution")
    _constantes(ejecucion, _EJECUCION, "execution")

    pre = _claves(efectivo["preprocess"], set(_PREPROCESO) | {"imgsz"}, "preprocess")
    _constantes(pre, _PREPROCESO, "preprocess")
    imgsz = _entero_positivo(pre["imgsz"], "preprocess.imgsz")
    if imgsz < 32 or imgsz > 4096 or imgsz % pre["stride"]:
        raise ErrorConfigDetector(
            "preprocess.imgsz: debe estar entre 32 y 4096 y ser múltiplo de 32"
        )

    post = _claves(
        efectivo["postprocess"],
        set(_POSPROCESO) | {"confidence", "nms_iou", "max_det", "class_ids"},
        "postprocess",
    )
    _constantes(post, _POSPROCESO, "postprocess")
    conf = _numero_unitario(post["confidence"], "postprocess.confidence")
    iou = _numero_unitario(post["nms_iou"], "postprocess.nms_iou")
    max_det = _entero_positivo(post["max_det"], "postprocess.max_det")
    clases = post["class_ids"]
    if (
        not isinstance(clases, list)
        or not clases
        or any(type(clase) is not int for clase in clases)
        or len(set(clases)) != len(clases)
        or not set(clases) <= _CLASES_APROBADAS
    ):
        raise ErrorConfigDetector("postprocess.class_ids: subconjunto no vacío de [39, 41]")

    normalizado = {
        "model": modelo,
        "runtime": runtime,
        "execution": ejecucion,
        "preprocess": {**pre, "imgsz": imgsz},
        "postprocess": {
            **post,
            "confidence": conf,
            "nms_iou": iou,
            "max_det": max_det,
            "class_ids": sorted(clases),
        },
    }
    try:
        canonico = json.dumps(
            normalizado, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ErrorConfigDetector(f"effective: no se pudo serializar: {exc}") from exc
    pesos = Path(ruta)
    if not pesos.is_absolute():
        pesos = raiz / pesos
    return ConfigDetector(canonico, pesos, sha)


def _rechazar_constante(valor: str) -> None:
    raise ErrorConfigDetector(f"JSON no permite {valor}")


def cargar_config_detector(ruta: str | Path = RUTA_CONFIG_DETECTOR) -> ConfigDetector:
    """Carga JSON estricto. Una ruta de pesos relativa se resuelve desde la raíz del repo."""
    try:
        datos = json.loads(
            Path(ruta).read_text(encoding="utf-8"), parse_constant=_rechazar_constante
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ErrorConfigDetector(f"no se pudo leer config del detector: {exc}") from exc
    return validar_config_detector(datos)


def verificar_versiones_runtime(config: ConfigDetector) -> None:
    """Falla si el entorno instalado no coincide con las versiones del hash."""
    if sys.version_info[:2] != (3, 12):
        raise ErrorConfigDetector("se requiere Python 3.12")
    for paquete, esperada in config.effective["runtime"].items():
        try:
            instalada = version(paquete)
        except PackageNotFoundError as exc:
            raise ErrorConfigDetector(f"falta el paquete {paquete}") from exc
        # La rueda oficial CPU de Linux añade una versión local (+cpu o hash).
        if instalada.partition("+")[0] != esperada:
            raise ErrorConfigDetector(f"{paquete}: instalado {instalada}, se requiere {esperada}")
