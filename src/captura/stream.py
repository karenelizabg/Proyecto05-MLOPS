"""Lectura del stream MJPEG de la ESP32-CAM y selección de cuadros. Sin red ni archivos: el
comando (`python -m captura`) abre la conexión y escribe; aquí todo se prueba con bytes.

El firmware del carro manda, por cada cuadro, un encabezado con `Content-Length`, los bytes del
JPEG y una línea con el separador (`--123456789000000000000987654321`). Los bytes se guardan tal
como llegan, sin recomprimir, para que el SHA-256 sea estable (P5-09).

Pillow no avisa si al JPEG le faltan datos y aun así trae EOI: rellena lo que falta de gris. Por
eso `_scan_completo` recorre el scan con las tablas de Huffman y cuenta los bloques, sin calcular
la imagen. Solo acepta lo que manda el firmware: baseline, un scan y sin marcadores de reinicio.

Un stream defectuoso no puede colgar la filmación: los encabezados y los cuadros tienen un tamaño
máximo y la captura entera un tiempo máximo.
"""

from __future__ import annotations

import hashlib
import io
import math
import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import BinaryIO

from PIL import Image

# Marcadores SOF que traen el tamaño de la imagen (todos menos DHT C4, JPG C8 y DAC CC).
_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}

MAX_LINEA = 1024  # una línea de encabezado o el separador
MAX_ENCABEZADO = 8 * 1024  # todo lo que va entre un JPEG y el siguiente
MAX_CUADRO = 1024 * 1024  # un VGA del ESP32 pesa entre 20 y 60 KB
_INICIO_SEPARADOR = b"\r\n--"  # lo que debe venir justo después de los bytes de cada cuadro
_MARCADOR_EN_SCAN = re.compile(rb"\xff[^\x00]")
_COEFICIENTES = 64  # por bloque de 8x8


