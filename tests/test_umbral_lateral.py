"""P5-22 parte 2 (C5): umbral lateral opcional, solo en config/vivo.yaml.

- Sin la clave, la política decide igual que antes: las corridas guardadas de S01 a S10 salen
  idénticas byte por byte, y `politica.yaml` y `expectativas.sha256` no cambian.
- Con `vivo.yaml` (0.25), un lado con una detección entre 0.25 y 0.5 queda "no comprobado
  libre" y no se gira hacia él. C5 pasa y C1, C3, C4 y C6 siguen pasando.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from control.__main__ import main as correr_control
from control.config import (
    RUTA_CONFIG_POLITICA,
    ErrorConfigPolitica,
    cargar_config_politica,
    cargar_politica_vivo,
    datos_politica_vivo,
    validar_config_politica,
)
from control.politica import ESTADO_INICIAL, decidir

RAIZ = Path(__file__).resolve().parents[1]
CONFIG = RAIZ / "config" / "control"
CASOS = RAIZ / "casos"
BASE = cargar_config_politica()
VIVO = cargar_politica_vivo()
CENTRO, IZQ, DER = [270.0, 220.0, 420.0, 360.0], [20.0, 40.0, 140.0, 350.0], [490, 30, 610, 340]

# Corridas guardadas (entrada de control → carpeta con lo que dejó). S01 a S08 de P5-14, S09 y S10
# del recorrido real y de la Mac, y S02 real.
CORRIDAS = {
    "S01-S08": ("resultados/p5-14/detector.jsonl", "resultados/p5-14/corrida"),
    "S09": ("resultados/recorrido-real/izq/detector.jsonl", "resultados/recorrido-real/izq"),
    "S10": ("resultados/recorrido-real/der/detector.jsonl", "resultados/recorrido-real/der"),
    "S02-real": (
        "resultados/recorrido-real/centro/detector.jsonl",
        "resultados/recorrido-real/centro",
    ),
    "S09-mac": ("resultados/p5-08-mac/izq/detector.jsonl", "resultados/p5-08-mac/izq"),
    "S10-mac": ("resultados/p5-08-mac/der/detector.jsonl", "resultados/p5-08-mac/der"),
}


def evento(*dets: tuple[int, float, list[float]]) -> dict:
    datos = json.loads((RAIZ / "config/contrato/ejemplos/vacio.json").read_text(encoding="utf-8"))
    datos["detections"] = [
        {"class_id": c, "class_name": "x", "confidence": conf, "bbox": list(caja)}
        for c, conf, caja in dets
    ]
    return datos


# -- la configuración ------------------------------------------------------------------
def test_politica_yaml_no_trae_la_clave():
    datos = yaml.safe_load(RUTA_CONFIG_POLITICA.read_text(encoding="utf-8"))
    assert "umbral_lateral" not in datos
    assert BASE.umbral_lateral is None
    assert BASE.umbral_lateral_efectivo == BASE.umbral_confianza == 0.5


def test_vivo_yaml_pone_0_25_y_nada_mas():
    assert VIVO.umbral_lateral == 0.25
    assert replace(VIVO, umbral_lateral=None) == BASE


@pytest.mark.parametrize("valor", [-0.1, 1.5, "0.3", True, 0.6])
def test_umbral_lateral_invalido(valor):
    datos = yaml.safe_load(RUTA_CONFIG_POLITICA.read_text(encoding="utf-8"))
    datos["umbral_lateral"] = valor
    with pytest.raises(ErrorConfigPolitica, match="umbral_lateral"):
        validar_config_politica(datos)


def test_vivo_no_puede_cambiar_valores_calificados(tmp_path):
    vivo = tmp_path / "vivo.yaml"
    vivo.write_text("politica:\n  umbral_confianza: 0.25\n", encoding="utf-8")
    with pytest.raises(ErrorConfigPolitica, match=r"politica.yaml"):
        cargar_politica_vivo(vivo)


def test_vivo_sin_seccion_politica_es_la_configuracion_base(tmp_path):
    vivo = tmp_path / "vivo.yaml"
    vivo.write_text("lazo:\n  ip: 127.0.0.1\n", encoding="utf-8")
    assert cargar_politica_vivo(vivo) == BASE


# -- decisiones con detecciones sintéticas ----------------------------------------------
def test_c5_lado_dudoso_y_el_otro_ocupado_frena():
    e = evento((41, 0.85, CENTRO), (39, 0.44, IZQ), (39, 0.63, DER))
    assert decidir(e, ESTADO_INICIAL, BASE)[0]["action"] == "GIRAR_IZQ"  # lo calificado
    comando, _ = decidir(e, ESTADO_INICIAL, VIVO)
    assert (comando["action"], comando["speed"], comando["steering"]) == ("STOP", 0, 0)
    assert "ningún lado libre" in comando["reason"]
    assert "No comprobado libre: la izquierda (class_id 39, confianza 0.44)" in comando["reason"]
    assert "umbral lateral 0.25" in comando["reason"]


def test_gira_hacia_el_lado_comprobado():
    e = evento((41, 0.85, CENTRO), (39, 0.30, IZQ))
    comando, _ = decidir(e, ESTADO_INICIAL, VIVO)
    assert comando["action"] == "GIRAR_DER"
    assert "No comprobado libre: la izquierda" in comando["reason"]


def test_debajo_del_umbral_lateral_no_cuenta():
    e = evento((41, 0.85, CENTRO), (39, 0.20, DER), (39, 0.70, IZQ))
    assert decidir(e, ESTADO_INICIAL, VIVO)[0]["action"] == "GIRAR_DER"


def test_el_centro_lo_sigue_decidiendo_umbral_confianza():
    # Centro con 0.44 y laterales dudosos: el centro está libre, así que avanza.
    e = evento((41, 0.44, CENTRO), (39, 0.30, IZQ), (39, 0.30, DER))
    assert decidir(e, ESTADO_INICIAL, VIVO)[0]["action"] == "AVANZAR"


def test_clase_que_no_es_obstaculo_no_cuenta():
    e = evento((41, 0.85, CENTRO), (0, 0.44, IZQ), (39, 0.63, DER))
    assert decidir(e, ESTADO_INICIAL, VIVO)[0]["action"] == "GIRAR_IZQ"


def test_histeresis_deja_de_girar_hacia_un_lado_dudoso():
    girando = {"nombre": "GIRANDO_IZQ", "esperando_libres": True, "libres_seguidos": 0}
    e = evento((39, 0.40, IZQ))
    assert decidir(e, girando, BASE)[0]["action"] == "GIRAR_IZQ"
    comando, estado = decidir(e, girando, VIVO)
    assert comando["action"] == "STOP"
    assert "No comprobado libre: la izquierda" in comando["reason"]
    assert estado["libres_seguidos"] == 1


@pytest.mark.parametrize(
    "dets",
    [
        [],
        [(41, 0.85, CENTRO), (39, 0.44, IZQ), (39, 0.63, DER)],
        [(41, 0.85, CENTRO), (39, 0.30, IZQ)],
        [(41, 0.49, CENTRO), (39, 0.26, DER)],
        [(39, 0.40, IZQ)],
    ],
)
@pytest.mark.parametrize(
    "estado",
    [
        ESTADO_INICIAL,
        {"nombre": "GIRANDO_IZQ", "esperando_libres": True, "libres_seguidos": 1},
        {"nombre": "GIRANDO_DER", "esperando_libres": True, "libres_seguidos": 0},
        {"nombre": "AVANZANDO", "esperando_libres": False, "libres_seguidos": 0},
    ],
)
def test_umbral_lateral_igual_al_central_no_cambia_nada(dets, estado):
    igual = replace(BASE, umbral_lateral=BASE.umbral_confianza)
    e = evento(*dets)
    assert decidir(e, copy.deepcopy(estado), igual) == decidir(e, copy.deepcopy(estado), BASE)


# -- lo calificado no cambia ------------------------------------------------------------
@pytest.mark.parametrize("nombre", sorted(CORRIDAS))
def test_corridas_s01_a_s10_identicas_byte_por_byte(nombre, tmp_path):
    entrada, guardada = (RAIZ / p for p in CORRIDAS[nombre])
    salida = tmp_path / nombre
    codigo = correr_control(
        ["--entrada", str(entrada), "--config", str(CONFIG), "--salida", str(salida)]
    )
    assert codigo == 0
    for archivo in ("comandos.jsonl", "decisiones.jsonl"):
        assert (salida / archivo).read_bytes() == (guardada / archivo).read_bytes(), archivo


def _comandos_con_vivo(tmp_path: Path) -> dict[str, list[tuple[dict, dict]]]:
    """Por corrida: pares (comando guardado, comando con vivo.yaml), línea por línea."""
    config = tmp_path / "config"
    config.mkdir()
    (config / "plazos.yaml").write_bytes((CONFIG / "plazos.yaml").read_bytes())
    (config / "politica.yaml").write_text(yaml.safe_dump(datos_politica_vivo()), encoding="utf-8")
    pares = {}
    for nombre, (entrada, guardada) in sorted(CORRIDAS.items()):
        salida = tmp_path / nombre
        correr_control(
            ["--entrada", str(RAIZ / entrada), "--config", str(config), "--salida", str(salida)]
        )
        antes = (RAIZ / guardada / "comandos.jsonl").read_text(encoding="utf-8").splitlines()
        despues = (salida / "comandos.jsonl").read_text(encoding="utf-8").splitlines()
        pares[nombre] = list(zip(map(json.loads, antes), map(json.loads, despues), strict=True))
    return pares


def test_con_vivo_solo_cambia_s05(tmp_path):
    """Línea completa, no solo la acción: fuera de S05 todo queda igual, y en S05 solo cambia
    lo que explica el umbral lateral."""
    cambios = {}
    for nombre, pares in _comandos_con_vivo(tmp_path).items():
        for antes, despues in pares:
            if antes != despues:
                campos = sorted(k for k in antes if antes[k] != despues[k])
                cambios[(nombre, antes["frame_id"])] = (campos, antes, despues)

    # Fuera de S05, ninguna línea cambia en ningún campo.
    assert {nombre for nombre, _ in cambios} == {"S01-S08"}
    assert all(frame.startswith("S05_") for _, frame in cambios)

    # S05_f0001: la única acción que cambia. Ya no gira hacia la botella de 0.44.
    campos, antes, despues = cambios.pop(("S01-S08", "S05_f0001"))
    assert campos == ["action", "reason", "speed", "state_after", "steering"]
    assert (antes["action"], antes["steering"]) == ("GIRAR_IZQ", -0.5)
    assert despues["action"] == "STOP"
    assert (despues["speed"], despues["steering"], despues["state_after"]) == (0, 0, "DETENIDO")
    assert (
        "No comprobado libre: la izquierda (class_id 39, confianza 0.439228)" in (despues["reason"])
    )

    # S05_f0002: llega DETENIDO en vez de GIRANDO_IZQ, consecuencia del cuadro anterior.
    campos, antes, despues = cambios.pop(("S01-S08", "S05_f0002"))
    assert campos == ["reason", "state_before"]
    assert (antes["state_before"], despues["state_before"]) == ("GIRANDO_IZQ", "DETENIDO")

    # El resto de S05: mismo STOP, misma velocidad y giro; solo el reason, que ya no dice que la
    # izquierda está libre.
    assert cambios, "se esperaban cuadros de S05 con solo el reason distinto"
    for (_, frame), (campos, antes, despues) in cambios.items():
        assert campos == ["reason"], frame
        assert antes["action"] == despues["action"] == "STOP", frame
        assert "la izquierda está libre" in antes["reason"], frame
        assert "No comprobado libre" in despues["reason"], frame


def test_expectativas_sin_cambios():
    for linea in (CASOS / "expectativas.sha256").read_text(encoding="utf-8").splitlines():
        if not linea.strip() or linea.startswith("#"):
            continue
        digesto, ruta = linea.split(maxsplit=1)
        ruta = ruta.lstrip("*")
        archivo = CASOS / ruta if (CASOS / ruta).exists() else RAIZ / ruta
        assert hashlib.sha256(archivo.read_bytes()).hexdigest() == digesto, ruta


# -- C5 con el runner ------------------------------------------------------------------
_spec = importlib.util.spec_from_file_location("runner_umbral_lateral", CASOS / "runner.py")
runner = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = runner
_spec.loader.exec_module(runner)


def test_runner_con_vivo_c5_pasa_y_c1_c3_c4_c6_siguen(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "plazos.yaml").write_bytes((CONFIG / "plazos.yaml").read_bytes())
    (config / "politica.yaml").write_text(yaml.safe_dump(datos_politica_vivo()), encoding="utf-8")
    salida = tmp_path / "salida"
    casos = ["C1", "C3", "C4", "C5", "C6"]
    assert runner.main([*casos, "--config", str(config), "--salida", str(salida)]) == 0
    for caso in casos:
        veredicto = json.loads((salida / caso / "veredicto.json").read_text(encoding="utf-8"))
        assert veredicto["pasa"], (caso, veredicto["motivos"])


def test_runner_sin_vivo_c5_sigue_fallando(tmp_path):
    assert runner.main(["C5", "--salida", str(tmp_path)]) == 1
