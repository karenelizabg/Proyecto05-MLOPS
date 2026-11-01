"""Inferencia JPEG: validación previa, NMS nativo y resultados en píxeles."""

from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
import torch

import infer.detector as modulo_detector
from infer.config import cargar_config_detector
from infer.detector import (
    DetectorJPEG,
    ErrorImagenJPEG,
    ErrorSalidaInvalida,
    PredictorValidado,
    _extraer_detecciones,
    _validar_prediccion_cruda,
)
from infer.pesos import ModeloCargado, cargar_pesos


def _crudo(*cajas, clase=39):
    """Cajas xywh de entrada; los canales 4:84 son puntajes COCO, no IDs."""
    tensor = torch.zeros((1, 84, len(cajas)), dtype=torch.float32)
    for i, (x, y, w, h, confianza) in enumerate(cajas):
        tensor[0, :4, i] = torch.tensor([x, y, w, h])
        tensor[0, 4 + clase, i] = confianza
    return [tensor, []]


def _predictor_para_postproceso(config=None):
    config = config or cargar_config_detector()
    predictor = PredictorValidado(overrides={**config.predict_kwargs(), "save": False})
    predictor.model = SimpleNamespace(names={i: str(i) for i in range(80)})
    predictor.batch = (["cuadro"], None, None)
    return predictor


def _resultado_falso(filas):
    datos = torch.tensor(filas, dtype=torch.float32) if filas else torch.empty((0, 6))
    return SimpleNamespace(boxes=SimpleNamespace(data=datos))


def _detector_falso(filas):
    config = cargar_config_detector()
    detector = object.__new__(DetectorJPEG)
    detector.cargado = ModeloCargado(object(), "a" * 64, config.config_sha256)
    detector.config = config
    detector.clases = {39, 41}
    detector._lock = threading.Lock()

    class Predictor:
        tensor_shape = (1, 3, 480, 640)

        def __call__(self, source, stream=False):
            assert stream is False
            assert source.dtype == np.uint8 and source.shape[2] == 3
            self.tensor_shape = (1, 3, *source.shape[:2])
            return [
                SimpleNamespace(orig_shape=source.shape[:2], boxes=_resultado_falso(filas).boxes)
            ]

    detector.predictor = Predictor()
    return detector


def _jpeg(ruta: Path, width=640, height=480):
    imagen = np.zeros((height, width, 3), dtype=np.uint8)
    imagen[:, :, 0] = 70  # BGR: el canal azul confirma la decodificación OpenCV.
    assert cv2.imwrite(str(ruta), imagen)
    return ruta


def test_jpeg_valido_dimensiones_y_sin_detecciones(tmp_path):
    ruta = _jpeg(tmp_path / "imagen.jpg", 320, 240)
    resultado = _detector_falso([]).inferir(ruta)
    assert (resultado.width, resultado.height) == (320, 240)
    assert resultado.detections == ()
    assert resultado.model_sha256 == "a" * 64
    assert resultado.elapsed_ms >= 0


def test_calentamiento_usa_predictor_con_bgr_sintetico(monkeypatch):
    detector = _detector_falso([])
    recibidas = []
    llamar_original = type(detector.predictor).__call__

    def registrar(self, source, stream=False):
        recibidas.append(source.copy())
        return llamar_original(self, source, stream=stream)

    monkeypatch.setattr(type(detector.predictor), "__call__", registrar)
    detector.calentar()
    assert len(recibidas) == 1
    assert recibidas[0].shape == (480, 640, 3)
    assert recibidas[0].dtype == np.uint8
    assert not np.any(recibidas[0])


def test_setup_model_restaurara_hilos_intraop_y_se_mantienen_tras_inferir(tmp_path, monkeypatch):
    config = cargar_config_detector()
    cargado = ModeloCargado(SimpleNamespace(model=object()), "a" * 64, config.config_sha256)

    class PredictorQueCambiaHilos:
        tensor_shape = None

        def __init__(self, overrides):
            self.overrides = overrides

        def setup_model(self, model, verbose=False):
            torch.set_num_threads(7)
            self.model = SimpleNamespace(device=torch.device("cpu"), fp16=False)

        def __call__(self, source, stream=False):
            self.tensor_shape = (1, 3, *source.shape[:2])
            return [SimpleNamespace(orig_shape=source.shape[:2], boxes=_resultado_falso([]).boxes)]

    monkeypatch.setattr(modulo_detector, "PredictorValidado", PredictorQueCambiaHilos)
    hilos_anteriores = torch.get_num_threads()
    try:
        detector = DetectorJPEG(cargado, config)
        assert torch.get_num_threads() == config.torch_threads == 2
        detector.inferir(_jpeg(tmp_path / "S01_f0001.jpg"))
        assert torch.get_num_threads() == config.torch_threads
    finally:
        torch.set_num_threads(hilos_anteriores)


