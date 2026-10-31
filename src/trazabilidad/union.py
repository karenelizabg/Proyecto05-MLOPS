"""Une una corrida cuadro por cuadro y recalcula sus cifras solo desde esa unión (P5-14).

Una corrida es la carpeta que deja `python -m control`: `detecciones.jsonl` (los eventos del
detector), `decisiones.jsonl`, `comandos.jsonl`, `errores.jsonl` y `run.json`. Con las anotaciones
de P5-10, `construir` arma una fila por cuadro con todo lo de ese cuadro, unido por `run_id` y
`frame_id`:

- `evento`: el evento del contrato v1 tal como lo emitió el detector (detecciones, estado, error,
  `model_sha256`, `config_sha256`), o `null` si un cuadro anotado no tuvo evento.
- `anotacion`: la verdad de referencia del cuadro, o `null` si no está anotado.
- `conteo`: TP/FP/FN del cuadro a IoU 0.50 (P5-13), o `null` si no está anotado.
- `decision` y `comando`: lo que decidió B y la orden que registró el adaptador.
- `errores`: lo que registró el supervisor para ese cuadro, con su motivo.

`recalcular` vuelve a producir las métricas de P5-13 y los conteos **solo** desde esas filas, sin
leer la corrida ni las anotaciones: si da lo mismo que el reporte, el reporte no tiene cifras
pegadas a mano.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from control.__main__ import NOMBRE_DECISIONES, NOMBRE_DETECCIONES, NOMBRE_RUN
from control.adaptador_virtual import NOMBRE_REGISTRO
from control.supervisor import NOMBRE_ERRORES
from metricas import evaluar
from metricas.evaluacion import EntradaInvalida

ARCHIVOS_CORRIDA = (NOMBRE_DETECCIONES, NOMBRE_DECISIONES, NOMBRE_REGISTRO, NOMBRE_ERRORES)
CAMPOS_DECISION = ("event", "t_ms", "state_before", "state_after", "action", "reason", "decidio")
CAMPOS_COMANDO = (
    "action",
    "speed",
    "steering",
    "reason",
    "t_decision_ms",
    "t_command_ms",
    "valid_until_ms",
    "received",
)


class ErrorTrazabilidad(ValueError):
    """La corrida o las anotaciones no se pueden unir."""


def leer_jsonl(ruta: Path) -> list[Any]:
    texto = ruta.read_text(encoding="utf-8")  # NOSONAR (S8707): carpeta elegida por quien corre
    return [json.loads(linea) for linea in texto.splitlines() if linea.strip()]


def leer_corrida(carpeta: Path) -> dict[str, Any]:
    """Los cuatro registros de `python -m control` y su `run.json`."""
    faltan = [n for n in (*ARCHIVOS_CORRIDA, NOMBRE_RUN) if not (carpeta / n).is_file()]
    if faltan:
        raise ErrorTrazabilidad(
            f"{carpeta.as_posix()} no es una corrida de control: faltan {faltan}"
        )
    datos = {nombre: leer_jsonl(carpeta / nombre) for nombre in ARCHIVOS_CORRIDA}
    datos[NOMBRE_RUN] = json.loads((carpeta / NOMBRE_RUN).read_text(encoding="utf-8"))  # NOSONAR
    return datos


def _por_cuadro(registros: Iterable[Mapping[str, Any]]) -> dict[tuple[Any, Any], list[Any]]:
    agrupados: dict[tuple[Any, Any], list[Any]] = {}
    for registro in registros:
        if registro.get("frame_id") is not None:
            agrupados.setdefault((registro["run_id"], registro["frame_id"]), []).append(registro)
    return agrupados


def _unico(registros: list[Any] | None, campos: tuple[str, ...]) -> dict[str, Any] | None:
    if not registros:
        return None
    # Un cuadro llega a B una vez; si hubiera más, se guarda el último y queda la advertencia.
    return {c: registros[-1].get(c) for c in campos}


def _filas(
    eventos: list[dict[str, Any]],
    anotaciones: list[dict[str, Any]],
    decisiones: dict[tuple[Any, Any], list[Any]],
    comandos: dict[tuple[Any, Any], list[Any]],
    errores: dict[tuple[Any, Any], list[Any]],
) -> list[dict[str, Any]]:
    run_id = eventos[0]["run_id"] if eventos else None
    anotacion_de = {a["frame_id"]: (n, a) for n, a in enumerate(anotaciones)}
    filas = []
    for n, evento in enumerate(eventos):
        clave = (evento["run_id"], evento["frame_id"])
        orden_anotacion, anotacion = anotacion_de.get(evento["frame_id"], (None, None))
        filas.append(
            {
                "run_id": evento["run_id"],
                "frame_id": evento["frame_id"],
                "sequence_id": evento["sequence_id"],
                "orden_evento": n,
                "orden_anotacion": orden_anotacion,
                "evento": evento,
                "anotacion": anotacion,
                "conteo": None,
                "decision": _unico(decisiones.get(clave), CAMPOS_DECISION),
                "comando": _unico(comandos.get(clave), CAMPOS_COMANDO),
                "errores": [
                    {"motivo": e.get("motivo"), "errores": e.get("errores", [])}
                    for e in errores.get(clave, [])
                ],
            }
        )
    # Un cuadro anotado sin evento sigue en el denominador (sus objetos son FN): también va.
    con_evento = {e["frame_id"] for e in eventos}
    for n, anotacion in enumerate(anotaciones):
        if anotacion["frame_id"] not in con_evento:
            filas.append(
                {
                    "run_id": run_id,
                    "frame_id": anotacion["frame_id"],
                    "sequence_id": anotacion["sequence_id"],
                    "orden_evento": None,
                    "orden_anotacion": n,
                    "evento": None,
                    "anotacion": anotacion,
                    "conteo": None,
                    "decision": None,
                    "comando": None,
                    "errores": [],
                }
            )
    return filas


def _evaluar(
    filas: list[dict[str, Any]], model_sha256: str | None, config_sha256: str | None
) -> Any:
    eventos = [f["evento"] for f in sorted(filas, key=_orden("orden_evento")) if f["evento"]]
    anotaciones = [
        f["anotacion"] for f in sorted(filas, key=_orden("orden_anotacion")) if f["anotacion"]
    ]
    if not anotaciones:
        return None
    try:
        return evaluar(anotaciones, eventos, model_sha256, config_sha256)
    except EntradaInvalida as exc:
        raise ErrorTrazabilidad("; ".join(exc.errores)) from exc


def _orden(campo: str):
    return lambda fila: (fila[campo] is None, fila[campo] or 0)


def _conteos(filas: list[dict[str, Any]], ordenes_sin_cuadro: list[dict[str, Any]]) -> dict:
    """Lo que se cuenta del lado de B, por cuadro y por secuencia, sin ocultar nada."""
    por_secuencia: dict[str, dict[str, Counter]] = {}
    for fila in filas:
        secuencia = por_secuencia.setdefault(
            fila["sequence_id"],
            {"acciones": Counter(), "estados": Counter(), "errores": Counter()},
        )
        secuencia["acciones"][fila["comando"]["action"] if fila["comando"] else "sin_comando"] += 1
        secuencia["estados"][fila["evento"]["status"] if fila["evento"] else "sin_evento"] += 1
        secuencia["errores"].update(e["motivo"] for e in fila["errores"])
    return {
        "cuadros": len(filas),
        "por_secuencia": {
            s: {k: dict(sorted(c.items())) for k, c in v.items()}
            for s, v in sorted(por_secuencia.items())
        },
        "errores": [
            {"frame_id": f["frame_id"], "motivo": e["motivo"]} for f in filas for e in f["errores"]
        ],
        "sin_decision": [f["frame_id"] for f in filas if f["evento"] and not f["decision"]],
        "sin_comando": [f["frame_id"] for f in filas if f["evento"] and not f["comando"]],
        "ordenes_sin_cuadro": dict(
            sorted(Counter(f"{o['event']}:{o['action']}" for o in ordenes_sin_cuadro).items())
        ),
    }


def _conteo_por_cuadro(resultado: Any) -> dict[str, dict[str, int]]:
    if resultado is None:
        return {}
    return {f["frame_id"]: {k: f[k] for k in ("tp", "fp", "fn")} for f in resultado.por_cuadro}


def recalcular(
    filas: list[dict[str, Any]],
    ordenes_sin_cuadro: list[dict[str, Any]],
    model_sha256: str | None = None,
    config_sha256: str | None = None,
) -> dict[str, Any]:
    """Las cifras del reporte, solo desde las filas: métricas de P5-13, conteos y hashes.

    También revisa que el TP/FP/FN guardado en cada fila sea el que sale de su evento y su
    anotación: `conteo_por_cuadro` lista los cuadros donde no.
    """
    resultado = _evaluar(filas, model_sha256, config_sha256)
    por_cuadro = _conteo_por_cuadro(resultado)
    eventos = [f["evento"] for f in filas if f["evento"]]
    cifras = {
        "metricas": None if resultado is None else resultado.resumen,
        "conteo_por_cuadro": {
            "distintos": [
                f["frame_id"] for f in filas if f["conteo"] != por_cuadro.get(f["frame_id"])
            ]
        },
        "conteos": _conteos(filas, ordenes_sin_cuadro),
        "detector": {
            campo: sorted({e[campo] for e in eventos})
            for campo in ("model_sha256", "config_sha256")
        },
    }
    # Por la misma ruta que el reporte escrito: así se compara lo que de verdad queda en JSON.
    return json.loads(json.dumps(cifras, ensure_ascii=False))


def construir(
    corrida: Mapping[str, Any],
    anotaciones: list[dict[str, Any]] | None,
    model_sha256: str | None = None,
    config_sha256: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    """Filas por cuadro, cifras del reporte y advertencias de una corrida."""
    eventos = corrida[NOMBRE_DETECCIONES]
    if len({e["run_id"] for e in eventos}) > 1:
        raise ErrorTrazabilidad("la corrida mezcla varios run_id: se une un run a la vez")
    anotaciones = anotaciones or []
    frames_evento = {e["frame_id"] for e in eventos}
    frames_anotados = {a["frame_id"] for a in anotaciones}
    if eventos and anotaciones and not frames_evento & frames_anotados:
        raise ErrorTrazabilidad(
            "ningún frame_id de los eventos está en las anotaciones (p. ej. "
            f"{sorted(frames_evento)[0]!r} contra {sorted(frames_anotados)[0]!r}): el detector y "
            "el conjunto deben usar el mismo frame_id para cada cuadro"
        )

    comandos = corrida[NOMBRE_REGISTRO]
    filas = _filas(
        eventos,
        anotaciones,
        _por_cuadro(corrida[NOMBRE_DECISIONES]),
        _por_cuadro(comandos),
        _por_cuadro(corrida[NOMBRE_ERRORES]),
    )
    ordenes_sin_cuadro = [
        {c: o.get(c) for c in ("event", *CAMPOS_COMANDO)}
        for o in comandos
        if o.get("frame_id") is None
    ]
    por_cuadro = _conteo_por_cuadro(_evaluar(filas, model_sha256, config_sha256))
    for fila in filas:
        fila["conteo"] = por_cuadro.get(fila["frame_id"])
    cifras = recalcular(filas, ordenes_sin_cuadro, model_sha256, config_sha256)

    advertencias = []
    if not anotaciones:
        advertencias.append("sin anotaciones: no hay métricas de detección, solo conteos de B")
    elif cifras["metricas"]["advertencias"]:
        advertencias += [f"métricas: {a}" for a in cifras["metricas"]["advertencias"]]
    conteos = cifras["conteos"]
    for clave, texto in (
        ("sin_decision", "cuadros con evento pero sin decisión de B"),
        ("sin_comando", "cuadros con evento pero sin comando"),
    ):
        if conteos[clave]:
            advertencias.append(f"{len(conteos[clave])} {texto}: {conteos[clave]}")
    repetidos = [
        f"{frame}" for (_, frame), registros in _por_cuadro(comandos).items() if len(registros) > 1
    ]
    if repetidos:
        advertencias.append(f"cuadros con más de un comando (se guarda el último): {repetidos}")
    return filas, {**cifras, "ordenes_sin_cuadro": ordenes_sin_cuadro}, advertencias
