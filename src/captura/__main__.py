"""Captura una secuencia del stream de la ESP32-CAM y guarda sus cuadros tal como llegan.

Uso:
    python -m captura --url http://192.168.0.32:81/stream --secuencia S01 [--cuadros 12] \
        [--cada-ms 200] [--limite-s 30] [--salida datos/cuadros] [--sin-pausa]

Una captura válida queda en SALIDA/SECUENCIA/: un JPEG por cuadro (`S01_f0001.jpg`, ...),
`captura.jsonl` (un cuadro por línea: frame_id, tiempo relativo de recepción, SHA-256, bytes y
tamaño) y, si algo del stream no sirvió, `rechazados/` con esos bytes y el motivo en el nombre
(P5-12 puede usar un JPEG truncado real). Los nombres no llevan la clase ni el caso.

Todo se escribe primero en una carpeta temporal y se renombra al final, así que la carpeta de la
secuencia solo aparece si la captura salió completa. Una captura con problemas (faltan cuadros,
hay huecos, el stream falló o se acabó el tiempo) se mueve a SALIDA/_fallidas/SECUENCIA_FECHA/
con `FALLIDA.txt` y sin `captura.jsonl`, para que nadie la tome por una secuencia del conjunto;
el siguiente intento puede usar la misma secuencia.

Salida: 0 si se capturaron todos los cuadros sin huecos de `validez_orden_ms` o más, 1 si la
captura falló (se vuelve a filmar), 2 si no se pudo conectar, escribir o la secuencia ya existe.

El máximo de hueco sale de `validez_orden_ms` en config/control/plazos.yaml. Las rutas las elige
quien corre el comando; por eso las escrituras llevan `NOSONAR (S8707)`, como en `python -m
metricas`.
"""

from __future__ import annotations

import argparse
import http.client
import json
import re
import shutil
import socket
import sys
import tempfile
import threading
import time
import urllib.parse
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, suppress
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

import yaml

from .stream import Captura, capturar, huecos_excedidos, leer_partes

RAIZ = Path(__file__).resolve().parents[2]
RUTA_PLAZOS = RAIZ / "config" / "control" / "plazos.yaml"
PATRON_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")  # el mismo del contrato
FALLIDAS = "_fallidas"
MARGEN_CORTE_S = 2  # después del límite, se cierra la conexión aunque no lleguen cuadros


def _max_hueco_ms() -> int:
    plazos = yaml.safe_load(RUTA_PLAZOS.read_text(encoding="utf-8"))
    return int(plazos["validez_orden_ms"])


def _sin_credenciales(url: str) -> str:
    """La URL para mensajes: sin usuario ni contraseña."""
    partes = urllib.parse.urlsplit(url)
    if "@" not in partes.netloc:
        return url
    return partes._replace(netloc="***@" + partes.netloc.rpartition("@")[2]).geturl()


def _url_valida(url: str) -> bool:
    partes = urllib.parse.urlsplit(url)
    try:
        partes.port  # noqa: B018 (lanza ValueError si el puerto no es un número)
    except ValueError:
        return False
    return partes.scheme in ("http", "https") and bool(partes.hostname)


@contextmanager
def _abrir(url: str, timeout: float) -> Iterator[tuple[BinaryIO, Callable[[], None]]]:
    """(respuesta, cortar): `cortar()` cierra el socket desde otro hilo y desbloquea la lectura."""
    partes = urllib.parse.urlsplit(url)
    clase = http.client.HTTPSConnection if partes.scheme == "https" else http.client.HTTPConnection
    # La URL la da quien corre el comando (la cámara en su red); solo se acepta http(s).
    conexion = clase(partes.hostname, partes.port, timeout=timeout)  # NOSONAR (S5332)
    respuesta = None
    try:
        conexion.connect()
        sock = conexion.sock

        def cortar() -> None:
            with suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)

        ruta = (partes.path or "/") + (f"?{partes.query}" if partes.query else "")
        conexion.request("GET", ruta)
        respuesta = conexion.getresponse()
        if respuesta.status != 200:
            raise OSError(f"HTTP {respuesta.status} {respuesta.reason}")
        yield respuesta, cortar
    finally:
        if respuesta is not None:
            respuesta.close()
        conexion.close()


