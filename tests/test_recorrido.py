"""T16 · Recorrido de punta a punta: salida del detector → contrato → control → comando.

Mientras no llegue la salida real del detector de A (P5-05), las secuencias se arman con el formato
exacto del contrato y anchos de cámara reales, y pasan por los mismos comandos del recorrido real:
`python -m contrato` y `python -m control`. Ver docs/recorrido-real.md.
"""

import json
from pathlib import Path

import pytest

from contrato.__main__ import main as validar
from control.__main__ import main as correr
from control.config import cargar_config_politica
from control.politica import decidir
from control.traza import main as traza

RAIZ = Path(__file__).resolve().parents[1]
CONFIG = RAIZ / "config" / "control"
POLITICA = cargar_config_politica(CONFIG / "politica.yaml")
FLUJO = RAIZ / "config" / "contrato" / "ejemplos" / "flujo.jsonl"
BASE = json.loads((RAIZ / "config" / "contrato" / "ejemplos" / "valido.json").read_text("utf-8"))

# Resoluciones del OV2640 de la ESP32-CAM: QVGA, VGA y SVGA.
ANCHOS = [320, 640, 800]
# Fracciones del ancho [x1, x2] de un obstáculo cargado a cada lado. Con la política actual, solo
# un obstáculo que toca el centro da comandos opuestos: uno solo de lado da AVANZAR en los dos.
EN_EL_CENTRO = {"izq": (0.36, 0.48), "der": (0.52, 0.64)}
DE_LADO_Y_CENTRO = {"izq": (0.05, 0.50), "der": (0.50, 0.95)}
SOLO_DE_LADO = {"izq": (0.05, 0.25), "der": (0.75, 0.95)}
ESPEJO = {"GIRAR_IZQ": "GIRAR_DER", "GIRAR_DER": "GIRAR_IZQ", "AVANZAR": "AVANZAR", "STOP": "STOP"}
TAZA = 41  # cup: una de las clases_obstaculo de config/control/politica.yaml


def secuencia(
    sequence_id: str, ancho: int, fracciones: tuple[float, float], formato: str = "xyxy"
) -> list[dict]:
    """Un cuadro libre y luego cinco con el obstáculo, a 5 fps, como los emitiría `infer`."""
    alto = ancho * 3 // 4
    x1, x2 = fracciones[0] * ancho, fracciones[1] * ancho
    y1, y2 = 0.3 * alto, 0.9 * alto
    bbox = [x1, y1, x2, y2] if formato == "xyxy" else [x1, y1, x2 - x1, y2 - y1]
    eventos = []
    for i in range(6):
        detecciones = [] if i == 0 else [{"class_id": TAZA, "confidence": 0.9, "bbox": bbox}]
        eventos.append(
            {
                **BASE,
                "run_id": f"recorrido-{sequence_id}",
                "sequence_id": sequence_id,
                "frame_id": f"{sequence_id}_f{i:04d}",
                "t_capture_ms": 200 * i,
                "t_emit_ms": 200 * i + 40,
                "image_width": ancho,
                "image_height": alto,
                "bbox_format": formato,
                "detections": detecciones,
            }
        )
    return eventos


def recorrido(carpeta: Path, eventos: list[dict]) -> list[dict]:
    """Los dos pasos del recorrido real. Devuelve los comandos de los cuadros con obstáculo."""
    carpeta.mkdir()
    entrada = carpeta / "detector.jsonl"
    entrada.write_text("".join(json.dumps(e) + "\n" for e in eventos), encoding="utf-8")
    assert validar([str(entrada)]) == 0
    salida = carpeta / "salida"
    assert (
        correr(["--entrada", str(entrada), "--config", str(CONFIG), "--salida", str(salida)]) == 0
    )
    comandos = [
        json.loads(linea) for linea in (salida / "comandos.jsonl").read_text("utf-8").splitlines()
    ]
    return [c for c in comandos if c["event"] == "frame" and not c["frame_id"].endswith("_f0000")]


def espejo(evento: dict) -> dict:
    """El mismo cuadro visto en un espejo: x pasa a ancho - x."""
    ancho = evento["image_width"]
    reflejadas = []
    for det in evento["detections"]:
        x1, y1, x2, y2 = det["bbox"]
        reflejadas.append({**det, "bbox": [ancho - x2, y1, ancho - x1, y2]})
    return {**evento, "detections": reflejadas}


# --- izquierda y derecha dan comandos opuestos ------------------------------------


@pytest.mark.parametrize("formato", ["xyxy", "xywh"])
@pytest.mark.parametrize("ancho", ANCHOS)
@pytest.mark.parametrize("forma", [EN_EL_CENTRO, DE_LADO_Y_CENTRO], ids=["centro", "lado_y_centro"])
def test_izquierda_y_derecha_dan_comandos_opuestos(tmp_path, forma, ancho, formato):
    izq = recorrido(tmp_path / "izq", secuencia("S03", ancho, forma["izq"], formato))
    der = recorrido(tmp_path / "der", secuencia("S04", ancho, forma["der"], formato))

    assert {c["action"] for c in izq} == {"GIRAR_DER"}
    assert {c["action"] for c in der} == {"GIRAR_IZQ"}
    assert all(c["steering"] > 0 for c in izq)
    assert all(c["steering"] < 0 for c in der)


