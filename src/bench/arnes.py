"""Arnés de benchmark (P5-15): 10 calentamientos + 100 ejecuciones válidas, por etapa.

Cada ejecución toma una entrada ya leída (decodificar la imagen no se cronometra, igual que en P4)
y mide por separado con `time.perf_counter_ns`:

- `preprocesamiento_ms`, `inferencia_ms` y `posprocesamiento_ms` del detector;
- `politica_ms`: el Supervisor de B con la política real y el AdaptadorVirtual (incluye validar el
  evento y escribir el comando), si se mide con política;
- `total_ms`: la suma de las etapas, es decir, el cómputo local de un cuadro.

No hay pausas de reproducción: el siguiente cuadro sale en cuanto termina el anterior, y su
`t_capture_ms` es solo la etiqueta que espera el supervisor (un cuadro cada `PERIODO_MS`).

Una ejecución que falla en cualquier etapa, o cuya salida no cumple el contrato, queda en la lista
de fallos con su etapa y su error, y **no** cuenta ni entra en p50/p95: el arnés sigue hasta juntar
las válidas. Si los fallos pasan de `max_fallos`, se detiene y el benchmark queda incompleto.
"""

from __future__ import annotations

import ctypes
import hashlib
import math
import os
import platform
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from contrato import validar_evento
from control import AdaptadorVirtual, Supervisor
from control.__main__ import CARPETA_CONFIG, NOMBRE_PLAZOS, NOMBRE_POLITICA, cargar_plazos
from control.config import cargar_config_politica
from control.politica import decidir

from .detector import Detector

CALENTAMIENTOS = 10
MINIMO_MEDICIONES = 100
MAX_FALLOS = 10
# Ritmo de entrada declarado por B (≈ 5 fps, plazos.yaml): solo etiqueta los t_capture_ms.
PERIODO_MS = 200
ETAPAS = ("preprocesamiento_ms", "inferencia_ms", "posprocesamiento_ms", "politica_ms", "total_ms")
VARIABLES_DE_HILOS = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")
RUN_ID = "bench"


class ErrorBench(ValueError):
    """No se puede medir así: configuración distinta, entradas o protocolo inválidos."""


class FalloEjecucion(Exception):
    """Una ejecución falló; `etapa` dice dónde."""

    def __init__(self, etapa: str, mensaje: str, tipo: str) -> None:
        super().__init__(mensaje)
        self.etapa = etapa
        self.tipo = tipo


@dataclass(frozen=True)
class Entrada:
    entrada_id: str
    ruta: Path
    sha256: str
    imagen: Any


def sha256_archivo(ruta: Path) -> str:
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()  # NOSONAR (S8707)


def cargar_entradas(detector: Detector, rutas: Sequence[Path]) -> list[Entrada]:
    """Lee las imágenes con el detector antes de cronometrar. Los `entrada_id` son los nombres."""
    if not rutas:
        raise ErrorBench("no hay entradas: se necesita al menos una imagen")
    nombres = [Path(r).stem for r in rutas]
    if len(set(nombres)) != len(nombres):
        raise ErrorBench("dos entradas tienen el mismo nombre de archivo")
    entradas = []
    for ruta in rutas:
        try:
            imagen = detector.leer(Path(ruta))
        except Exception as exc:
            raise ErrorBench(f"no se pudo leer la entrada {ruta}: {exc}") from exc
        entradas.append(Entrada(Path(ruta).stem, Path(ruta), sha256_archivo(ruta), imagen))
    return entradas


def verificar_procedencia(
    detector: Detector, model_sha256: str | None, config_sha256: str | None
) -> tuple[dict[str, Any], list[str]]:
    """Compara los hashes del detector (y de sus pesos) con los congelados.

    Uno distinto lanza `ErrorBench`: no se mide otra configuración. Uno sin indicar es advertencia.
    """
    pesos = None
    if detector.ruta_pesos is not None:
        ruta = Path(detector.ruta_pesos)
        pesos = {
            "ruta": ruta.as_posix(),
            "bytes": ruta.stat().st_size,
            "sha256": sha256_archivo(ruta),
        }
        if pesos["sha256"] != detector.model_sha256:
            raise ErrorBench(
                f"los pesos {ruta} tienen SHA-256 {pesos['sha256']}, "
                f"pero el detector dice {detector.model_sha256}"
            )
    advertencias = []
    for campo, esperado in (("model_sha256", model_sha256), ("config_sha256", config_sha256)):
        real = getattr(detector, campo)
        if esperado is None:
            advertencias.append(f"procedencia no comprobada: no se indicó el {campo} congelado")
        elif real != esperado:
            raise ErrorBench(f"{campo} del detector {real} no coincide con el congelado {esperado}")
    procedencia = {
        "model_sha256": detector.model_sha256,
        "config_sha256": detector.config_sha256,
        "model_sha256_esperado": model_sha256,
        "config_sha256_esperado": config_sha256,
        "comprobada": not advertencias,
        "pesos": pesos,
    }
    return procedencia, advertencias


