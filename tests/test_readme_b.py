"""T18 · La sección "Grupo B · Control y verificación" del README dice la verdad.

Cada ejemplo del README se corre aquí y su salida se compara con la que muestra el README. Si cambia
un comando, una ruta o un resultado, esta prueba avisa que hay que actualizar el README.
"""

import importlib.util
import re
import shutil
import sys
from pathlib import Path

import pytest

from contrato.__main__ import main as validar
from control.__main__ import main as correr_control

RAIZ = Path(__file__).resolve().parents[1]
README = (RAIZ / "README.md").read_text(encoding="utf-8")
SECCION = README.split("## Grupo B · Control y verificación", 1)[1].split("\n## ", 1)[0]
FLUJO = "config/contrato/ejemplos/flujo.jsonl"
CORRER_CASOS = "3. Correr los casos C1\u2013C10"  # el título del README lleva guion largo

# casos/ no es un paquete: se carga el archivo.
_spec = importlib.util.spec_from_file_location("runner_del_readme", RAIZ / "casos" / "runner.py")
runner = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = runner
_spec.loader.exec_module(runner)


def bloque(titulo: str) -> str:
    """El texto de una subsección `### titulo` de la sección B."""
    return SECCION.split(f"### {titulo}", 1)[1].split("\n### ", 1)[0]


def comentado(texto: str, inicio: str) -> str:
    """La salida esperada que el README escribe como comentario `# ...` debajo de un comando."""
    for linea in texto.splitlines():
        resto = linea.strip().removeprefix("#").strip()
        if linea.strip().startswith("#") and resto.startswith(inicio):
            return resto
    raise AssertionError(f"el README no muestra una salida que empiece con {inicio!r}")


def sin_barras_de_windows(texto: str) -> str:
    return texto.replace("\\", "/")


def test_la_seccion_tiene_lo_que_pide_t18():
    for titulo in (
        "Integrantes",
        "Instalación",
        "1. Validar eventos contra el contrato",
        "2. Correr una secuencia",
        CORRER_CASOS,
        "4. Comprobar que una expectativa alterada se detecta",
        "Dónde quedan los resultados",
    ):
        assert f"### {titulo}" in SECCION, titulo
    for nombre in ("Alejandra Viera", "Hannah Chenoa", "Stephy Borrego", "Luis Santana"):
        assert nombre in bloque("Integrantes"), nombre


def test_las_rutas_del_repo_que_menciona_existen():
    enlaces = re.findall(r"\]\(([^)#\s]+)\)", SECCION)
    citadas = re.findall(r"`((?:config|casos|docs|src|tests)/[^`\s<*]*)`", SECCION)
    rutas = {r for r in enlaces + citadas if "://" not in r and "Cn" not in r}
    assert rutas
    faltan = sorted(r for r in rutas if not (RAIZ / r).exists())
    assert faltan == []


def test_la_lista_de_pruebas_de_b_existe_y_cubre_todas_las_de_b():
    listadas = re.findall(r"tests/(test_\w+\.py)", bloque("Pruebas del grupo B"))
    assert all((RAIZ / "tests" / nombre).is_file() for nombre in listadas)
    assert "test_readme_b.py" in listadas


def test_validar_el_contrato_da_lo_que_dice_el_readme(capsys, monkeypatch):
    monkeypatch.chdir(RAIZ)
    assert validar([FLUJO]) == 0
    esperado = comentado(bloque("1. Validar eventos contra el contrato"), FLUJO)
    assert sin_barras_de_windows(capsys.readouterr().out.strip()) == esperado


def test_correr_una_secuencia_da_lo_que_dice_el_readme(tmp_path, capsys):
    texto = bloque("2. Correr una secuencia")
    salida = tmp_path / "ejemplo-01"
    argv = ["--entrada", str(RAIZ / FLUJO), "--config", str(RAIZ / "config" / "control")]
    assert correr_control([*argv, "--salida", str(salida)]) == 0

    esperado = comentado(texto, "resultados/ejemplo-01:").split(":", 1)[1]
    assert capsys.readouterr().out.strip().endswith(esperado)
    archivos = re.findall(r"^\| `(\w+\.jsonl?)` \|", texto, flags=re.MULTILINE)
    assert sorted(archivos) == sorted(p.name for p in salida.iterdir())


def test_hoy_pasan_los_casos_que_dice_el_readme(tmp_path, capsys):
    runner.main(["--salida", str(tmp_path)])
    pasan = re.search(r"Hoy pasan \*\*(\d+) de 10\*\*", bloque(CORRER_CASOS))
    assert pasan, "el README debe decir cuántos casos pasan hoy"
    assert f"{pasan.group(1)} de 10 casos pasan." in capsys.readouterr().out


@pytest.fixture
def copia_alterada(tmp_path) -> Path:
    """La copia de casos/ con el cambio que pide el README en el tramo `hueco` de C8."""
    copia = tmp_path / "casos-copia"
    shutil.copytree(RAIZ / "casos", copia, ignore=shutil.ignore_patterns("__pycache__"))
    ruta = copia / "C8" / "expectativa.yaml"
    texto = ruta.read_text(encoding="utf-8")
    viejo, nuevo = "acciones_permitidas: [STOP]", "acciones_permitidas: [AVANZAR]"
    inicio = texto.index(viejo, texto.index("- nombre: hueco"))
    ruta.write_text(texto[:inicio] + nuevo + texto[inicio + len(viejo) :], encoding="utf-8")
    return copia


def test_una_expectativa_alterada_falla_como_dice_el_readme(copia_alterada, tmp_path, capsys):
    texto = bloque("4. Comprobar que una expectativa alterada se detecta")
    assert 'tramo "hueco": acciones_permitidas: [AVANZAR]' in texto

    salida = tmp_path / "casos-salida"
    assert runner.main(["C8", "--casos", str(copia_alterada), "--salida", str(salida)]) == 1
    impreso = capsys.readouterr().out
    assert comentado(texto, "C8 ") in impreso
    assert comentado(texto, "- hueco:") in impreso
