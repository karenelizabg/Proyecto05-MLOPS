"""Configuración efectiva y config_sha256 del detector P5-05."""

from __future__ import annotations

import copy
import hashlib
import json
import tomllib
from importlib.metadata import distribution
from pathlib import Path

import pytest
import yaml

from infer.config import (
    RAIZ,
    RUTA_CONFIG_DETECTOR,
    ErrorConfigDetector,
    cargar_config_detector,
    validar_config_detector,
    verificar_versiones_runtime,
)


@pytest.fixture
def datos() -> dict:
    return json.loads(RUTA_CONFIG_DETECTOR.read_text(encoding="utf-8"))


def test_carga_config_valida_y_argumentos_efectivos():
    config = cargar_config_detector()
    assert config.expected_model_sha256 == (
        "0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1"
    )
    assert config.torch_threads == 1
    assert config.predict_kwargs() == {
        "device": "cpu",
        "half": False,
        "batch": 1,
        "augment": False,
        "imgsz": 640,
        "conf": 0.25,
        "iou": 0.7,
        "agnostic_nms": False,
        "max_det": 300,
        "classes": [39, 41],
    }
    assert "rect" not in config.predict_kwargs()
    assert "rect" not in config.effective["preprocess"]


@pytest.mark.parametrize(
    ("seccion", "clave", "valor"),
    [
        ("execution", "device", "cuda:0"),
        ("execution", "dtype", "float16"),
        ("execution", "batch", 2),
        ("execution", "torch_threads", 0),
        ("preprocess", "letterbox", "square"),
        ("preprocess", "padding_value", 0),
        ("preprocess", "input_channels", "RGB"),
        ("preprocess", "imgsz", 641),
        ("postprocess", "class_ids", []),
        ("postprocess", "class_ids", [39, 39]),
        ("postprocess", "class_ids", [24]),
        ("postprocess", "max_det", 0),
        ("postprocess", "confidence", -0.1),
        ("postprocess", "nms_iou", 1.1),
    ],
)
def test_rechaza_valores_que_no_corresponden_al_runtime(datos, seccion, clave, valor):
    datos["effective"][seccion][clave] = valor
    with pytest.raises(ErrorConfigDetector):
        validar_config_detector(datos)


def test_rechaza_rect_y_campos_desconocidos(datos):
    datos["effective"]["preprocess"]["rect"] = False
    with pytest.raises(ErrorConfigDetector, match="preprocess"):
        validar_config_detector(datos)
    del datos["effective"]["preprocess"]["rect"]
    datos["timestamp"] = "2026-10-30"
    with pytest.raises(ErrorConfigDetector, match="config"):
        validar_config_detector(datos)


@pytest.mark.parametrize("valor", [float("nan"), float("inf"), float("-inf")])
def test_rechaza_numeros_no_finitos_en_diccionario(datos, valor):
    datos["effective"]["postprocess"]["confidence"] = valor
    with pytest.raises(ErrorConfigDetector, match="finito"):
        validar_config_detector(datos)


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_rechaza_json_no_finito(tmp_path: Path, datos, literal):
    ruta = tmp_path / "detector.json"
    texto = json.dumps(datos).replace('"confidence": 0.25', f'"confidence": {literal}')
    ruta.write_text(texto, encoding="utf-8")
    with pytest.raises(ErrorConfigDetector):
        cargar_config_detector(ruta)


