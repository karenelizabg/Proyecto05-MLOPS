"""El adaptador de P5-05 para el arnés (bench.yolo) con los pesos reales.

Como las pruebas de inferencia real de P5-05, necesitan `P5_05_YOLO11N_PT` con la ruta al
checkpoint verificado; sin ella se saltan.
"""

import json
import os
from pathlib import Path

import pytest
import torch

from bench.__main__ import main

RAIZ = Path(__file__).resolve().parents[1]
CUADROS = [
    RAIZ / "docs/carro/objeto_taza_centro_cerca.jpg",
    RAIZ / "docs/carro/objeto_botella_izq.jpg",
    RAIZ / "docs/carro/objeto_botella_der.jpg",
    RAIZ / "docs/carro/atras.jpg",  # otra proporción: el letterbox da otro tensor
]
PESOS = os.environ.get("P5_05_YOLO11N_PT")
pytestmark = pytest.mark.skipif(not PESOS, reason="definir P5_05_YOLO11N_PT para inferencia real")


@pytest.fixture(scope="module")
def yolo():
    from bench.yolo import crear

    return crear(PESOS)


def por_etapas(detector, ruta):
    imagen = detector.leer(ruta)
    return detector.posprocesar(detector.inferir(detector.preprocesar(imagen)), imagen)


@pytest.mark.parametrize("ruta", CUADROS, ids=lambda r: r.stem)
def test_por_etapas_da_lo_mismo_que_infer(yolo, ruta):
    esperado = [
        {"class_id": d.class_id, "confidence": d.confidence, "bbox": list(d.bbox)}
        for d in yolo._detector.inferir(ruta).detections
    ]
    assert por_etapas(yolo, ruta) == esperado


def test_detecta_la_taza_y_las_botellas(yolo):
    clases = [[d["class_id"] for d in por_etapas(yolo, ruta)] for ruta in CUADROS[:3]]
    assert clases == [[41], [39], [39]]


def test_hilos_de_la_configuracion(yolo):
    # Ultralytics los restablece al preparar el predictor; DetectorJPEG los vuelve a fijar.
    hilos = yolo._detector.config.torch_threads
    assert torch.get_num_threads() == hilos
    assert yolo.descripcion()["hilos_torch"] == hilos
    assert yolo.descripcion()["hilos_configurados"] == hilos


def test_sin_opcion_para_cambiar_los_hilos():
    from bench.yolo import crear

    with pytest.raises(TypeError):
        crear(PESOS, hilos=4)


def test_jpeg_vacio_no_truena_con_cv2_error(yolo, tmp_path):
    vacio = tmp_path / "vacio.jpg"
    vacio.write_bytes(b"")
    with pytest.raises(ValueError):
        yolo.leer(vacio)


def test_salida_cruda_invalida(yolo):
    from infer.detector import ErrorSalidaInvalida

    imagen = yolo.leer(CUADROS[0])
    crudo, *auxiliares = yolo.inferir(yolo.preprocesar(imagen))
    crudo = crudo.clone()
    crudo[0, 4 + 39, 0] = float("nan")
    with pytest.raises(ErrorSalidaInvalida):
        yolo.posprocesar([crudo, *auxiliares], imagen)


def test_medicion_oficial_con_el_detector_real(tmp_path, monkeypatch, yolo):
    monkeypatch.setattr("bench.__main__.energia", lambda: "corriente")
    salida = tmp_path / "run"
    argumentos = [
        "--entradas", *map(str, CUADROS[:3]), "--salida", str(salida), "--equipo", "pruebas",
        "--detector", "bench.yolo", "--opcion", f"pesos={PESOS}",
        "--model-sha256", yolo.model_sha256, "--config-sha256", yolo.config_sha256,
    ]  # fmt: skip
    assert main(argumentos) == 0
    resumen = json.loads((salida / "resumen.json").read_text(encoding="utf-8"))
    assert resumen["procedencia"]["detector"]["comprobada"] is True
    assert resumen["conteos"] == {"calentamientos": 10, "mediciones": 100, "fallos": 0}
    assert resumen["runtime"]["detector"]["hilos_torch"] == yolo._detector.config.torch_threads
    assert resumen["advertencias"] == []
