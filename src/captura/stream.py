"""Lectura del stream MJPEG de la ESP32-CAM y selección de cuadros. Sin red ni archivos: el
comando (`python -m captura`) abre la conexión y escribe; aquí todo se prueba con bytes.

El firmware del carro manda, por cada cuadro, un encabezado con `Content-Length`, los bytes del
JPEG y una línea con el separador (`--123456789000000000000987654321`). Los bytes se guardan tal
como llegan, sin recomprimir, para que el SHA-256 sea estable (P5-09).

Un stream defectuoso no puede colgar la filmación: los encabezados y los cuadros tienen un tamaño
máximo y la captura entera un tiempo máximo.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import BinaryIO

from PIL import Image

# Marcadores SOF que traen el tamaño de la imagen (todos menos DHT C4, JPG C8 y DAC CC).
_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}

MAX_LINEA = 1024  # una línea de encabezado o el separador
MAX_ENCABEZADO = 8 * 1024  # todo lo que va entre un JPEG y el siguiente
MAX_CUADRO = 1024 * 1024  # un VGA del ESP32 pesa entre 20 y 60 KB


class StreamDefectuoso(ValueError):
    """El stream no sigue el formato del firmware; la captura se detiene con este motivo."""


def _leer_encabezado(flujo: BinaryIO) -> int | None:
    """`Content-Length` del siguiente cuadro; None si el stream termina antes."""
    largo = None
    leidos = 0
    while True:
        linea = flujo.readline(MAX_LINEA + 1)
        if not linea:
            return None
        leidos += len(linea)
        if len(linea) > MAX_LINEA or leidos > MAX_ENCABEZADO:
            raise StreamDefectuoso(f"encabezado de más de {MAX_ENCABEZADO} bytes sin cuadro")
        texto = linea.strip()
        if not texto:
            if largo is not None:
                return largo
            continue
        nombre, _, valor = texto.partition(b":")
        if nombre.strip().lower() == b"content-length":
            valor = valor.strip()
            if not valor.isdigit():
                raise StreamDefectuoso(f"Content-Length no numérico: {valor[:20]!r}")
            largo = int(valor)


def leer_partes(flujo: BinaryIO, max_cuadro: int = MAX_CUADRO) -> Iterator[bytes]:
    """Devuelve los bytes de cada JPEG del stream, en orden, y termina si el stream se corta.

    Si el último cuadro llega a medias también se devuelve lo que llegó, para que quede
    registrado entre los rechazados. Un encabezado demasiado largo, un `Content-Length` no
    numérico o mayor que `max_cuadro` lanzan `StreamDefectuoso`.
    """
    while True:
        largo = _leer_encabezado(flujo)
        if largo is None:
            return
        if largo > max_cuadro:
            raise StreamDefectuoso(f"Content-Length de {largo} bytes (máximo {max_cuadro})")
        datos = flujo.read(largo)
        yield datos
        if len(datos) < largo:
            return


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


def _tiene_soi_y_eoi(datos: bytes) -> bool:
    """El ESP32 a veces deja relleno después del EOI: se acepta."""
    return datos.startswith(b"\xff\xd8") and datos.rfind(b"\xff\xd9") > 1


def _decodifica(datos: bytes) -> bool:
    """Pillow decodifica la imagen entera (un JPEG truncado o sin scan falla)."""
    try:
        with Image.open(io.BytesIO(datos)) as imagen:
            if imagen.format != "JPEG":
                return False
            imagen.load()
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        return False
    return True


def jpeg_completo(datos: bytes) -> bool:
    """Empieza con SOI, trae EOI y se decodifica completo."""
    return _tiene_soi_y_eoi(datos) and _decodifica(datos)


def motivo_rechazo(datos: bytes, tamano: tuple[int, int]) -> str | None:
    """Por qué estos bytes no sirven como cuadro de `tamano`; None si sirven.

    El tamaño se revisa en el encabezado antes de decodificar, para no gastar memoria en una
    imagen enorme.
    """
    if not _tiene_soi_y_eoi(datos):
        return "jpeg_incompleto"
    dims = dimensiones_jpeg(datos)
    if dims != tamano:
        return f"tamano_{dims[0]}x{dims[1]}" if dims else "sin_sof"
    if not _decodifica(datos):
        return "jpeg_no_decodifica"
    return None


@dataclass(frozen=True)
class Cuadro:
    datos: bytes
    t_ms: float  # desde el primer cuadro guardado de la secuencia, tal como se midió
    ancho: int
    alto: int

    @property
    def t_capture_ms(self) -> int:
        """El tiempo que va en captura.jsonl."""
        return round(self.t_ms)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.datos).hexdigest()


@dataclass
class Captura:
    cuadros: list[Cuadro] = field(default_factory=list)
    # (motivo, bytes) de lo que llegó del stream y no se guardó como cuadro; solo los primeros
    # `max_rechazados`, los demás solo se cuentan.
    rechazados: list[tuple[str, bytes]] = field(default_factory=list)
    rechazados_sin_guardar: int = 0
    duplicados: int = 0
    tiempo_agotado: bool = False
    error: str | None = None  # el stream falló o no sigue el formato


def capturar(
    partes: Iterable[bytes],
    reloj_ms: Callable[[], float],
    cuadros: int,
    cada_ms: int,
    tamano: tuple[int, int],
    descartar: int = 2,
    limite_ms: float | None = None,
    max_rechazados: int = 20,
) -> Captura:
    """Toma `cuadros` cuadros del stream, uno cada `cada_ms` como mínimo.

    `reloj_ms` se lee una vez al empezar y luego al terminar de recibir cada cuadro: es la
    marca de tiempo real de recepción, no una calculada. Los primeros `descartar` cuadros se
    tiran porque la cámara guarda cuadros viejos en su búfer. Un JPEG que no se decodifica, de
    otro tamaño o idéntico a uno ya guardado no cuenta como cuadro. Si pasan `limite_ms` desde
    el inicio sin juntar los cuadros, se detiene con `tiempo_agotado`.
    """
    captura = Captura()
    vistos: set[str] = set()
    arranque = reloj_ms()
    inicio = ultimo = None
    try:
        for n, datos in enumerate(partes):
            ahora = reloj_ms()
            if limite_ms is not None and ahora - arranque > limite_ms:
                captura.tiempo_agotado = True
                break
            if n < descartar or (ultimo is not None and ahora - ultimo < cada_ms):
                continue
            motivo = motivo_rechazo(datos, tamano)
            if motivo:
                if len(captura.rechazados) < max_rechazados:
                    captura.rechazados.append((motivo, datos))
                else:
                    captura.rechazados_sin_guardar += 1
                continue
            cuadro_sha = hashlib.sha256(datos).hexdigest()
            if cuadro_sha in vistos:
                captura.duplicados += 1
                continue
            vistos.add(cuadro_sha)
            if inicio is None:
                inicio = ahora
            ultimo = ahora
            captura.cuadros.append(Cuadro(datos, ahora - inicio, *tamano))
            if len(captura.cuadros) == cuadros:
                break
    except (StreamDefectuoso, OSError) as exc:
        captura.error = str(exc) or type(exc).__name__
    return captura


def huecos_excedidos(cuadros: list[Cuadro], maximo_ms: int) -> list[tuple[int, float]]:
    """(índice del cuadro, hueco en ms) donde el hueco con el anterior llega a `maximo_ms`.

    El requisito es un hueco menor que el máximo. Se revisa con el tiempo medido y con el
    redondeado de captura.jsonl, para que el redondeo no esconda un hueco en ninguno de los dos.
    """
    excedidos = []
    for i in range(1, len(cuadros)):
        medido = cuadros[i].t_ms - cuadros[i - 1].t_ms
        escrito = cuadros[i].t_capture_ms - cuadros[i - 1].t_capture_ms
        hueco = max(medido, escrito)
        if hueco >= maximo_ms:
            excedidos.append((i, hueco))
    return excedidos
