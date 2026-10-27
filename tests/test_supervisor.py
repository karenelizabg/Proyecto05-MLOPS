import copy
import json
from pathlib import Path

import pytest
import yaml

from contrato import validar_comando
from control import AdaptadorVirtual, Supervisor, politica_de_prueba
from control.config import cargar_config_politica
from control.politica import decidir

RAIZ = Path(__file__).resolve().parents[1]
EJEMPLOS = RAIZ / "config" / "contrato" / "ejemplos"
PLAZOS = yaml.safe_load((RAIZ / "config" / "control" / "plazos.yaml").read_text(encoding="utf-8"))


def evento(nombre: str, **cambios) -> dict:
    datos = json.loads((EJEMPLOS / nombre).read_text(encoding="utf-8"))
    datos.update(cambios)
    return datos


def nuevo_supervisor(carpeta: Path, politica=politica_de_prueba) -> Supervisor:
    adaptador = AdaptadorVirtual(carpeta, PLAZOS["validez_orden_ms"])
    return Supervisor(politica, adaptador, PLAZOS, config_politica={})


def leer(ruta: Path) -> list[dict]:
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]


def roto() -> dict:
    """Evento que no cumple el contrato: le falta t_emit_ms."""
    datos = evento("valido.json")
    datos.pop("t_emit_ms")
    return datos


# --- eventos válidos ----------------------------------------------------------


@pytest.mark.parametrize("nombre", ["valido.json", "vacio.json"])
def test_evento_valido_pasa_por_la_politica_y_llega_al_adaptador(tmp_path, nombre):
    supervisor = nuevo_supervisor(tmp_path)
    ev = evento(nombre)
    supervisor.procesar_evento(ev, ahora_ms=ev["t_emit_ms"] + 5)

    registro = leer(supervisor.adaptador.ruta_registro)
    assert len(registro) == 1
    comando = registro[0]
    assert comando["action"] == "AVANZAR"
    assert comando["speed"] == 0.5
    assert comando["reason"] == "politica_de_prueba"
    assert comando["run_id"] == ev["run_id"]
    assert comando["frame_id"] == ev["frame_id"]
    assert comando["event"] == "frame"
    assert validar_comando(comando) == []


def test_el_comando_llega_con_valid_until_ms(tmp_path):
    supervisor = nuevo_supervisor(tmp_path)
    comando = supervisor.procesar_evento(evento("valido.json"), ahora_ms=440.0)

    assert comando["t_decision_ms"] == 440.0
    assert comando["t_command_ms"] == 440.0
    assert comando["valid_until_ms"] == 440.0 + PLAZOS["validez_orden_ms"]


def test_la_politica_recibe_evento_estado_y_config(tmp_path):
    llamadas = []

    def politica(ev, estado, config):
        llamadas.append((ev["frame_id"], estado, config))
        return politica_de_prueba(ev, estado, config)

    adaptador = AdaptadorVirtual(tmp_path, PLAZOS["validez_orden_ms"])
    supervisor = Supervisor(politica, adaptador, PLAZOS, config_politica={"umbral": 0.5})
    supervisor.procesar_evento(evento("vacio.json"), ahora_ms=50.0)
    supervisor.procesar_evento(evento("valido.json"), ahora_ms=440.0)

    assert llamadas == [
        ("S01_f0001", {"nombre": "DETENIDO"}, {"umbral": 0.5}),
        ("S02_f0003", {"nombre": "AVANZANDO"}, {"umbral": 0.5}),
    ]


def test_el_estado_avanza_con_la_politica(tmp_path):
    supervisor = nuevo_supervisor(tmp_path)
    comando = supervisor.procesar_evento(evento("valido.json"), ahora_ms=440.0)

    assert comando["state_before"] == "DETENIDO"
    assert comando["state_after"] == "AVANZANDO"
    assert supervisor.estado == {"nombre": "AVANZANDO"}


