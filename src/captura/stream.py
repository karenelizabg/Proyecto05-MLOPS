"""Lectura del stream MJPEG de la ESP32-CAM y selección de cuadros. Sin red ni archivos: el
comando (`python -m captura`) abre la conexión y escribe; aquí todo se prueba con bytes.

El firmware del carro manda, por cada cuadro, un encabezado con `Content-Length`, los bytes del
JPEG y una línea con el separador (`--123456789000000000000987654321`). Los bytes se guardan tal
como llegan, sin recomprimir, para que el SHA-256 sea estable (P5-09).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import BinaryIO

# Marcadores SOF que traen el tamaño de la imagen (todos menos DHT C4, JPG C8 y DAC CC).
_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def leer_partes(flujo: BinaryIO) -> Iterator[bytes]:
    """Devuelve los bytes de cada JPEG del stream, en orden. Termina si el stream se corta."""
    while True:
        largo = None
        while True:
            linea = flujo.readline()
            if not linea:
                return
            texto = linea.strip()
            if not texto:
                if largo is not None:
                    break
                continue
            nombre, _, valor = texto.partition(b":")
            if nombre.strip().lower() == b"content-length":
                largo = int(valor.strip())
        datos = flujo.read(largo)
        if len(datos) < largo:
            return
        yield datos


def jpeg_completo(datos: bytes) -> bool:
    """Empieza con SOI y trae EOI. El ESP32 a veces deja relleno después del EOI: se acepta."""
    return datos.startswith(b"\xff\xd8") and datos.rfind(b"\xff\xd9") > 1


def dimensiones_jpeg(datos: bytes) -> tuple[int, int] | None:
    """(ancho, alto) leído del segmento SOF; None si no se encuentra."""
    i = 2
    while i + 3 < len(datos):
        if datos[i] != 0xFF:
            return None
        marcador = datos[i + 1]
        if marcador == 0xFF:  # relleno entre marcadores
            i += 1
            continue
        largo = int.from_bytes(datos[i + 2 : i + 4], "big")
        if marcador in _SOF and i + 9 <= len(datos):
            alto = int.from_bytes(datos[i + 5 : i + 7], "big")
            ancho = int.from_bytes(datos[i + 7 : i + 9], "big")
            return ancho, alto
        if marcador == 0xDA:  # empieza la imagen comprimida: ya no hay SOF
            return None
        i += 2 + largo
    return None


@dataclass(frozen=True)
class Cuadro:
    datos: bytes
    t_ms: int  # desde el primer cuadro guardado de la secuencia
    ancho: int
    alto: int

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.datos).hexdigest()


@dataclass
class Captura:
    cuadros: list[Cuadro] = field(default_factory=list)
    # (motivo, bytes) de lo que llegó del stream y no se guardó como cuadro.
    rechazados: list[tuple[str, bytes]] = field(default_factory=list)
    duplicados: int = 0


def capturar(
    partes: Iterable[bytes],
    reloj_ms: Callable[[], float],
    cuadros: int,
    cada_ms: int,
    tamano: tuple[int, int],
    descartar: int = 2,
) -> Captura:
    """Toma `cuadros` cuadros del stream, uno cada `cada_ms` como mínimo.

    `reloj_ms` se lee al terminar de recibir cada cuadro: es la marca de tiempo real de
    recepción, no una calculada. Los primeros `descartar` cuadros se tiran porque la cámara
    guarda cuadros viejos en su búfer. Un JPEG incompleto, de otro tamaño o idéntico a uno ya
    guardado no cuenta como cuadro.
    """
    captura = Captura()
    vistos: set[str] = set()
    inicio = ultimo = None
    for n, datos in enumerate(partes):
        ahora = reloj_ms()
        if n < descartar:
            continue
        if ultimo is not None and ahora - ultimo < cada_ms:
            continue
        if not jpeg_completo(datos):
            captura.rechazados.append(("jpeg_incompleto", datos))
            continue
        dims = dimensiones_jpeg(datos)
        if dims != tamano:
            captura.rechazados.append((f"tamano_{dims[0]}x{dims[1]}" if dims else "sin_sof", datos))
            continue
        cuadro_sha = hashlib.sha256(datos).hexdigest()
        if cuadro_sha in vistos:
            captura.duplicados += 1
            continue
        vistos.add(cuadro_sha)
        if inicio is None:
            inicio = ahora
        ultimo = ahora
        captura.cuadros.append(Cuadro(datos, round(ahora - inicio), *dims))
        if len(captura.cuadros) == cuadros:
            break
    return captura


def huecos_mayores(cuadros: list[Cuadro], maximo_ms: int) -> list[tuple[int, int]]:
    """(índice del cuadro, hueco en ms) donde el hueco con el anterior pasa de `maximo_ms`."""
    return [
        (i, cuadros[i].t_ms - cuadros[i - 1].t_ms)
        for i in range(1, len(cuadros))
        if cuadros[i].t_ms - cuadros[i - 1].t_ms > maximo_ms
    ]
