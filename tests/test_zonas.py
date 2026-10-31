"""Pruebas de zonas izquierda / centro / derecha (T08, #28)."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from contrato import validar_evento
from control.config import RAIZ, cargar_config_politica
from control.politica import caja_a_xyxy, zonas_ocupadas

CONFIG = cargar_config_politica()
EJEMPLOS = RAIZ / "config" / "contrato" / "ejemplos"

# Una clase de obstáculo real de politica.yaml (T12, #32); así la prueba no depende del id.
CLASE_OBSTACULO = min(CONFIG.clases_obstaculo)
CLASE_NO_RELEVANTE = 7  # cualquier class_id que no esté en clases_obstaculo


def evento(detecciones, *, ancho=640, alto=480, formato="xyxy"):
    """Evento `ok` mínimo que cumple el contrato v1."""
    ev = {
        "schema_version": "1",
        "run_id": "prueba-t08",
        "sequence_id": "S01",
        "frame_id": "S01_f0001",
        "t_capture_ms": 0,
        "t_emit_ms": 30,
        "image_width": ancho,
        "image_height": alto,
        "model_sha256": "a" * 64,
        "config_sha256": "b" * 64,
        "status": "ok",
        "bbox_format": formato,
        "bbox_unit": "px",
        "detections": [
            {"class_id": c, "confidence": conf, "bbox": list(caja)} for c, conf, caja in detecciones
        ],
    }
    assert validar_evento(ev) == [], validar_evento(ev)
    return ev


def obst(caja, conf=0.9, clase=CLASE_OBSTACULO):
    return (clase, conf, caja)


# --- Una caja por zona, en imágenes de distinto ancho ----------------------------------


@pytest.mark.parametrize("ancho", [320, 640, 1280])
@pytest.mark.parametrize(
    ("x1_frac", "x2_frac", "esperado"),
    [
        (0.05, 0.25, {"izq"}),
        (0.40, 0.60, {"centro"}),
        (0.75, 0.95, {"der"}),
    ],
)
def test_una_caja_por_zona(ancho, x1_frac, x2_frac, esperado):
    caja = [x1_frac * ancho, 100, x2_frac * ancho, 300]
    assert zonas_ocupadas(evento([obst(caja)], ancho=ancho), CONFIG) == esperado


def test_misma_caja_en_px_cambia_de_zona_segun_el_ancho():
    # x de 250 a 300 px: en 320 de ancho está a la derecha; en 640, en el centro.
    caja = [250, 100, 300, 200]
    assert zonas_ocupadas(evento([obst(caja)], ancho=320), CONFIG) == {"der"}
    assert zonas_ocupadas(evento([obst(caja)], ancho=640), CONFIG) == {"centro"}


# --- Cajas anchas y traslape mínimo ---------------------------------------------------


def test_caja_ancha_ocupa_dos_zonas():
    # 640 px: izq 0-211.2, centro 211.2-428.8. Caja 100-350: 44 % en izq, 56 % en centro.
    assert zonas_ocupadas(evento([obst([100, 0, 350, 480])]), CONFIG) == {"izq", "centro"}


def test_caja_que_cubre_toda_la_imagen_ocupa_las_tres():
    assert zonas_ocupadas(evento([obst([0, 0, 640, 480])]), CONFIG) == {"izq", "centro", "der"}


def test_caja_que_apenas_roza_otra_zona_no_la_ocupa():
    # Caja 120-230 (110 px): 19 px en el centro = 17 % >= 15 % -> ocupa el centro.
    assert zonas_ocupadas(evento([obst([120, 0, 230, 100])]), CONFIG) == {"izq", "centro"}
    # Caja 120-220 (100 px): 8.8 px en el centro = 8.8 % < 15 % -> solo izquierda.
    assert zonas_ocupadas(evento([obst([120, 0, 220, 100])]), CONFIG) == {"izq"}


def test_traslape_minimo_sale_de_la_config():
    caja = [120, 0, 220, 100]  # 8.8 % en el centro
    estricta = replace(CONFIG, traslape_minimo=0.05)
    assert zonas_ocupadas(evento([obst(caja)]), estricta) == {"izq", "centro"}


# --- Formato xywh ---------------------------------------------------------------------


def test_xywh_da_lo_mismo_que_xyxy():
    xyxy = [100, 50, 350, 400]
    xywh = [100, 50, 250, 350]
    a = zonas_ocupadas(evento([obst(xyxy)], formato="xyxy"), CONFIG)
    b = zonas_ocupadas(evento([obst(xywh)], formato="xywh"), CONFIG)
    assert a == b == {"izq", "centro"}


@pytest.mark.parametrize(
    ("caja", "esperado"),
    [
        ([10, 10, 60, 100], {"izq"}),  # x 10-70
        ([280, 10, 80, 100], {"centro"}),  # x 280-360
        ([500, 10, 120, 100], {"der"}),  # x 500-620
    ],
)
def test_xywh_por_zona(caja, esperado):
    assert zonas_ocupadas(evento([obst(caja)], formato="xywh"), CONFIG) == esperado


def test_caja_a_xyxy():
    assert caja_a_xyxy([1, 2, 3, 4], "xyxy") == (1, 2, 3, 4)
    assert caja_a_xyxy([1, 2, 3, 4], "xywh") == (1, 2, 4, 6)
    with pytest.raises(ValueError, match="bbox_format"):
        caja_a_xyxy([1, 2, 3, 4], "cxcywh")


# --- Filtros: clase y confianza --------------------------------------------------------


def test_clase_no_relevante_se_ignora():
    caja = [280, 0, 360, 480]
    assert zonas_ocupadas(evento([obst(caja, clase=CLASE_NO_RELEVANTE)]), CONFIG) == set()


def test_decide_con_class_id_no_con_class_name():
    ev = evento([obst([280, 0, 360, 480], clase=CLASE_NO_RELEVANTE)])
    ev["detections"][0]["class_name"] = "mochila"  # el nombre no cuenta
    assert zonas_ocupadas(ev, CONFIG) == set()


def test_confianza_baja_se_ignora_y_el_umbral_es_inclusivo():
    caja = [280, 0, 360, 480]
    umbral = CONFIG.umbral_confianza
    assert zonas_ocupadas(evento([obst(caja, conf=umbral - 0.01)]), CONFIG) == set()
    assert zonas_ocupadas(evento([obst(caja, conf=umbral)]), CONFIG) == {"centro"}


def test_varias_detecciones_se_juntan():
    dets = [
        obst([10, 0, 60, 100]),  # izq
        obst([500, 0, 620, 100]),  # der
        obst([280, 0, 360, 100], clase=CLASE_NO_RELEVANTE),  # ignorada
        obst([280, 0, 360, 100], conf=0.1),  # ignorada
    ]
    assert zonas_ocupadas(evento(dets), CONFIG) == {"izq", "der"}


# --- Casos borde y estados -------------------------------------------------------------


def test_sin_detecciones_no_hay_zonas():
    assert zonas_ocupadas(evento([]), CONFIG) == set()


def test_caja_pegada_al_borde_derecho():
    assert zonas_ocupadas(evento([obst([600, 0, 640, 100])]), CONFIG) == {"der"}


@pytest.mark.parametrize("archivo", ["stale.json", "fallido.json"])
def test_stale_y_error_no_son_via_libre(archivo):
    ev = json.loads((EJEMPLOS / archivo).read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="status"):
        zonas_ocupadas(ev, CONFIG)


def test_ejemplos_del_contrato():
    valido = json.loads((EJEMPLOS / "valido.json").read_text(encoding="utf-8"))
    # En los ejemplos del contrato lata = 0 y mochila = 1; con esas clases:
    # mochila 212-431 en 640 -> centro; lata 20-88.5 (conf 0.55) -> izquierda.
    con_clases_de_ejemplo = replace(CONFIG, clases_obstaculo=frozenset({0, 1}))
    assert zonas_ocupadas(valido, con_clases_de_ejemplo) == {"izq", "centro"}
    # Con las clases definitivas (T12, #32), los ids de ejemplo ya no son obstáculo.
    assert zonas_ocupadas(valido, CONFIG) == set()
    vacio = json.loads((EJEMPLOS / "vacio.json").read_text(encoding="utf-8"))
    assert zonas_ocupadas(vacio, CONFIG) == set()
