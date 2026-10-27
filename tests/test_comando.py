import copy
import json
import math
from pathlib import Path

import pytest

from contrato import validar_comando

EJEMPLOS = Path(__file__).resolve().parents[1] / "config" / "contrato" / "ejemplos_comando"

CAMPOS_OBLIGATORIOS = [
    "schema_version",
    "run_id",
    "frame_id",
    "event",
    "state_before",
    "state_after",
    "action",
    "reason",
    "speed",
    "steering",
    "t_decision_ms",
    "t_command_ms",
    "valid_until_ms",
    "received",
]


def cargar(nombre: str) -> dict:
    return json.loads((EJEMPLOS / nombre).read_text(encoding="utf-8"))


def mutar(nombre: str, cambios: dict | None = None, quitar: tuple[str, ...] = ()) -> dict:
    comando = copy.deepcopy(cargar(nombre))
    comando.update(cambios or {})
    for campo in quitar:
        comando.pop(campo)
    return comando


# --- ejemplos ---------------------------------------------------------------


@pytest.mark.parametrize("nombre", ["avanzar.json", "stop.json", "reloj.json"])
def test_los_ejemplos_cumplen_el_contrato(nombre):
    assert validar_comando(cargar(nombre)) == []


def test_stop_lleva_velocidad_y_direccion_cero():
    for nombre in ["stop.json", "reloj.json"]:
        comando = cargar(nombre)
        assert comando["action"] == "STOP"
        assert comando["speed"] == 0
        assert comando["steering"] == 0


def test_reloj_no_trae_cuadro():
    comando = cargar("reloj.json")
    assert comando["event"] == "clock"
    assert comando["frame_id"] is None


# --- comandos válidos que no están en los ejemplos --------------------------


VALIDOS = {
    "stop con velocidad 0.0": mutar("stop.json", {"speed": 0.0}),
    "girar a la izquierda": mutar("avanzar.json", {"action": "GIRAR_IZQ", "steering": -1}),
    "girar a la derecha": mutar("avanzar.json", {"action": "GIRAR_DER", "steering": 1}),
    "emergencia sin cuadro": mutar("reloj.json", {"event": "emergency"}),
    "rearme con cuadro": mutar("avanzar.json", {"event": "rearm"}),
    "apagado sin cuadro": mutar("reloj.json", {"event": "shutdown"}),
    "no recibido": mutar("avanzar.json", {"received": False}),
    "tiempos iguales": mutar(
        "avanzar.json", {"t_decision_ms": 50, "t_command_ms": 50, "valid_until_ms": 50}
    ),
}


@pytest.mark.parametrize("nombre", VALIDOS)
def test_comando_valido_se_acepta(nombre):
    assert validar_comando(VALIDOS[nombre]) == []


# --- comandos inválidos -----------------------------------------------------


@pytest.mark.parametrize("campo", CAMPOS_OBLIGATORIOS)
def test_falta_un_campo_obligatorio(campo):
    assert validar_comando(mutar("avanzar.json", quitar=(campo,)))


