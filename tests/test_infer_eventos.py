"""CLI y JSONL v1 del detector, con un recorrido real opcional."""

from __future__ import annotations

import math
import os
import shutil
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pytest

import infer.eventos as modulo_eventos
from contrato.validador import leer_eventos, validar_evento, validar_flujo
from infer.__main__ import main
from infer.config import cargar_config_detector
from infer.detector import Deteccion, ErrorImagenJPEG, ErrorSalidaInvalida, ResultadoJPEG
from infer.eventos import ErrorRunInfer, _serializar_evento, ejecutar_run
from infer.pesos import ModeloCargado


def _jpeg(ruta: Path):
    assert cv2.imwrite(str(ruta), np.zeros((60, 80, 3), dtype=np.uint8))
    return ruta


class DetectorFalso:
    def __init__(self, detecciones=(), error=None):
        self.config = cargar_config_detector()
        self.cargado = ModeloCargado(object(), "a" * 64, self.config.config_sha256)
        self.detecciones = detecciones
        self.error = error
        self.rutas = []

    def inferir(self, ruta):
        self.rutas.append(ruta)
        if self.error:
            raise self.error
        if cv2.imread(str(ruta), cv2.IMREAD_COLOR) is None:
            raise ErrorImagenJPEG("JPEG ilegible")
        return ResultadoJPEG(
            80,
            60,
            (1, 3, 480, 640),
            tuple(self.detecciones),
            1.0,
            self.cargado.model_sha256,
            self.config.config_sha256,
        )


def _run(tmp_path, detector=None, *, capturas=None, entrada=None, run_id="prueba", **kwargs):
    detector = detector or DetectorFalso()
    entrada = entrada or _jpeg(tmp_path / "cuadro.jpg")
    salida = tmp_path / f"{run_id}.jsonl"
    ruta, cantidad, errores = ejecutar_run(
        detector, entrada, salida, run_id=run_id, capture_ms=capturas, **kwargs
    )
    eventos = leer_eventos(ruta)
    assert cantidad == len(eventos)
    assert validar_flujo(eventos) == []
    assert all(validar_evento(ev) == [] for ev in eventos)
    return eventos, errores


def test_un_jpeg_vacio_usa_recepcion_monotonica(tmp_path):
    eventos, errores = _run(tmp_path)
    ev = eventos[0]
    assert errores == 0
    assert ev["sequence_id"] == "independent" and ev["frame_id"] == "f000001"
    assert ev["status"] == "ok" and ev["detections"] == [] and "error" not in ev
    assert ev["t_emit_ms"] >= ev["t_capture_ms"] >= 0


def test_bottle_y_cup_en_jsonl(tmp_path):
    detecciones = (
        Deteccion(39, 0.9, (1, 2, 20, 30)),
        Deteccion(41, 0.8, (30, 3, 50, 40)),
    )
    eventos, _ = _run(tmp_path, DetectorFalso(detecciones))
    assert [d["class_id"] for d in eventos[0]["detections"]] == [39, 41]
    assert eventos[0]["bbox_format"] == "xyxy" and eventos[0]["bbox_unit"] == "px"


def test_directorio_reproduce_tiempos_explicitos_y_ids_unicos(tmp_path):
    carpeta = tmp_path / "entrada"
    carpeta.mkdir()
    _jpeg(carpeta / "b.jpg")
    _jpeg(carpeta / "a.jpeg")
    (carpeta / "anotaciones.json").write_text("{}")
    (carpeta / "manifiesto.csv").write_text("frame,label\n")
    detector = DetectorFalso()
    eventos, _ = _run(
        tmp_path,
        detector,
        capturas=[0.0, 1.0],
        entrada=carpeta,
        sequence_id="S01",
    )
    assert [e["t_capture_ms"] for e in eventos] == [0.0, 1.0]
    assert [e["frame_id"] for e in eventos] == ["f000001", "f000002"]
    assert [r.name for r in detector.rutas] == ["a.jpeg", "b.jpg"]


