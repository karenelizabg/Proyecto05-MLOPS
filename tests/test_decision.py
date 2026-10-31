"""Pruebas de la decisión avanzar / girar / frenar (T09, #29, casos C1 a C5)."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from contrato import validar_comando, validar_evento
from control.adaptador_virtual import AdaptadorVirtual
from control.config import RAIZ, cargar_config_politica
from control.politica import (
    AVANZANDO,
    DETENIDO,
    ESTADO_INICIAL,
    GIRANDO_DER,
    GIRANDO_IZQ,
    NOMBRES_DE_ESTADO,
    decidir,
)

CONFIG = cargar_config_politica()
EJEMPLOS = RAIZ / "config" / "contrato" / "ejemplos"
# Una clase de obstáculo real de politica.yaml (T12, #32); así la prueba no depende del id.
OBSTACULO = min(CONFIG.clases_obstaculo)
NO_RELEVANTE = 7

# Cajas en una imagen de 640 px (izq 0-211.2, centro 211.2-428.8, der 428.8-640).
IZQ = [20, 100, 120, 400]
CENTRO = [260, 100, 380, 400]
CENTRO_CARGADO_IZQ = [215, 100, 300, 400]  # en el centro, pero su mitad cae a la izquierda
DER = [520, 100, 620, 400]


def evento(*cajas, clase=OBSTACULO, conf=0.9, t=400, ancho=640):
    ev = {
        "schema_version": "1",
        "run_id": "prueba-t09",
        "sequence_id": "S01",
        "frame_id": "S01_f0003",
        "t_capture_ms": t,
        "t_emit_ms": t + 30,
        "image_width": ancho,
        "image_height": 480,
        "model_sha256": "a" * 64,
        "config_sha256": "b" * 64,
        "status": "ok",
        "bbox_format": "xyxy",
        "bbox_unit": "px",
        "detections": [{"class_id": clase, "confidence": conf, "bbox": c} for c in cajas],
    }
    assert validar_evento(ev) == []
    return ev


def ejemplo(nombre):
    return json.loads((EJEMPLOS / nombre).read_text(encoding="utf-8"))


def comando_completo(comando, tmp_path):
    """Pasa el comando por el adaptador virtual (T02) y lo valida contra el contrato."""
    registrado = AdaptadorVirtual(tmp_path, validez_orden_ms=400).enviar(
        comando, ahora_ms=comando["t_decision_ms"] + 1
    )
    assert validar_comando(registrado) == [], validar_comando(registrado)
    return registrado


def es_stop(comando):
    return comando["action"] == "STOP" and comando["speed"] == 0 and comando["steering"] == 0


# --- C1: vía libre ---------------------------------------------------------------------


def test_c1_libre_avanza():
    comando, nuevo = decidir(evento(), dict(ESTADO_INICIAL), CONFIG)
    assert comando["action"] == "AVANZAR"
    assert comando["speed"] == CONFIG.velocidad_avance > 0
    assert comando["steering"] == 0
    assert (comando["state_before"], comando["state_after"]) == (DETENIDO, AVANZANDO)
    assert nuevo["nombre"] == AVANZANDO


def test_c1_clase_no_relevante_o_poca_confianza_no_estorban():
    for ev in (evento(CENTRO, clase=NO_RELEVANTE), evento(CENTRO, conf=0.1)):
        comando, _ = decidir(ev, dict(ESTADO_INICIAL), CONFIG)
        assert comando["action"] == "AVANZAR"


# --- C2: obstáculo al centro -----------------------------------------------------------


def test_c2_centro_con_lados_libres_gira_y_lo_explica():
    comando, nuevo = decidir(evento(CENTRO), {"nombre": AVANZANDO}, CONFIG)
    assert comando["action"] in {"GIRAR_IZQ", "GIRAR_DER"}
    assert "libre" in comando["reason"]
    assert f"class_id {OBSTACULO}" in comando["reason"]
    esperado = GIRANDO_IZQ if comando["action"] == "GIRAR_IZQ" else GIRANDO_DER
    assert comando["state_after"] == esperado
    assert nuevo["nombre"] == esperado


def test_c2_gira_al_lado_contrario_del_obstaculo():
    comando, _ = decidir(evento(CENTRO_CARGADO_IZQ), dict(ESTADO_INICIAL), CONFIG)
    assert comando["action"] == "GIRAR_DER"
    assert comando["steering"] == CONFIG.giro > 0


def test_c2_sin_permiso_de_girar_frena():
    sin_giro = replace(CONFIG, permitir_giro=False)
    comando, nuevo = decidir(evento(CENTRO), {"nombre": AVANZANDO}, sin_giro)
    assert es_stop(comando)
    assert "giro desactivado" in comando["reason"]
    assert (comando["state_before"], comando["state_after"]) == (AVANZANDO, DETENIDO)
    assert nuevo["nombre"] == DETENIDO


# --- C3 / C4: obstáculo a un lado ------------------------------------------------------


def test_c3_obstaculo_a_la_izquierda_avanza_recto():
    comando, _ = decidir(evento(IZQ), dict(ESTADO_INICIAL), CONFIG)
    assert comando["action"] == "AVANZAR"
    assert comando["steering"] == 0
    assert "la izquierda" in comando["reason"]


def test_c4_obstaculo_a_la_derecha_avanza_recto():
    comando, _ = decidir(evento(DER), dict(ESTADO_INICIAL), CONFIG)
    assert comando["action"] == "AVANZAR"
    assert comando["steering"] == 0
    assert "la derecha" in comando["reason"]


def test_c3_centro_e_izquierda_ocupados_nunca_gira_a_la_izquierda():
    comando, _ = decidir(evento(CENTRO, IZQ), dict(ESTADO_INICIAL), CONFIG)
    assert comando["action"] == "GIRAR_DER"
    assert comando["steering"] > 0
    assert "la derecha está libre" in comando["reason"]


def test_c4_centro_y_derecha_ocupados_nunca_gira_a_la_derecha():
    comando, _ = decidir(evento(CENTRO, DER), dict(ESTADO_INICIAL), CONFIG)
    assert comando["action"] == "GIRAR_IZQ"
    assert comando["steering"] < 0
    assert "la izquierda está libre" in comando["reason"]


def test_caja_ancha_que_tapa_centro_e_izquierda_gira_a_la_derecha():
    comando, _ = decidir(evento([0, 100, 400, 400]), dict(ESTADO_INICIAL), CONFIG)
    assert comando["action"] == "GIRAR_DER"


# --- C5: varios obstáculos sin zona libre ----------------------------------------------


def test_c5_todo_ocupado_frena():
    comando, nuevo = decidir(evento(IZQ, CENTRO, DER), {"nombre": AVANZANDO}, CONFIG)
    assert es_stop(comando)
    assert "ningún lado libre" in comando["reason"]
    assert nuevo["nombre"] == DETENIDO


def test_c5_una_caja_que_cubre_todo_frena():
    comando, _ = decidir(evento([0, 0, 640, 480]), dict(ESTADO_INICIAL), CONFIG)
    assert es_stop(comando)


# --- Pérdida de percepción: siempre STOP -----------------------------------------------


@pytest.mark.parametrize(
    ("archivo", "texto"), [("stale.json", "stale"), ("fallido.json", "Error del detector")]
)
def test_stale_y_error_frenan(archivo, texto):
    ev = ejemplo(archivo)
    comando, nuevo = decidir(ev, {"nombre": AVANZANDO}, CONFIG)
    assert es_stop(comando)
    assert texto in comando["reason"]
    assert comando["frame_id"] == ev["frame_id"]
    assert nuevo["nombre"] == DETENIDO


def test_version_desconocida_frena():
    ev = evento()
    ev["schema_version"] = "2"
    comando, _ = decidir(ev, {"nombre": AVANZANDO}, CONFIG)
    assert es_stop(comando)
    assert "schema_version" in comando["reason"]


def test_status_desconocido_frena():
    ev = evento()
    ev["status"] = "quiza"
    assert es_stop(decidir(ev, dict(ESTADO_INICIAL), CONFIG)[0])


def test_evento_fuera_de_contrato_frena():
    ev = evento(CENTRO)
    ev["detections"][0]["bbox"] = [300, 100, 900, 400]  # se sale de la imagen
    comando, _ = decidir(ev, {"nombre": AVANZANDO}, CONFIG)
    assert es_stop(comando)
    assert "fuera de contrato" in comando["reason"]


# --- Forma del comando -----------------------------------------------------------------


def test_campos_del_comando_y_reloj():
    ev = evento(t=1234.5)
    comando, _ = decidir(ev, dict(ESTADO_INICIAL), CONFIG)
    assert comando["schema_version"] == "1"
    assert comando["run_id"] == ev["run_id"]
    assert comando["frame_id"] == ev["frame_id"]
    assert comando["event"] == "frame"
    assert comando["t_decision_ms"] == 1234.5  # no lee el reloj: usa t_capture_ms


def test_es_pura_no_modifica_evento_ni_estado():
    ev = evento(CENTRO)
    copia = json.loads(json.dumps(ev))
    estado = dict(ESTADO_INICIAL)
    primero = decidir(ev, estado, CONFIG)
    assert decidir(ev, estado, CONFIG) == primero
    assert ev == copia
    assert estado == {"nombre": DETENIDO}


# --- Estado: diccionario con "nombre" (acuerdo del grupo B) ---------------------------


def test_estado_inicial():
    assert ESTADO_INICIAL == {"nombre": "DETENIDO"}
    assert NOMBRES_DE_ESTADO == ("DETENIDO", "AVANZANDO", "GIRANDO_IZQ", "GIRANDO_DER")


@pytest.mark.parametrize(
    ("ev", "accion", "nombre"),
    [
        (evento(), "AVANZAR", "AVANZANDO"),
        (evento(CENTRO, DER), "GIRAR_IZQ", "GIRANDO_IZQ"),
        (evento(CENTRO, IZQ), "GIRAR_DER", "GIRANDO_DER"),
        (evento(IZQ, CENTRO, DER), "STOP", "DETENIDO"),
    ],
)
def test_cada_accion_lleva_a_su_estado(ev, accion, nombre):
    comando, nuevo = decidir(ev, dict(ESTADO_INICIAL), CONFIG)
    assert comando["action"] == accion
    assert comando["state_after"] == nuevo["nombre"] == nombre
    assert nuevo["nombre"] in NOMBRES_DE_ESTADO


def test_state_before_sale_del_nombre_del_estado():
    for nombre in NOMBRES_DE_ESTADO:
        comando, _ = decidir(evento(), {"nombre": nombre}, CONFIG)
        assert comando["state_before"] == nombre


def test_estado_con_mas_datos_los_conserva_y_no_lo_modifica():
    estado = {"nombre": "AVANZANDO", "otro_dato": [1, 2]}
    comando, nuevo = decidir(evento(IZQ, CENTRO, DER), estado, CONFIG)
    assert comando["state_before"] == "AVANZANDO"
    assert nuevo["nombre"] == "DETENIDO"
    assert nuevo["otro_dato"] == [1, 2]
    assert estado == {"nombre": "AVANZANDO", "otro_dato": [1, 2]}  # el original no cambia
    assert nuevo is not estado


def test_estado_sin_nombre_se_toma_como_detenido():
    comando, nuevo = decidir(evento(), {}, CONFIG)
    assert comando["state_before"] == "DETENIDO"
    assert nuevo["nombre"] == "AVANZANDO"


@pytest.mark.parametrize(
    "ev",
    [
        evento(),
        evento(IZQ),
        evento(DER),
        evento(CENTRO),
        evento(CENTRO, IZQ),
        evento(CENTRO, DER),
        evento(IZQ, CENTRO, DER),
        ejemplo("valido.json"),
        ejemplo("vacio.json"),
        ejemplo("stale.json"),
        ejemplo("fallido.json"),
    ],
)
def test_todo_comando_cumple_el_contrato_tras_el_adaptador(ev, tmp_path):
    comando, _ = decidir(ev, dict(ESTADO_INICIAL), CONFIG)
    comando_completo(comando, tmp_path)
