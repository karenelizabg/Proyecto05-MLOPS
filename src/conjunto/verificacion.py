"""`verify_dataset` (P5-11): revisa que el conjunto de evaluación cumpla E3 antes de congelarlo.

Cada regla rota es un error y el comando sale con código distinto de 0:

- Mínimos de E3: 60 cuadros, 6 secuencias, 20 con obstáculo y 20 despejados (los mismos de
  `metricas`, que limitan el criterio 1.4).
- Cuadros únicos: ningún SHA-256 repetido; cada archivo existe dentro de la raíz, su SHA-256 y su
  tamaño coinciden con el manifiesto y es un JPEG completo (el mismo criterio de la captura).
- `split`: todos `evaluacion` (D-06, no hubo ajuste).
- Huecos: dentro de una secuencia el tiempo crece y dos cuadros seguidos están separados por
  **menos** de `validez_orden_ms` (config/control/plazos.yaml). Un hueco armado a propósito se
  marca con `hueco_intencional: true` en el cuadro que llega tarde.
- Anotaciones: válidas (esquema v1), una por cuadro, con la misma secuencia y el mismo tamaño, y
  el estado esperado y las zonas del manifiesto coinciden con las cajas.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Mapping
from itertools import pairwise
from pathlib import Path
from typing import Any

import yaml

from captura import motivo_rechazo
from control.config import ConfigPolitica, cargar_config_politica
from metricas.evaluacion import MINIMOS_E3, validar_anotaciones

from .manifiesto import RAIZ, SPLIT, ruta_relativa, zonas_de

RUTA_PLAZOS = RAIZ / "config" / "control" / "plazos.yaml"

CAMPOS = (
    "frame_id",
    "sequence_id",
    "t_relativo_ms",
    "ruta",
    "sha256",
    "image_width",
    "image_height",
    "split",
    "estado_esperado",
    "objetos",
    "zonas_ocupadas",
    "procedencia",
    "hueco_intencional",
)


def max_hueco_ms() -> int:
    plazos = yaml.safe_load(RUTA_PLAZOS.read_text(encoding="utf-8"))
    return int(plazos["validez_orden_ms"])


def _revisar_archivo(f: Mapping[str, Any], raiz: Path) -> list[str]:
    frame, ruta = f["frame_id"], f["ruta"]
    # Debe ser ya la ruta relativa y resuelta: ni absoluta, ni con `..`, ni un enlace a otro lado.
    if not isinstance(ruta, str) or ruta_relativa(raiz / ruta, raiz) != ruta:
        return [f"{frame}: la ruta {ruta!r} debe ser relativa y estar dentro de la raíz"]
    try:
        datos = (raiz / ruta).read_bytes()  # NOSONAR (S8707)
    except OSError:
        return [f"{frame}: no existe {ruta}"]
    errores: list[str] = []
    if hashlib.sha256(datos).hexdigest() != f["sha256"]:
        errores.append(f"{frame}: el SHA-256 de {ruta} no coincide con el manifiesto")
    motivo = motivo_rechazo(datos, (f["image_width"], f["image_height"]))
    if motivo:
        errores.append(f"{frame}: {ruta} no es un cuadro válido ({motivo})")
    return errores


def _revisar_archivos(filas: list[Mapping[str, Any]], raiz: Path) -> list[str]:
    errores: list[str] = []
    por_sha: dict[str, str] = {}
    for f in filas:
        frame = f["frame_id"]
        if f["sha256"] in por_sha:
            errores.append(f"{frame}: misma imagen que {por_sha[f['sha256']]} (SHA-256 repetido)")
        por_sha.setdefault(f["sha256"], frame)
        errores += _revisar_archivo(f, raiz)
    return errores


def _revisar_huecos(filas: list[Mapping[str, Any]], maximo: int) -> list[str]:
    errores: list[str] = []
    por_secuencia: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for f in filas:
        por_secuencia[f["sequence_id"]].append(f)
    for secuencia, cuadros in por_secuencia.items():
        for antes, despues in pairwise(cuadros):
            hueco = despues["t_relativo_ms"] - antes["t_relativo_ms"]
            if hueco <= 0:
                errores.append(
                    f"{despues['frame_id']}: el tiempo no crece respecto a "
                    f"{antes['frame_id']} en la secuencia {secuencia}"
                )
            elif hueco >= maximo and not despues["hueco_intencional"]:
                errores.append(
                    f"{despues['frame_id']}: hueco de {hueco} ms desde {antes['frame_id']} "
                    f"(debe ser menor que {maximo}; se vuelve a filmar la secuencia)"
                )
    return errores


def _revisar_anotacion(
    f: Mapping[str, Any],
    a: Mapping[str, Any],
    config: ConfigPolitica,
    clases: set[int] | None,
) -> list[str]:
    """Lo que no coincide entre una fila del manifiesto y su anotación."""
    frame = f["frame_id"]
    errores: list[str] = []
    if a["sequence_id"] != f["sequence_id"]:
        errores.append(f"{frame}: la anotación dice la secuencia {a['sequence_id']}")
    if (a["image_width"], a["image_height"]) != (f["image_width"], f["image_height"]):
        errores.append(f"{frame}: la anotación tiene otro tamaño de imagen")
    estado = "obstaculo" if a["objetos"] else "despejado"
    if f["estado_esperado"] != estado or f["objetos"] != len(a["objetos"]):
        errores.append(f"{frame}: el estado esperado no coincide con la anotación")
    if f["zonas_ocupadas"] != zonas_de(a, config):
        errores.append(f"{frame}: las zonas ocupadas no coinciden con las cajas anotadas")
    ajenas = sorted({o["class_id"] for o in a["objetos"]} - clases) if clases is not None else []
    if ajenas:
        errores.append(f"{frame}: class_id {ajenas} no está en modelo/clases.json")
    return errores


def _revisar_anotaciones(
    filas: list[Mapping[str, Any]],
    anotaciones: list[Any],
    config: ConfigPolitica,
    clases: set[int] | None,
) -> list[str]:
    errores = validar_anotaciones(anotaciones)
    if errores:
        return errores
    por_frame = {a["frame_id"]: a for a in anotaciones}
    for f in filas:
        a = por_frame.get(f["frame_id"])
        if a is None:
            errores.append(f"{f['frame_id']}: no tiene anotación")
        else:
            errores += _revisar_anotacion(f, a, config, clases)
    sobrantes = sorted(set(por_frame) - {f["frame_id"] for f in filas})
    errores += [
        f"{frame}: anotación de un cuadro que no está en el manifiesto" for frame in sobrantes
    ]
    return errores


def conteo(filas: list[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "cuadros": len(filas),
        "secuencias": len({f["sequence_id"] for f in filas}),
        "con_objetos": sum(1 for f in filas if f["estado_esperado"] == "obstaculo"),
        "sin_objetos": sum(1 for f in filas if f["estado_esperado"] == "despejado"),
    }


def verificar(
    filas: list[Mapping[str, Any]],
    anotaciones: list[Any],
    raiz: Path = RAIZ,
    config: ConfigPolitica | None = None,
    clases: set[int] | None = None,
    maximo_ms: int | None = None,
) -> list[str]:
    """Lista de reglas rotas; vacía si el conjunto se puede congelar."""
    errores: list[str] = []
    for n, f in enumerate(filas, start=1):
        faltan = [c for c in CAMPOS if c not in f]
        if faltan:
            errores.append(f"fila {n}: faltan {faltan}")
    if errores:
        return errores

    frames = [f["frame_id"] for f in filas]
    errores += [
        f"{fr}: frame_id repetido" for fr in sorted({x for x in frames if frames.count(x) > 1})
    ]
    errores += [
        f"{f['frame_id']}: split {f['split']!r}, debe ser {SPLIT!r}"
        for f in filas
        if f["split"] != SPLIT
    ]

    total = conteo(filas)
    errores += [
        f"mínimo de E3: {clave} = {total[clave]}, se piden al menos {minimo}"
        for clave, minimo in MINIMOS_E3.items()
        if total[clave] < minimo
    ]
    errores += _revisar_archivos(filas, raiz)
    errores += _revisar_huecos(filas, max_hueco_ms() if maximo_ms is None else maximo_ms)
    errores += _revisar_anotaciones(filas, anotaciones, config or cargar_config_politica(), clases)
    return errores