def test_infer_no_abre_anotaciones_ni_manifiesto(tmp_path, monkeypatch):
    carpeta = tmp_path / "entrada"
    carpeta.mkdir()
    _jpeg(carpeta / "cuadro.jpg")
    (carpeta / "anotaciones.json").write_text('{"class_id":41}')
    (carpeta / "manifiesto.csv").write_text("cuadro.jpg,cup\n")
    abrir_original = Path.open

    def abrir_sin_metadatos(self, *args, **kwargs):
        if self.name in {"anotaciones.json", "manifiesto.csv"}:
            pytest.fail("infer intentó abrir anotaciones o manifiesto")
        return abrir_original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", abrir_sin_metadatos)
    eventos, _ = _run(tmp_path, entrada=carpeta, capturas=[0.0], sequence_id="S01")
    assert eventos[0]["status"] == "ok"


@pytest.mark.parametrize(
    ("error", "codigo"),
    [
        (ErrorImagenJPEG("no se pudo leer"), "unreadable_image"),
        (ErrorSalidaInvalida("NaN"), "invalid_output"),
        (RuntimeError("falló el predictor"), "detector_exception"),
    ],
)
def test_errores_no_son_ok_vacio(tmp_path, error, codigo):
    eventos, errores = _run(tmp_path, DetectorFalso(error=error))
    ev = eventos[0]
    assert errores == 1 and ev["status"] == "error" and ev["detections"] == []
    assert ev["error"]["code"] == codigo
    assert (ev["image_width"], ev["image_height"]) == (
        (None, None) if codigo == "unreadable_image" else (80, 60)
    )


def test_jpeg_corrupto_emite_unreadable_image(tmp_path):
    ruta = tmp_path / "corrupto.jpg"
    ruta.write_bytes(b"incorrecto")
    eventos, errores = _run(tmp_path, entrada=ruta)
    assert errores == 1 and eventos[0]["error"]["code"] == "unreadable_image"


@pytest.mark.parametrize(
    ("error_type", "codigo"),
    [
        (ErrorImagenJPEG, "unreadable_image"),
        (ErrorSalidaInvalida, "invalid_output"),
        (RuntimeError, "detector_exception"),
    ],
)
def test_evento_error_no_publica_ruta_absoluta(tmp_path, capsys, error_type, codigo):
    ruta_privada = tmp_path / "imagenes" / "privada.jpg"
    detector = DetectorFalso(error=error_type(f"falló {ruta_privada}"))
    eventos, errores = _run(tmp_path, detector)
    evento = eventos[0]
    assert errores == 1 and evento["status"] == "error"
    assert evento["error"]["code"] == codigo
    assert str(ruta_privada) not in (tmp_path / "prueba.jsonl").read_text()
    assert str(ruta_privada) not in evento["error"]["message"]
    assert str(ruta_privada) in capsys.readouterr().err


@pytest.mark.parametrize("capturas", [[0, 0], [1, 0], [0], [0, math.nan], [0, math.inf]])
def test_tiempos_invalidos_se_rechazan_antes_de_abrir_salida(tmp_path, capturas):
    carpeta = tmp_path / "entrada"
    carpeta.mkdir()
    _jpeg(carpeta / "a.jpg")
    _jpeg(carpeta / "b.jpg")
    with pytest.raises(ErrorRunInfer, match="capture-ms"):
        ejecutar_run(
            DetectorFalso(),
            carpeta,
            tmp_path / "salida.jsonl",
            run_id="prueba",
            sequence_id="S01",
            capture_ms=capturas,
        )
    assert not (tmp_path / "salida.jsonl").exists()


def test_directorio_sin_capturas_o_secuencia_se_rechaza(tmp_path):
    carpeta = tmp_path / "entrada"
    carpeta.mkdir()
    _jpeg(carpeta / "a.jpg")
    with pytest.raises(ErrorRunInfer):
        ejecutar_run(DetectorFalso(), carpeta, tmp_path / "x.jsonl", run_id="r")