def test_un_evento_valido_no_deja_errores(tmp_path):
    supervisor = nuevo_supervisor(tmp_path)
    supervisor.procesar_evento(evento("valido.json"), ahora_ms=440.0)

    assert leer(supervisor.ruta_errores) == []


# --- estado como diccionario (acuerdo con T09/T11) --------------------------------


def politica_que_cuenta(ev, estado, config):
    """Guarda en el estado cuántos cuadros libres lleva, además del nombre."""
    libres = estado.get("libres_seguidos", 0) + 1
    comando = {"action": "AVANZAR", "speed": 0.5, "steering": 0.0, "reason": "libre"}
    return comando, {"nombre": "AVANZANDO", "libres_seguidos": libres}


def test_el_estado_inicial_es_un_diccionario_detenido(tmp_path):
    assert nuevo_supervisor(tmp_path).estado == {"nombre": "DETENIDO"}


def test_un_estado_con_mas_datos_sale_avanzar_y_no_stop(tmp_path):
    def politica(ev, estado, config):
        comando = {"action": "AVANZAR", "speed": 0.5, "steering": 0.0, "reason": "libre"}
        return comando, {"nombre": "AVANZANDO", "libres_seguidos": 2}

    supervisor = nuevo_supervisor(tmp_path, politica)
    comando = supervisor.procesar_evento(evento("vacio.json"), ahora_ms=50.0)

    assert comando["action"] == "AVANZAR"
    assert comando["state_after"] == "AVANZANDO"
    assert supervisor.estado == {"nombre": "AVANZANDO", "libres_seguidos": 2}
    assert leer(supervisor.ruta_errores) == []
    assert [c["action"] for c in leer(supervisor.adaptador.ruta_registro)] == ["AVANZAR"]


def test_politica_de_prueba_devuelve_un_estado_diccionario():
    _, estado = politica_de_prueba(evento("vacio.json"), {"nombre": "DETENIDO"}, {})
    assert estado == {"nombre": "AVANZANDO"}


def test_guarda_el_estado_completo_y_se_lo_pasa_a_la_politica(tmp_path):
    vistos = []

    def politica(ev, estado, config):
        vistos.append(copy.deepcopy(estado))
        return politica_que_cuenta(ev, estado, config)

    supervisor = nuevo_supervisor(tmp_path, politica)
    primero = supervisor.procesar_evento(evento("vacio.json"), ahora_ms=50.0)
    segundo = supervisor.procesar_evento(evento("valido.json"), ahora_ms=440.0)

    assert vistos == [{"nombre": "DETENIDO"}, {"nombre": "AVANZANDO", "libres_seguidos": 1}]
    assert supervisor.estado == {"nombre": "AVANZANDO", "libres_seguidos": 2}
    assert (primero["state_before"], primero["state_after"]) == ("DETENIDO", "AVANZANDO")
    assert (segundo["state_before"], segundo["state_after"]) == ("AVANZANDO", "AVANZANDO")
    assert validar_comando(primero) == []
    assert validar_comando(segundo) == []


def test_state_before_y_after_usan_el_nombre(tmp_path):
    def politica(ev, estado, config):
        comando = {
            "action": "GIRAR_IZQ",
            "speed": 0.3,
            "steering": -0.5,
            "reason": "obstáculo a la derecha",
        }
        return comando, {"nombre": "GIRANDO_IZQ", "giro_desde_ms": 440.0}

    comando = nuevo_supervisor(tmp_path, politica).procesar_evento(
        evento("valido.json"), ahora_ms=440.0
    )

    assert comando["state_before"] == "DETENIDO"
    assert comando["state_after"] == "GIRANDO_IZQ"
    assert validar_comando(comando) == []


def test_un_stop_solo_cambia_el_nombre_y_conserva_los_datos_de_la_politica(tmp_path):
    supervisor = nuevo_supervisor(tmp_path, politica_que_cuenta)
    supervisor.procesar_evento(evento("vacio.json"), ahora_ms=50.0)
    assert supervisor.estado["libres_seguidos"] == 1

    comando = supervisor.procesar_evento(roto(), ahora_ms=440.0)

    assert comando["state_before"] == "AVANZANDO"
    assert comando["state_after"] == "DETENIDO"
    assert supervisor.estado == {"nombre": "DETENIDO", "libres_seguidos": 1}


