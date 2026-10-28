"""Evalúa un run del detector contra las anotaciones (P5-13).

`evaluar` recorre **todos** los cuadros anotados, en su orden: un cuadro sin evento, con `error`
o con `stale` sigue en el denominador (sus objetos son FN) y queda listado. Nada se quita para
mejorar el F1. Además comprueba la procedencia (hashes de modelo y configuración), la cobertura y
los mínimos de E3 que limitan el puntaje 1.4.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from contrato import validar_evento, validar_flujo

from .calculo import (
    UMBRAL_IOU,
    Conteo,
    Objeto,
    Par,
    Prediccion,
    a_xyxy,
    contar,
    emparejar,
    puntaje_1_4,
)
from .calculo import metricas as calcular_metricas

RAIZ = Path(__file__).resolve().parents[2]
RUTA_ESQUEMA_ANOTACIONES = RAIZ / "config" / "anotaciones" / "anotaciones.v1.schema.json"

# Mínimos de E3: si no se cumplen, el criterio 1.4 se limita a 3 de 6.
MINIMOS_E3 = {"cuadros": 60, "secuencias": 6, "con_objetos": 20, "sin_objetos": 20}
TOPE_SIN_MINIMOS_E3 = 3.0


class EntradaInvalida(Exception):
    """Las detecciones o las anotaciones no se pueden evaluar tal como están."""

    def __init__(self, errores: list[str]):
        super().__init__("\n".join(errores))
        self.errores = errores


@dataclass
class Resultado:
    resumen: dict[str, Any]
    por_cuadro: list[dict[str, Any]] = field(default_factory=list)
    detalle: list[dict[str, Any]] = field(default_factory=list)

    @property
    def advertencias(self) -> list[str]:
        return self.resumen["advertencias"]


@lru_cache(maxsize=1)
def _validador_anotaciones() -> Draft202012Validator:
    esquema = json.loads(RUTA_ESQUEMA_ANOTACIONES.read_text(encoding="utf-8"))
    return Draft202012Validator(esquema)


def validar_anotaciones(anotaciones: list[Any]) -> list[str]:
    errores: list[str] = []
    vistos: set[str] = set()
    for n, anotacion in enumerate(anotaciones, start=1):
        fallos = list(_validador_anotaciones().iter_errors(anotacion))
        if fallos:
            errores += [
                f"anotación {n}: {'/'.join(map(str, e.absolute_path)) or '(cuadro)'}: {e.message}"
                for e in fallos
            ]
            continue
        frame = anotacion["frame_id"]
        if frame in vistos:
            errores.append(f"anotación {n}: frame_id {frame!r} repetido")
        vistos.add(frame)
        ancho, alto = anotacion["image_width"], anotacion["image_height"]
        for i, objeto in enumerate(anotacion["objetos"]):
            x1, y1, x2, y2 = objeto["bbox"]
            donde = f"anotación {n} ({frame}): objetos/{i}/bbox"
            if not all(math.isfinite(v) for v in objeto["bbox"]):
                errores.append(f"{donde}: debe tener números finitos")
            elif x2 <= x1 or y2 <= y1:
                errores.append(f"{donde}: la caja debe tener ancho y alto positivos")
            elif x2 > ancho or y2 > alto:
                errores.append(f"{donde}: la caja sale de la imagen ({ancho}x{alto})")
    return errores


def _validar_eventos(eventos: list[Any]) -> list[str]:
    errores = [
        f"evento {n}: {msg}" for n, ev in enumerate(eventos, start=1) for msg in validar_evento(ev)
    ]
    if errores:
        return errores
    errores = validar_flujo(eventos)
    runs = sorted({ev["run_id"] for ev in eventos})
    if len(runs) > 1:
        errores.append(f"las detecciones mezclan varios run_id {runs}: se evalúa un run a la vez")
    return errores


def _procedencia(
    eventos: list[dict[str, Any]], model_sha256: str | None, config_sha256: str | None
) -> tuple[dict[str, Any], list[str]]:
    advertencias: list[str] = []
    datos: dict[str, Any] = {"run_id": eventos[0]["run_id"] if eventos else None}
    for campo, esperado in (("model_sha256", model_sha256), ("config_sha256", config_sha256)):
        vistos = sorted({ev[campo] for ev in eventos})
        datos[campo] = vistos
        datos[f"{campo}_esperado"] = esperado
        if esperado is None:
            advertencias.append(f"procedencia no comprobada: no se indicó el {campo} congelado")
        elif vistos != [esperado]:
            advertencias.append(f"{campo} de las detecciones {vistos} no coincide con {esperado}")
    datos["comprobada"] = not advertencias
    return datos, advertencias


def _estado_y_predicciones(evento: dict[str, Any] | None) -> tuple[str, list[Prediccion]]:
    """Solo un evento `ok` trae predicciones; sin evento, `error` o `stale` no predicen nada."""
    if evento is None:
        return "sin_evento", []
    if evento["status"] != "ok":
        return evento["status"], []
    return "ok", [
        Prediccion(d["class_id"], d["confidence"], a_xyxy(d["bbox"], evento["bbox_format"]))
        for d in evento["detections"]
    ]


def evaluar(
    anotaciones: list[Any],
    eventos: list[Any],
    model_sha256: str | None = None,
    config_sha256: str | None = None,
) -> Resultado:
    """Evalúa un run. Lanza `EntradaInvalida` si alguna entrada no cumple su formato."""
    errores = [f"anotaciones: {e}" for e in validar_anotaciones(anotaciones)]
    errores += [f"detecciones: {e}" for e in _validar_eventos(eventos)]
    if errores:
        raise EntradaInvalida(errores)

    por_frame = {ev["frame_id"]: ev for ev in eventos}
    anotados = {a["frame_id"] for a in anotaciones}
    procedencia, advertencias = _procedencia(eventos, model_sha256, config_sha256)

    por_cuadro: list[dict[str, Any]] = []
    detalle: list[dict[str, Any]] = []
    total, por_clase = Conteo(), {}
    sin_evento, con_falla, otras_dimensiones = [], [], []

    for anotacion in anotaciones:
        frame = anotacion["frame_id"]
        reales = [Objeto(o["class_id"], tuple(map(float, o["bbox"]))) for o in anotacion["objetos"]]
        evento = por_frame.get(frame)
        estado, predicciones = _estado_y_predicciones(evento)
        if estado == "sin_evento":
            sin_evento.append(frame)
        elif estado != "ok":
            con_falla.append(frame)
        elif (evento["image_width"], evento["image_height"]) != (
            anotacion["image_width"],
            anotacion["image_height"],
        ):
            otras_dimensiones.append(frame)

        pares = emparejar(predicciones, reales)
        conteo = contar(pares)
        total += conteo
        # Todo objeto real sale en un par (TP o FN), así que los pares cubren todas las clases.
        for par in pares:
            por_clase[par.class_id] = por_clase.get(par.class_id, Conteo()) + contar([par])
        por_cuadro.append(
            {
                "frame_id": frame,
                "sequence_id": anotacion["sequence_id"],
                "estado": estado,
                "reales": len(reales),
                "predichas": len(predicciones),
                "tp": conteo.tp,
                "fp": conteo.fp,
                "fn": conteo.fn,
            }
        )
        detalle += [_fila_detalle(frame, par) for par in pares]

    sin_anotar = sorted(set(por_frame) - anotados)
    if sin_evento:
        advertencias.append(f"{len(sin_evento)} cuadros anotados sin evento del detector")
    if con_falla:
        advertencias.append(f"{len(con_falla)} cuadros con status error o stale")
    if otras_dimensiones:
        advertencias.append(
            f"{len(otras_dimensiones)} cuadros con dimensiones distintas a las anotadas: "
            "las cajas no están en el mismo sistema de coordenadas"
        )
    if sin_anotar:
        advertencias.append(f"{len(sin_anotar)} eventos de cuadros sin anotación (no se cuentan)")

    conjunto = {
        "cuadros": len(anotaciones),
        "secuencias": len({a["sequence_id"] for a in anotaciones}),
        "con_objetos": sum(1 for a in anotaciones if a["objetos"]),
        "sin_objetos": sum(1 for a in anotaciones if not a["objetos"]),
    }
    faltan_minimos = [k for k, minimo in MINIMOS_E3.items() if conjunto[k] < minimo]
    if faltan_minimos:
        advertencias.append(
            "no se cumplen los mínimos de E3 ("
            + ", ".join(f"{k}: {conjunto[k]} < {MINIMOS_E3[k]}" for k in faltan_minimos)
            + f"): 1.4 se limita a {TOPE_SIN_MINIMOS_E3:g}"
        )

    puntaje = puntaje_1_4(total)
    resumen = {
        "version": 1,
        "umbral_iou": UMBRAL_IOU,
        "procedencia": procedencia,
        "conjunto": {**conjunto, "minimos_e3": MINIMOS_E3, "cumple_minimos_e3": not faltan_minimos},
        "cuadros": {
            "ok": sum(1 for f in por_cuadro if f["estado"] == "ok"),
            "sin_evento": sin_evento,
            "error_o_stale": con_falla,
            "dimensiones_distintas": otras_dimensiones,
            "eventos_sin_anotacion": sin_anotar,
        },
        "micro": calcular_metricas(total),
        "por_clase": {
            str(clase): {**calcular_metricas(c), "soporte": c.tp + c.fn}
            for clase, c in sorted(por_clase.items())
        },
        "criterio_1_4": {
            "formula": "floor(12 * F1 micro) / 2",
            "puntaje": puntaje,
            "puntaje_con_tope_e3": min(puntaje, TOPE_SIN_MINIMOS_E3) if faltan_minimos else puntaje,
            "procedencia_comprobada": procedencia["comprobada"],
            "cobertura_completa": not (sin_evento or con_falla or sin_anotar),
        },
        "advertencias": advertencias,
    }
    return Resultado(resumen, por_cuadro, detalle)


def _caja_texto(caja: tuple[float, ...] | None) -> str:
    return "" if caja is None else json.dumps(list(caja))


def _fila_detalle(frame: str, par: Par) -> dict[str, Any]:
    return {
        "frame_id": frame,
        "tipo": par.tipo,
        "class_id": par.class_id,
        "confidence": "" if par.confidence is None else par.confidence,
        "iou": "" if par.iou is None else round(par.iou, 6),
        "caja_predicha": _caja_texto(par.caja_predicha),
        "caja_real": _caja_texto(par.caja_real),
    }
