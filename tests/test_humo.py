"""Pruebas de humo del repo (P5-01): entorno, modo por defecto y convención de nombres."""

import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[1]

# Paquetes que delatan un runtime de GPU en el lockfile.
PAQUETES_GPU = re.compile(
    r'^name = "(nvidia-[^"]+|onnxruntime-gpu|tensorflow-gpu|cupy[^"]*)"', re.MULTILINE
)


def test_version_de_python_declarada():
    declarada = (RAIZ / ".python-version").read_text(encoding="utf-8").strip()
    assert f"{sys.version_info.major}.{sys.version_info.minor}" == declarada
    pyproject = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["requires-python"] == f"=={declarada}.*"


def test_paquete_instalado_desde_src():
    import contrato

    assert Path(contrato.__file__).resolve().is_relative_to(RAIZ / "src")
    assert contrato.RUTA_ESQUEMA.is_file()


def test_modo_por_defecto_cpu_y_sin_motores():
    config = yaml.safe_load((RAIZ / "config" / "ejecucion.yaml").read_text(encoding="utf-8"))
    assert config == {
        "dispositivo": "cpu",
        "adaptador": "virtual",
        "motores_conectados": False,
        "red_permitida": False,
    }


def test_lockfile_sin_paquetes_de_gpu():
    lock = (RAIZ / "uv.lock").read_text(encoding="utf-8")
    assert PAQUETES_GPU.findall(lock) == []


def test_carpetas_de_la_entrega():
    for carpeta in ("modelo", "config", "datos", "src", "casos", "resultados", "mediciones"):
        assert (RAIZ / carpeta).is_dir(), carpeta
    assert (RAIZ / "README.md").is_file()


def _buscar_bash() -> str | None:
    if sys.platform != "win32":
        return shutil.which("bash")
    # En Windows, `bash` del PATH suele ser el de WSL (System32), que no entiende rutas
    # de Windows. Se usa el de Git for Windows: <Git>/cmd/git.exe → <Git>/bin/bash.exe.
    git = shutil.which("git")
    if git is None:
        return None
    bash = Path(git).resolve().parents[1] / "bin" / "bash.exe"
    return str(bash) if bash.is_file() else None


BASH = _buscar_bash()
CHECK_NAMING = RAIZ / ".github" / "scripts" / "check-naming.sh"


def _check_naming(rama: str, titulo: str) -> int:
    resultado = subprocess.run(
        [BASH, str(CHECK_NAMING), rama, titulo], capture_output=True, text=True, check=False
    )
    return resultado.returncode


@pytest.mark.skipif(BASH is None, reason="hace falta bash (en Windows, Git Bash)")
@pytest.mark.parametrize(
    ("rama", "titulo"),
    [
        ("p5-01-repo-base", "P5-01: repo base"),
        ("p5-13-15-metricas-bench", "P5-13 P5-15: métricas y benchmark"),
        ("p5-13-15-metricas-bench", "P5-13/15: métricas y benchmark"),
        ("p5-t01-plazos", "T01: Declarar los plazos del sistema"),
        ("p5-t04-t05-fallas", "T04 T05: fallas y watchdog"),
        ("fix/contrato-typo", "fix: typo en el contrato"),
        ("docs/readme", "docs(readme): comandos"),
    ],
)
def test_nombres_validos(rama, titulo):
    assert _check_naming(rama, titulo) == 0


@pytest.mark.skipif(BASH is None, reason="hace falta bash (en Windows, Git Bash)")
@pytest.mark.parametrize(
    ("rama", "titulo"),
    [
        ("p6-01-x", "P5-01: repo base"),
        ("p4-01-x", "P5-01: repo base"),
        ("P5-01-repo-base", "P5-01: repo base"),
        ("T13-formato-del-comando", "T13: formato"),
        ("p5-01", "P5-01: repo base"),
        ("p5-01-repo-base", "P6-01: repo base"),
        ("p5-01-repo-base", "P5-01 repo base"),
        ("p5-t13-contrato-comando", "T13 · Formato del comando"),
    ],
)
def test_nombres_invalidos(rama, titulo):
    assert _check_naming(rama, titulo) == 1
