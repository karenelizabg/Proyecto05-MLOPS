"""Corre los casos C1 a C10 y juzga cada uno con su expectativa (T17).

    uv run python casos/runner.py              # los diez
    uv run python casos/runner.py C8 C10       # solo esos

Cada carpeta casos/Cn/ trae:

- `expectativa.yaml`: qué debe pasar (T15, congelada).
- `entrada.jsonl`: los eventos de percepción. C1 a C5 y C7 usan secuencias reales de A
  (datos/MAPA_CASOS.md); C8 a C10 pueden usar eventos armados.
- `tramos.yaml`: si la entrada es `real` o `armada` y qué `frame_id` le toca a cada tramo.
- `acciones.yaml` (opcional): `tick`, `emergencia`, `rearmar` y `cerrar` en instantes fijos.

Cada caso se corre con `python -m control` (la misma `main`, en este proceso) y deja sus registros
en `resultados/casos/Cn/`. Después se juzga solo con esos archivos, tramo por tramo, con las reglas
de casos/README.md ("Cómo se juzga un tramo"), y se escribe `veredicto.json` con cada motivo. Al
final se imprime la tabla PASA/FALLA, que también queda en `resultados/casos/resumen.txt`.

Un caso falla si le falta la entrada o los tramos, si su entrada no cumple el contrato, si pide
una secuencia real y trae una armada, si `python -m control` no sale con 0, o si no se cumple
algún tramo o algún `stop_con_evento`. En los motivos, "orden N" es la línea N de comandos.jsonl.

Las rutas de `--casos`, `--config` y `--salida` las elige quien corre el comando (las pruebas usan
una copia temporal), por eso sus lecturas y escrituras llevan `NOSONAR (S8707)`.

Salida: 0 si todos los casos pasan, 1 si alguno falla, 2 si la configuración no se puede leer.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from contrato import leer_eventos, validar_evento, validar_flujo
from control.__main__ import main as correr_control
from control.config import ConfigPolitica, ErrorConfigPolitica, cargar_config_politica
from control.politica import zonas_ocupadas

RAIZ = Path(__file__).resolve().parents[1]
CASOS = RAIZ / "casos"
CONFIG = RAIZ / "config" / "control"
SALIDA = RAIZ / "resultados" / "casos"
NOMBRES = tuple(f"C{n}" for n in range(1, 11))
# Los que corren con secuencias reales de A (P5-12, datos/MAPA_CASOS.md).
CON_SECUENCIA_REAL = ("C1", "C2", "C3", "C4", "C5", "C7")
ENTRADAS = ("real", "armada")

NOMBRE_ESQUEMA = "expectativa.v1.schema.json"
NOMBRE_EXPECTATIVA = "expectativa.yaml"
NOMBRE_ENTRADA = "entrada.jsonl"
NOMBRE_TRAMOS = "tramos.yaml"
NOMBRE_ACCIONES = "acciones.yaml"
NOMBRE_VEREDICTO = "veredicto.json"
NOMBRE_RESUMEN = "resumen.txt"
REGISTROS = ("detecciones.jsonl", "decisiones.jsonl", "comandos.jsonl", "errores.jsonl", "run.json")

# Qué acción de acciones.yaml deja las órdenes de cada `origen` sin cuadro.
ACCION_DEL_ORIGEN = {"emergency": "emergencia", "rearm": "rearmar", "shutdown": "cerrar"}
LADO_DEL_GIRO = {"GIRAR_IZQ": "izq", "GIRAR_DER": "der"}


class CasoMalArmado(ValueError):
    """A la carpeta del caso le falta un archivo o uno no tiene la forma esperada."""


@dataclass
class Caso:
    nombre: str
    carpeta: Path
    expectativa: dict[str, Any]
    entrada: str
    cuadros: dict[str, list[str]]


@dataclass
class Registros:
    """Lo que dejó `python -m control` en la carpeta del caso."""

    comandos: list[dict[str, Any]]
    errores: list[dict[str, Any]]
    eventos: dict[str, dict[str, Any]]
    llegada: dict[str, int]
    acciones: list[dict[str, Any]]


# --- leer el caso -----------------------------------------------------------------


def cargar_caso(carpeta: Path, esquema: dict[str, Any]) -> Caso:
    """Lee la carpeta del caso y revisa que sus archivos se correspondan."""
    if not carpeta.is_dir():
        raise CasoMalArmado(f"falta la carpeta {carpeta.name}/")
    expectativa = _leer_yaml(_exigir(carpeta / NOMBRE_EXPECTATIVA))
    errores = [e.message for e in Draft202012Validator(esquema).iter_errors(expectativa)]
    if errores:
        raise CasoMalArmado(f"{NOMBRE_EXPECTATIVA} no cumple su esquema: {errores[0]}")
    if expectativa["caso"] != carpeta.name:
        raise CasoMalArmado(f"{NOMBRE_EXPECTATIVA} dice caso {expectativa['caso']}")

    pide_real = " (pide una secuencia real de A: datos/MAPA_CASOS.md)"
    ruta_entrada = _exigir(
        carpeta / NOMBRE_ENTRADA, pide_real if carpeta.name in CON_SECUENCIA_REAL else ""
    )
    eventos = leer_eventos(ruta_entrada)
    errores = [
        f"evento {n}: {msg}"
        for n, evento in enumerate(eventos, start=1)
        for msg in validar_evento(evento)
    ] or validar_flujo(eventos)
    if errores:
        raise CasoMalArmado(f"{NOMBRE_ENTRADA} no cumple el contrato: {errores[0]}")

    tramos = _leer_yaml(_exigir(carpeta / NOMBRE_TRAMOS))
    entrada, cuadros = _revisar_tramos(tramos, expectativa, eventos)
    return Caso(carpeta.name, carpeta, expectativa, entrada, cuadros)


def _revisar_tramos(
    datos: Any, expectativa: dict[str, Any], eventos: list[dict[str, Any]]
) -> tuple[str, dict[str, list[str]]]:
    """tramos.yaml: `entrada` y los `frame_id` de cada tramo con origen `cuadros`."""
    if not isinstance(datos, dict) or set(datos) != {"entrada", "tramos"}:
        raise CasoMalArmado(f"{NOMBRE_TRAMOS} lleva exactamente `entrada` y `tramos`")
    if datos["entrada"] not in ENTRADAS:
        raise CasoMalArmado(f"{NOMBRE_TRAMOS}: `entrada` es {' o '.join(ENTRADAS)}")
    cuadros = datos["tramos"]
    esperados = {t["nombre"] for t in expectativa["tramos"] if t["origen"] == "cuadros"}
    if not isinstance(cuadros, dict) or set(cuadros) != esperados:
        raise CasoMalArmado(f"{NOMBRE_TRAMOS} lista los cuadros de {sorted(esperados)}")

    en_la_entrada = {e["frame_id"] for e in eventos}
    vistos: set[str] = set()
    for nombre, lista in cuadros.items():
        if not isinstance(lista, list) or not lista:
            raise CasoMalArmado(f"{NOMBRE_TRAMOS}: {nombre} necesita al menos un frame_id")
        for frame_id in lista:
            if frame_id not in en_la_entrada:
                raise CasoMalArmado(f"{NOMBRE_TRAMOS}: {frame_id!r} no está en {NOMBRE_ENTRADA}")
            if frame_id in vistos:
                raise CasoMalArmado(f"{NOMBRE_TRAMOS}: {frame_id} está en más de un tramo")
            vistos.add(frame_id)
    return datos["entrada"], cuadros


def _exigir(ruta: Path, detalle: str = "") -> Path:
    if not ruta.is_file():
        raise CasoMalArmado(f"falta {ruta.name}{detalle}")
    return ruta


def _leer_yaml(ruta: Path) -> Any:
    return yaml.safe_load(ruta.read_text(encoding="utf-8"))  # NOSONAR (S8707)


# --- correrlo ---------------------------------------------------------------------


def correr_caso(caso: Caso, config: Path, salida: Path) -> tuple[int, str]:
    """`python -m control` con la entrada y las acciones del caso. Devuelve su código y lo que
    imprimió."""
    argv = ["--entrada", _relativa(caso.carpeta / NOMBRE_ENTRADA)]
    argv += ["--config", _relativa(config), "--salida", _relativa(salida)]
    acciones = caso.carpeta / NOMBRE_ACCIONES
    if acciones.is_file():
        argv += ["--acciones", _relativa(acciones)]
    impreso = io.StringIO()
    with contextlib.redirect_stdout(impreso), contextlib.redirect_stderr(impreso):
        codigo = correr_control(argv)
    return codigo, impreso.getvalue().strip()


def _relativa(ruta: Path) -> str:
    """La ruta desde la carpeta actual, para que run.json no guarde la carpeta de quien corre."""
    try:
        return Path(os.path.relpath(ruta)).as_posix()
    except ValueError:
        # En Windows, otra unidad de disco no tiene ruta relativa.
        return str(ruta)


def leer_registros(salida: Path) -> Registros:
    detecciones = _leer_jsonl(salida / "detecciones.jsonl")
    run = json.loads((salida / "run.json").read_text(encoding="utf-8"))  # NOSONAR (S8707)
    return Registros(
        comandos=_leer_jsonl(salida / "comandos.jsonl"),
        errores=_leer_jsonl(salida / "errores.jsonl"),
        eventos={e["frame_id"]: e for e in detecciones},
        llegada={e["frame_id"]: n for n, e in enumerate(detecciones)},
        acciones=run["acciones"]["hechas"],
    )


def _leer_jsonl(ruta: Path) -> list[Any]:
    texto = ruta.read_text(encoding="utf-8")  # NOSONAR (S8707)
    return [json.loads(linea) for linea in texto.splitlines() if linea.strip()]


# --- juzgarlo (casos/README.md, "Cómo se juzga un tramo") ---------------------------


def juzgar(
    expectativa: dict[str, Any],
    cuadros: dict[str, list[str]],
    reg: Registros,
    config: ConfigPolitica,
) -> list[dict[str, Any]]:
    """Un resultado por tramo, en orden: sus órdenes (líneas de comandos.jsonl) y sus motivos."""
    de_cuadros = {nombre: _ordenes_de_cuadros(reg, lista) for nombre, lista in cuadros.items()}
    tramos = expectativa["tramos"]
    resultados = []
    fin_previo = -1
    for i, tramo in enumerate(tramos):
        if tramo["origen"] == "cuadros":
            frames = sorted(cuadros[tramo["nombre"]], key=reg.llegada.__getitem__)
            indices = de_cuadros[tramo["nombre"]]
            inicio = fin = None
        else:
            # Las órdenes con ese event entre el tramo anterior y el siguiente.
            frames = []
            inicio, fin = fin_previo + 1, _inicio_siguiente(tramos[i + 1 :], de_cuadros, reg)
            indices = [k for k in range(inicio, fin) if reg.comandos[k]["event"] == tramo["origen"]]
        t0 = _instante_del_plazo(tramo, frames, inicio, fin, reg)
        motivos = revisar_tramo(tramo, indices, frames, t0, reg, config)
        resultados.append(
            {"tramo": tramo["nombre"], "ordenes": [k + 1 for k in indices], "motivos": motivos}
        )
        if indices:
            fin_previo = max(fin_previo, indices[-1])
    return resultados


def revisar_tramo(
    tramo: dict[str, Any],
    indices: list[int],
    frames: list[str],
    t0: float | None,
    reg: Registros,
    config: ConfigPolitica,
) -> list[str]:
    """Pasos 1 a 4 de casos/README.md. Vacío si el tramo se cumple."""
    comandos = reg.comandos
    permitidas = set(tramo["acciones_permitidas"])
    prohibidas = set(tramo["acciones_prohibidas"])
    motivos = [
        f"{_orden(comandos, k)}: {comandos[k]['action']} está prohibida"
        for k in indices
        if comandos[k]["action"] in prohibidas
    ]
    if tramo["plazo_reaccion_ms"] is None:
        motivos += [
            f"{_orden(comandos, k)}: {comandos[k]['action']} no está permitida"
            for k in indices
            if comandos[k]["action"] not in permitidas | prohibidas
        ]
        motivos += [
            f"el cuadro {f} no dejó ninguna orden"
            for f in frames
            if not any(comandos[k]["frame_id"] == f for k in indices)
        ]
    else:
        motivos += _revisar_plazo(tramo, indices, t0, comandos)
    motivos += _revisar_mantener(tramo, indices, frames, comandos)
    for condicion in tramo.get("condiciones", []):
        motivos += CONDICIONES[condicion](indices, frames, reg, config)
    return motivos


def revisar_stop_con_evento(expectativa: dict[str, Any], reg: Registros) -> list[str]:
    return [
        f"stop_con_evento: ninguna orden STOP con event={evento}"
        for evento in expectativa["stop_con_evento"]
        if not any(c["event"] == evento and c["action"] == "STOP" for c in reg.comandos)
    ]


def _revisar_plazo(
    tramo: dict[str, Any], indices: list[int], t0: float | None, comandos: list[dict[str, Any]]
) -> list[str]:
    """La primera orden permitida sale a tiempo y desde ella todas están permitidas."""
    plazo = tramo["plazo_reaccion_ms"]
    permitidas = set(tramo["acciones_permitidas"])
    prohibidas = set(tramo["acciones_prohibidas"])
    if t0 is None:
        return [f"no hay desde dónde medir el plazo (plazo_desde: {tramo['plazo_desde']})"]
    primera = next((k for k in indices if comandos[k]["action"] in permitidas), None)
    if primera is None:
        return [f"ninguna orden con {'/'.join(sorted(permitidas))} en el plazo de {plazo:g} ms"]
    motivos = []
    demora = comandos[primera]["t_command_ms"] - t0
    if demora > plazo:
        motivos.append(
            f"{_orden(comandos, primera)}: sale a los {demora:g} ms; el plazo es {plazo:g}"
        )
    motivos += [
        f"{_orden(comandos, k)}: {comandos[k]['action']} no está permitida después de reaccionar"
        for k in indices
        if k > primera and comandos[k]["action"] not in permitidas | prohibidas
    ]
    return motivos


def _revisar_mantener(
    tramo: dict[str, Any], indices: list[int], frames: list[str], comandos: list[dict[str, Any]]
) -> list[str]:
    """Los primeros N cuadros dejan la misma acción que la última orden antes del tramo."""
    n = tramo.get("mantener_accion_cuadros", 0)
    if not n:
        return []
    if not indices or indices[0] == 0:
        return ["mantener_accion_cuadros: no hay una orden antes del tramo"]
    previa = comandos[indices[0] - 1]["action"]
    primeros = set(frames[:n])
    return [
        f"{_orden(comandos, k)}: cambia a {comandos[k]['action']}; los primeros {n} cuadros "
        f"mantienen {previa}"
        for k in indices
        if comandos[k]["frame_id"] in primeros and comandos[k]["action"] != previa
    ]


def _avanzar_con_velocidad(
    indices: list[int], _frames: list[str], reg: Registros, _config: ConfigPolitica
) -> list[str]:
    return [
        f"{_orden(reg.comandos, k)}: AVANZAR con speed {reg.comandos[k]['speed']}, no > 0"
        for k in indices
        if reg.comandos[k]["action"] == "AVANZAR" and not reg.comandos[k]["speed"] > 0
    ]


def _giro_hacia_zona_libre(
    indices: list[int], _frames: list[str], reg: Registros, config: ConfigPolitica
) -> list[str]:
    motivos = []
    for k in indices:
        lado = LADO_DEL_GIRO.get(reg.comandos[k]["action"])
        if lado is None:
            continue
        evento = reg.eventos.get(reg.comandos[k]["frame_id"])
        if evento is None or evento["status"] != "ok":
            motivos.append(f"{_orden(reg.comandos, k)}: gira sin un cuadro ok que lo explique")
        elif lado in zonas_ocupadas(evento, config):
            motivos.append(
                f"{_orden(reg.comandos, k)}: gira hacia la zona {lado}, que está ocupada"
            )
    return motivos


def _error_registrado(
    _indices: list[int], frames: list[str], reg: Registros, _config: ConfigPolitica
) -> list[str]:
    registrados = {(e["run_id"], e["frame_id"]) for e in reg.errores}
    return [
        f"el cuadro {f} no quedó en errores.jsonl"
        for f in frames
        if (reg.eventos[f]["run_id"], f) not in registrados
    ]


def _es_el_ultimo_comando(
    indices: list[int], _frames: list[str], reg: Registros, _config: ConfigPolitica
) -> list[str]:
    if indices and indices[-1] == len(reg.comandos) - 1:
        return []
    return [f"la orden del tramo no es la última del run (hay {len(reg.comandos)} órdenes)"]


CONDICIONES: dict[str, Callable[[list[int], list[str], Registros, ConfigPolitica], list[str]]] = {
    "avanzar_con_velocidad": _avanzar_con_velocidad,
    "giro_hacia_zona_libre": _giro_hacia_zona_libre,
    "error_registrado": _error_registrado,
    "es_el_ultimo_comando": _es_el_ultimo_comando,
}


def _ordenes_de_cuadros(reg: Registros, frames: list[str]) -> list[int]:
    """Líneas de comandos.jsonl con event=frame de esos cuadros."""
    ids = set(frames)
    return [k for k, c in enumerate(reg.comandos) if c["event"] == "frame" and c["frame_id"] in ids]


def _inicio_siguiente(
    resto: list[dict[str, Any]], de_cuadros: dict[str, list[int]], reg: Registros
) -> int:
    """Primera orden del siguiente tramo de cuadros que dejó órdenes; si no hay, el final."""
    for tramo in resto:
        if tramo["origen"] == "cuadros" and de_cuadros[tramo["nombre"]]:
            return de_cuadros[tramo["nombre"]][0]
    return len(reg.comandos)


def _instante_del_plazo(
    tramo: dict[str, Any], frames: list[str], inicio: int | None, fin: int | None, reg: Registros
) -> float | None:
    """El instante de `plazo_desde`; `None` si no hay plazo o no se encuentra."""
    desde = tramo["plazo_desde"]
    if desde in ("captura", "llegada"):
        campo = "t_capture_ms" if desde == "captura" else "t_emit_ms"
        return reg.eventos[frames[0]][campo]
    if desde == "ultimo_cuadro":
        previos = [c["frame_id"] for c in reg.comandos[:inicio] if c["event"] == "frame"]
        evento = reg.eventos.get(previos[-1]) if previos else None
        return evento["t_emit_ms"] if evento else None
    if desde == "evento":
        accion = ACCION_DEL_ORIGEN[tramo["origen"]]
        hechas = [
            a["t_ms"]
            for a in reg.acciones
            if a["accion"] == accion and a["comando"] is not None and inicio <= a["comando"] < fin
        ]
        return hechas[0] if hechas else None
    return None


def _orden(comandos: list[dict[str, Any]], k: int) -> str:
    c = comandos[k]
    return f"orden {k + 1} ({c['action']}, event={c['event']}, frame_id={c['frame_id']})"


# --- un caso de punta a punta ---------------------------------------------------------


def evaluar(
    carpeta: Path,
    esquema: dict[str, Any],
    config: Path,
    config_politica: ConfigPolitica,
    salida: Path,
) -> dict[str, Any]:
    """Lee, corre y juzga un caso. Deja veredicto.json en `salida` y lo devuelve."""
    veredicto: dict[str, Any] = {"caso": carpeta.name, "entrada": None, "tramos": []}
    salida.mkdir(parents=True, exist_ok=True)  # NOSONAR (S8707)
    try:
        caso = cargar_caso(carpeta, esquema)
    except (CasoMalArmado, OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
        # Sin correr: que no queden registros de una corrida anterior junto a este veredicto.
        for nombre in REGISTROS:
            (salida / nombre).unlink(missing_ok=True)  # NOSONAR (S8707)
        motivos = [str(exc)]
    else:
        veredicto["entrada"] = caso.entrada
        motivos = _correr_y_juzgar(caso, config, config_politica, salida, veredicto)

    veredicto["pasa"] = not motivos
    veredicto["motivos"] = motivos
    texto = json.dumps(veredicto, ensure_ascii=False, indent=2) + "\n"
    (salida / NOMBRE_VEREDICTO).write_text(texto, encoding="utf-8")  # NOSONAR (S8707)
    return veredicto


def _correr_y_juzgar(
    caso: Caso,
    config: Path,
    config_politica: ConfigPolitica,
    salida: Path,
    veredicto: dict[str, Any],
) -> list[str]:
    motivos = []
    if caso.nombre in CON_SECUENCIA_REAL and caso.entrada != "real":
        motivos.append(
            f"{caso.nombre} pide una secuencia real de A (datos/MAPA_CASOS.md) y la entrada "
            f"es {caso.entrada}"
        )
    codigo, impreso = correr_caso(caso, config, salida)
    if codigo != 0:
        motivos.append(f"python -m control salió con {codigo}: {impreso}")
    if codigo == 2:
        # No escribió nada que juzgar.
        return motivos

    reg = leer_registros(salida)
    tramos = juzgar(caso.expectativa, caso.cuadros, reg, config_politica)
    veredicto["tramos"] = tramos
    motivos += [f"{t['tramo']}: {m}" for t in tramos for m in t["motivos"]]
    return motivos + revisar_stop_con_evento(caso.expectativa, reg)


# --- tabla y línea de comandos --------------------------------------------------------


def tabla(veredictos: list[dict[str, Any]]) -> str:
    """La tabla PASA/FALLA y, debajo, cada motivo de los casos que fallan."""
    lineas = [f"{'Caso':<5} {'Entrada':<8} {'Tramos':<7} Resultado"]
    for v in veredictos:
        cumplen = sum(not t["motivos"] for t in v["tramos"])
        tramos = f"{cumplen}/{len(v['tramos'])}" if v["tramos"] else "-"
        resultado = "PASA" if v["pasa"] else "FALLA"
        lineas.append(f"{v['caso']:<5} {v['entrada'] or '-':<8} {tramos:<7} {resultado}")

    fallan = [v for v in veredictos if not v["pasa"]]
    lineas += ["", f"{len(veredictos) - len(fallan)} de {len(veredictos)} casos pasan."]
    if fallan:
        lineas += ["", "Por qué fallan (detalle en resultados/casos/Cn/veredicto.json):"]
        for v in fallan:
            lineas.append(f"  {v['caso']}")
            lineas += [f"    - {motivo}" for motivo in v["motivos"]]
    return "\n".join(lineas) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python casos/runner.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("casos", nargs="*", metavar="Cn", help="casos a correr (todos si no hay)")
    parser.add_argument("--casos", dest="carpeta", type=Path, default=CASOS, help="carpeta casos/")
    parser.add_argument("--config", type=Path, default=CONFIG, help="carpeta config/control/")
    parser.add_argument("--salida", type=Path, default=SALIDA, help="carpeta de resultados")
    args = parser.parse_args(argv)
    desconocidos = sorted(set(args.casos) - set(NOMBRES))
    if desconocidos:
        parser.error(f"casos desconocidos: {desconocidos}; son {NOMBRES[0]} a {NOMBRES[-1]}")
    nombres = [n for n in NOMBRES if n in args.casos] or list(NOMBRES)

    try:
        config_politica = cargar_config_politica(args.config / "politica.yaml")
        esquema = json.loads(
            (args.carpeta / NOMBRE_ESQUEMA).read_text(encoding="utf-8")
        )  # NOSONAR (S8707)
    except (ErrorConfigPolitica, OSError, json.JSONDecodeError) as exc:
        print(f"no se pudo leer la configuración o el esquema: {exc}", file=sys.stderr)
        return 2

    veredictos = [
        evaluar(args.carpeta / n, esquema, args.config, config_politica, args.salida / n)
        for n in nombres
    ]
    texto = tabla(veredictos)
    (args.salida / NOMBRE_RESUMEN).write_text(texto, encoding="utf-8")  # NOSONAR (S8707)
    print(texto, end="")
    return 0 if all(v["pasa"] for v in veredictos) else 1


if __name__ == "__main__":
    raise SystemExit(main())