def test_si_la_politica_cambia_el_estado_y_falla_el_guardado_no_se_toca(tmp_path):
    def politica(ev, estado, config):
        if ev["frame_id"] == "S02_f0003":
            estado["libres_seguidos"] = 99
            raise RuntimeError("falla a medias")
        return politica_que_cuenta(ev, estado, config)

    supervisor = nuevo_supervisor(tmp_path, politica)
    supervisor.procesar_evento(evento("vacio.json"), ahora_ms=50.0)
    guardado = copy.deepcopy(supervisor.estado)
    comando = supervisor.procesar_evento(evento("valido.json"), ahora_ms=440.0)

    assert guardado == {"nombre": "AVANZANDO", "libres_seguidos": 1}
    assert comando["action"] == "STOP"
    # Conserva lo guardado antes de la falla (1), no lo que la política cambió a medias (99).
    assert supervisor.estado == {"nombre": "DETENIDO", "libres_seguidos": 1}


# --- con la política real: el STOP del supervisor no rompe la histéresis (T11) -------


def con_politica_real(carpeta: Path) -> Supervisor:
    adaptador = AdaptadorVirtual(carpeta, PLAZOS["validez_orden_ms"])
    return Supervisor(decidir, adaptador, PLAZOS, cargar_config_politica())


LIBRE, BLOQUEO, STALE = "libre", "bloqueo", "stale"
# Obstáculos en las tres zonas de una imagen de 640 px: no hay hacia dónde girar, la política frena.
CAJAS_BLOQUEO = [[20, 100, 120, 400], [260, 100, 380, 400], [520, 100, 620, 400]]


def en_t(tipo: str, frame_id: str, t_capture_ms: float) -> dict:
    """Un cuadro libre, bloqueado o stale en t_capture_ms; A lo emite 40 ms después."""
    nombre = {LIBRE: "vacio.json", BLOQUEO: "valido.json", STALE: "stale.json"}[tipo]
    ev = evento(nombre, frame_id=frame_id, t_capture_ms=t_capture_ms, t_emit_ms=t_capture_ms + 40)
    if tipo == BLOQUEO:
        ev["detections"] = [
            {"class_id": 1, "confidence": 0.9, "bbox": caja} for caja in CAJAS_BLOQUEO
        ]
    return ev


def test_libre_bloqueo_libre_stale_libre_sigue_en_stop(tmp_path):
    assert cargar_config_politica().cuadros_libres_para_reanudar == 3
    supervisor = con_politica_real(tmp_path)
    secuencia = [LIBRE, BLOQUEO, LIBRE, STALE, LIBRE]

    acciones = []
    for n, nombre in enumerate(secuencia):
        t = n * 200
        comando = supervisor.procesar_evento(en_t(nombre, f"f{n}", t), ahora_ms=t + 45)
        acciones.append(comando["action"])

    assert acciones == ["AVANZAR", "STOP", "STOP", "STOP", "STOP"]
    ultimo = comando
    assert ultimo["reason"].startswith("esperando_cuadros_libres")
    # El STOP por stale solo cambió el nombre: la espera de cuadros libres siguió viva.
    assert supervisor.estado["nombre"] == "DETENIDO"
    assert supervisor.estado["esperando_libres"] is True


def test_el_stop_por_stale_conserva_la_espera_de_la_politica(tmp_path):
    supervisor = con_politica_real(tmp_path)
    for n, nombre in enumerate([LIBRE, BLOQUEO, LIBRE]):
        supervisor.procesar_evento(en_t(nombre, f"f{n}", n * 200), ahora_ms=n * 200 + 45)
    antes = dict(supervisor.estado)

    supervisor.procesar_evento(en_t(STALE, "f3", 600), ahora_ms=645)

    assert supervisor.estado == {**antes, "nombre": "DETENIDO"}
    assert [c["reason"] for c in leer(tmp_path / "comandos.jsonl")][-1] == "stale"


