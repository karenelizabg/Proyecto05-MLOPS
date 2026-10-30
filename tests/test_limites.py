import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from bench.__main__ import main as bench
from bench.arnes import sha256_archivo
from bench.detector import DetectorFalso
from bench.limites import (
    CUMPLE,
    CUMPLE_EN_P95,
    NO_CUMPLE,
    ErrorLimites,
    cargar_resumen,
    contrastar,
    main,
    veredicto,
)

RAIZ = Path(__file__).resolve().parents[1]
PLAZOS = RAIZ / "config" / "control" / "plazos.yaml"
VALORES = {
    "max_frame_age_ms": 500,
    "detector_timeout_ms": 500,
    "watchdog_ms": 600,
    "validez_orden_ms": 400,
    "paso_reloj_ms": 100,
}


def etapa(p50, p95, maximo):
    return {"n": 100, "p50": p50, "p95": p95, "maximo": maximo, "minimo": p50, "media": p50}


def resumen_de(inferencia, total, advertencias=(), sha_plazos=None):
    return {
        "estado": "completo",
        "equipo": "pruebas",
        "energia": "corriente",
        "conteos": {"calentamientos": 10, "mediciones": 100, "fallos": 0},
        "procedencia": {
            "detector": {"comprobada": True},
            "config_b": {"plazos.yaml": sha_plazos or sha256_archivo(PLAZOS)},
        },
        "etapas": {"inferencia_ms": etapa(*inferencia), "total_ms": etapa(*total)},
        "advertencias": list(advertencias),
    }


@pytest.fixture
def corrida(tmp_path):
    def escribir(resumen):
        (tmp_path / "resumen.json").write_text(json.dumps(resumen), encoding="utf-8")
        return tmp_path

    return escribir


def leer(carpeta):
    return json.loads((carpeta / "contraste.json").read_text(encoding="utf-8"))


def test_veredictos():
    assert veredicto(p95=100, maximo=200, plazo=200) == CUMPLE
    assert veredicto(p95=150, maximo=250, plazo=200) == CUMPLE_EN_P95
    assert veredicto(p95=201, maximo=250, plazo=200) == NO_CUMPLE


def test_con_margen_todo_cumple_y_sale_con_cero(corrida):
    carpeta = corrida(resumen_de(inferencia=(80, 100, 155), total=(87, 113, 162)))
    assert main([str(carpeta)]) == 0
    contraste = leer(carpeta)
    assert {f["veredicto"] for f in contraste["contraste"]} == {CUMPLE}
    assert contraste["advertencias"] == []
    assert (carpeta / "contraste.md").read_text(encoding="utf-8").count("**cumple**") == 5


def test_el_intervalo_es_el_periodo_mientras_el_proceso_lo_alcance():
    filas = {
        f["id"]: f for f in contrastar(resumen_de((80, 100, 155), (87, 113, 162)), VALORES, 200)
    }
    assert filas["intervalo_vs_validez"]["p95"] == 200
    lento = {
        f["id"]: f for f in contrastar(resumen_de((80, 100, 155), (300, 450, 700)), VALORES, 200)
    }
    assert lento["intervalo_vs_validez"]["p95"] == 450
    assert lento["intervalo_vs_validez"]["veredicto"] == NO_CUMPLE
    assert lento["intervalo_vs_watchdog"]["veredicto"] == CUMPLE_EN_P95


def test_maximo_sobre_el_periodo_es_cumple_en_p95(corrida):
    # Los tiempos de 1 hilo en la laptop de A3: el máximo pasa los 200 ms de un cuadro.
    carpeta = corrida(resumen_de(inferencia=(134, 167, 203), total=(142, 179, 210)))
    assert main([str(carpeta)]) == 1
    filas = {f["id"]: f for f in leer(carpeta)["contraste"]}
    assert filas["total_vs_periodo"]["veredicto"] == CUMPLE_EN_P95
    assert filas["total_vs_periodo"]["margen_p95_ms"] == pytest.approx(21)
    assert filas["total_vs_edad"]["veredicto"] == CUMPLE


def test_en_bateria_no_cumple(corrida):
    carpeta = corrida(resumen_de(inferencia=(329, 689, 2350), total=(352, 708, 2382)))
    assert main([str(carpeta)]) == 1
    filas = {f["id"]: f for f in leer(carpeta)["contraste"]}
    assert filas["inferencia_vs_timeout"]["veredicto"] == NO_CUMPLE
    assert filas["total_vs_edad"]["veredicto"] == NO_CUMPLE