class EtapaPolitica:
    """Supervisor + política real + AdaptadorVirtual de B, con su configuración del repo."""

    def __init__(self, carpeta_salida: Path, carpeta_config: Path = CARPETA_CONFIG) -> None:
        plazos = cargar_plazos(carpeta_config / NOMBRE_PLAZOS)
        config = cargar_config_politica(carpeta_config / NOMBRE_POLITICA)
        adaptador = AdaptadorVirtual(carpeta_salida, plazos["validez_orden_ms"])
        self.supervisor = Supervisor(decidir, adaptador, plazos, config)

    def __call__(self, evento: dict[str, Any], ahora_ms: float) -> dict[str, Any]:
        return self.supervisor.procesar_evento(evento, ahora_ms)


def _cronometrar(etapa: str, funcion: Callable[..., Any], *args: Any) -> tuple[Any, float]:
    inicio = time.perf_counter_ns()
    try:
        resultado = funcion(*args)
    except Exception as exc:
        raise FalloEjecucion(etapa, str(exc), type(exc).__name__) from exc
    return resultado, (time.perf_counter_ns() - inicio) / 1_000_000


def _evento(detector: Detector, entrada: Entrada, detecciones: Any, intento: int) -> dict[str, Any]:
    ancho, alto = detector.dimensiones(entrada.imagen)
    t_ms = intento * PERIODO_MS
    return {
        "schema_version": "1",
        "run_id": RUN_ID,
        "sequence_id": RUN_ID,
        "frame_id": f"{RUN_ID}_{intento:05d}",
        "t_capture_ms": t_ms,
        "t_emit_ms": t_ms,
        "image_width": ancho,
        "image_height": alto,
        "model_sha256": detector.model_sha256,
        "config_sha256": detector.config_sha256,
        "status": "ok",
        "bbox_format": "xyxy",
        "bbox_unit": "px",
        "detections": detecciones,
    }


