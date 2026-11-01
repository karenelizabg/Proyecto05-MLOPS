"""Hojas de revisión visual de las anotaciones (P5-10): las cajas dibujadas sobre cada cuadro.

Una hoja por secuencia, con los cuadros a resolución completa: a la mitad de resolución no se veía
que había cajas copiadas de un cuadro a otro (revisión de #79). Las líneas azules son los límites
de las zonas de `config/control/politica.yaml`. No usa el detector.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from control.config import ConfigPolitica, cargar_config_politica

COLUMNAS = 4
# Dos cajas pueden medir igual por casualidad; en tres o más cuadros ya parece una copia movida.
MIN_MISMO_TAMANO = 3
COLOR_CLASE = {39: (74, 222, 128), 41: (255, 213, 74)}
COLOR_OTRA = (248, 113, 113)
COLOR_ZONA = (96, 165, 250)


def cajas_repetidas(anotaciones: Sequence[Mapping[str, Any]]) -> list[str]:
    """Cajas que parecen copiadas dentro de una secuencia.

    Avisa de la misma caja en dos cuadros o más y del mismo ancho x alto en `MIN_MISMO_TAMANO`
    cuadros o más, aunque se haya movido (las 8 de S06 en #79). Los cuadros de una caja idéntica
    que ya salen en un aviso de tamaño no se repiten.
    """
    cuadros_caja: dict[tuple[Any, ...], list[str]] = {}
    cuadros_tamano: dict[tuple[Any, ...], list[str]] = {}
    for anotacion in anotaciones:
        secuencia, frame = anotacion["sequence_id"], anotacion["frame_id"]
        for objeto in anotacion["objetos"]:
            x1, y1, x2, y2 = objeto["bbox"]
            tamano = (round(x2 - x1, 1), round(y2 - y1, 1))
            cuadros_caja.setdefault((secuencia, objeto["class_id"], x1, y1, x2, y2), []).append(
                frame
            )
            cuadros_tamano.setdefault((secuencia, objeto["class_id"], *tamano), []).append(frame)

    avisos, cubiertas = [], set()
    for (secuencia, clase, ancho, alto), cuadros in cuadros_tamano.items():
        if len(set(cuadros)) >= MIN_MISMO_TAMANO:
            cubiertas.add((secuencia, clase, ancho, alto))
            avisos.append(
                f"{secuencia}: clase {clase}, mismo tamaño {ancho} x {alto} en {', '.join(cuadros)}"
            )
    for (secuencia, clase, x1, y1, x2, y2), cuadros in cuadros_caja.items():
        tamano = (round(x2 - x1, 1), round(y2 - y1, 1))
        if len(cuadros) > 1 and (secuencia, clase, *tamano) not in cubiertas:
            caja = [x1, y1, x2, y2]
            avisos.append(
                f"{secuencia}: clase {clase}, caja {caja} repetida en {', '.join(cuadros)}"
            )
    return avisos


def _cuadro(ruta: Path, anotacion: Mapping[str, Any], config: ConfigPolitica) -> Image.Image:
    with Image.open(ruta) as original:  # NOSONAR (S8707)
        imagen = original.convert("RGB")
    dibujo = ImageDraw.Draw(imagen)
    for zona in ("izq", "centro"):
        x = config.zonas[zona][1] * imagen.width
        dibujo.line([(x, 0), (x, imagen.height)], fill=COLOR_ZONA)
    for objeto in anotacion["objetos"]:
        color = COLOR_CLASE.get(objeto["class_id"], COLOR_OTRA)
        dibujo.rectangle(objeto["bbox"], outline=color, width=1)
    texto = f"{anotacion['frame_id']} n={len(anotacion['objetos'])}"
    dibujo.rectangle(dibujo.textbbox((2, 2), texto), fill=(0, 0, 0))
    dibujo.text((2, 2), texto, fill=(255, 255, 255))
    return imagen


def escribir_hojas(
    anotaciones: Sequence[Mapping[str, Any]],
    cuadros: Path,
    salida: Path,
    config: ConfigPolitica | None = None,
) -> list[Path]:
    """Escribe `<salida>/<secuencia>.png` y devuelve las rutas. `salida` ya debe existir."""
    config = config or cargar_config_politica()
    por_secuencia: dict[str, list[Mapping[str, Any]]] = {}
    for anotacion in anotaciones:
        por_secuencia.setdefault(anotacion["sequence_id"], []).append(anotacion)

    hojas = []
    for secuencia, filas in por_secuencia.items():
        imagenes = [
            _cuadro(cuadros / secuencia / f"{fila['frame_id']}.jpg", fila, config) for fila in filas
        ]
        ancho, alto = imagenes[0].size
        renglones = (len(imagenes) + COLUMNAS - 1) // COLUMNAS
        hoja = Image.new("RGB", (ancho * COLUMNAS, alto * renglones))
        for n, imagen in enumerate(imagenes):
            hoja.paste(imagen, ((n % COLUMNAS) * ancho, (n // COLUMNAS) * alto))
        ruta = salida / f"{secuencia}.png"
        hoja.save(ruta)  # NOSONAR (S8707)
        hojas.append(ruta)
    return hojas
