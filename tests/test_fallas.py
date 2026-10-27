"""T04 · Fallas del detector y de la política terminan en STOP (C9).

Las pruebas revisan lo que queda en comandos.jsonl y errores.jsonl, no lo que se imprime.
"""

import json
from pathlib import Path

import pytest
import yaml

from contrato import validar_comando
from control import AdaptadorVirtual, Supervisor, politica_de_prueba

RAIZ = Path(__file__).resolve().parents[1]
EJEMPLOS = RAIZ / "config" / "contrato" / "ejemplos"
PLAZOS = yaml.safe_load((RAIZ / "config" / "control" / "plazos.yaml").read_text(encoding="utf-8"))

CODIGOS_DEL_CONTRATO = ["unreadable_image", "detector_exception", "detector_timeout", "invalid_output"]


def evento(nombre: str, **cambios) -> dict:
    datos = json.loads((EJEMPLOS / nombre).read_text(encoding="utf-8"))
    datos.update(cambios)
    return datos


def fallido(codigo) -> dict:
    return evento("fallido.json", error={"code": codigo, "message": "falla de prueba"})


def nuevo_supervisor(carpeta: Path, politica=politica_de_prueba) -> Supervisor:
    adaptador = AdaptadorVirtual(carpeta, PLAZOS["validez_orden_ms"])
    return Supervisor(politica, adaptador, PLAZOS, config_politica={})


def comandos(carpeta: Path) -> list[dict]:
    return leer(carpeta / "comandos.jsonl")


def errores(carpeta: Path) -> list[dict]:
    return leer(carpeta / "errores.jsonl")


def leer(ruta: Path) -> list[dict]:
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]


def assert_stop_registrado(carpeta: Path, motivo: str, frame_id: str) -> None:
    """Un solo STOP en comandos.jsonl y una sola línea en errores.jsonl, con el mismo motivo."""
    [comando] = comandos(carpeta)
    assert comando["action"] == "STOP"
    assert comando["speed"] == 0
    assert comando["steering"] == 0
    assert comando["reason"] == motivo
    assert comando["frame_id"] == frame_id
    assert validar_comando(comando) == []

    [error] = errores(carpeta)
    assert error["motivo"] == motivo
    assert error["run_id"] == "ejemplo-01"
    assert error["frame_id"] == frame_id


# --- errores del detector ---------------------------------------------------------


@pytest.mark.parametrize("codigo", CODIGOS_DEL_CONTRATO)
def test_cada_error_code_del_contrato_da_stop(tmp_path, codigo):
    nuevo_supervisor(tmp_path).procesar_evento(fallido(codigo), ahora_ms=610.0)

    assert_stop_registrado(tmp_path, f"error_detector:{codigo}", "S02_f0004")
    assert f"error.code: {codigo!r}" in errores(tmp_path)[0]["errores"]


def test_el_ejemplo_fallido_del_contrato_da_stop(tmp_path):
    nuevo_supervisor(tmp_path).procesar_evento(evento("fallido.json"), ahora_ms=610.0)

    assert_stop_registrado(tmp_path, "error_detector:unreadable_image", "S02_f0004")
    assert "error.message: 'No se pudo decodificar el cuadro (JPEG truncado).'" in (
        errores(tmp_path)[0]["errores"]
    )


def test_un_codigo_inventado_da_stop_y_se_marca_desconocido(tmp_path):
    nuevo_supervisor(tmp_path).procesar_evento(fallido("camara_en_llamas"), ahora_ms=610.0)

    assert_stop_registrado(tmp_path, "error_detector:camara_en_llamas", "S02_f0004")
    assert "error.code desconocido: se trata como error" in errores(tmp_path)[0]["errores"]


def test_un_error_sin_objeto_error_da_stop(tmp_path):
    ev = evento("fallido.json")
    ev.pop("error")
    nuevo_supervisor(tmp_path).procesar_evento(ev, ahora_ms=610.0)

    assert_stop_registrado(tmp_path, "error_detector:None", "S02_f0004")


def test_los_errores_del_detector_no_llegan_a_la_politica(tmp_path):
    def politica(ev, estado, config):
        raise AssertionError("la política no debe ver errores del detector")

    supervisor = nuevo_supervisor(tmp_path, politica)
    for codigo in CODIGOS_DEL_CONTRATO + ["camara_en_llamas"]:
        supervisor.procesar_evento(fallido(codigo), ahora_ms=610.0)

    assert [c["action"] for c in comandos(tmp_path)] == ["STOP"] * 5
    assert len(errores(tmp_path)) == 5


# --- cuadro viejo -----------------------------------------------------------------


def test_stale_da_stop(tmp_path):
    nuevo_supervisor(tmp_path).procesar_evento(evento("stale.json"), ahora_ms=1655.0)

    assert_stop_registrado(tmp_path, "stale", "S02_f0005")
    assert "850" in errores(tmp_path)[0]["errores"][0]


def test_stale_cancela_la_orden_previa(tmp_path):
    supervisor = nuevo_supervisor(tmp_path)
    supervisor.procesar_evento(evento("vacio.json"), ahora_ms=50.0)
    assert supervisor.adaptador.activo["action"] == "AVANZAR"

    supervisor.procesar_evento(evento("stale.json"), ahora_ms=1655.0)

    assert [c["action"] for c in comandos(tmp_path)] == ["AVANZAR", "STOP"]
    assert supervisor.adaptador.activo["action"] == "STOP"
    assert supervisor.estado == {"nombre": "DETENIDO"}


# --- fallas de la política --------------------------------------------------------