@pytest.mark.parametrize("contenido", [b"", b"no es JPEG", b"\xff\xd8\xff"])
def test_jpeg_ilegible_no_se_confunde_con_cero_detecciones(tmp_path, contenido):
    ruta = tmp_path / "corrupto.jpg"
    ruta.write_bytes(contenido)
    with pytest.raises(ErrorImagenJPEG, match="decodificar"):
        _detector_falso([]).inferir(ruta)


def test_error_de_opencv_al_decodificar_es_error_imagen(tmp_path, monkeypatch):
    ruta = tmp_path / "vacio.jpg"
    ruta.write_bytes(b"")

    def imread_con_error(_ruta, _modo):
        raise cv2.error("!buf.empty() en imdecode")

    monkeypatch.setattr(cv2, "imread", imread_con_error)
    with pytest.raises(ErrorImagenJPEG, match="decodificar"):
        _detector_falso([]).inferir(ruta)


def test_bottle_cup_y_otra_clase_coco(tmp_path):
    ruta = _jpeg(tmp_path / "objetos.jpeg")
    filas = [
        [10, 20, 50, 100, 0.9, 39],
        [100, 30, 130, 90, 0.8, 41],
        [200, 30, 230, 90, 0.95, 0],
    ]
    resultado = _detector_falso(filas).inferir(ruta)
    assert [d.class_id for d in resultado.detections] == [39, 41]
    assert resultado.detections[0].bbox == (10, 20, 50, 100)


@pytest.mark.parametrize(
    "fila",
    [
        [0, 0, 10, 10, 0.9, 80],
        [0, 0, 10, 10, 0.9, -1],
        [0, 0, 10, 10, float("nan"), 39],
        [0, 0, 10, 10, float("inf"), 39],
        [0, 0, 10, 10, -0.1, 39],
        [0, 0, 10, 10, 1.1, 39],
        [0, 0, float("nan"), 10, 0.9, 39],
        [0, 0, 10, float("-inf"), 0.9, 39],
        [10, 0, 10, 10, 0.9, 39],
        [20, 0, 10, 10, 0.9, 39],
        [-20, 0, -1, 10, 0.9, 39],
    ],
)
def test_resultado_corrupto_emite_invalid_output_antes_del_filtro(tmp_path, fila):
    ruta = _jpeg(tmp_path / "imagen.jpg")
    with pytest.raises(ErrorSalidaInvalida) as error:
        _detector_falso([fila]).inferir(ruta)
    assert error.value.code == "invalid_output"


def test_caja_fuera_de_limites_se_recorta_si_conserva_area():
    detecciones = _extraer_detecciones(
        _resultado_falso([[-10, 20, 660, 500, 0.9, 39]]), 640, 480, {39, 41}
    )
    assert detecciones[0].bbox == (0, 20, 640, 480)


@pytest.mark.parametrize("valor", [float("nan"), float("inf"), float("-inf")])
def test_valor_crudo_no_finito_nunca_llega_a_nms(valor):
    crudo = _crudo((320, 240, 100, 100, 0.9))
    crudo[0][0, 4 + 39, 0] = valor
    with pytest.raises(ErrorSalidaInvalida, match="NaN o Infinity"):
        _validar_prediccion_cruda(crudo)
    crudo = _crudo((320, 240, 100, 100, 0.9))
    crudo[0][0, 0, 0] = valor
    with pytest.raises(ErrorSalidaInvalida, match="NaN o Infinity"):
        _validar_prediccion_cruda(crudo)


@pytest.mark.parametrize("valor", [-0.01, 1.01])
def test_puntaje_crudo_fuera_de_rango(valor):
    crudo = _crudo((320, 240, 100, 100, 0.9))
    crudo[0][0, 4 + 39, 0] = valor
    with pytest.raises(ErrorSalidaInvalida, match="puntaje"):
        _validar_prediccion_cruda(crudo)


@pytest.mark.parametrize("ancho,alto", [(0, 10), (-1, 10), (10, 0), (10, -1)])
def test_geometria_cruda_no_positiva(ancho, alto):
    with pytest.raises(ErrorSalidaInvalida, match="ancho o alto"):
        _validar_prediccion_cruda(_crudo((320, 240, ancho, alto, 0.9)))


def test_centros_crudos_fuera_de_imagen_no_se_rechazan():
    _validar_prediccion_cruda(_crudo((-20, 700, 100, 100, 0.9)))


def test_geometria_cruda_que_desborda_xyxy():
    with pytest.raises(ErrorSalidaInvalida, match="desborda"):
        _validar_prediccion_cruda(_crudo((3e38, 240, 3e38, 100, 0.9)))