def ejecutar_una(
    detector: Detector,
    entrada: Entrada,
    intento: int,
    politica: Callable[[dict[str, Any], float], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Una ejecución. Lanza `FalloEjecucion` si una etapa falla o la salida no es válida."""
    tensor, pre_ms = _cronometrar("preprocesamiento", detector.preprocesar, entrada.imagen)
    salida, inf_ms = _cronometrar("inferencia", detector.inferir, tensor)
    detecciones, post_ms = _cronometrar(
        "posprocesamiento", detector.posprocesar, salida, entrada.imagen
    )
    # Fuera del cronómetro: la validación es del arnés, no del detector.
    evento = _evento(detector, entrada, detecciones, intento)
    errores = validar_evento(evento)
    if errores:
        raise FalloEjecucion("salida", "; ".join(errores), "salida_invalida")
    fila = {
        "preprocesamiento_ms": pre_ms,
        "inferencia_ms": inf_ms,
        "posprocesamiento_ms": post_ms,
        "politica_ms": None,
        "detecciones": len(detecciones),
        "accion": "",
    }
    if politica is not None:
        comando, fila["politica_ms"] = _cronometrar(
            "politica", politica, evento, evento["t_emit_ms"]
        )
        fila["accion"] = comando["action"]
    fila["total_ms"] = pre_ms + inf_ms + post_ms + (fila["politica_ms"] or 0.0)
    return fila


@dataclass
class Medicion:
    ejecuciones: list[dict[str, Any]]
    fallos: list[dict[str, Any]]
    completa: bool


def medir(
    detector: Detector,
    entradas: Sequence[Entrada],
    politica: Callable[[dict[str, Any], float], dict[str, Any]] | None = None,
    calentamientos: int = CALENTAMIENTOS,
    mediciones: int = MINIMO_MEDICIONES,
    max_fallos: int = MAX_FALLOS,
) -> Medicion:
    """Corre hasta juntar `calentamientos` + `mediciones` ejecuciones válidas.

    Las entradas se recorren en orden y en ciclo, una por intento (también los fallidos).
    """
    if not entradas:
        raise ErrorBench("no hay entradas")
    ejecuciones: list[dict[str, Any]] = []
    fallos: list[dict[str, Any]] = []
    intento = 0
    while len(ejecuciones) < calentamientos + mediciones:
        intento += 1
        entrada = entradas[(intento - 1) % len(entradas)]
        fase = "calentamiento" if len(ejecuciones) < calentamientos else "medicion"
        base = {"intento": intento, "fase": fase, "entrada_id": entrada.entrada_id}
        try:
            fila = ejecutar_una(detector, entrada, intento, politica)
        except FalloEjecucion as fallo:
            fallos.append(
                {**base, "etapa": fallo.etapa, "error": fallo.tipo, "mensaje": str(fallo)}
            )
            if len(fallos) > max_fallos:
                return Medicion(ejecuciones, fallos, completa=False)
            continue
        ejecuciones.append({**base, **fila})
    return Medicion(ejecuciones, fallos, completa=True)


def percentil(valores: Sequence[float], q: float) -> float:
    """Percentil lineal: posición (n - 1) * q, interpolando entre vecinos (como en P4)."""
    if not valores or not 0 <= q <= 1:
        raise ValueError("percentil sin datos")
    ordenados = sorted(valores)
    posicion = (len(ordenados) - 1) * q
    abajo, arriba = math.floor(posicion), math.ceil(posicion)
    return ordenados[abajo] + (ordenados[arriba] - ordenados[abajo]) * (posicion - abajo)


def resumir_etapas(ejecuciones: Sequence[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """p50, p95, máximo, mínimo y media por etapa, solo con las mediciones (sin calentamientos)."""
    medidas = [e for e in ejecuciones if e["fase"] == "medicion"]
    resumen = {}
    for etapa in ETAPAS:
        valores = [e[etapa] for e in medidas if e[etapa] is not None]
        if not valores:
            continue
        resumen[etapa] = {
            "n": len(valores),
            "p50": percentil(valores, 0.50),
            "p95": percentil(valores, 0.95),
            "maximo": max(valores),
            "minimo": min(valores),
            "media": sum(valores) / len(valores),
        }
    return resumen


# --- Hardware y condiciones -------------------------------------------------------------------


def _nombre_cpu() -> str | None:
    sistema = platform.system()
    try:
        if sistema == "Windows":
            import winreg

            clave = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, clave) as abierta:
                return str(winreg.QueryValueEx(abierta, "ProcessorNameString")[0]).strip()
        if sistema == "Linux":
            for linea in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
                if linea.startswith("model name"):
                    return linea.split(":", 1)[1].strip()
        if sistema == "Darwin":
            comando = ["sysctl", "-n", "machdep.cpu.brand_string"]
            return subprocess.run(
                comando, capture_output=True, text=True, check=True
            ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return platform.processor() or None


def _ram_bytes() -> int | None:
    try:
        if platform.system() == "Windows":

            class _Memoria(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            memoria = _Memoria()
            memoria.dwLength = ctypes.sizeof(_Memoria)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memoria))
            return int(memoria.ullTotalPhys)
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, OSError, ValueError):
        return None


def energia() -> str:
    """`corriente`, `bateria` o `desconocida`. Solo se detecta en Windows y Linux."""
    try:
        if platform.system() == "Windows":

            class _Energia(ctypes.Structure):
                _fields_ = [
                    ("ACLineStatus", ctypes.c_ubyte),
                    ("BatteryFlag", ctypes.c_ubyte),
                    ("BatteryLifePercent", ctypes.c_ubyte),
                    ("SystemStatusFlag", ctypes.c_ubyte),
                    ("BatteryLifeTime", ctypes.c_ulong),
                    ("BatteryFullLifeTime", ctypes.c_ulong),
                ]

            estado = _Energia()
            if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(estado)):
                return {1: "corriente", 0: "bateria"}.get(estado.ACLineStatus, "desconocida")
        elif platform.system() == "Linux":
            for fuente in Path("/sys/class/power_supply").glob("*/online"):
                if (fuente.parent / "type").read_text(encoding="utf-8").strip() == "Mains":
                    return (
                        "corriente"
                        if fuente.read_text(encoding="utf-8").strip() == "1"
                        else "bateria"
                    )
    except (AttributeError, OSError):
        pass
    return "desconocida"


def hardware() -> dict[str, Any]:
    return {
        "so": platform.platform(),
        "arquitectura": platform.machine(),
        "cpu": _nombre_cpu(),
        "nucleos_logicos": os.cpu_count(),
        "ram_bytes": _ram_bytes(),
    }


def runtime(detector: Detector) -> dict[str, Any]:
    return {
        "python": sys.version.split()[0],
        "implementacion": platform.python_implementation(),
        "detector": detector.descripcion(),
        "variables_de_hilos": {v: os.environ.get(v) for v in VARIABLES_DE_HILOS},
    }