@pytest.mark.parametrize("ancho", ANCHOS)
def test_un_obstaculo_solo_de_lado_no_da_comandos_opuestos(tmp_path, ancho):
    """Por eso las secuencias del recorrido real deben tener el obstáculo tocando el centro."""
    izq = recorrido(tmp_path / "izq", secuencia("S03", ancho, SOLO_DE_LADO["izq"]))
    der = recorrido(tmp_path / "der", secuencia("S04", ancho, SOLO_DE_LADO["der"]))
    assert {c["action"] for c in izq} == {c["action"] for c in der} == {"AVANZAR"}


@pytest.mark.parametrize("ancho", ANCHOS)
def test_el_espejo_de_un_cuadro_invierte_el_giro(ancho):
    """Si x estuviera al revés, el carrito giraría hacia el obstáculo (C3, C4)."""
    for inicio in range(0, 90, 5):
        for largo in (5, 15, 30, 45):
            fin = inicio + largo
            if fin > 100 or inicio + fin == 100:
                continue  # fuera de la imagen, o justo a la mitad (empate: gira a la izquierda)
            evento = secuencia("S03", ancho, (inicio / 100, fin / 100))[1]
            comando, _ = decidir(evento, {"nombre": "AVANZANDO"}, POLITICA)
            reflejado, _ = decidir(espejo(evento), {"nombre": "AVANZANDO"}, POLITICA)
            assert reflejado["action"] == ESPEJO[comando["action"]], (inicio, fin)
            assert reflejado["steering"] == -comando["steering"], (inicio, fin)


# --- seguir un cuadro de punta a punta ---------------------------------------------


@pytest.fixture
def corrida(tmp_path):
    """Corre `flujo.jsonl` con la mochila (1) del ejemplo del contrato cambiada por la taza."""
    eventos = [json.loads(linea) for linea in FLUJO.read_text(encoding="utf-8").splitlines()]
    for evento in eventos:
        for deteccion in evento.get("detections") or []:
            if deteccion["class_id"] == 1:
                deteccion.update(class_id=TAZA, class_name="cup")
    entrada = tmp_path / "flujo.jsonl"
    entrada.write_text("".join(json.dumps(e) + "\n" for e in eventos), encoding="utf-8")
    salida = tmp_path / "salida"
    argumentos = ["--entrada", str(entrada), "--config", str(CONFIG), "--salida", str(salida)]
    assert correr(argumentos) == 0
    return salida


def test_la_traza_sigue_cada_cuadro_hasta_su_comando(corrida, capsys):
    assert traza(["--salida", str(corrida)]) == 0
    texto = capsys.readouterr().out
    for linea in FLUJO.read_text(encoding="utf-8").splitlines():
        frame_id = json.loads(linea)["frame_id"]
        bloque = texto.split(frame_id, 1)[1].split("\n\n", 1)[0]
        assert "decisión:" in bloque
        assert "comando:" in bloque
    assert "shutdown" in texto
    assert "Acciones por cuadro: AVANZAR 1, GIRAR_IZQ 2, STOP 2" in texto


def test_la_traza_de_un_cuadro_une_deteccion_decision_y_comando(corrida, capsys):
    assert traza(["--salida", str(corrida), "--frame-id", "S02_f0002"]) == 0
    texto = capsys.readouterr().out
    assert texto.count("S02_f0") == 1
    assert "bbox [212.0, 148.5, 431.0, 452.0] -> centro" in texto
    assert "AVANZANDO -> GIRANDO_IZQ" in texto
    assert "comando: GIRAR_IZQ · speed 0.4 · steering -0.5" in texto


def test_la_traza_marca_lo_que_no_cuenta_como_obstaculo(tmp_path, capsys):
    evento = {**BASE, "detections": [{**BASE["detections"][0], "confidence": 0.2}]}
    entrada = tmp_path / "e.jsonl"
    entrada.write_text(json.dumps(evento) + "\n", encoding="utf-8")
    salida = tmp_path / "s"
    assert correr(["--entrada", str(entrada), "--salida", str(salida)]) == 0
    assert traza(["--salida", str(salida)]) == 0
    assert "-> no cuenta (clase o confianza)" in capsys.readouterr().out


def test_un_cuadro_sin_comando_sale_1(corrida, capsys):
    registro = corrida / "comandos.jsonl"
    lineas = registro.read_text(encoding="utf-8").splitlines()
    registro.write_text("\n".join(lineas[1:]) + "\n", encoding="utf-8")
    assert traza(["--salida", str(corrida)]) == 1
    texto = capsys.readouterr().out
    assert "FALTA el comando" in texto
    assert "Cuadros sin decisión o sin comando: S02_f0001" in texto


def test_un_frame_id_que_no_esta_sale_1(corrida, capsys):
    assert traza(["--salida", str(corrida), "--frame-id", "no_existe"]) == 1
    assert "no_existe: no está en detecciones.jsonl" in capsys.readouterr().out


def test_una_carpeta_sin_corrida_sale_2(tmp_path):
    assert traza(["--salida", str(tmp_path / "vacia")]) == 2
