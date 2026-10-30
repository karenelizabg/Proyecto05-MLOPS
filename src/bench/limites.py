"""Contraste del benchmark con los plazos de B (P5-16, E7).

Uso:
    python -m bench.limites mediciones/<run>/ [--config-control config/control/] [--periodo-ms 200]

Lee `resumen.json` de una corrida de `python -m bench` y `plazos.yaml` de B, y escribe en la
misma carpeta `contraste.json` y `contraste.md`: p50/p95/máximo frente a cada presupuesto, con
veredicto y razón. Lo declarado (los plazos de B y el ritmo de entrada de PEND-09) y lo
reproducido (lo que midió el benchmark) quedan en secciones aparte.

Veredicto de cada presupuesto:
- `cumple`: hasta el máximo observado queda dentro del plazo.
- `cumple en p95`: el p95 queda dentro, pero el máximo lo pasa; algún cuadro se pierde.
- `no cumple`: el p95 pasa el plazo.

Salida: 0 si todo cumple y la corrida es la del entregable (completa, sin advertencias y con los
mismos plazos con que se midió); 1 si algo no cumple del todo o hay advertencias; 2 si no se
puede leer la corrida o los plazos (no se escribe nada).

Las rutas las elige quien corre el comando. Por eso las lecturas y escrituras con esas rutas
llevan `NOSONAR (S8707)`, como en `python -m bench`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from control.__main__ import CARPETA_CONFIG, NOMBRE_PLAZOS, cargar_plazos

from .arnes import PERIODO_MS, ruta_publicable, sha256_archivo

CUMPLE = "cumple"
CUMPLE_EN_P95 = "cumple en p95"
NO_CUMPLE = "no cumple"
ESTADISTICOS = ("p50", "p95", "maximo")

# Cada presupuesto: qué tiempo medido se compara, contra qué plazo y por qué importa.
# `intervalo` es el tiempo entre dos eventos (o comandos) seguidos: el periodo de entrada, o lo
# que tarde procesar un cuadro si tarda más que eso.
PRESUPUESTOS = (
    {
        "id": "inferencia_vs_timeout",
        "medido": "inferencia_ms",
        "plazo": "detector_timeout_ms",
        "razon": (
            "Una inferencia más larga que el plazo hace que A emita status=error "
            "(detector_timeout) y B frene (C9)."
        ),
    },
    {
        "id": "total_vs_edad",
        "medido": "total_ms",
        "plazo": "max_frame_age_ms",
        "razon": (
            "El comando sale cuando el cuadro ya tiene al menos total_ms de edad; pasado "
            "max_frame_age_ms, B lo rechaza por viejo y frena (C8)."
        ),
    },
    {
        "id": "total_vs_periodo",
        "medido": "total_ms",
        "plazo": "periodo_entrada_ms",
        "razon": (
            "Si procesar un cuadro tarda más que el periodo de entrada, los cuadros se acumulan "
            "y cada uno llega más viejo que el anterior."
        ),
    },
    {
        "id": "intervalo_vs_validez",
        "medido": "intervalo",
        "plazo": "validez_orden_ms",
        "razon": (
            "Entre dos comandos pasa el periodo de entrada o lo que tarde procesar un cuadro; "
            "si eso pasa validez_orden_ms, el adaptador frena por su cuenta entre cuadros."
        ),
    },
    {
        "id": "intervalo_vs_watchdog",
        "medido": "intervalo",
        "plazo": "watchdog_ms",
        "razon": (
            "Si entre dos eventos pasa más que watchdog_ms, B emite STOP por falta de "
            "percepción aunque el detector siga funcionando."
        ),
    },
)

NO_MEDIDO = (
    "Captura en la ESP32-CAM, transmisión por WiFi, lectura y decodificación del JPEG: el "
    "benchmark parte de la imagen ya en memoria, así que la edad real del cuadro es mayor que "
    "total_ms.",
    "Carga del modelo: se hace una vez al arrancar, antes del primer cuadro.",
    "Frenado mecánico, distancia de frenado y movimiento del carro: el control es virtual y los "
    "comandos solo se registran.",
)


class ErrorLimites(ValueError):
    """La corrida o los plazos no se pueden contrastar."""


def cargar_resumen(carpeta: Path) -> dict[str, Any]:
    """Lee `resumen.json` y revisa que traiga p50/p95/máximo de las etapas que se contrastan."""
    ruta = carpeta / "resumen.json"
    try:
        resumen = json.loads(ruta.read_text(encoding="utf-8"))  # NOSONAR (S8707)
    except FileNotFoundError as exc:
        raise ErrorLimites(f"no hay {ruta_publicable(ruta)}: corre antes python -m bench") from exc
    except json.JSONDecodeError as exc:
        raise ErrorLimites(f"{ruta_publicable(ruta)} no es JSON válido: {exc}") from exc
    etapas = resumen.get("etapas") if isinstance(resumen, dict) else None
    if not isinstance(etapas, dict):
        raise ErrorLimites(f"{ruta_publicable(ruta)} no tiene la sección etapas")
    for etapa in {p["medido"] for p in PRESUPUESTOS} - {"intervalo"}:
        valores = etapas.get(etapa)
        if not isinstance(valores, dict) or not all(
            isinstance(valores.get(e), (int, float)) and not isinstance(valores.get(e), bool)
            for e in ESTADISTICOS
        ):
            raise ErrorLimites(f"{ruta_publicable(ruta)}: falta p50/p95/maximo de {etapa}")
    return resumen


def veredicto(p95: float, maximo: float, plazo: float) -> str:
    if maximo <= plazo:
        return CUMPLE
    if p95 <= plazo:
        return CUMPLE_EN_P95
    return NO_CUMPLE


def contrastar(
    resumen: dict[str, Any], plazos: dict[str, Any], periodo_ms: float
) -> list[dict[str, Any]]:
    """Una fila por presupuesto: los estadísticos medidos, el plazo, el veredicto y el margen."""
    etapas = resumen["etapas"]
    limites = {**plazos, "periodo_entrada_ms": periodo_ms}
    filas = []
    for presupuesto in PRESUPUESTOS:
        if presupuesto["medido"] == "intervalo":
            medidos = {e: max(periodo_ms, etapas["total_ms"][e]) for e in ESTADISTICOS}
        else:
            medidos = {e: etapas[presupuesto["medido"]][e] for e in ESTADISTICOS}
        plazo = limites[presupuesto["plazo"]]
        filas.append(
            {
                **presupuesto,
                **medidos,
                "plazo_ms": plazo,
                "margen_p95_ms": plazo - medidos["p95"],
                "veredicto": veredicto(medidos["p95"], medidos["maximo"], plazo),
            }
        )
    return filas


def advertencias_de_corrida(resumen: dict[str, Any], sha_plazos: str) -> list[str]:
    """Por qué esta corrida no sirve como la medición del entregable, si es el caso."""
    advertencias = []
    if resumen.get("estado") != "completo":
        advertencias.append("la corrida quedó incompleta: demasiados fallos")
    if resumen.get("advertencias"):
        advertencias.append(
            "la corrida tiene advertencias, no es la medición del entregable: "
            + "; ".join(resumen["advertencias"])
        )
    config_b = (resumen.get("procedencia") or {}).get("config_b")
    if not config_b:
        advertencias.append("la corrida no midió la etapa de B (--sin-politica)")
    elif config_b.get(NOMBRE_PLAZOS) != sha_plazos:
        advertencias.append(
            "plazos.yaml cambió desde la corrida: se contrasta con plazos distintos a los medidos"
        )
    return advertencias


def _fmt(valor: float) -> str:
    return f"{valor:.2f}"


def reporte_md(contraste: dict[str, Any]) -> str:
    corrida, plazos = contraste["corrida"], contraste["plazos"]
    lineas = [
        "# Contraste con los plazos de B (P5-16)",
        "",
        "Generado por `python -m bench.limites`; no editar a mano.",
        "",
        "## Reproducido (benchmark)",
        "",
        f"- Corrida: `{corrida['carpeta']}` (`resumen.json` SHA-256 `{corrida['resumen_sha256']}`)",
        f"- Equipo: {corrida['equipo']} · energía: {corrida['energia']} · estado: "
        f"{corrida['estado']}",
        f"- Mediciones: {corrida['mediciones']} (sin calentamientos) · fallos aparte: "
        f"{corrida['fallos']}",
        "",
        "## Declarado (plazos de B y ritmo de entrada)",
        "",
        f"- `{plazos['archivo']}` (SHA-256 `{plazos['sha256']}`)",
    ]
    lineas += [f"- `{k}`: {v} ms" for k, v in plazos["valores"].items()]
    lineas += [
        f"- `periodo_entrada_ms`: {plazos['periodo_entrada_ms']} ms ({plazos['fuente_periodo']})",
        "",
        "## Contraste",
        "",
        "| Medido | p50 | p95 | Máximo | Plazo | Margen p95 | Veredicto | Razón |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for fila in contraste["contraste"]:
        lineas.append(
            f"| `{fila['medido']}` | {_fmt(fila['p50'])} | {_fmt(fila['p95'])} | "
            f"{_fmt(fila['maximo'])} | `{fila['plazo']}` = {fila['plazo_ms']} | "
            f"{_fmt(fila['margen_p95_ms'])} | **{fila['veredicto']}** | {fila['razon']} |"
        )
    lineas += [
        "",
        "Todo en ms. `intervalo` = el mayor entre `periodo_entrada_ms` y `total_ms`: el tiempo "
        "entre dos eventos seguidos.",
        "",
        "## No medido",
        "",
        *(f"- {texto}" for texto in contraste["no_medido"]),
        "",
        "## Advertencias",
        "",
        *(f"- {texto}" for texto in contraste["advertencias"] or ["Ninguna."]),
        "",
    ]
    return "\n".join(lineas)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m bench.limites", description="Contrasta un benchmark con los plazos de B."
    )
    parser.add_argument("corrida", type=Path, help="carpeta de salida de python -m bench")
    parser.add_argument(
        "--config-control",
        type=Path,
        default=CARPETA_CONFIG,
        help="carpeta con plazos.yaml (por omisión config/control/)",
    )
    parser.add_argument(
        "--periodo-ms",
        type=float,
        default=PERIODO_MS,
        help=f"periodo de entrada declarado en PEND-09 (por omisión {PERIODO_MS})",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.periodo_ms <= 0:
        parser.error("--periodo-ms debe ser mayor que 0")

    ruta_plazos = args.config_control / NOMBRE_PLAZOS
    try:
        resumen = cargar_resumen(args.corrida)
        plazos = cargar_plazos(ruta_plazos)
        sha_plazos = sha256_archivo(ruta_plazos)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"no se contrasta: {exc}", file=sys.stderr)
        return 2

    filas = contrastar(resumen, plazos, args.periodo_ms)
    advertencias = advertencias_de_corrida(resumen, sha_plazos)
    conteos = resumen.get("conteos", {})
    contraste = {
        "version": 1,
        "corrida": {
            "carpeta": ruta_publicable(args.corrida),
            "resumen_sha256": sha256_archivo(args.corrida / "resumen.json"),
            "equipo": resumen.get("equipo"),
            "energia": resumen.get("energia"),
            "estado": resumen.get("estado"),
            "mediciones": conteos.get("mediciones"),
            "fallos": conteos.get("fallos"),
        },
        "plazos": {
            "archivo": ruta_publicable(ruta_plazos),
            "sha256": sha_plazos,
            "valores": {
                p["plazo"]: plazos[p["plazo"]] for p in PRESUPUESTOS if p["plazo"] in plazos
            },
            "periodo_entrada_ms": args.periodo_ms,
            "fuente_periodo": "PEND-09, provisional: ≈ 5 fps hasta que B lo declare",
        },
        "contraste": filas,
        "no_medido": list(NO_MEDIDO),
        "advertencias": advertencias,
    }

    texto = json.dumps(contraste, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    (args.corrida / "contraste.json").write_text(texto, encoding="utf-8")  # NOSONAR (S8707)
    (args.corrida / "contraste.md").write_text(  # NOSONAR (S8707)
        reporte_md(contraste), encoding="utf-8"
    )

    for fila in filas:
        print(
            f"{fila['medido']} vs {fila['plazo']}: p95={_fmt(fila['p95'])} "
            f"máx={_fmt(fila['maximo'])} / {fila['plazo_ms']} ms: {fila['veredicto']}"
        )
    for advertencia in advertencias:
        print(f"advertencia: {advertencia}", file=sys.stderr)
    print(f"contraste en {args.corrida.as_posix()}/contraste.md")
    todo_cumple = all(f["veredicto"] == CUMPLE for f in filas)
    return 0 if todo_cumple and not advertencias else 1


if __name__ == "__main__":
    raise SystemExit(main())