INVALIDOS = {
    "version distinta": mutar("avanzar.json", {"schema_version": "2"}),
    "version como numero": mutar("avanzar.json", {"schema_version": 1}),
    "campo extra": mutar("avanzar.json", {"motor_pwm": 120}),
    "run_id con espacios": mutar("avanzar.json", {"run_id": "ejemplo 01"}),
    "frame_id con espacios": mutar("avanzar.json", {"frame_id": "S01 f0001"}),
    "event desconocido": mutar("avanzar.json", {"event": "timer"}),
    "action desconocida": mutar("avanzar.json", {"action": "RETROCEDER"}),
    "action en minusculas": mutar("avanzar.json", {"action": "avanzar"}),
    "estado vacio": mutar("avanzar.json", {"state_before": ""}),
    "estado null": mutar("avanzar.json", {"state_after": None}),
    "reason vacia": mutar("avanzar.json", {"reason": ""}),
    "stop con velocidad": mutar("stop.json", {"speed": 0.3}),
    "reloj stop con velocidad": mutar("reloj.json", {"speed": 1}),
    "stop con direccion": mutar("stop.json", {"steering": 0.3}),
    "avanzar con velocidad cero": mutar("avanzar.json", {"speed": 0}),
    "girar a la izquierda hacia la derecha": mutar(
        "avanzar.json", {"action": "GIRAR_IZQ", "steering": 0.5}
    ),
    "girar a la izquierda recto": mutar("avanzar.json", {"action": "GIRAR_IZQ", "steering": 0}),
    "girar a la derecha hacia la izquierda": mutar(
        "avanzar.json", {"action": "GIRAR_DER", "steering": -0.5}
    ),
    "girar a la derecha recto": mutar("avanzar.json", {"action": "GIRAR_DER", "steering": 0}),
    "frame sin frame_id": mutar("avanzar.json", {"frame_id": None}),
    "reloj con frame_id": mutar("reloj.json", {"frame_id": "S02_f0005"}),
    "velocidad negativa": mutar("avanzar.json", {"speed": -0.1}),
    "velocidad mayor que 1": mutar("avanzar.json", {"speed": 1.5}),
    "velocidad como texto": mutar("avanzar.json", {"speed": "0.5"}),
    "direccion menor que -1": mutar("avanzar.json", {"steering": -1.01}),
    "direccion mayor que 1": mutar("avanzar.json", {"steering": 2}),
    "tiempo negativo": mutar("avanzar.json", {"t_decision_ms": -1}),
    "comando anterior a la decision": mutar(
        "avanzar.json", {"t_decision_ms": 100, "t_command_ms": 90, "valid_until_ms": 300}
    ),
    "vence antes de enviarse": mutar(
        "avanzar.json", {"t_decision_ms": 100, "t_command_ms": 110, "valid_until_ms": 105}
    ),
    "received como texto": mutar("avanzar.json", {"received": "true"}),
    "received como numero": mutar("avanzar.json", {"received": 1}),
}


@pytest.mark.parametrize("nombre", INVALIDOS)
def test_comando_invalido_se_rechaza(nombre):
    assert validar_comando(INVALIDOS[nombre])


def test_el_error_dice_que_campo_falla():
    errores = validar_comando(mutar("stop.json", {"speed": 0.3}))
    assert any(e.startswith("speed:") for e in errores)


@pytest.mark.parametrize(
    ("accion", "direccion"), [("GIRAR_IZQ", 0.5), ("GIRAR_DER", -0.5), ("STOP", 0.3)]
)
def test_direccion_que_no_coincide_con_la_accion(accion, direccion):
    """C4: el giro y su dirección deben coincidir; STOP va recto."""
    velocidad = 0 if accion == "STOP" else 0.5
    comando = mutar("avanzar.json", {"action": accion, "speed": velocidad, "steering": direccion})
    assert any(e.startswith("steering:") for e in validar_comando(comando))


def test_avanzar_sin_velocidad():
    """C1: AVANZAR con speed=0 no mueve el auto."""
    errores = validar_comando(mutar("avanzar.json", {"speed": 0}))
    assert any(e.startswith("speed:") for e in errores)


def test_lo_que_no_es_un_objeto_se_rechaza():
    assert validar_comando([]) and validar_comando(None)


def test_un_evento_de_percepcion_no_es_un_comando():
    percepcion = Path(__file__).resolve().parents[1] / "config" / "contrato" / "ejemplos"
    evento = json.loads((percepcion / "valido.json").read_text(encoding="utf-8"))
    assert validar_comando(evento)


# --- números no finitos ------------------------------------------------------


@pytest.mark.parametrize("valor", [math.nan, math.inf, -math.inf], ids=["nan", "inf", "-inf"])
@pytest.mark.parametrize(
    "campo", ["speed", "steering", "t_decision_ms", "t_command_ms", "valid_until_ms"]
)
def test_nan_e_infinito_se_rechazan(campo, valor):
    """NaN pasa los rangos del esquema (toda comparación con NaN es falsa); se revisa aparte."""
    errores = validar_comando(mutar("avanzar.json", {campo: valor}))
    assert f"{campo}: debe ser un número finito" in errores


def test_nan_se_rechaza_tambien_en_un_stop():
    errores = validar_comando(mutar("stop.json", {"steering": math.nan}))
    assert errores == ["steering: debe ser un número finito"]