def _escribir(captura: Captura, carpeta: Path, secuencia: str, registro: str) -> None:
    filas = []
    for n, cuadro in enumerate(captura.cuadros, start=1):
        frame_id = f"{secuencia}_f{n:04d}"
        (carpeta / f"{frame_id}.jpg").write_bytes(cuadro.datos)  # NOSONAR (S8707)
        filas.append(
            {
                "frame_id": frame_id,
                "sequence_id": secuencia,
                "archivo": f"{frame_id}.jpg",
                "t_capture_ms": cuadro.t_capture_ms,
                "sha256": cuadro.sha256,
                "bytes": len(cuadro.datos),
                "image_width": cuadro.ancho,
                "image_height": cuadro.alto,
            }
        )
    if captura.rechazados:
        rechazados = carpeta / "rechazados"
        rechazados.mkdir()  # NOSONAR (S8707)
        for n, (motivo, datos) in enumerate(captura.rechazados, start=1):
            (rechazados / f"{n:03d}_{motivo}.bin").write_bytes(datos)  # NOSONAR (S8707)
    # El registro va al final: si está, todo lo demás ya se escribió.
    texto = "".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas)
    (carpeta / registro).write_text(texto, encoding="utf-8")  # NOSONAR (S8707)


def _guardar(captura: Captura, salida: Path, secuencia: str, problemas: list[str]) -> Path:
    """Escribe en una carpeta temporal y la renombra a su lugar; devuelve dónde quedó."""
    salida.mkdir(parents=True, exist_ok=True)  # NOSONAR (S8707)
    temporal = Path(tempfile.mkdtemp(prefix=f".{secuencia}.", suffix=".parcial", dir=salida))
    try:
        if problemas:
            _escribir(captura, temporal, secuencia, "intento.jsonl")
            texto = "".join(f"{p}\n" for p in problemas)
            (temporal / "FALLIDA.txt").write_text(texto, encoding="utf-8")  # NOSONAR (S8707)
            sello = datetime.now().strftime("%Y%m%dT%H%M%S")
            destino = salida / FALLIDAS / f"{secuencia}_{sello}"
            destino.parent.mkdir(exist_ok=True)  # NOSONAR (S8707)
        else:
            _escribir(captura, temporal, secuencia, "captura.jsonl")
            destino = salida / secuencia
            if destino.exists():  # alguien la creó mientras se capturaba
                raise FileExistsError(f"{destino.as_posix()} ya existe")
        temporal.rename(destino)  # NOSONAR (S8707)
    except BaseException:
        shutil.rmtree(temporal, ignore_errors=True)
        raise
    return destino