class StreamDefectuoso(ValueError):
    """El stream no sigue el formato del firmware; la captura se detiene con este motivo.

    `datos` son los bytes del cuadro donde se detectó, si hay, para guardarlos como rechazados.
    """

    def __init__(self, mensaje: str, datos: bytes = b"") -> None:
        super().__init__(mensaje)
        self.datos = datos


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

    Un encabezado demasiado largo, un `Content-Length` no numérico o mayor que `max_cuadro`
    lanzan `StreamDefectuoso`. También un cuerpo que no mide lo anunciado, aunque el JPEG se
    decodifique: si llega de menos, o si después de sus bytes no sigue el separador. Ese cuadro
    no se devuelve; va en `StreamDefectuoso.datos`.
    """
    while True:
        largo = _leer_encabezado(flujo)
        if largo is None:
            return
        if largo > max_cuadro:
            raise StreamDefectuoso(f"Content-Length de {largo} bytes (máximo {max_cuadro})")
        datos = flujo.read(largo)
        if len(datos) < largo:
            raise StreamDefectuoso(
                f"el cuerpo trae {len(datos)} bytes y Content-Length anuncia {largo}", datos
            )
        # Puede terminar aquí mismo (o a medio separador) si se corta después del cuadro.
        if not _INICIO_SEPARADOR.startswith(flujo.read(len(_INICIO_SEPARADOR))):
            raise StreamDefectuoso(
                f"después de los {largo} bytes de Content-Length no sigue el separador", datos
            )
        yield datos


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


def _tablas_huffman(cuerpo: bytes) -> dict[int, dict[str, int]]:
    """Las tablas de un segmento DHT, por clase e id: {código en bits como texto: símbolo}."""
    tablas = {}
    i = 0
    while i < len(cuerpo):
        tabla = {}
        codigo = 0
        simbolo = i + 17
        for largo, cuantos in enumerate(cuerpo[i + 1 : i + 17], start=1):
            for _ in range(cuantos):
                tabla[format(codigo, f"0{largo}b")] = cuerpo[simbolo]
                codigo += 1
                simbolo += 1
            codigo <<= 1
        tablas[cuerpo[i]] = tabla
        i = simbolo
    return tablas


def _segmentos_hasta_scan(datos: bytes) -> tuple[dict, bytes, bytes, int] | None:
    """(tablas de Huffman, cuerpo del SOF0, cuerpo del SOS, dónde empieza el scan).

    None si no es baseline o trae marcadores de reinicio.
    """
    tablas: dict[int, dict[str, int]] = {}
    sof = b""
    i = 2
    while True:
        marcador = datos[i + 1]
        fin = i + 2 + int.from_bytes(datos[i + 2 : i + 4], "big")
        cuerpo = datos[i + 4 : fin]
        if marcador == 0xDA:
            return tablas, sof, cuerpo, fin
        if marcador == 0xC4:
            tablas |= _tablas_huffman(cuerpo)
        elif marcador == 0xC0:
            sof = cuerpo
        elif marcador in _SOF or (marcador == 0xDD and any(cuerpo)):
            return None
        i = fin


def _bloques_y_mcus(tablas: dict, sof: bytes, sos: bytes) -> tuple[list[tuple[dict, dict]], int]:
    """(tablas DC y AC de cada bloque de un MCU, cuántos MCU tiene la imagen)."""
    alto, ancho = int.from_bytes(sof[1:3], "big"), int.from_bytes(sof[3:5], "big")
    muestreo = {sof[j]: sof[j + 1] for j in range(6, 6 + 3 * sof[5], 3)}
    max_h = max(m >> 4 for m in muestreo.values())
    max_v = max(m & 15 for m in muestreo.values())
    bloques = []
    for j in range(1, 1 + 2 * sos[0], 2):
        dc, ac = tablas[sos[j + 1] >> 4], tablas[0x10 | (sos[j + 1] & 15)]
        bloques += [(dc, ac)] * ((muestreo[sos[j]] >> 4) * (muestreo[sos[j]] & 15))
    return bloques, math.ceil(ancho / (8 * max_h)) * math.ceil(alto / (8 * max_v))


def _simbolo(bits: str, pos: int, tabla: dict[str, int]) -> tuple[int, int]:
    """(símbolo, siguiente posición). KeyError si los bits no forman un código."""
    for largo in range(1, 17):
        simbolo = tabla.get(bits[pos : pos + largo])
        if simbolo is not None:
            return simbolo, pos + largo
    raise KeyError(pos)


def _saltar_bloque(bits: str, pos: int, dc: dict[str, int], ac: dict[str, int]) -> int:
    """Posición después de un bloque; sus valores no se calculan, solo se saltan."""
    categoria, pos = _simbolo(bits, pos, dc)
    pos += categoria
    k = 1
    while k < _COEFICIENTES:
        simbolo, pos = _simbolo(bits, pos, ac)
        ceros, categoria = simbolo >> 4, simbolo & 15
        if categoria:
            k += ceros + 1
            pos += categoria
        elif ceros == 15:
            k += 16
        else:
            break  # fin de bloque: el resto son ceros
    if k > _COEFICIENTES:
        raise KeyError(pos)
    return pos


def _scan_completo(datos: bytes) -> bool:
    """El scan trae todos los bloques de la imagen, antes del primer marcador (EOI)."""
    try:
        segmentos = _segmentos_hasta_scan(datos)
        if segmentos is None:
            return False
        tablas, sof, sos, inicio = segmentos
        if not sof or sos[0] != sof[5]:  # sin SOF0, o más de un scan
            return False
        bloques, mcus = _bloques_y_mcus(tablas, sof, sos)
        marcador = _MARCADOR_EN_SCAN.search(datos, inicio)
        scan = datos[inicio : marcador.start() if marcador else len(datos)]
        scan = scan.replace(b"\xff\x00", b"\xff")
        bits = format(int.from_bytes(scan, "big"), f"0{8 * len(scan)}b") if scan else ""
        pos = 0
        for _ in range(mcus):
            for dc, ac in bloques:
                pos = _saltar_bloque(bits, pos, dc, ac)
        return pos <= len(bits)
    except (IndexError, KeyError):
        return False


def jpeg_completo(datos: bytes) -> bool:
    """Empieza con SOI, trae EOI, se decodifica y su scan trae todos los bloques."""
    return _tiene_soi_y_eoi(datos) and _decodifica(datos) and _scan_completo(datos)


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
    if not _scan_completo(datos):
        return "jpeg_truncado"
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

    def rechazar(motivo: str, datos: bytes) -> None:
        if len(captura.rechazados) < max_rechazados:
            captura.rechazados.append((motivo, datos))
        else:
            captura.rechazados_sin_guardar += 1

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
                rechazar(motivo, datos)
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
    except StreamDefectuoso as exc:
        captura.error = str(exc)
        if exc.datos:
            rechazar("content_length", exc.datos)
    except OSError as exc:
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
