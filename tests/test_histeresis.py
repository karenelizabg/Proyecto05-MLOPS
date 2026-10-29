"""Pruebas de la histéresis libre -> bloqueo -> libre (T11, #31, caso C7)."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from contrato import validar_comando, validar_evento
from control.adaptador_virtual import AdaptadorVirtual
from control.config import RAIZ, cargar_config_politica
from control.politica import ESTADO_INICIAL, decidir

# Sin giro, un obstáculo al centro siempre es STOP (como en la secuencia del issue).
CONFIG = replace(cargar_config_politica(), permitir_giro=False)
# Una clase de obstáculo real de politica.yaml (T12, #32); así la prueba no depende del id.
OBSTACULO = min(CONFIG.clases_obstaculo)
N = CONFIG.cuadros_libres_para_reanudar
EJEMPLOS = RAIZ / "config" / "contrato" / "ejemplos"
CENTRO = [260, 100, 380, 400]  # en una imagen de 640 px
IZQ = [20, 100, 120, 400]
DER = [520, 100, 620, 400]


def evento(i, *cajas, conf=0.9):
    ev = {
        "schema_version": "1",
        "run_id": "prueba-t11",
        "sequence_id": "S07",
        "frame_id": f"S07_f{i:04d}",
        "t_capture_ms": i * 200,
        "t_emit_ms": i * 200 + 30,
        "image_width": 640,
        "image_height": 480,
        "model_sha256": "a" * 64,
        "config_sha256": "b" * 64,
        "status": "ok",
        "bbox_format": "xyxy",
        "bbox_unit": "px",
        "detections": [{"class_id": OBSTACULO, "confidence": conf, "bbox": c} for c in cajas],
    }
    assert validar_evento(ev) == []
    return ev


def correr(secuencia, config=CONFIG, estado=None):
    """Pasa una lista de cuadros por la política. 'L' = libre, 'B' = centro bloqueado."""
    estado = dict(ESTADO_INICIAL) if estado is None else estado
    comandos = []
    for i, cuadro in enumerate(secuencia, start=1):
        if isinstance(cuadro, dict):
            ev = cuadro
        else:
            ev = evento(i) if cuadro == "L" else evento(i, CENTRO)
        comando, estado = decidir(ev, estado, config)
        comandos.append(comando)
    return comandos, estado


def acciones(comandos):
    return [c["action"] for c in comandos]


# --- Secuencia del issue ---------------------------------------------------------------


def test_secuencia_libre_bloqueo_libre():
    # 3 libres, 4 bloqueados, 1 libre, 1 bloqueado, N libres.
    secuencia = ["L"] * 3 + ["B"] * 4 + ["L"] + ["B"] + ["L"] * N
    comandos, estado = correr(secuencia)

    assert acciones(comandos[:3]) == ["AVANZAR"] * 3  # libres: avanza
    assert acciones(comandos[3:7]) == ["STOP"] * 4  # bloqueo: frena al primer cuadro
    assert comandos[7]["action"] == "STOP"  # un solo libre en medio no reanuda
    assert "esperando_cuadros_libres 1/" in comandos[7]["reason"]
    assert comandos[8]["action"] == "STOP"  # bloqueo otra vez: la racha se corta
    assert "esperando_cuadros_libres 0/" in comandos[8]["reason"]

    finales = comandos[9:]
    assert acciones(finales) == ["STOP"] * (N - 1) + ["AVANZAR"]  # reanuda en el N-ésimo
    for k, comando in enumerate(finales[:-1], start=1):
        assert f"esperando_cuadros_libres {k}/{N}" in comando["reason"]
    assert f"Reanuda tras {N}/{N}" in finales[-1]["reason"]
    assert estado["nombre"] == "AVANZANDO"
    assert estado["esperando_libres"] is False


def test_frena_en_el_primer_cuadro_bloqueado():
    comandos, estado = correr(["L", "B"])
    assert acciones(comandos) == ["AVANZAR", "STOP"]
    assert comandos[1]["state_before"] == "AVANZANDO"
    assert comandos[1]["state_after"] == "DETENIDO"
    assert estado == {"nombre": "DETENIDO", "esperando_libres": True, "libres_seguidos": 0}


def test_state_before_y_after_reflejan_la_espera():
    comandos, _ = correr(["B"] + ["L"] * N)
    # Mientras espera: DETENIDO -> DETENIDO. Al reanudar: DETENIDO -> AVANZANDO.
    for comando in comandos[:-1]:
        assert (comando["state_before"], comando["state_after"]) == ("DETENIDO", "DETENIDO")
    assert (comandos[-1]["state_before"], comandos[-1]["state_after"]) == (
        "DETENIDO",
        "AVANZANDO",
    )


def test_contador_en_el_estado():
    _, estado = correr(["B", "L"])
    assert estado["libres_seguidos"] == 1
    assert estado["esperando_libres"] is True
    _, estado = correr(["B", "L", "B"])
    assert estado["libres_seguidos"] == 0


def test_al_reanudar_un_bloqueo_nuevo_vuelve_a_esperar():
    comandos, _ = correr(["B"] + ["L"] * N + ["B", "L"])
    assert acciones(comandos[-2:]) == ["STOP", "STOP"]
    assert "esperando_cuadros_libres 1/" in comandos[-1]["reason"]


# --- N sale de la config ---------------------------------------------------------------


@pytest.mark.parametrize("n", [1, 2, 5])
def test_n_sale_de_la_config(n):
    config = replace(CONFIG, cuadros_libres_para_reanudar=n)
    comandos, _ = correr(["B"] + ["L"] * n, config)
    assert acciones(comandos[1:]) == ["STOP"] * (n - 1) + ["AVANZAR"]


def test_arranque_sin_bloqueo_previo_no_espera():
    # La histéresis aplica después de un STOP por obstáculo, no al arrancar.
    comandos, _ = correr(["L"])
    assert acciones(comandos) == ["AVANZAR"]


# --- Interacción con el resto de la política -------------------------------------------


def test_mientras_espera_no_gira_aunque_haya_lado_libre():
    con_giro = replace(CONFIG, permitir_giro=True)
    # Todo ocupado -> STOP; luego centro ocupado con lados libres: sigue en STOP, no gira.
    secuencia = [evento(1, IZQ, CENTRO, DER), evento(2, CENTRO)]
    comandos, estado = correr(secuencia, con_giro)
    assert acciones(comandos) == ["STOP", "STOP"]
    assert "esperando_cuadros_libres 0/" in comandos[1]["reason"]
    assert estado["libres_seguidos"] == 0


# --- Espera después de un giro (C7 con un lado libre) -----------------------------------
# La caja CENTRO cae justo a la mitad: con los dos lados libres desempata hacia la izquierda.


def test_tras_un_giro_un_cuadro_libre_no_reanuda():
    con_giro = replace(CONFIG, permitir_giro=True)
    # libre -> bloqueo con un lado libre -> un libre -> bloqueo -> N libres
    secuencia = [evento(1), evento(2, CENTRO, DER), evento(3), evento(4, CENTRO)]
    secuencia += [evento(i) for i in range(5, 5 + N)]
    comandos, estado = correr(secuencia, con_giro)

    assert acciones(comandos[:2]) == ["AVANZAR", "GIRAR_IZQ"]  # gira hacia el lado libre
    assert comandos[2]["action"] == "STOP"  # el libre suelto no hace avanzar
    assert "esperando_cuadros_libres 1/" in comandos[2]["reason"]
    assert comandos[3]["action"] == "STOP"  # bloqueo otra vez: la racha se corta
    assert "esperando_cuadros_libres 0/" in comandos[3]["reason"]
    finales = comandos[4:]
    assert acciones(finales) == ["STOP"] * (N - 1) + ["AVANZAR"]  # reanuda en el N-ésimo
    assert finales[-1]["reason"].startswith(f"Reanuda tras {N}/{N}")
    assert estado["esperando_libres"] is False


def test_un_desvio_de_varios_cuadros_sigue_girando():
    con_giro = replace(CONFIG, permitir_giro=True)
    comandos, estado = correr(["L", "B", "B", "B"], con_giro)
    assert acciones(comandos) == ["AVANZAR"] + ["GIRAR_IZQ"] * 3
    assert estado["esperando_libres"] is True


@pytest.mark.parametrize("n", [2, 5])
def test_tras_un_giro_n_sale_de_la_config(n):
    config = replace(CONFIG, permitir_giro=True, cuadros_libres_para_reanudar=n)
    comandos, _ = correr(["L", "B"] + ["L"] * n, config)
    assert acciones(comandos) == ["AVANZAR", "GIRAR_IZQ"] + ["STOP"] * (n - 1) + ["AVANZAR"]


def test_obstaculo_con_poca_confianza_cuenta_como_libre():
    secuencia = [evento(1, CENTRO)] + [evento(i, CENTRO, conf=0.1) for i in range(2, N + 2)]
    comandos, _ = correr(secuencia)
    assert acciones(comandos) == ["STOP"] * N + ["AVANZAR"]


@pytest.mark.parametrize("archivo", ["stale.json", "fallido.json"])
def test_perdida_de_percepcion_corta_la_racha(archivo):
    falla = json.loads((EJEMPLOS / archivo).read_text(encoding="utf-8"))
    comandos, estado = correr(["B", "L", falla])
    assert comandos[-1]["action"] == "STOP"
    assert estado["libres_seguidos"] == 0
    assert estado["esperando_libres"] is True


def test_es_pura_no_modifica_el_estado_recibido():
    estado = {"nombre": "DETENIDO", "esperando_libres": True, "libres_seguidos": 1}
    copia = dict(estado)
    decidir(evento(1), estado, CONFIG)
    assert estado == copia


def test_todos_los_comandos_cumplen_el_contrato(tmp_path):
    comandos, _ = correr(["L", "B", "L", "B"] + ["L"] * N)
    adaptador = AdaptadorVirtual(tmp_path, validez_orden_ms=400)
    for comando in comandos:
        registrado = adaptador.enviar(comando, ahora_ms=comando["t_decision_ms"] + 1)
        assert validar_comando(registrado) == []
