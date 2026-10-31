"""Genera las entradas fallidas de C8 y C9 (P5-12). Ver datos/MAPA_CASOS.md.

Uso:
    python datos/fixtures/generar.py

Parten de un degradado sintético, no de cuadros del conjunto: una fixture no debe dejar ver ni
alterar datos de evaluación. Los archivos que valen son los del repo, con el SHA-256 de
`SHA256SUMS`; otra versión de Pillow podría generar bytes distintos.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image

AQUI = Path(__file__).resolve().parent
ANCHO, ALTO = 640, 480


def _jpeg(ancho: int, alto: int) -> bytes:
    imagen = Image.linear_gradient("L").resize((ancho, alto)).convert("RGB")
    salida = io.BytesIO()
    imagen.save(salida, format="JPEG", quality=90)
    return salida.getvalue()


def fixtures() -> dict[str, bytes]:
    """Nombre de archivo -> bytes de cada fixture."""
    valido = _jpeg(ANCHO, ALTO)
    inicio_scan = valido.index(b"\xff\xda")
    return {
        "vacia.jpg": b"",
        "no_es_jpeg.jpg": b"esto no es un JPEG\n",
        "sin_imagen.jpg": valido[:inicio_scan],
        "truncado.jpg": valido[: inicio_scan + (len(valido) - inicio_scan) // 2],
        "otras_dimensiones.jpg": _jpeg(ANCHO // 2, ALTO // 2),
    }


def main() -> None:
    lineas = []
    for nombre, datos in sorted(fixtures().items()):
        (AQUI / nombre).write_bytes(datos)
        lineas.append(f"{hashlib.sha256(datos).hexdigest()}  {nombre}\n")
    (AQUI / "SHA256SUMS").write_text("".join(lineas), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