def test_politica_que_lanza_excepcion_da_stop(tmp_path):
    def politica(ev, estado, config):
        raise ZeroDivisionError("división entre cero")

    nuevo_supervisor(tmp_path, politica).procesar_evento(evento("valido.json"), ahora_ms=440.0)

    assert_stop_registrado(tmp_path, "politica_excepcion", "S02_f0003")
    assert errores(tmp_path)[0]["errores"] == ["ZeroDivisionError: división entre cero"]


RESPUESTAS_INVALIDAS = {
    "sin action": ({"speed": 0.5, "steering": 0.0, "reason": "x"}, {"nombre": "AVANZANDO"}),
    "action inventada": ({"action": "VOLAR", "speed": 0.5, "steering": 0.0, "reason": "x"}, {"nombre": "AVANZANDO"}),
    "avanzar sin velocidad": ({"action": "AVANZAR", "speed": 0, "steering": 0.0, "reason": "x"}, {"nombre": "AVANZANDO"}),
    "velocidad fuera de rango": ({"action": "AVANZAR", "speed": 3, "steering": 0.0, "reason": "x"}, {"nombre": "AVANZANDO"}),
    "estado como texto": ({"action": "AVANZAR", "speed": 0.5, "steering": 0.0, "reason": "x"}, "AVANZANDO"),
    "estado sin nombre": ({"action": "AVANZAR", "speed": 0.5, "steering": 0.0, "reason": "x"}, {"libres_seguidos": 1}),
    "nombre inventado": ({"action": "AVANZAR", "speed": 0.5, "steering": 0.0, "reason": "x"}, {"nombre": "VOLANDO"}),
    "no es una tupla": ("AVANZAR", None),
    "None": None,
}


@pytest.mark.parametrize("respuesta", RESPUESTAS_INVALIDAS.values(), ids=RESPUESTAS_INVALIDAS)
def test_politica_que_devuelve_algo_invalido_da_stop(tmp_path, respuesta):
    def politica(ev, estado, config):
        return respuesta

    supervisor = nuevo_supervisor(tmp_path, politica)
    supervisor.procesar_evento(evento("valido.json"), ahora_ms=440.0)

    [comando] = comandos(tmp_path)
    assert comando["action"] == "STOP"
    assert comando["reason"] in ("politica_excepcion", "politica_invalida")
    assert validar_comando(comando) == []
    [error] = errores(tmp_path)
    assert error["motivo"] == comando["reason"]
    assert supervisor.estado == {"nombre": "DETENIDO"}


def test_politica_invalida_registra_el_detalle(tmp_path):
    def politica(ev, estado, config):
        return {"action": "VOLAR", "speed": 0.5, "steering": 0.0, "reason": "x"}, {"nombre": "AVANZANDO"}

    nuevo_supervisor(tmp_path, politica).procesar_evento(evento("valido.json"), ahora_ms=440.0)

    assert_stop_registrado(tmp_path, "politica_invalida", "S02_f0003")
    assert any(e.startswith("action:") for e in errores(tmp_path)[0]["errores"])


def test_un_estado_fuera_de_lo_acordado_registra_el_detalle(tmp_path):
    def politica(ev, estado, config):
        return {"action": "AVANZAR", "speed": 0.5, "steering": 0.0, "reason": "x"}, {"nombre": "VOLANDO"}

    nuevo_supervisor(tmp_path, politica).procesar_evento(evento("valido.json"), ahora_ms=440.0)

    assert_stop_registrado(tmp_path, "politica_invalida", "S02_f0003")
    assert errores(tmp_path)[0]["errores"][0].startswith("estado.nombre: 'VOLANDO'")


def test_el_programa_sigue_despues_de_una_falla(tmp_path):
    llamadas = {"n": 0}

    def politica(ev, estado, config):
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            raise RuntimeError("falla una vez")
        return politica_de_prueba(ev, estado, config)

    supervisor = nuevo_supervisor(tmp_path, politica)
    supervisor.procesar_evento(evento("vacio.json"), ahora_ms=50.0)
    supervisor.procesar_evento(evento("valido.json"), ahora_ms=440.0)

    assert [c["action"] for c in comandos(tmp_path)] == ["STOP", "AVANZAR"]
    assert len(errores(tmp_path)) == 1


# --- lo que NO es error -----------------------------------------------------------


def test_ok_sin_detecciones_no_es_error_y_avanza(tmp_path):
    nuevo_supervisor(tmp_path).procesar_evento(evento("vacio.json"), ahora_ms=50.0)

    [comando] = comandos(tmp_path)
    assert comando["action"] == "AVANZAR"
    assert comando["frame_id"] == "S01_f0001"
    assert errores(tmp_path) == []


def test_el_flujo_del_contrato_termina_en_los_comandos_esperados(tmp_path):
    supervisor = nuevo_supervisor(tmp_path)
    lineas = (EJEMPLOS / "flujo.jsonl").read_text(encoding="utf-8").splitlines()
    eventos = [json.loads(linea) for linea in lineas if linea.strip()]
    assert {ev["status"] for ev in eventos} == {"ok", "stale", "error"}
    for ev in eventos:
        supervisor.procesar_evento(ev, ahora_ms=ev["t_emit_ms"] + 1)

    esperado = {"ok": "AVANZAR", "stale": "STOP", "error": "STOP"}
    assert [c["action"] for c in comandos(tmp_path)] == [esperado[ev["status"]] for ev in eventos]
    assert len(errores(tmp_path)) == sum(ev["status"] != "ok" for ev in eventos)