# --- eventos inválidos ----------------------------------------------------------


def test_evento_roto_da_stop(tmp_path):
    supervisor = nuevo_supervisor(tmp_path)
    comando = supervisor.procesar_evento(roto(), ahora_ms=440.0)

    assert comando["action"] == "STOP"
    assert comando["speed"] == 0
    assert comando["steering"] == 0
    assert comando["reason"] == "evento_invalido"
    assert validar_comando(comando) == []


@pytest.mark.parametrize("version", ["2", 1, None])
def test_schema_version_distinta_de_1_da_stop(tmp_path, version):
    supervisor = nuevo_supervisor(tmp_path)
    comando = supervisor.procesar_evento(
        evento("valido.json", schema_version=version), ahora_ms=440.0
    )

    assert comando["action"] == "STOP"
    assert comando["reason"] == "version_no_reconocida"
    assert validar_comando(comando) == []


def test_evento_invalido_no_llama_a_la_politica(tmp_path):
    def politica(ev, estado, config):
        raise AssertionError("la política no debe ver eventos inválidos")

    supervisor = nuevo_supervisor(tmp_path, politica)
    supervisor.procesar_evento(roto(), ahora_ms=440.0)
    supervisor.procesar_evento(evento("valido.json", schema_version="2"), ahora_ms=640.0)


def test_stop_cancela_el_avanzar_previo(tmp_path):
    supervisor = nuevo_supervisor(tmp_path)
    supervisor.procesar_evento(evento("vacio.json"), ahora_ms=50.0)
    assert supervisor.adaptador.activo["action"] == "AVANZAR"

    supervisor.procesar_evento(roto(), ahora_ms=440.0)
    assert supervisor.adaptador.activo["action"] == "STOP"
    assert supervisor.estado == {"nombre": "DETENIDO"}


def test_errores_quedan_registrados_con_run_id_y_frame_id(tmp_path):
    supervisor = nuevo_supervisor(tmp_path)
    supervisor.procesar_evento(roto(), ahora_ms=440.0)
    supervisor.procesar_evento(evento("valido.json", schema_version="2"), ahora_ms=640.0)

    errores = leer(tmp_path / "errores.jsonl")
    assert [e["motivo"] for e in errores] == ["evento_invalido", "version_no_reconocida"]
    for error in errores:
        assert error["run_id"] == "ejemplo-01"
        assert error["frame_id"] == "S02_f0003"
        assert error["errores"]
    assert any("t_emit_ms" in e for e in errores[0]["errores"])


@pytest.mark.parametrize("basura", [None, "no soy un evento", [], {}])
def test_algo_que_no_es_evento_da_stop_con_ids_desconocidos(tmp_path, basura):
    supervisor = nuevo_supervisor(tmp_path)
    comando = supervisor.procesar_evento(copy.deepcopy(basura), ahora_ms=440.0)

    assert comando["action"] == "STOP"
    assert comando["run_id"] == "desconocido"
    assert comando["frame_id"] == "desconocido"
    assert validar_comando(comando) == []
    assert leer(supervisor.ruta_errores)[0]["frame_id"] == "desconocido"


def test_sin_run_id_valido_usa_el_del_ultimo_evento_valido(tmp_path):
    supervisor = nuevo_supervisor(tmp_path)
    supervisor.procesar_evento(evento("vacio.json"), ahora_ms=50.0)
    comando = supervisor.procesar_evento(
        evento("valido.json", run_id="con espacios"), ahora_ms=440.0
    )

    assert comando["action"] == "STOP"
    assert comando["run_id"] == "ejemplo-01"


# --- corrida ---------------------------------------------------------------


def test_errores_empieza_vacio_en_cada_corrida(tmp_path):
    primera = nuevo_supervisor(tmp_path)
    primera.procesar_evento(roto(), ahora_ms=440.0)

    segunda = nuevo_supervisor(tmp_path)
    assert leer(segunda.ruta_errores) == []
