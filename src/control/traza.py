"""Sigue cada cuadro de una corrida de punta a punta (T16).

    PYTHONPATH=src python -m control.traza --salida resultados/recorrido-real/izq/ \\
        [--frame-id S03_f0012] [--config config/control/]

Lee la carpeta que deja `python -m control` y, por cada cuadro de `detecciones.jsonl`, muestra en
orden qué vio el detector (clase, confianza, caja y zonas que ocupa), qué se decidió (estados,
acción, razón y quién decidió), qué comando registró el adaptador y si quedó un error. Todo se une
por `run_id` y `frame_id`. Al final van las órdenes sin cuadro (reloj, emergencia, rearme, cierre)
y cuántas veces salió cada acción, para comparar la secuencia de izquierda con la de derecha.

Las zonas se calculan con `config/control/politica.yaml` (o el de `--config`), igual que la
política: una detección que no es obstáculo o tiene poca confianza aparece como "no cuenta".

Salida: 0 si cada cuadro llegó a una decisión y a un comando, 1 si alguno no, 2 si la carpeta no se
puede leer.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .__main__ import CARPETA_CONFIG, NOMBRE_DECISIONES, NOMBRE_DETECCIONES, NOMBRE_POLITICA
from .adaptador_virtual import NOMBRE_REGISTRO
from .config import ConfigPolitica, ErrorConfigPolitica, cargar_config_politica
from .politica import detecciones_por_zona
from .supervisor import NOMBRE_ERRORES

Clave = tuple[Any, Any]


def trazar(salida: Path, config: ConfigPolitica) -> dict[str, Any]:
    """Une detecciones, decisiones, comandos y errores de una corrida por cuadro."""
    detecciones = _leer_jsonl(salida / NOMBRE_DETECCIONES)
    decisiones = _leer_jsonl(salida / NOMBRE_DECISIONES)
    comandos = _leer_jsonl(salida / NOMBRE_REGISTRO)
    errores = _leer_jsonl(salida / NOMBRE_ERRORES)

    de_cuadro = [c for c in comandos if c.get("event") == "frame"]
    cuadros = []
    for evento in detecciones:
        clave = _clave(evento)
        cuadros.append(
            {
                "run_id": clave[0],
                "frame_id": clave[1],
                "evento": evento,
                "zonas": _zonas_por_deteccion(evento, config),
                "decisiones": [
                    d for d in decisiones if d.get("event") == "frame" and _clave(d) == clave
                ],
                "comandos": [c for c in de_cuadro if _clave(c) == clave],
                "errores": [e for e in errores if _clave(e) == clave],
            }
        )
    return {
        "cuadros": cuadros,
        "sin_cuadro": [c for c in comandos if c.get("event") != "frame"],
        "acciones": Counter(c.get("action") for c in de_cuadro),
        "incompletos": [
            str(c["frame_id"]) for c in cuadros if not c["decisiones"] or not c["comandos"]
        ],
    }


def formatear(traza: dict[str, Any], frame_id: str | None = None) -> str:
    """La traza como texto, un bloque por cuadro. Con `frame_id`, solo ese cuadro."""
    lineas: list[str] = []
    for cuadro in traza["cuadros"]:
        if frame_id is None or cuadro["frame_id"] == frame_id:
            lineas.extend(_bloque(cuadro))
            lineas.append("")
    if frame_id is not None:
        return "\n".join(lineas) if lineas else f"{frame_id}: no está en {NOMBRE_DETECCIONES}"

    lineas.append("Órdenes sin cuadro:")
    for comando in traza["sin_cuadro"]:
        lineas.append(
            f"  {comando.get('event')} a los {comando.get('t_command_ms')} ms: "
            f"{comando.get('action')} ({comando.get('reason')})"
        )
    if not traza["sin_cuadro"]:
        lineas.append("  ninguna")
    acciones = ", ".join(f"{a} {n}" for a, n in sorted(traza["acciones"].items()))
    lineas.append(f"Acciones por cuadro: {acciones or 'ninguna'}")
    if traza["incompletos"]:
        lineas.append(f"Cuadros sin decisión o sin comando: {', '.join(traza['incompletos'])}")
    return "\n".join(lineas)


def _bloque(cuadro: dict[str, Any]) -> list[str]:
    evento = cuadro["evento"]
    if not isinstance(evento, dict):
        return [f"{cuadro['frame_id']}: la línea no es un evento ({evento!r})"]
    lineas = [
        f"{cuadro['frame_id']} · run {cuadro['run_id']} · status {evento.get('status')} · "
        f"captura {evento.get('t_capture_ms')} ms · llegada {evento.get('t_emit_ms')} ms · "
        f"{evento.get('image_width')}x{evento.get('image_height')} px "
        f"({evento.get('bbox_format')})"
    ]
    dets = evento.get("detections") or []
    if isinstance(evento.get("error"), dict):
        lineas.append(f"  error del detector: {evento['error'].get('code')}")
    if not dets:
        lineas.append("  detecciones: ninguna")
    for det, zonas in zip(dets, cuadro["zonas"], strict=False):
        donde = ", ".join(zonas) if zonas else "no cuenta (clase o confianza)"
        lineas.append(
            f"  detección: class_id {det.get('class_id')} · confianza {det.get('confidence')} · "
            f"bbox {det.get('bbox')} -> {donde}"
        )
    for d in cuadro["decisiones"]:
        lineas.append(
            f"  decisión: {d.get('state_before')} -> {d.get('state_after')} · {d.get('action')} "
            f"(decidió {d.get('decidio')}) · {d.get('reason')}"
        )
    for c in cuadro["comandos"]:
        lineas.append(
            f"  comando: {c.get('action')} · speed {c.get('speed')} · steering {c.get('steering')} "
            f"· t_command {c.get('t_command_ms')} ms · vale hasta {c.get('valid_until_ms')} ms"
        )
    for e in cuadro["errores"]:
        lineas.append(f"  error registrado: {e.get('motivo')}")
    if not cuadro["decisiones"]:
        lineas.append("  FALTA la decisión")
    if not cuadro["comandos"]:
        lineas.append("  FALTA el comando")
    return lineas


def _zonas_por_deteccion(evento: Any, config: ConfigPolitica) -> list[list[str]]:
    """Por cada detección, las zonas que ocupa como obstáculo; vacía si no cuenta."""
    if not isinstance(evento, dict) or evento.get("status") != "ok":
        return []
    try:
        por_zona = detecciones_por_zona(evento, config)
    except (KeyError, TypeError, ValueError):
        # Un evento fuera de contrato: el supervisor ya lo frenó; aquí solo no hay zonas.
        return [[] for _ in evento.get("detections") or []]
    return [
        [zona for zona, dets in por_zona.items() if any(d is det for d in dets)]
        for det in evento["detections"]
    ]


def _clave(linea: Any) -> Clave:
    if not isinstance(linea, dict):
        return (None, None)
    return (linea.get("run_id"), linea.get("frame_id"))


def _leer_jsonl(ruta: Path) -> list[Any]:
    texto = ruta.read_text(encoding="utf-8")  # NOSONAR (S8707): carpeta elegida con --salida
    return [json.loads(linea) for linea in texto.splitlines() if linea.strip()]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m control.traza",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--salida", type=Path, required=True, help="carpeta de python -m control")
    parser.add_argument("--frame-id", help="mostrar solo este cuadro")
    parser.add_argument(
        "--config", type=Path, default=CARPETA_CONFIG, help="carpeta con politica.yaml"
    )
    args = parser.parse_args(argv)

    try:
        config = cargar_config_politica(args.config / NOMBRE_POLITICA)
        traza = trazar(args.salida, config)
    except (OSError, json.JSONDecodeError, ErrorConfigPolitica) as exc:
        print(f"no se pudo leer la corrida o la configuración: {exc}", file=sys.stderr)
        return 2

    print(formatear(traza, args.frame_id))
    if args.frame_id is not None:
        return 0 if any(c["frame_id"] == args.frame_id for c in traza["cuadros"]) else 1
    return 1 if traza["incompletos"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
