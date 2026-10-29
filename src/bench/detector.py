"""Lo que el arnés le pide a un detector, y un detector falso para probarlo (P5-15).

El detector real llega con P5-05. Para medirlo, su paquete expone una fábrica `crear(**opciones)`
que devuelve un objeto con esta forma (`Detector`). El arnés llama a `leer` antes de cronometrar
(leer y decodificar la imagen no es cómputo del detector) y cronometra por separado
`preprocesar`, `inferir` y `posprocesar`.
"""

from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path
from typing import Any, Protocol


class Detector(Protocol):
    model_sha256: str
    config_sha256: str
    # Archivo de pesos: el arnés calcula su SHA-256 y su tamaño. None solo en el detector falso.
    ruta_pesos: Path | None

    def descripcion(self) -> dict[str, Any]:
        """Runtime, versiones e hilos con que corre (va tal cual a `resumen.json`)."""
        ...

    def leer(self, ruta: Path) -> Any:
        """Lee y decodifica una imagen. No se cronometra."""
        ...

    def dimensiones(self, imagen: Any) -> tuple[int, int]:
        """(ancho, alto) del cuadro original."""
        ...

    def preprocesar(self, imagen: Any) -> Any: ...

    def inferir(self, entrada: Any) -> Any: ...

    def posprocesar(self, salida: Any, imagen: Any) -> list[dict[str, Any]]:
        """Detecciones del contrato v1 (`class_id`, `confidence`, `bbox` xyxy en px)."""
        ...


class FalloInyectado(RuntimeError):
    """Falla a propósito del detector falso, para probar que el arnés la deja aparte."""


class DetectorFalso:
    """Detector de mentira: no usa pesos ni dependencias y da siempre lo mismo para la misma imagen.

    Sirve para probar el arnés sin el detector real. `fallar_en` y `salida_invalida_en` son números
    de llamada a `inferir` (empezando en 1) en los que lanza una excepción o devuelve una confianza
    NaN. Cambiar `umbral` o `nms` cambia `config_sha256`, como en el detector real.
    """

    model_sha256 = hashlib.sha256(b"mini-tesla-p5 detector falso v1").hexdigest()
    ruta_pesos = None
    ANCHO, ALTO = 640, 480

    def __init__(
        self,
        umbral: float = 0.5,
        nms: float = 0.45,
        fallar_en: frozenset[int] = frozenset(),
        salida_invalida_en: frozenset[int] = frozenset(),
    ) -> None:
        self.config = {"umbral": umbral, "nms": nms}
        texto = json.dumps(self.config, sort_keys=True).encode("utf-8")
        self.config_sha256 = hashlib.sha256(texto).hexdigest()
        self.fallar_en = fallar_en
        self.salida_invalida_en = salida_invalida_en
        self.llamadas = 0

    def descripcion(self) -> dict[str, Any]:
        return {
            "nombre": "detector falso (P5-15)",
            "runtime": f"python-{platform.python_version()}",
            "hilos": 1,
            "config": self.config,
        }

    def leer(self, ruta: Path) -> bytes:
        """No decodifica (no hay Pillow), pero rechaza lo que no es un JPEG o PNG completo."""
        datos = Path(ruta).read_bytes()
        es_jpeg = datos.startswith(b"\xff\xd8") and datos.rstrip(b"\x00").endswith(b"\xff\xd9")
        es_png = datos.startswith(b"\x89PNG\r\n\x1a\n") and b"IEND" in datos[-12:]
        if not (es_jpeg or es_png):
            raise ValueError(f"{ruta} no es un JPEG ni un PNG completo")
        return datos

    def dimensiones(self, imagen: bytes) -> tuple[int, int]:
        return self.ANCHO, self.ALTO

    def preprocesar(self, imagen: bytes) -> bytes:
        return hashlib.sha256(imagen).digest()

    def inferir(self, entrada: bytes) -> list[float]:
        self.llamadas += 1
        if self.llamadas in self.fallar_en:
            raise FalloInyectado(f"falla inyectada en la llamada {self.llamadas}")
        # Una "caja" y una confianza que dependen solo de los bytes de la imagen.
        x1, y1 = entrada[0] % 200, entrada[1] % 150
        confianza = 0.5 + entrada[2] / 510
        if self.llamadas in self.salida_invalida_en:
            confianza = float("nan")
        return [x1, y1, x1 + 200 + entrada[3] % 200, y1 + 150 + entrada[4] % 150, confianza]

    def posprocesar(self, salida: list[float], imagen: bytes) -> list[dict[str, Any]]:
        *caja, confianza = salida
        # Un NaN no se filtra: sale como la salida rota de un detector real y el arnés lo rechaza.
        if confianza < self.config["umbral"]:
            return []
        return [{"class_id": 1, "confidence": confianza, "bbox": [float(v) for v in caja]}]


def crear(**opciones: Any) -> DetectorFalso:
    """Fábrica del detector falso (`--detector falso`)."""
    return DetectorFalso(**opciones)