def test_salida_existente_no_se_sobrescribe(tmp_path):
    entrada = _jpeg(tmp_path / "cuadro.jpg")
    salida = tmp_path / "salida.jsonl"
    previo = b"resultado anterior\n"
    salida.write_bytes(previo)
    with pytest.raises(FileExistsError):
        ejecutar_run(DetectorFalso(), entrada, salida, run_id="r")
    assert salida.read_bytes() == previo


@pytest.mark.parametrize("enlace_roto", [False, True])
def test_enlace_final_de_salida_no_se_sobrescribe(tmp_path, enlace_roto):
    entrada = _jpeg(tmp_path / "cuadro.jpg")
    destino = tmp_path / "destino.jsonl"
    if not enlace_roto:
        destino.write_bytes(b"intacto")
    enlace = tmp_path / "enlace.jsonl"
    try:
        enlace.symlink_to(destino)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"el entorno no permite crear enlaces simbólicos: {exc}")
    with pytest.raises(FileExistsError):
        ejecutar_run(DetectorFalso(), entrada, enlace, run_id="r")
    assert enlace.is_symlink()
    if enlace_roto:
        assert not destino.exists()
    else:
        assert destino.read_bytes() == b"intacto"


def test_directorio_padre_de_salida_enlazado_se_sigue(tmp_path):
    entrada = _jpeg(tmp_path / "cuadro.jpg")
    destino_real = tmp_path / "destino-real"
    destino_real.mkdir()
    enlace_padre = tmp_path / "enlace-padre"
    try:
        enlace_padre.symlink_to(destino_real, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"el entorno no permite crear enlaces simbólicos: {exc}")
    salida, cantidad, errores = ejecutar_run(
        DetectorFalso(), entrada, enlace_padre / "salida.jsonl", run_id="r"
    )
    assert (cantidad, errores) == (1, 0)
    assert salida.is_file()
    assert (destino_real / "salida.jsonl").is_file()


def test_fallo_durante_procesamiento_deja_solo_eventos_completos(tmp_path, monkeypatch):
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    _jpeg(entrada / "a.jpg")
    _jpeg(entrada / "b.jpg")
    salida = tmp_path / "parcial.jsonl"
    original = modulo_eventos._serializar_evento

    def fallar_en_segundo(evento, anteriores):
        if anteriores:
            raise ErrorRunInfer("fallo posterior al primer cuadro")
        return original(evento, anteriores)

    monkeypatch.setattr(modulo_eventos, "_serializar_evento", fallar_en_segundo)
    with pytest.raises(ErrorRunInfer, match="fallo posterior"):
        ejecutar_run(
            DetectorFalso(),
            entrada,
            salida,
            run_id="r",
            sequence_id="S01",
            capture_ms=[0, 1],
        )
    assert [evento["frame_id"] for evento in leer_eventos(salida)] == ["f000001"]


def test_id_repetido_y_hash_cambiante_se_rechazan(tmp_path):
    eventos, _ = _run(tmp_path)
    original = eventos[0]
    duplicado = {
        **original,
        "t_capture_ms": original["t_capture_ms"] + 1,
        "t_emit_ms": original["t_emit_ms"] + 2,
    }
    with pytest.raises(ErrorRunInfer, match="repetido"):
        _serializar_evento(duplicado, eventos)
    cambiado = {**duplicado, "frame_id": "f000002", "model_sha256": "b" * 64}
    with pytest.raises(ErrorRunInfer, match="cambia de modelo"):
        _serializar_evento(cambiado, eventos)


