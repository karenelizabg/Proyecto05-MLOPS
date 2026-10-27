"""T06 · Emergencia, rearme y cierre (C10).

Reloj controlado: cada prueba pasa `ahora_ms` a mano. Se revisan comandos.jsonl y errores.jsonl.
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
MAX_EDAD = PLAZOS["max_frame_age_ms"]


def cuadro(t_capture_ms: float, frame_id: str, nombre: str = "vacio.json") -> dict:
    """Un ejemplo del contrato capturado en t_capture_ms (vacio.json = libre)."""
    datos = json.loads((EJEMPLOS / nombre).read_text(encoding="utf-8"))
    datos.update(frame_id=frame_id, t_capture_ms=t_capture_ms, t_emit_ms=t_capture_ms + 40)
    return datos


def nuevo_supervisor(carpeta: Path, politica=politica_de_prueba) -> Supervisor:
    adaptador = AdaptadorVirtual(carpeta, PLAZOS["validez_orden_ms"])
    return Supervisor(politica, adaptador, PLAZOS, config_politica={})


def comandos(carpeta: Path) -> list[dict]:
    return leer(carpeta / "comandos.jsonl")


def errores(carpeta: Path) -> list[dict]:
    return leer(carpeta / "errores.jsonl")


def leer(ruta: Path) -> list[dict]:
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]


def en_emergencia(carpeta: Path, politica=politica_de_prueba) -> Supervisor:
    """Supervisor que avanzó con un cuadro libre en t=0 y recibió la emergencia en t=100."""
    supervisor = nuevo_supervisor(carpeta, politica)
    supervisor.procesar_evento(cuadro(0, "f0"), ahora_ms=0)
    supervisor.emergencia(100)
    return supervisor


def assert_stop(comando: dict, evento: str, motivo: str) -> None:
    assert comando["action"] == "STOP"
    assert comando["speed"] == 0
    assert comando["steering"] == 0
    assert comando["event"] == evento
    assert comando["reason"] == motivo
    assert validar_comando(comando) == []


# --- emergencia ---------------------------------------------------------------------


def test_emergencia_da_stop_inmediato_con_event_emergency(tmp_path):
    supervisor = nuevo_supervisor(tmp_path)
    supervisor.procesar_evento(cuadro(0, "f0"), ahora_ms=0)

    stop = supervisor.emergencia(100)

    assert_stop(stop, "emergency", "emergencia")
    assert stop["frame_id"] is None
    assert stop["t_command_ms"] == 100
    assert [c["action"] for c in comandos(tmp_path)] == ["AVANZAR", "STOP"]
    assert supervisor.adaptador.activo["event"] == "emergency"
    assert supervisor.estado["nombre"] == "DETENIDO"


def test_con_emergencia_los_cuadros_libres_no_la_quitan(tmp_path):
    supervisor = en_emergencia(tmp_path)

    for n, t in enumerate([200, 400, 600, 800], start=1):
        comando = supervisor.procesar_evento(cuadro(t, f"f{n}"), ahora_ms=t)
        assert_stop(comando, "frame", "emergencia_activa")
        assert comando["frame_id"] == f"f{n}"

    assert [c["action"] for c in comandos(tmp_path)] == ["AVANZAR"] + ["STOP"] * 5


def test_con_emergencia_no_se_llama_a_la_politica(tmp_path):
    llamadas = []

    def politica(ev, estado, config):
        llamadas.append(ev["frame_id"])
        return politica_de_prueba(ev, estado, config)

    supervisor = en_emergencia(tmp_path, politica)
    supervisor.procesar_evento(cuadro(200, "f1"), ahora_ms=200)

    assert llamadas == ["f0"]


def test_la_emergencia_gana_a_un_error_del_detector(tmp_path):
    supervisor = en_emergencia(tmp_path)
    comando = supervisor.procesar_evento(cuadro(200, "f1", "fallido.json"), ahora_ms=200)

    assert_stop(comando, "frame", "emergencia_activa")


def test_con_emergencia_el_reloj_no_repite_stop(tmp_path):
    supervisor = en_emergencia(tmp_path)

    assert supervisor.tick(5000) is None
    assert len(comandos(tmp_path)) == 2


def test_emergencia_sin_cuadros_previos_tambien_frena(tmp_path):
    stop = nuevo_supervisor(tmp_path).emergencia(0)

    assert_stop(stop, "emergency", "emergencia")
    assert stop["run_id"] == "desconocido"


# --- rearme ---------------------------------------------------------------------------


def test_rearmar_sin_cuadro_desde_la_emergencia_sigue_en_stop(tmp_path):
    supervisor = en_emergencia(tmp_path)

    comando = supervisor.rearmar(150)

    assert_stop(comando, "rearm", "rearme_rechazado")
    [error] = errores(tmp_path)
    assert error["motivo"] == "rearme_rechazado"
    assert error["errores"] == ["no ha llegado ningún cuadro desde la emergencia"]
    # Sigue enclavado: el siguiente cuadro libre también da STOP.
    siguiente = supervisor.procesar_evento(cuadro(200, "f1"), ahora_ms=200)
    assert siguiente["reason"] == "emergencia_activa"


def test_un_cuadro_de_antes_de_la_emergencia_no_sirve_para_rearmar(tmp_path):
    supervisor = nuevo_supervisor(tmp_path)
    supervisor.procesar_evento(cuadro(0, "f0"), ahora_ms=0)
    supervisor.emergencia(10)

    # f0 todavía sería fresco (edad 20 ms), pero llegó antes de la emergencia.
    assert supervisor.rearmar(20)["reason"] == "rearme_rechazado"


def test_rearmar_con_un_cuadro_viejo_sigue_en_stop(tmp_path):
    supervisor = en_emergencia(tmp_path)
    supervisor.procesar_evento(cuadro(200, "f1"), ahora_ms=200)

    comando = supervisor.rearmar(200 + MAX_EDAD + 1)

    assert_stop(comando, "rearm", "rearme_rechazado")
    assert comando["frame_id"] == "f1"
    assert f"> max_frame_age_ms {MAX_EDAD}" in errores(tmp_path)[0]["errores"][0]


@pytest.mark.parametrize(
    "nombre, cambios, pista",
    [
        ("stale.json", {}, "status 'stale'"),
        ("fallido.json", {}, "status 'error'"),
        ("vacio.json", {"schema_version": "2"}, "schema_version"),
        ("vacio.json", {"image_width": 0}, "no cumple el contrato"),
    ],
    ids=["stale", "error", "otra_version", "fuera_de_contrato"],
)
def test_rearmar_con_un_cuadro_que_no_es_ok_valido_sigue_en_stop(tmp_path, nombre, cambios, pista):
    supervisor = en_emergencia(tmp_path)
    ultimo = {**cuadro(200, "f1", nombre), **cambios}
    supervisor.procesar_evento(ultimo, ahora_ms=200)

    comando = supervisor.rearmar(210)

    assert_stop(comando, "rearm", "rearme_rechazado")
    assert pista in errores(tmp_path)[-1]["errores"][0]


def test_el_ultimo_cuadro_es_el_que_cuenta(tmp_path):
    # Un cuadro libre y luego uno stale: el último recibido es stale, no rearma.
    supervisor = en_emergencia(tmp_path)
    supervisor.procesar_evento(cuadro(200, "f1"), ahora_ms=200)
    supervisor.procesar_evento(cuadro(400, "f2", "stale.json"), ahora_ms=400)

    assert supervisor.rearmar(410)["reason"] == "rearme_rechazado"


def test_rearmar_con_un_cuadro_fresco_y_valido_reanuda(tmp_path):
    supervisor = en_emergencia(tmp_path)
    supervisor.procesar_evento(cuadro(200, "f1"), ahora_ms=200)

    comando = supervisor.rearmar(250)

    assert comando["action"] == "AVANZAR"
    assert comando["event"] == "rearm"
    assert comando["frame_id"] == "f1"
    assert comando["reason"] == "politica_de_prueba"
    assert validar_comando(comando) == []
    assert supervisor.estado["nombre"] == "AVANZANDO"
    # Ya no hay emergencia: el siguiente cuadro libre pasa por la política.
    siguiente = supervisor.procesar_evento(cuadro(400, "f2"), ahora_ms=400)
    assert (siguiente["action"], siguiente["event"]) == ("AVANZAR", "frame")


@pytest.mark.parametrize("edad_ms, accion", [(MAX_EDAD, "AVANZAR"), (MAX_EDAD + 1, "STOP")])
def test_el_limite_de_frescura_del_rearme_es_max_frame_age_ms(tmp_path, edad_ms, accion):
    supervisor = en_emergencia(tmp_path)
    supervisor.procesar_evento(cuadro(200, "f1"), ahora_ms=200)

    assert supervisor.rearmar(200 + edad_ms)["action"] == accion


def test_al_rearmar_decide_la_politica_aunque_diga_stop(tmp_path):
    def politica(ev, estado, config):
        if ev["frame_id"] == "f1":
            return {"action": "STOP", "speed": 0, "steering": 0.0, "reason": "obstáculo"}, {
                "nombre": "DETENIDO"
            }
        return politica_de_prueba(ev, estado, config)

    supervisor = en_emergencia(tmp_path, politica)
    supervisor.procesar_evento(cuadro(200, "f1"), ahora_ms=200)

    comando = supervisor.rearmar(250)
    assert (comando["action"], comando["event"], comando["reason"]) == (
        "STOP",
        "rearm",
        "obstáculo",
    )
    # La emergencia se quitó: el siguiente cuadro decide la política.
    assert supervisor.procesar_evento(cuadro(400, "f2"), ahora_ms=400)["action"] == "AVANZAR"


def test_si_la_politica_falla_al_rearmar_da_stop_con_event_rearm(tmp_path):
    def politica(ev, estado, config):
        if ev["frame_id"] == "f1":
            raise RuntimeError("falla")
        return politica_de_prueba(ev, estado, config)

    supervisor = en_emergencia(tmp_path, politica)
    supervisor.procesar_evento(cuadro(200, "f1"), ahora_ms=200)

    assert_stop(supervisor.rearmar(250), "rearm", "politica_excepcion")


def test_despues_de_rearmar_el_watchdog_vuelve_a_vigilar(tmp_path):
    supervisor = en_emergencia(tmp_path)
    supervisor.procesar_evento(cuadro(200, "f1"), ahora_ms=200)
    supervisor.rearmar(250)

    assert supervisor.tick(300) is None
    assert supervisor.tick(2000)["event"] == "clock"


def test_rearmar_sin_emergencia_no_hace_nada(tmp_path):
    supervisor = nuevo_supervisor(tmp_path)
    supervisor.procesar_evento(cuadro(0, "f0"), ahora_ms=0)

    assert supervisor.rearmar(50) is None
    assert len(comandos(tmp_path)) == 1


# --- cierre ---------------------------------------------------------------------------


def test_cerrar_manda_stop_con_event_shutdown(tmp_path):
    supervisor = nuevo_supervisor(tmp_path)
    supervisor.procesar_evento(cuadro(0, "f0"), ahora_ms=0)

    stop = supervisor.cerrar(300)

    assert_stop(stop, "shutdown", "cierre")
    assert stop["frame_id"] is None
    assert stop["run_id"] == "ejemplo-01"
    assert [c["action"] for c in comandos(tmp_path)] == ["AVANZAR", "STOP"]
    assert supervisor.adaptador.activo["event"] == "shutdown"


def test_cerrar_ya_detenido_tambien_manda_el_stop_final(tmp_path):
    supervisor = en_emergencia(tmp_path)

    assert_stop(supervisor.cerrar(300), "shutdown", "cierre")


def test_despues_de_cerrar_ningun_cuadro_mueve_el_carro(tmp_path):
    supervisor = nuevo_supervisor(tmp_path)
    supervisor.cerrar(0)

    comando = supervisor.procesar_evento(cuadro(100, "f1"), ahora_ms=100)

    assert_stop(comando, "frame", "supervisor_cerrado")


def test_rearmar_no_reabre_un_supervisor_cerrado(tmp_path):
    supervisor = en_emergencia(tmp_path)
    supervisor.cerrar(150)
    supervisor.procesar_evento(cuadro(200, "f1"), ahora_ms=200)

    assert supervisor.rearmar(210) is None
    assert supervisor.procesar_evento(cuadro(400, "f2"), ahora_ms=400)["action"] == "STOP"


# --- secuencia completa -------------------------------------------------------------


def test_secuencia_emergencia_rearme_y_cierre(tmp_path):
    supervisor = nuevo_supervisor(tmp_path)
    supervisor.procesar_evento(cuadro(0, "f0"), ahora_ms=0)
    supervisor.emergencia(100)
    supervisor.procesar_evento(cuadro(200, "f1"), ahora_ms=200)
    supervisor.rearmar(1000)  # f1 ya es viejo: rechazado
    supervisor.procesar_evento(cuadro(1100, "f2"), ahora_ms=1100)
    supervisor.rearmar(1150)  # f2 es fresco: reanuda
    supervisor.cerrar(1300)

    registro = comandos(tmp_path)
    assert [(c["event"], c["action"], c["reason"]) for c in registro] == [
        ("frame", "AVANZAR", "politica_de_prueba"),
        ("emergency", "STOP", "emergencia"),
        ("frame", "STOP", "emergencia_activa"),
        ("rearm", "STOP", "rearme_rechazado"),
        ("frame", "STOP", "emergencia_activa"),
        ("rearm", "AVANZAR", "politica_de_prueba"),
        ("shutdown", "STOP", "cierre"),
    ]
    assert all(validar_comando(c) == [] for c in registro)