def test_hash_canonico_y_copia_inmutable(datos):
    a = validar_config_detector(datos)
    assert a.config_sha256 == "bd736aff92ac6ae39348272ec48763764edf16b30c6ba0d3847cf9bae0658fdf"
    datos_reordenados = {
        "effective": {
            clave: dict(reversed(list(valor.items())))
            for clave, valor in reversed(list(datos["effective"].items()))
        },
        "artifacts": dict(reversed(list(datos["artifacts"].items()))),
    }
    datos_reordenados["effective"]["postprocess"]["class_ids"] = [41, 39]
    b = validar_config_detector(datos_reordenados)
    assert a.config_sha256 == b.config_sha256
    canonico = json.dumps(
        a.effective, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    assert a.config_sha256 == hashlib.sha256(canonico).hexdigest()
    copia = a.effective
    copia["preprocess"]["imgsz"] = 672
    assert a.effective["preprocess"]["imgsz"] == 640


def test_hash_no_depende_de_ruta_local(datos, tmp_path: Path):
    original = validar_config_detector(datos)
    datos["artifacts"]["weights_path"] = str(tmp_path / "otra-carpeta" / "yolo11n.pt")
    otra_ruta = validar_config_detector(datos)
    assert original.weights_path != otra_ruta.weights_path
    assert original.config_sha256 == otra_ruta.config_sha256


@pytest.mark.parametrize(
    ("seccion", "clave", "valor"),
    [
        ("postprocess", "confidence", 0.3),
        ("postprocess", "nms_iou", 0.6),
        ("postprocess", "class_ids", [39]),
        ("preprocess", "imgsz", 672),
    ],
)
def test_hash_cambia_con_parametro_efectivo(datos, seccion, clave, valor):
    original = validar_config_detector(datos).config_sha256
    modificado = copy.deepcopy(datos)
    modificado["effective"][seccion][clave] = valor
    assert validar_config_detector(modificado).config_sha256 != original


def test_coincide_con_la_decision_de_p5_04():
    config = cargar_config_detector()
    propuesta = json.loads(
        (RAIZ / "modelo" / "configuracion.p5-04.propuesta.json").read_text(encoding="utf-8")
    )
    clases_bytes = (RAIZ / "modelo" / "clases.json").read_bytes()
    assert hashlib.sha256(clases_bytes).hexdigest() == propuesta["clases"]["archivo_sha256"]
    assert config.expected_model_sha256 == propuesta["modelo"]["checkpoint_sha256"]
    assert config.effective["model"]["name"] == propuesta["modelo"]["nombre"]
    assert config.effective["runtime"]["ultralytics"] == propuesta["modelo"]["runtime_version"]
    assert config.predict_kwargs()["imgsz"] == propuesta["inferencia"]["imgsz"]
    assert config.predict_kwargs()["conf"] == propuesta["inferencia"]["conf"]
    assert config.predict_kwargs()["iou"] == propuesta["inferencia"]["iou"]
    assert config.predict_kwargs()["batch"] == propuesta["inferencia"]["batch"]
    assert config.predict_kwargs()["classes"] == propuesta["clases"]["class_ids"]


def test_versiones_directas_estan_fijadas_en_pyproject_y_lock():
    config = cargar_config_detector()
    pyproject = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((RAIZ / "uv.lock").read_text(encoding="utf-8"))
    dependencias = set(pyproject["project"]["dependencies"])
    for paquete, esperada in config.effective["runtime"].items():
        if paquete == "torchvision":
            assert (
                "torchvision==0.24.0+cpu; sys_platform == 'linux' and platform_machine == 'x86_64'"
            ) in dependencias
            assert (
                "torchvision==0.24.0; sys_platform != 'linux' or platform_machine != 'x86_64'"
            ) in dependencias
        else:
            assert f"{paquete}=={esperada}" in dependencias
        versiones = {
            item["version"].partition("+")[0] for item in lock["package"] if item["name"] == paquete
        }
        assert versiones == {esperada}
        assert distribution(paquete).version.partition("+")[0] == esperada
    verificar_versiones_runtime(config)


def test_lock_contiene_artefactos_torchvision_para_las_tres_plataformas():
    lock = tomllib.loads((RAIZ / "uv.lock").read_text(encoding="utf-8"))
    paquetes = [item for item in lock["package"] if item["name"] == "torchvision"]
    cpu = next(item for item in paquetes if item["version"] == "0.24.0+cpu")
    pypi = next(
        item
        for item in paquetes
        if item["version"] == "0.24.0" and "pypi.org" in str(item["source"])
    )
    assert any("cp312-cp312-manylinux_2_28_x86_64" in w["url"] for w in cpu["wheels"])
    assert any("cp312-cp312-macosx_11_0_arm64" in w["url"] for w in pypi["wheels"])
    assert any("cp312-cp312-win_amd64" in w["url"] for w in pypi["wheels"])


def test_argumentos_predict_reconocidos_por_ultralytics_instalado():
    ruta_defaults = distribution("ultralytics").locate_file("ultralytics/cfg/default.yaml")
    defaults = yaml.safe_load(ruta_defaults.read_text(encoding="utf-8"))
    assert set(cargar_config_detector().predict_kwargs()) <= set(defaults)
