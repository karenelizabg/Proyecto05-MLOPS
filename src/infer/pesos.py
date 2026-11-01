"""Carga local de YOLO11n con SHA-256 comprobado antes de deserializar."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ConfigDetector, verificar_versiones_runtime

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_BLOQUE = 1024 * 1024
_CARGA_LOCK = threading.Lock()


class ErrorCargaPesos(RuntimeError):
    """El checkpoint local no se pudo verificar o cargar de forma segura."""


@dataclass(frozen=True)
class ModeloCargado:
    """Modelo en memoria y hashes independientes para el contrato A→B."""

    modelo: Any
    model_sha256: str
    config_sha256: str


def _abrir_checkpoint(ruta: Path):
    """Abre el archivo local sin seguir enlaces simbólicos cuando el SO lo permite."""
    if ruta.suffix.lower() != ".pt":
        raise ErrorCargaPesos(f"checkpoint local inválido (se requiere .pt): {ruta}")
    if ruta.is_symlink():
        raise ErrorCargaPesos(f"el checkpoint no puede ser un enlace simbólico: {ruta}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(ruta, flags)
    except OSError as exc:
        raise ErrorCargaPesos(f"no se pudo abrir el checkpoint local {ruta}: {exc}") from exc
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ErrorCargaPesos(f"el checkpoint no es un archivo regular: {ruta}")
        return os.fdopen(descriptor, "rb")
    except BaseException as exc:
        os.close(descriptor)
        if isinstance(exc, OSError):
            raise ErrorCargaPesos(f"no se pudo inspeccionar el checkpoint {ruta}: {exc}") from exc
        raise


def _copiar_y_calcular_sha256(origen: Path, copia: Path) -> str:
    """Calcula el hash de los mismos bloques que escribe en la copia privada."""
    digest = hashlib.sha256()
    with _abrir_checkpoint(origen) as fuente:
        try:
            descriptor = os.open(copia, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as destino:
                for bloque in iter(lambda: fuente.read(_BLOQUE), b""):
                    digest.update(bloque)
                    destino.write(bloque)
                destino.flush()
                os.fsync(destino.fileno())
        except OSError as exc:
            raise ErrorCargaPesos(
                f"no se pudo leer o copiar el checkpoint {origen}: {exc}"
            ) from exc
    return digest.hexdigest()


def _construir_yolo(ruta_verificada: Path, config: ConfigDetector):
    """Carga la copia local y bloquea el resolvedor de descargas de pesos."""
    os.environ["YOLO_AUTOINSTALL"] = "false"
    import torch
    from ultralytics import YOLO
    from ultralytics.utils import checks, downloads

    checks.AUTOINSTALL = False
    torch.set_num_threads(config.torch_threads)

    def solo_copia_verificada(archivo: str | Path, *args: Any, **kwargs: Any) -> str:
        candidato = Path(archivo)
        if candidato != ruta_verificada or not candidato.is_file():
            raise ErrorCargaPesos("descarga automática de pesos prohibida")
        return str(candidato)

    # torch_safe_load importa este resolvedor durante la deserialización. La
    # sustitución temporal impide que una desaparición de la copia active red.
    with _CARGA_LOCK:
        original = downloads.attempt_download_asset
        downloads.attempt_download_asset = solo_copia_verificada
        try:
            return YOLO(str(ruta_verificada), task="detect", verbose=False)
        finally:
            downloads.attempt_download_asset = original


def _preparar_cpu(modelo: Any, config: ConfigDetector) -> None:
    """Comprueba que los pesos corresponden a detección COCO y activa CPU/FP32/eval."""
    import torch

    if modelo.task != "detect" or not isinstance(modelo.model, torch.nn.Module):
        raise ErrorCargaPesos("el checkpoint verificado no es un detector PyTorch")
    red = modelo.model.to(torch.device("cpu")).float().eval()
    if int(red.stride.max()) != config.effective["preprocess"]["stride"]:
        raise ErrorCargaPesos("el stride del checkpoint no coincide con la configuración")
    if modelo.names[39] != "bottle" or modelo.names[41] != "cup":
        raise ErrorCargaPesos("las clases del checkpoint no coinciden con P5-04")
    parametro = next(red.parameters(), None)
    if parametro is None or parametro.device.type != "cpu" or parametro.dtype != torch.float32:
        raise ErrorCargaPesos("el detector no quedó en CPU y FP32")
    if red.training:
        raise ErrorCargaPesos("el detector no quedó en modo de evaluación")


def cargar_pesos(ruta: str | Path, config: ConfigDetector) -> ModeloCargado:
    """Verifica bytes locales, carga la copia privada y devuelve el SHA real.

    La copia vive en un directorio temporal exclusivo. Un cambio del archivo
    original después de leerlo no cambia los bytes entregados a Ultralytics.
    """
    esperado = config.expected_model_sha256
    if not isinstance(esperado, str) or _SHA256.fullmatch(esperado) is None:
        raise ErrorCargaPesos("el SHA-256 esperado debe tener 64 hexadecimales minúsculos")
    try:
        origen = Path(ruta)
    except (TypeError, ValueError) as exc:
        raise ErrorCargaPesos("se requiere una ruta local explícita al checkpoint") from exc

    with tempfile.TemporaryDirectory(prefix="p5-05-checkpoint-") as temporal:
        copia = Path(temporal) / "yolo11n-verificado.pt"
        actual = _copiar_y_calcular_sha256(origen, copia)
        if actual != esperado:
            raise ErrorCargaPesos(
                f"SHA-256 del checkpoint no coincide: esperado {esperado}, obtenido {actual}"
            )
        verificar_versiones_runtime(config)
        try:
            modelo = _construir_yolo(copia, config)
            _preparar_cpu(modelo, config)
        except ErrorCargaPesos:
            raise
        except Exception as exc:
            raise ErrorCargaPesos(f"falló la carga del checkpoint verificado: {exc}") from exc
    return ModeloCargado(modelo, actual, config.config_sha256)
