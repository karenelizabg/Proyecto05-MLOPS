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
COLOR_CLASE = {39: (74, 222, 128), 41: (255, 213, 74)}
COLOR_OTRA = (248, 113, 113)
COLOR_ZONA = (96, 165, 250)


def cajas_repetidas(anotaciones: Sequence[Mapping[str, Any]]) -> list[str]:
    """La misma caja en más de un cuadro de una secuencia: suele ser una caja copiada."""
    cuadros_de: dict[tuple[Any, ...], list[str]] = {}
    for anotacion in anotaciones:
        for objeto in anotacion["objetos"]:
            clave = (anotacion["sequence_id"], objeto["class_id"], tuple(objeto["bbox"]))
            cuadros_de.setdefault(clave, []).append(anotacion["frame_id"])
    return [
        f"{clave[0]}: clase {clave[1]}, caja {list(clave[2])} repetida en {', '.join(cuadros)}"
        for clave, cuadros in cuadros_de.items()
        if len(cuadros) > 1
    ]


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