def test_otro_periodo_de_entrada(corrida):
    carpeta = corrida(resumen_de(inferencia=(134, 167, 203), total=(142, 179, 210)))
    assert main([str(carpeta), "--periodo-ms", "250"]) == 0
    assert leer(carpeta)["plazos"]["periodo_entrada_ms"] == 250


def test_corrida_con_advertencias_no_es_la_del_entregable(corrida):
    carpeta = corrida(resumen_de((80, 100, 155), (87, 113, 162), advertencias=["en batería"]))
    assert main([str(carpeta)]) == 1
    assert "en batería" in leer(carpeta)["advertencias"][0]


def test_plazos_distintos_a_los_medidos(corrida):
    carpeta = corrida(resumen_de((80, 100, 155), (87, 113, 162), sha_plazos="0" * 64))
    assert main([str(carpeta)]) == 1
    assert any("plazos.yaml cambió" in a for a in leer(carpeta)["advertencias"])


def test_sin_politica(corrida):
    resumen = resumen_de((80, 100, 155), (87, 113, 162))
    resumen["procedencia"]["config_b"] = None
    carpeta = corrida(resumen)
    assert main([str(carpeta)]) == 1
    assert any("--sin-politica" in a for a in leer(carpeta)["advertencias"])


def test_plazos_de_otra_carpeta(corrida, tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    shutil.copy(PLAZOS, config / "plazos.yaml")
    texto = (config / "plazos.yaml").read_text(encoding="utf-8")
    (config / "plazos.yaml").write_text(
        texto.replace("detector_timeout_ms: 500", "detector_timeout_ms: 90"), encoding="utf-8"
    )
    carpeta = corrida(resumen_de((80, 100, 155), (87, 113, 162)))
    assert main([str(carpeta), "--config-control", str(config)]) == 1
    filas = {f["id"]: f for f in leer(carpeta)["contraste"]}
    assert filas["inferencia_vs_timeout"]["veredicto"] == NO_CUMPLE


def test_sin_resumen_no_se_contrasta(tmp_path, capsys):
    assert main([str(tmp_path)]) == 2
    assert "corre antes python -m bench" in capsys.readouterr().err
    assert not (tmp_path / "contraste.json").exists()


def test_resumen_sin_etapas(corrida):
    resumen = resumen_de((80, 100, 155), (87, 113, 162))
    del resumen["etapas"]["inferencia_ms"]
    carpeta = corrida(resumen)
    with pytest.raises(ErrorLimites, match="inferencia_ms"):
        cargar_resumen(carpeta)
    assert main([str(carpeta)]) == 2


def test_resumen_que_no_es_json(tmp_path):
    (tmp_path / "resumen.json").write_text("{", encoding="utf-8")
    with pytest.raises(ErrorLimites, match="no es JSON"):
        cargar_resumen(tmp_path)


def test_periodo_invalido(corrida):
    carpeta = corrida(resumen_de((80, 100, 155), (87, 113, 162)))
    with pytest.raises(SystemExit):
        main([str(carpeta), "--periodo-ms", "0"])


def test_sobre_una_corrida_real_del_arnes(tmp_path, monkeypatch):
    monkeypatch.setattr("bench.__main__.energia", lambda: "corriente")
    imagenes = tmp_path / "imagenes"
    imagenes.mkdir()
    for i in range(3):
        (imagenes / f"{i}.jpg").write_bytes(b"\xff\xd8" + bytes([i]) * 10 + b"\xff\xd9")
    salida = tmp_path / "run"
    falso = DetectorFalso()
    argumentos = [
        "--entradas", str(imagenes), "--salida", str(salida), "--equipo", "pruebas",
        "--model-sha256", falso.model_sha256, "--config-sha256", falso.config_sha256, "--prueba",
    ]  # fmt: skip
    assert bench(argumentos) == 1
    # El detector falso es casi instantáneo: cumple, pero la corrida es de prueba.
    assert main([str(salida)]) == 1
    contraste = leer(salida)
    assert {f["veredicto"] for f in contraste["contraste"]} == {CUMPLE}
    assert any("modo de prueba" in a for a in contraste["advertencias"])
    assert contraste["corrida"]["resumen_sha256"] == sha256_archivo(salida / "resumen.json")


def test_la_consola_de_windows_puede_imprimir_el_resumen(corrida):
    # cp1252 es la codificación por omisión de la consola en Windows: el resumen no debe tronar.
    carpeta = corrida(resumen_de((80, 100, 155), (87, 113, 162)))
    resultado = subprocess.run(
        [sys.executable, "-m", "bench.limites", str(carpeta)],
        capture_output=True,
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr.decode("cp1252", "replace")
