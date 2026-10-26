import copy
import json
from pathlib import Path

import pytest

from contrato import validar_evento, validar_flujo
from contrato.__main__ import main

EJEMPLOS = Path(__file__).resolve().parents[1] / "config" / "contrato" / "ejemplos"

CAMPOS_OBLIGATORIOS = [
    "schema_version",
    "run_id",
    "sequence_id",
    "frame_id",
    "t_capture_ms",
    "t_emit_ms",
    "image_width",
    "image_height",
    "model_sha256",
    "config_sha256",
    "status",
    "bbox_format",
    "bbox_unit",
    "detections",
]

DETECCION = {"class_id": 0, "confidence": 0.9, "bbox": [10.0, 10.0, 100.0, 100.0]}


def cargar(nombre: str) -> dict:
    return json.loads((EJEMPLOS / nombre).read_text(encoding="utf-8"))


def mutar(nombre: str, cambios: dict | None = None, quitar: tuple[str, ...] = ()) -> dict:
    evento = copy.deepcopy(cargar(nombre))
    evento.update(cambios or {})
    for campo in quitar:
        evento.pop(campo)
    return evento


# --- ejemplos ---------------------------------------------------------------


@pytest.mark.parametrize("nombre", ["valido.json", "vacio.json", "fallido.json", "stale.json"])
def test_los_ejemplos_cumplen_el_contrato(nombre):
    assert validar_evento(cargar(nombre)) == []


def test_vacio_es_ok_con_lista_vacia():
    evento = cargar("vacio.json")
    assert evento["status"] == "ok"
    assert evento["detections"] == []


def test_fallido_es_error_con_causa_y_sin_detecciones():
    evento = cargar("fallido.json")
    assert evento["status"] == "error"
    assert evento["error"]["code"] == "unreadable_image"
    assert evento["detections"] == []


def test_el_flujo_de_ejemplo_cumple_el_contrato():
    assert main([str(EJEMPLOS / "flujo.jsonl")]) == 0


# --- eventos inválidos ------------------------------------------------------


@pytest.mark.parametrize("campo", CAMPOS_OBLIGATORIOS)
def test_falta_un_campo_obligatorio(campo):
    assert validar_evento(mutar("valido.json", quitar=(campo,)))


def _caja(formato: str, caja: list[float]) -> dict:
    return mutar(
        "valido.json",
        {"bbox_format": formato, "detections": [{**DETECCION, "bbox": caja}]},
    )


INVALIDOS = {
    "version distinta": mutar("valido.json", {"schema_version": "2"}),
    "status desconocido": mutar("valido.json", {"status": "unknown"}),
    "campo extra": mutar("valido.json", {"velocidad": 1}),
    "tiempo negativo": mutar("valido.json", {"t_capture_ms": -1}),
    "emision anterior a captura": mutar("valido.json", {"t_capture_ms": 500, "t_emit_ms": 400}),
    "hash corto": mutar("valido.json", {"model_sha256": "abc"}),
    "hash en mayusculas": mutar("valido.json", {"config_sha256": "A" * 64}),
    "id con espacios": mutar("valido.json", {"frame_id": "S02 f0003"}),
    "unidad distinta": mutar("valido.json", {"bbox_unit": "m"}),
    "formato de caja desconocido": mutar("valido.json", {"bbox_format": "cxcywh"}),
    "ok con error": mutar("valido.json", {"error": {"code": "invalid_output", "message": "x"}}),
    "ok con ancho null": mutar("valido.json", {"image_width": None}),
    "error sin objeto error": mutar("fallido.json", quitar=("error",)),
    "error con detecciones": mutar("fallido.json", {"detections": [DETECCION]}),
    "error con codigo desconocido": mutar(
        "fallido.json", {"error": {"code": "explotó", "message": "x"}}
    ),
    "stale con detecciones": mutar("stale.json", {"detections": [DETECCION]}),
    "stale con ancho null": mutar("stale.json", {"image_width": None}),
    "confianza mayor que 1": mutar(
        "valido.json", {"detections": [{**DETECCION, "confidence": 1.2}]}
    ),
    "class_id negativo": mutar("valido.json", {"detections": [{**DETECCION, "class_id": -1}]}),
    "caja con tres valores": _caja("xyxy", [1, 2, 3]),
    "xyxy invertida": _caja("xyxy", [100, 100, 10, 10]),
    "xyxy fuera de la imagen": _caja("xyxy", [10, 10, 700, 100]),
    "xywh sin alto": _caja("xywh", [10, 10, 50, 0]),
    "xywh fuera de la imagen": _caja("xywh", [600, 10, 100, 50]),
}


@pytest.mark.parametrize("nombre", INVALIDOS)
def test_evento_invalido_se_rechaza(nombre):
    assert validar_evento(INVALIDOS[nombre])


def test_xywh_valida_cuando_cabe():
    assert validar_evento(_caja("xywh", [10, 10, 90, 90])) == []


def test_lo_que_no_es_un_objeto_se_rechaza():
    assert validar_evento([]) and validar_evento(None)


# --- reglas entre eventos ---------------------------------------------------


def _flujo() -> list[dict]:
    return [
        mutar("valido.json", {"frame_id": "S02_f0001", "t_capture_ms": 0, "t_emit_ms": 30}),
        mutar("valido.json", {"frame_id": "S02_f0002", "t_capture_ms": 200, "t_emit_ms": 230}),
        mutar("valido.json", {"frame_id": "S02_f0003", "t_capture_ms": 400, "t_emit_ms": 430}),
    ]


def test_flujo_valido():
    assert validar_flujo(_flujo()) == []


def test_flujo_con_frame_repetido():
    eventos = _flujo()
    eventos[2]["frame_id"] = "S02_f0001"
    assert any("repetido" in e for e in validar_flujo(eventos))


def test_flujo_con_tiempo_que_no_crece():
    eventos = _flujo()
    eventos[2]["t_capture_ms"] = 200
    eventos[2]["t_emit_ms"] = 230
    assert any("no crece" in e for e in validar_flujo(eventos))


def test_el_tiempo_se_compara_dentro_de_cada_secuencia():
    eventos = _flujo()
    eventos.append(
        mutar(
            "valido.json",
            {"sequence_id": "S03", "frame_id": "S03_f0001", "t_capture_ms": 0, "t_emit_ms": 30},
        )
    )
    assert validar_flujo(eventos) == []


def test_flujo_que_cambia_de_modelo_dentro_del_run():
    eventos = _flujo()
    eventos[1]["model_sha256"] = "c" * 64
    assert any("cambia de modelo" in e for e in validar_flujo(eventos))


# --- línea de comandos ------------------------------------------------------


def _escribir(tmp_path: Path, eventos: list[dict], nombre: str = "e.jsonl") -> Path:
    ruta = tmp_path / nombre
    ruta.write_text("\n".join(json.dumps(e) for e in eventos) + "\n", encoding="utf-8")
    return ruta


def test_cli_acepta_un_archivo_valido(tmp_path):
    assert main([str(_escribir(tmp_path, _flujo()))]) == 0


def test_cli_rechaza_un_archivo_con_eventos_invalidos(tmp_path, capsys):
    eventos = _flujo()
    eventos[1]["status"] = "unknown"
    assert main([str(_escribir(tmp_path, eventos))]) == 1
    assert "evento 2" in capsys.readouterr().err


def test_cli_distingue_archivo_ilegible(tmp_path):
    assert main([str(tmp_path / "no_existe.jsonl")]) == 2
    malo = tmp_path / "malo.jsonl"
    malo.write_text("{no es json\n", encoding="utf-8")
    assert main([str(malo)]) == 2