def test_emit_antes_de_capture_y_nan_rechazados(tmp_path):
    eventos, _ = _run(tmp_path)
    original = eventos[0]
    with pytest.raises(ErrorRunInfer, match="anterior"):
        _serializar_evento({**original, "t_capture_ms": original["t_emit_ms"] + 1}, [])
    with pytest.raises(ErrorRunInfer, match="finito"):
        _serializar_evento({**original, "t_capture_ms": math.nan}, [])
    with pytest.raises(ErrorRunInfer, match="finito"):
        _serializar_evento({**original, "t_emit_ms": math.inf}, [])


def test_hash_de_resultado_inconsistente_emite_invalid_output(tmp_path):
    class Cambiante(DetectorFalso):
        def inferir(self, ruta):
            return replace(super().inferir(ruta), model_sha256="b" * 64)

    eventos, errores = _run(tmp_path, Cambiante())
    assert errores == 1 and eventos[0]["error"]["code"] == "invalid_output"
    assert eventos[0]["model_sha256"] == "a" * 64


@pytest.mark.parametrize("valor", [math.nan, math.inf, -math.inf])
def test_deteccion_no_finita_emite_invalid_output_sin_json_especial(tmp_path, valor):
    detector = DetectorFalso((Deteccion(39, valor, (1, 2, 20, 30)),))
    eventos, errores = _run(tmp_path, detector)
    assert errores == 1 and eventos[0]["error"]["code"] == "invalid_output"
    assert eventos[0]["detections"] == []
    texto = (tmp_path / "prueba.jsonl").read_text()
    assert "NaN" not in texto and "Infinity" not in texto


def test_renombrar_jpeg_y_anotaciones_no_cambian_predicciones(tmp_path):
    original = _jpeg(tmp_path / "botella.jpg")
    renombrada = tmp_path / "vacio.jpg"
    shutil.copyfile(original, renombrada)
    (tmp_path / "botella.json").write_text('{"class_id":41}')
    detector = DetectorFalso((Deteccion(39, 0.9, (1, 2, 20, 30)),))
    primero, _ = _run(tmp_path, detector, entrada=original)
    segundo, _ = _run(tmp_path, detector, entrada=renombrada, run_id="otro")
    assert primero[0]["detections"] == segundo[0]["detections"]


def test_cli_real_extremo_a_extremo_sin_descargas(tmp_path, monkeypatch):
    checkpoint = os.environ.get("P5_05_YOLO11N_PT")
    if not checkpoint:
        pytest.skip("definir P5_05_YOLO11N_PT para el recorrido real")
    from ultralytics.utils import downloads

    def prohibido(*args, **kwargs):
        pytest.fail("se intentó una descarga")

    monkeypatch.setattr(downloads, "safe_download", prohibido)
    monkeypatch.setattr(downloads, "get_github_assets", prohibido)
    raiz = Path(__file__).resolve().parents[1]
    salida = tmp_path / "real.jsonl"
    codigo = main(
        [
            "--input",
            str(raiz / "docs/carro/objeto_taza_centro_cerca.jpg"),
            "--weights",
            checkpoint,
            "--output",
            str(salida),
            "--run-id",
            "real-01",
        ]
    )
    assert codigo == 0
    eventos = leer_eventos(salida)
    assert len(eventos) == 1 and validar_evento(eventos[0]) == []
    assert validar_flujo(eventos) == []
    assert eventos[0]["model_sha256"] == cargar_config_detector().expected_model_sha256
    assert eventos[0]["config_sha256"] == cargar_config_detector().config_sha256
    assert any(d["class_id"] == 41 for d in eventos[0]["detections"])
    assert "NaN" not in salida.read_text() and "Infinity" not in salida.read_text()


def test_cli_ayuda_y_error_de_pesos(tmp_path, capsys):
    assert (
        main(
            [
                "--input",
                str(tmp_path / "x.jpg"),
                "--weights",
                str(tmp_path / "x.pt"),
                "--output",
                str(tmp_path / "x.jsonl"),
                "--run-id",
                "r",
            ]
        )
        == 2
    )
    assert "no se pudo abrir" in capsys.readouterr().err