def _problemas(captura: Captura, pedidos: int, maximo: int, secuencia: str) -> list[str]:
    problemas = []
    if captura.error:
        problemas.append(f"el stream falló: {captura.error}")
    if captura.tiempo_agotado:
        problemas.append("se acabó el tiempo límite sin juntar los cuadros")
    if len(captura.cuadros) < pedidos:
        problemas.append(f"solo {len(captura.cuadros)} de {pedidos} cuadros")
    problemas += [
        f"hueco de {hueco:.0f} ms antes de {secuencia}_f{i + 1:04d} (debe ser menor que {maximo})"
        for i, hueco in huecos_excedidos(captura.cuadros, maximo)
    ]
    return problemas


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m captura",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--url", required=True, help="Stream MJPEG, p. ej. http://IP:81/stream.")
    parser.add_argument("--secuencia", required=True, help="sequence_id, p. ej. S01.")
    parser.add_argument("--cuadros", type=int, default=12, help="Cuántos cuadros (12).")
    parser.add_argument("--cada-ms", type=int, default=200, help="Separación mínima (200 ms).")
    parser.add_argument(
        "--limite-s", type=float, default=30, help="Duración máxima de la captura (30 s)."
    )
    parser.add_argument("--salida", type=Path, default=Path("datos/cuadros"))
    parser.add_argument("--ancho", type=int, default=640)
    parser.add_argument("--alto", type=int, default=480)
    parser.add_argument(
        "--descartar", type=int, default=2, help="Cuadros viejos del búfer que se tiran (2)."
    )
    parser.add_argument("--sin-pausa", action="store_true", help="No esperar Enter para empezar.")
    args = parser.parse_args(argv)

    if not PATRON_ID.match(args.secuencia):
        parser.error("--secuencia solo admite letras, números, '.', '_' y '-' (hasta 64)")
    if args.cuadros < 1 or args.cada_ms < 1 or args.limite_s <= 0:
        parser.error("--cuadros, --cada-ms y --limite-s deben ser positivos")
    if not _url_valida(args.url):
        parser.error("--url debe ser http(s)://IP:puerto/stream")
    carpeta = args.salida / args.secuencia
    if carpeta.exists():
        print(f"{carpeta.as_posix()} ya existe: bórrala o usa otra secuencia", file=sys.stderr)
        return 2
    maximo = _max_hueco_ms()

    if not args.sin_pausa:
        input(f"Secuencia {args.secuencia}: Enter para empezar a capturar...")
    try:
        with _abrir(args.url, timeout=10) as (respuesta, cortar):
            # Respaldo de `limite_ms` para un stream que se queda a medio cuadro.
            cortado = threading.Event()
            vigilante = threading.Timer(
                args.limite_s + MARGEN_CORTE_S, lambda: (cortado.set(), cortar())
            )
            vigilante.daemon = True
            vigilante.start()
            try:
                captura = capturar(
                    leer_partes(respuesta),
                    reloj_ms=lambda: time.monotonic_ns() / 1e6,
                    cuadros=args.cuadros,
                    cada_ms=args.cada_ms,
                    tamano=(args.ancho, args.alto),
                    descartar=args.descartar,
                    limite_ms=args.limite_s * 1000,
                )
            finally:
                vigilante.cancel()
            if cortado.is_set():
                captura.tiempo_agotado = True
                captura.error = None  # el error de lectura lo causó el corte
    except (OSError, http.client.HTTPException) as exc:
        url_segura = _sin_credenciales(args.url)
        print(f"no se pudo leer el stream {url_segura}: {exc}", file=sys.stderr)
        return 2

    problemas = _problemas(captura, args.cuadros, maximo, args.secuencia)
    if not captura.cuadros and not captura.rechazados:
        for problema in problemas:
            print(f"error: {problema}", file=sys.stderr)
        print("no llegó nada utilizable; no se guardó nada", file=sys.stderr)
        return 1
    try:
        destino = _guardar(captura, args.salida, args.secuencia, problemas)
    except OSError as exc:
        print(f"no se pudo guardar la captura (no quedó nada a medias): {exc}", file=sys.stderr)
        return 2

    cuadros = captura.cuadros
    duracion = cuadros[-1].t_capture_ms if cuadros else 0
    print(
        f"{len(cuadros)} cuadros en {duracion} ms "
        f"({datetime.now().isoformat(timespec='seconds')}) -> {destino.as_posix()}/"
    )
    descartados = len(captura.rechazados) + captura.rechazados_sin_guardar
    if captura.duplicados or descartados:
        print(f"descartados: {captura.duplicados} duplicados, {descartados} rechazados")
    if problemas:
        for problema in problemas:
            print(f"error: {problema}", file=sys.stderr)
        print("captura fallida: vuelve a filmar la secuencia", file=sys.stderr)
    return 1 if problemas else 0


if __name__ == "__main__":
    raise SystemExit(main())
