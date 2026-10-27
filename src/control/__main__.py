"""Corre una secuencia completa (T14).

    PYTHONPATH=src python -m control --entrada eventos.jsonl --config config/control/ \\
        --salida resultados/<run>/

Lee los eventos de percepción (`.json` o `.jsonl`), los pasa uno por uno al Supervisor con la
política (`politica.decidir`) y el AdaptadorVirtual, y deja en la carpeta de salida:

- `detecciones.jsonl`: cada evento tal como llegó del detector.
- `decisiones.jsonl`: qué se decidió en cada cuadro o tic de reloj, quién lo decidió (la política o
  el supervisor), qué había propuesto la política y el estado completo después.
- `comandos.jsonl`: lo que registró el adaptador (lo escribe el AdaptadorVirtual).
- `errores.jsonl`: cada STOP por falla (lo escribe el Supervisor) y cada comando que no cumpla el
  contrato de comando (`comando_fuera_de_contrato`).
- `run.json`: SHA-256 de la entrada y de la configuración, hashes del detector, versiones y conteos.

Todo va enlazado por `run_id` y `frame_id`. El reloj es el `t_emit_ms` de cada evento (cuando B
recibe el cuadro), así funciona el rechazo por edad (`ahora_ms - t_capture_ms`, T05). Entre un
cuadro y el siguiente se llama a `tick(ahora_ms)` cada `paso_reloj_ms` (plazos.yaml), para que el
watchdog frene a tiempo aunque haya un hueco (C8); también justo antes de cada cuadro, y al final
`cerrar(ahora_ms)`. No se lee el reloj del sistema, así que la misma entrada deja siempre los
mismos archivos.

Las rutas de `--entrada`, `--config` y `--salida` las elige quien corre el comando y pueden estar
en cualquier carpeta (el evaluador usa las suyas). Por eso las lecturas y escrituras con esas rutas
llevan `NOSONAR (S8707)`: no hay una carpeta base contra la cual limitarlas.

Los archivos se escriben con `allow_nan=False`: NaN e infinito no son JSON. Una entrada que los
trae no se puede leer (salida 2). Si la política los propone, el supervisor manda STOP, y en
`decisiones.jsonl` lo que propuso queda como texto (`"nan"`, `"inf"`).

Salida: 0 si todos los comandos cumplen el contrato, 1 si alguno no, 2 si la entrada o la
configuración no se pueden leer (en ese caso no se escribe nada).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from contrato import leer_eventos, validar_comando

from .adaptador_virtual import NOMBRE_REGISTRO, AdaptadorVirtual
from .config import RAIZ, ErrorConfigPolitica, cargar_config_politica
from .politica import decidir
from .supervisor import NOMBRE_ERRORES, Estado, Politica, Supervisor

CARPETA_CONFIG = RAIZ / "config" / "control"
NOMBRE_PLAZOS = "plazos.yaml"
NOMBRE_POLITICA = "politica.yaml"
NOMBRE_DETECCIONES = "detecciones.jsonl"
NOMBRE_DECISIONES = "decisiones.jsonl"
NOMBRE_RUN = "run.json"
PLAZOS = (
    "max_frame_age_ms",
    "detector_timeout_ms",
    "watchdog_ms",
    "validez_orden_ms",
    "paso_reloj_ms",
)
CAMPOS_DE_LA_POLITICA = ("action", "speed", "steering", "reason")


class ErrorPlazos(ValueError):
    """plazos.yaml falta, no se puede leer o le falta un plazo."""


class ErrorEntrada(ValueError):
    """La entrada trae NaN o Infinity, que no son JSON."""


def cargar_plazos(ruta: Path) -> dict[str, Any]:
    """Lee plazos.yaml y revisa que cada plazo sea un número > 0."""
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))  # NOSONAR (S8707)
    if not isinstance(datos, dict):
        raise ErrorPlazos(f"{ruta}: debe ser un mapa clave: valor")
    malos = [
        p
        for p in PLAZOS
        if not isinstance(datos.get(p), (int, float)) or isinstance(datos[p], bool) or datos[p] <= 0
    ]
    if malos:
        raise ErrorPlazos(f"{ruta}: faltan o no son números > 0: {malos}")
    return datos


class PoliticaRegistrada:
    """Envuelve la política para saber qué propuso en el cuadro, aunque el supervisor la rechace."""

    def __init__(self, politica: Politica) -> None:
        self.politica = politica
        self.propuesta: dict[str, Any] | None = None

    def __call__(
        self, evento: dict[str, Any], estado: Estado, config: Any
    ) -> tuple[dict[str, Any], Estado]:
        comando, estado_nuevo = self.politica(evento, estado, config)
        if isinstance(comando, dict):
            self.propuesta = {campo: comando.get(campo) for campo in CAMPOS_DE_LA_POLITICA}
        return comando, estado_nuevo


class Corrida:
    """Una corrida: Supervisor + política + AdaptadorVirtual escribiendo en `salida`."""

    def __init__(
        self,
        salida: Path,
        plazos: dict[str, Any],
        config_politica: Any,
        politica: Politica = decidir,
    ) -> None:
        self.salida = Path(salida)
        self.paso_reloj_ms = plazos["paso_reloj_ms"]
        self.adaptador = AdaptadorVirtual(self.salida, plazos["validez_orden_ms"])
        self.politica = PoliticaRegistrada(politica)
        self.supervisor = Supervisor(self.politica, self.adaptador, plazos, config_politica)
        # Igual que comandos.jsonl y errores.jsonl: cada corrida empieza con los registros vacíos.
        self.ruta_detecciones = self.salida / NOMBRE_DETECCIONES
        self.ruta_decisiones = self.salida / NOMBRE_DECISIONES
        self.ruta_detecciones.write_text("", encoding="utf-8")  # NOSONAR (S8707)
        self.ruta_decisiones.write_text("", encoding="utf-8")  # NOSONAR (S8707)
        self.eventos = 0
        self.comandos = 0
        self.invalidos = 0
        self.ahora_ms = 0.0

    def cuadro(self, evento: Any) -> None:
        """Un evento del detector: tics de reloj hasta su llegada y luego el supervisor decide."""
        self.eventos += 1
        _anexar(self.ruta_detecciones, evento)
        llegada_ms = _reloj(evento, self.ahora_ms)
        if self.eventos > 1:
            self._tics_hasta(llegada_ms)
        self.ahora_ms = llegada_ms
        self._registrar(self.supervisor.tick(self.ahora_ms), None)
        self.politica.propuesta = None
        comando = self.supervisor.procesar_evento(evento, self.ahora_ms)
        self._registrar(comando, self.politica.propuesta)

    def cerrar(self) -> None:
        self._registrar(self.supervisor.cerrar(self.ahora_ms), None)

    def _tics_hasta(self, llegada_ms: float) -> None:
        """Un tic cada `paso_reloj_ms` desde el cuadro anterior, sin llegar al siguiente."""
        inicio_ms = self.ahora_ms
        # Se multiplica en vez de sumar para no acumular error de coma flotante.
        n = 1
        while inicio_ms + n * self.paso_reloj_ms < llegada_ms:
            self.ahora_ms = inicio_ms + n * self.paso_reloj_ms
            self._registrar(self.supervisor.tick(self.ahora_ms), None)
            n += 1

    def _registrar(self, comando: dict[str, Any] | None, propuesta: dict[str, Any] | None) -> None:
        """Valida el comando que quedó en el adaptador y escribe su decisión."""
        # tick() devuelve None cuando no hizo falta un STOP de reloj (T05).
        if comando is None:
            return
        self.comandos += 1
        run_id, frame_id = comando.get("run_id"), comando.get("frame_id")

        errores = validar_comando(comando)
        if errores:
            self.invalidos += 1
            _anexar(
                self.salida / NOMBRE_ERRORES,
                {
                    "run_id": run_id,
                    "frame_id": frame_id,
                    "t_ms": self.ahora_ms,
                    "motivo": "comando_fuera_de_contrato",
                    "errores": errores,
                },
            )

        de_la_politica = propuesta is not None and all(
            propuesta[c] == comando.get(c) for c in ("action", "reason")
        )
        _anexar(
            self.ruta_decisiones,
            {
                "run_id": run_id,
                "frame_id": frame_id,
                "event": comando.get("event"),
                "t_ms": self.ahora_ms,
                "state_before": comando.get("state_before"),
                "state_after": comando.get("state_after"),
                "action": comando.get("action"),
                "reason": comando.get("reason"),
                "decidio": "politica" if de_la_politica else "supervisor",
                "propuesta_politica": _texto_si_no_finito(propuesta),
                "estado": _texto_si_no_finito(self.supervisor.estado),
            },
        )

    def escribir_run(self, entrada: Path, carpeta_config: Path) -> dict[str, Any]:
        """run.json: con qué entrada y configuración se corrió y cuánto salió."""
        detecciones = _leer_jsonl(self.ruta_detecciones)
        eventos = [e for e in detecciones if isinstance(e, dict)]
        resumen = {
            "run_ids": _distintos(eventos, "run_id"),
            "entrada": {"ruta": entrada.as_posix(), "sha256": _sha256(entrada)},
            "config": {
                nombre: {
                    "ruta": (carpeta_config / nombre).as_posix(),
                    "sha256": _sha256(carpeta_config / nombre),
                }
                for nombre in (NOMBRE_PLAZOS, NOMBRE_POLITICA)
            },
            "detector": {
                "model_sha256": _distintos(eventos, "model_sha256"),
                "config_sha256": _distintos(eventos, "config_sha256"),
            },
            "contratos": {"percepcion": "1", "comando": "1"},
            "conteos": {
                "eventos": self.eventos,
                "comandos": self.comandos,
                "comandos_fuera_de_contrato": self.invalidos,
                "errores": len(_leer_jsonl(self.salida / NOMBRE_ERRORES)),
            },
            "archivos": [
                NOMBRE_DETECCIONES,
                NOMBRE_DECISIONES,
                NOMBRE_REGISTRO,
                NOMBRE_ERRORES,
            ],
        }
        texto = json.dumps(resumen, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        (self.salida / NOMBRE_RUN).write_text(texto, encoding="utf-8")
        return resumen


def _reloj(evento: Any, anterior_ms: float) -> float:
    """`t_emit_ms` del evento; si no trae uno válido, se queda el instante anterior."""
    t = evento.get("t_emit_ms") if isinstance(evento, dict) else None
    if isinstance(t, (int, float)) and not isinstance(t, bool) and t >= 0:
        return float(t)
    return anterior_ms


def _anexar(ruta: Path, linea: Any) -> None:
    with ruta.open("a", encoding="utf-8") as registro:
        registro.write(json.dumps(linea, ensure_ascii=False, allow_nan=False) + "\n")


def _texto_si_no_finito(valor: Any) -> Any:
    """Copia de `valor` con NaN e infinito como texto ("nan", "inf"), para poder escribirla."""
    if isinstance(valor, float) and not math.isfinite(valor):
        return repr(valor)
    if isinstance(valor, dict):
        return {clave: _texto_si_no_finito(hijo) for clave, hijo in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_texto_si_no_finito(hijo) for hijo in valor]
    return valor


def _revisar_entrada(eventos: list[Any]) -> None:
    try:
        json.dumps(eventos, allow_nan=False)
    except ValueError as exc:
        raise ErrorEntrada("la entrada trae NaN o Infinity, que no son JSON") from exc


def _leer_jsonl(ruta: Path) -> list[Any]:
    texto = ruta.read_text(encoding="utf-8")
    return [json.loads(linea) for linea in texto.splitlines() if linea.strip()]


def _sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()  # NOSONAR (S8707)


def _distintos(eventos: list[dict[str, Any]], campo: str) -> list[str]:
    return sorted({e[campo] for e in eventos if isinstance(e.get(campo), str)})


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m control",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--entrada", type=Path, required=True, help="eventos .json o .jsonl")
    parser.add_argument(
        "--config",
        type=Path,
        default=CARPETA_CONFIG,
        help="carpeta con plazos.yaml y politica.yaml",
    )
    parser.add_argument("--salida", type=Path, required=True, help="carpeta de resultados del run")
    args = parser.parse_args(argv)

    entrada, carpeta_config, salida = args.entrada, args.config, args.salida
    # Entrada y configuración se leen antes de crear la salida: si algo falla, no queda una
    # corrida a medias.
    try:
        plazos = cargar_plazos(carpeta_config / NOMBRE_PLAZOS)
        config_politica = cargar_config_politica(carpeta_config / NOMBRE_POLITICA)
        eventos = leer_eventos(entrada)
        _revisar_entrada(eventos)
    except (
        OSError,
        json.JSONDecodeError,
        yaml.YAMLError,
        ErrorPlazos,
        ErrorConfigPolitica,
        ErrorEntrada,
    ) as exc:
        print(f"no se pudo leer la entrada o la configuración: {exc}", file=sys.stderr)
        return 2

    corrida = Corrida(salida, plazos, config_politica)
    for evento in eventos:
        corrida.cuadro(evento)
    corrida.cerrar()
    conteos = corrida.escribir_run(entrada, carpeta_config)["conteos"]

    print(
        f"{salida}: {conteos['eventos']} eventos, {conteos['comandos']} comandos, "
        f"{conteos['errores']} errores"
    )
    if corrida.invalidos:
        print(
            f"{corrida.invalidos} comandos no cumplen el contrato; ver {NOMBRE_ERRORES}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
