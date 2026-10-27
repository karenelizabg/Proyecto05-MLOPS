"""T05 · Watchdog: si dejan de llegar cuadros o la orden vence, STOP de reloj (C8).

Reloj controlado: cada prueba pasa `ahora_ms` a mano. Se revisa comandos.jsonl.
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


def cuadro(t_capture_ms: float, frame_id: str) -> dict:
    """Un cuadro ok sin detecciones, capturado en t_capture_ms."""
    datos = json.loads((EJEMPLOS / "vacio.json").read_text(encoding="utf-8"))
    datos.update(frame_id=frame_id, t_capture_ms=t_capture_ms, t_emit_ms=t_capture_ms + 40)
    return datos


def nuevo_supervisor(carpeta: Path, **plazos) -> Supervisor:
    plazos = {**PLAZOS, **plazos}
    adaptador = AdaptadorVirtual(carpeta, plazos["validez_orden_ms"])
    return Supervisor(politica_de_prueba, adaptador, plazos, config_politica={})


def comandos(carpeta: Path) -> list[dict]:
    return leer(carpeta / "comandos.jsonl")


def errores(carpeta: Path) -> list[dict]:
    return leer(carpeta / "errores.jsonl")


def leer(ruta: Path) -> list[dict]:
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]


def assert_stop_de_reloj(comando: dict, motivo: str) -> None:
    assert comando["action"] == "STOP"
    assert comando["speed"] == 0
    assert comando["steering"] == 0
    assert comando["event"] == "clock"
    assert comando["frame_id"] is None
    assert comando["reason"] == motivo
    assert validar_comando(comando) == []


# --- el caso del issue -------------------------------------------------------------


def test_avanzar_en_0_tick_300_no_frena_y_tick_700_frena(tmp_path):
    supervisor = nuevo_supervisor(tmp_path)
    supervisor.procesar_evento(cuadro(0, "f0"), ahora_ms=0)

    assert supervisor.tick(300) is None
    assert [c["action"] for c in comandos(tmp_path)] == ["AVANZAR"]

    stop = supervisor.tick(700)
    assert_stop_de_reloj(stop, "watchdog_vencido")
    assert [c["action"] for c in comandos(tmp_path)] == ["AVANZAR", "STOP"]
    assert_stop_de_reloj(comandos(tmp_path)[-1], "watchdog_vencido")


def test_el_stop_de_reloj_se_manda_una_sola_vez(tmp_path):
    supervisor = nuevo_supervisor(tmp_path)
    supervisor.procesar_evento(cuadro(0, "f0"), ahora_ms=0)

    supervisor.tick(700)
    for ahora_ms in (800, 900, 5000):
        assert supervisor.tick(ahora_ms) is None

    assert [c["action"] for c in comandos(tmp_path)] == ["AVANZAR", "STOP"]
    assert len(errores(tmp_path)) == 1


def test_el_stop_de_reloj_queda_en_errores_y_deja_el_estado_detenido(tmp_path):
    supervisor = nuevo_supervisor(tmp_path)
    supervisor.procesar_evento(cuadro(0, "f0"), ahora_ms=0)
    stop = supervisor.tick(700)

    [error] = errores(tmp_path)
    assert error["motivo"] == "watchdog_vencido"
    assert error["run_id"] == "ejemplo-01"
    assert error["frame_id"] is None
    assert (stop["state_before"], stop["state_after"]) == ("AVANZANDO", "DETENIDO")
    assert supervisor.estado == {"nombre": "DETENIDO"}
    assert supervisor.adaptador.activo["action"] == "STOP"


# --- watchdog ----------------------------------------------------------------------


def test_cuadros_a_tiempo_no_disparan_el_watchdog(tmp_path):
    supervisor = nuevo_supervisor(tmp_path)
    for n, t in enumerate(range(0, 2000, 200)):
        supervisor.procesar_evento(cuadro(t, f"f{n}"), ahora_ms=t)
        assert supervisor.tick(t + 199) is None

    assert {c["action"] for c in comandos(tmp_path)} == {"AVANZAR"}


def test_el_watchdog_cuenta_desde_el_ultimo_cuadro(tmp_path):
    # Validez larga para que solo cuente el watchdog.
    supervisor = nuevo_supervisor(tmp_path, watchdog_ms=600, validez_orden_ms=5000)
    supervisor.procesar_evento(cuadro(0, "f0"), ahora_ms=0)
    supervisor.procesar_evento(cuadro(500, "f1"), ahora_ms=500)

    assert supervisor.tick(1100) is None  # 600 ms justos: todavía no es "más de"
    assert_stop_de_reloj(supervisor.tick(1101), "watchdog_vencido")


def test_tras_el_stop_de_reloj_un_cuadro_nuevo_reanuda_y_se_vigila_otra_vez(tmp_path):
    supervisor = nuevo_supervisor(tmp_path)
    supervisor.procesar_evento(cuadro(0, "f0"), ahora_ms=0)
    supervisor.tick(700)

    supervisor.procesar_evento(cuadro(1000, "f1"), ahora_ms=1000)
    assert supervisor.tick(1300) is None
    assert_stop_de_reloj(supervisor.tick(1700), "watchdog_vencido")
    assert [c["action"] for c in comandos(tmp_path)] == ["AVANZAR", "STOP", "AVANZAR", "STOP"]


def test_sin_ordenes_el_tick_no_hace_nada(tmp_path):
    supervisor = nuevo_supervisor(tmp_path)

    assert supervisor.tick(10_000) is None
    assert comandos(tmp_path) == []


def test_si_ya_esta_en_stop_el_tick_no_repite(tmp_path):
    supervisor = nuevo_supervisor(tmp_path)
    roto = cuadro(0, "f0")
    roto.pop("t_emit_ms")
    supervisor.procesar_evento(roto, ahora_ms=0)

    assert supervisor.tick(10_000) is None
    assert [c["event"] for c in comandos(tmp_path)] == ["frame"]


# --- orden vencida -----------------------------------------------------------------


def test_una_orden_vence_sola(tmp_path):
    # Watchdog largo para que solo cuente la validez de la orden (400 ms).
    supervisor = nuevo_supervisor(tmp_path, watchdog_ms=5000)
    avanzar = supervisor.procesar_evento(cuadro(0, "f0"), ahora_ms=0)
    assert avanzar["valid_until_ms"] == PLAZOS["validez_orden_ms"]

    assert supervisor.tick(PLAZOS["validez_orden_ms"]) is None  # vale hasta ese instante
    stop = supervisor.tick(PLAZOS["validez_orden_ms"] + 1)
    assert_stop_de_reloj(stop, "orden_vencida")
    assert errores(tmp_path)[0]["motivo"] == "orden_vencida"


def test_con_los_plazos_del_yaml_la_orden_vence_antes_que_el_watchdog(tmp_path):
    # validez_orden_ms (400) < watchdog_ms (600): entre los dos, frena primero la orden vencida.
    assert PLAZOS["validez_orden_ms"] < PLAZOS["watchdog_ms"]
    supervisor = nuevo_supervisor(tmp_path)
    supervisor.procesar_evento(cuadro(0, "f0"), ahora_ms=0)

    assert_stop_de_reloj(supervisor.tick(500), "orden_vencida")


def test_si_vencen_los_dos_la_razon_es_el_watchdog(tmp_path):
    supervisor = nuevo_supervisor(tmp_path)
    supervisor.procesar_evento(cuadro(0, "f0"), ahora_ms=0)

    assert_stop_de_reloj(supervisor.tick(10_000), "watchdog_vencido")


# --- cuadro viejo ------------------------------------------------------------------


def test_un_cuadro_ok_muy_viejo_se_rechaza(tmp_path):
    supervisor = nuevo_supervisor(tmp_path)
    comando = supervisor.procesar_evento(cuadro(0, "f0"), ahora_ms=2000)

    assert comando["action"] == "STOP"
    assert comando["reason"] == "cuadro_viejo"
    assert comando["event"] == "frame"
    assert comando["frame_id"] == "f0"
    assert validar_comando(comando) == []
    [error] = errores(tmp_path)
    assert error["motivo"] == "cuadro_viejo"
    assert "2000" in error["errores"][0]


def test_un_cuadro_viejo_no_llega_a_la_politica(tmp_path):
    def politica(ev, estado, config):
        raise AssertionError("la política no debe ver cuadros viejos")

    adaptador = AdaptadorVirtual(tmp_path, PLAZOS["validez_orden_ms"])
    supervisor = Supervisor(politica, adaptador, PLAZOS, config_politica={})
    supervisor.procesar_evento(cuadro(0, "f0"), ahora_ms=2000)

    assert [c["reason"] for c in comandos(tmp_path)] == ["cuadro_viejo"]


@pytest.mark.parametrize(
    "edad_ms, accion",
    [(PLAZOS["max_frame_age_ms"], "AVANZAR"), (PLAZOS["max_frame_age_ms"] + 1, "STOP")],
)
def test_el_limite_de_edad_es_max_frame_age_ms(tmp_path, edad_ms, accion):
    supervisor = nuevo_supervisor(tmp_path)
    comando = supervisor.procesar_evento(cuadro(1000, "f0"), ahora_ms=1000 + edad_ms)

    assert comando["action"] == accion


def test_un_cuadro_viejo_cancela_la_orden_previa(tmp_path):
    supervisor = nuevo_supervisor(tmp_path)
    supervisor.procesar_evento(cuadro(0, "f0"), ahora_ms=0)
    supervisor.procesar_evento(cuadro(100, "f1"), ahora_ms=900)

    assert [c["action"] for c in comandos(tmp_path)] == ["AVANZAR", "STOP"]
    assert supervisor.adaptador.activo["reason"] == "cuadro_viejo"


def test_un_cuadro_viejo_no_reinicia_el_watchdog(tmp_path):
    supervisor = nuevo_supervisor(tmp_path)
    supervisor.procesar_evento(cuadro(0, "f0"), ahora_ms=0)
    supervisor.procesar_evento(cuadro(100, "f1"), ahora_ms=900)  # viejo: STOP

    # Ya está en STOP; no hay otro STOP de reloj aunque pase el tiempo.
    assert supervisor.tick(2000) is None
    assert [c["reason"] for c in comandos(tmp_path)] == ["politica_de_prueba", "cuadro_viejo"]