def test_hook_rechaza_nan_antes_del_nms_y_filtro_de_clases(monkeypatch):
    from ultralytics.models.yolo.detect import predict

    def nms_prohibido(*args, **kwargs):
        pytest.fail("NMS recibió una predicción corrupta")

    monkeypatch.setattr(predict.ops, "non_max_suppression", nms_prohibido)
    crudo = _crudo((320, 240, 100, 100, 0.9), clase=0)
    crudo[0][0, 4, 0] = float("nan")
    predictor = _predictor_para_postproceso()
    with pytest.raises(ErrorSalidaInvalida) as error:
        predictor.postprocess(crudo, torch.zeros((1, 3, 480, 640)), [np.zeros((480, 640, 3))])
    assert error.value.code == "invalid_output"


@pytest.mark.parametrize("forma", [(1, 6, 300), (2, 84, 100), (1, 85, 100)])
def test_estructura_cruda_o_catalogo_incorrecto(forma):
    with pytest.raises(ErrorSalidaInvalida, match="estructura cruda"):
        _validar_prediccion_cruda(torch.zeros(forma))


def test_nms_nativo_y_remapeo_de_letterbox():
    predictor = _predictor_para_postproceso()
    original = np.zeros((720, 1280, 3), dtype=np.uint8)
    # Entrada 384x640: escala 0.5 y padding vertical de 12 px.
    tensor = torch.zeros((1, 3, 384, 640), dtype=torch.float32)
    crudo = _crudo((200, 137, 200, 150, 0.9), (202, 139, 200, 150, 0.8))
    resultados = predictor.postprocess(crudo, tensor, [original])
    assert len(resultados[0].boxes) == 1  # NMS nativo suprime la superposición.
    assert resultados[0].boxes.cls.tolist() == [39.0]
    assert resultados[0].boxes.xyxy[0].tolist() == pytest.approx([200, 100, 600, 400])


def test_nms_nativo_filtra_clase_coco_fuera_del_dominio():
    predictor = _predictor_para_postproceso()
    original = np.zeros((480, 640, 3), dtype=np.uint8)
    tensor = torch.zeros((1, 3, 480, 640), dtype=torch.float32)
    crudo = _crudo((200, 200, 100, 100, 0.9), clase=0)
    resultado = predictor.postprocess(crudo, tensor, [original])[0]
    assert len(resultado.boxes) == 0


def test_jpeg_mismas_predicciones_tras_cambiar_nombre(tmp_path):
    ruta_a = _jpeg(tmp_path / "objeto_botella.jpg")
    ruta_b = tmp_path / "despejado.jpg"
    shutil.copyfile(ruta_a, ruta_b)
    detector = _detector_falso([[20, 30, 50, 90, 0.8, 39]])
    assert detector.inferir(ruta_a).detections == detector.inferir(ruta_b).detections


def test_checkpoint_real_jpeg_y_validacion_en_ruta_de_inferencia(monkeypatch, tmp_path):
    ruta = os.environ.get("P5_05_YOLO11N_PT")
    if not ruta:
        pytest.skip("definir P5_05_YOLO11N_PT para inferencia real")
    from ultralytics.utils import downloads

    def descarga_prohibida(*args, **kwargs):
        pytest.fail("la inferencia intentó descargar un archivo")

    monkeypatch.setattr(downloads, "safe_download", descarga_prohibida)
    monkeypatch.setattr(downloads, "get_github_assets", descarga_prohibida)
    config = cargar_config_detector()
    detector = DetectorJPEG(cargar_pesos(ruta, config), config)
    assert torch.get_num_threads() == config.torch_threads
    raiz = Path(__file__).resolve().parents[1]
    taza = detector.inferir(raiz / "docs/carro/objeto_taza_centro_cerca.jpg")
    detector.calentar()
    taza_tras_calentar = detector.inferir(raiz / "docs/carro/objeto_taza_centro_cerca.jpg")
    assert taza_tras_calentar.detections == taza.detections
    assert torch.get_num_threads() == config.torch_threads
    lateral = detector.inferir(raiz / "docs/carro/objeto_botella_der.jpg")
    otra_proporcion = detector.inferir(raiz / "docs/carro/atras.jpg")
    assert (taza.width, taza.height, taza.tensor_shape) == (640, 480, (1, 3, 480, 640))
    assert 41 in [d.class_id for d in taza.detections]
    assert 39 in [d.class_id for d in lateral.detections]
    assert otra_proporcion.tensor_shape == (1, 3, 640, 480)

    copia = tmp_path / "nombre_sin_objetos.jpg"
    shutil.copyfile(raiz / "docs/carro/objeto_taza_centro_cerca.jpg", copia)
    assert detector.inferir(copia).detections == taza.detections

    def inferencia_corrupta(im, *args, **kwargs):
        crudo = _crudo((320, 240, 100, 100, 0.9))
        crudo[0][0, 4 + 39, 0] = float("nan")
        return crudo

    monkeypatch.setattr(detector.predictor, "inference", inferencia_corrupta)
    with pytest.raises(ErrorSalidaInvalida) as error:
        detector.inferir(raiz / "docs/carro/objeto_taza_centro_cerca.jpg")
    assert error.value.code == "invalid_output"
