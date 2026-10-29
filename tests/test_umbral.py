"""Pruebas del umbral de confianza (T10, #30, caso C6)."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from contrato import validar_evento
from control.config import RAIZ, cargar_config_politica
from control.politica import ESTADO_INICIAL, decidir, ignoradas_por_confianza

CONFIG = cargar_config_politica()
UMBRAL = CONFIG.umbral_confianza
EJEMPLOS = RAIZ / "config" / "contrato" / "ejemplos"
# Una clase de obstáculo real de politica.yaml (T12, #32); así la prueba no depende del id.
OBSTACULO = min(CONFIG.clases_obstaculo)
NO_RELEVANTE = 7
CENTRO = [260, 100, 380, 400]  # en una imagen de 640 px
IZQ = [20, 100, 120, 400]
DER = [520, 100, 620, 400]


def evento(*dets):
    """dets: (caja, confianza) o (caja, confianza, class_id)."""
    ev = {
        "schema_version": "1",
        "run_id": "prueba-t10",
        "sequence_id": "S01",
        "frame_id": "S01_f0001",
        "t_capture_ms": 200,
        "t_emit_ms": 230,
        "image_width": 640,
        "image_height": 480,
        "model_sha256": "a" * 64,
        "config_sha256": "b" * 64,
        "status": "ok",
        "bbox_format": "xyxy",
        "bbox_unit": "px",
        "detections": [
            {"class_id": d[2] if len(d) > 2 else OBSTACULO, "confidence": d[1], "bbox": d[0]}
            for d in dets
        ],
    }
    assert validar_evento(ev) == []
    return ev


def decide(ev, config=CONFIG):
    return decidir(ev, dict(ESTADO_INICIAL), config)[0]


# --- C6: mismo obstáculo, distinta confianza -------------------------------------------


def test_debajo_del_umbral_avanza_y_lo_menciona():
    comando = decide(evento((CENTRO, 0.1)))
    assert comando["action"] == "AVANZAR"
    assert comando["speed"] > 0
    assert "ignorada_por_confianza" in comando["reason"]
    assert f"class_id {OBSTACULO}, confianza 0.1" in comando["reason"]


def test_justo_en_el_umbral_cuenta():
    comando = decide(evento((CENTRO, UMBRAL)))
    assert comando["action"] in {"GIRAR_IZQ", "GIRAR_DER"}
    assert "ignorada_por_confianza" not in comando["reason"]


def test_arriba_del_umbral_reacciona():
    comando = decide(evento((CENTRO, 0.9)))
    assert comando["action"] in {"GIRAR_IZQ", "GIRAR_DER"}
    sin_giro = decide(evento((CENTRO, 0.9)), replace(CONFIG, permitir_giro=False))
    assert sin_giro["action"] == "STOP"


@pytest.mark.parametrize(
    ("umbral", "accion"),
    [(0.2, "STOP"), (0.3, "STOP"), (0.31, "AVANZAR"), (0.8, "AVANZAR")],
)
def test_cambiar_el_umbral_en_config_cambia_el_resultado(umbral, accion):
    config = replace(CONFIG, umbral_confianza=umbral, permitir_giro=False)
    assert decide(evento((CENTRO, 0.3)), config)["action"] == accion


def test_obstaculo_seguro_y_otro_dudoso():
    # El de la derecha es dudoso: no cuenta, así que la derecha sigue libre para girar.
    comando = decide(evento((CENTRO, 0.9), (IZQ, 0.9), (DER, 0.2)))
    assert comando["action"] == "GIRAR_DER"
    assert f"ignorada_por_confianza: class_id {OBSTACULO}, confianza 0.2" in comando["reason"]


def test_clase_no_relevante_no_se_reporta_como_ignorada():
    # Una clase que no es obstáculo se descarta por clase, no por confianza.
    comando = decide(evento((CENTRO, 0.1, NO_RELEVANTE)))
    assert comando["action"] == "AVANZAR"
    assert "ignorada_por_confianza" not in comando["reason"]


def test_ignoradas_por_confianza():
    ev = evento((CENTRO, 0.1), (IZQ, 0.9), (DER, 0.2, NO_RELEVANTE), (DER, UMBRAL))
    ignoradas = ignoradas_por_confianza(ev, CONFIG)
    assert [d["confidence"] for d in ignoradas] == [0.1]


# --- Poca confianza no es falla de percepción ------------------------------------------


def test_poca_confianza_no_es_falla_de_percepcion():
    """Cuadro ok con detección dudosa -> se ignora y avanza. stale/error -> siempre STOP."""
    dudoso = decide(evento((CENTRO, 0.1)))
    assert dudoso["action"] == "AVANZAR"
    assert "no es falla de percepción" in dudoso["reason"]

    for archivo in ("stale.json", "fallido.json"):
        ev = json.loads((EJEMPLOS / archivo).read_text(encoding="utf-8"))
        falla = decide(ev)
        assert falla["action"] == "STOP"
        assert "ignorada_por_confianza" not in falla["reason"]


def test_umbral_cero_cuenta_todo():
    config = replace(CONFIG, umbral_confianza=0.0, permitir_giro=False)
    comando = decide(evento((CENTRO, 0.0)), config)
    assert comando["action"] == "STOP"
    assert "ignorada_por_confianza" not in comando["reason"]
