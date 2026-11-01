"""La evidencia de latencia no debe sobrescribir salidas existentes."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def guardar_resultado():
    ruta = Path(__file__).resolve().parents[1] / "resultados" / "p5-05-benchmark.py"
    return runpy.run_path(str(ruta))["_guardar_resultado"]


def _enlace_o_skip(enlace: Path, destino: Path) -> None:
    try:
        enlace.symlink_to(destino)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"el entorno no permite crear enlaces simbólicos: {exc}")


def test_benchmark_crea_json_nuevo_con_formato_actual(tmp_path, guardar_resultado):
    ruta = tmp_path / "latencia.json"
    datos = {"muestras": [1.0, 2.0], "equipo": "Mac de prueba"}
    guardar_resultado(ruta, datos)
    assert ruta.read_text(encoding="utf-8") == (
        json.dumps(datos, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )


def test_benchmark_rechaza_archivo_existente_sin_alterarlo(tmp_path, guardar_resultado):
    ruta = tmp_path / "latencia.json"
    previo = b"evidencia anterior\n"
    ruta.write_bytes(previo)
    with pytest.raises(SystemExit, match="la salida ya existe"):
        guardar_resultado(ruta, {"nuevo": True})
    assert ruta.read_bytes() == previo


@pytest.mark.parametrize("enlace_roto", [False, True])
def test_benchmark_rechaza_enlace_final_sin_tocar_destino(tmp_path, guardar_resultado, enlace_roto):
    destino = tmp_path / "destino.json"
    if not enlace_roto:
        destino.write_bytes(b"contenido intacto")
    enlace = tmp_path / "latencia.json"
    _enlace_o_skip(enlace, destino)
    with pytest.raises(SystemExit, match="la salida ya existe"):
        guardar_resultado(enlace, {"nuevo": True})
    assert enlace.is_symlink()
    if enlace_roto:
        assert not destino.exists()
    else:
        assert destino.read_bytes() == b"contenido intacto"


def test_benchmark_error_controlado_si_no_puede_crear_salida(tmp_path, guardar_resultado):
    ruta = tmp_path / "latencia.json"
    with pytest.MonkeyPatch.context() as cambios:
        original = Path.open

        def sin_permiso(self, *args, **kwargs):
            if self == ruta:
                raise PermissionError("acceso denegado")
            return original(self, *args, **kwargs)

        cambios.setattr(Path, "open", sin_permiso)
        with pytest.raises(SystemExit, match=r"no se pudo crear.*acceso denegado"):
            guardar_resultado(ruta, {"nuevo": True})
    assert not ruta.exists()
