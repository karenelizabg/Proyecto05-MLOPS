import json
import math
from pathlib import Path

import pytest
import yaml

from contrato import validar_comando
from control import AdaptadorVirtual

RAIZ = Path(__file__).resolve().parents[1]
EJEMPLOS = RAIZ / "config" / "contrato" / "ejemplos_comando"
PLAZOS = yaml.safe_load((RAIZ / "config" / "control" / "plazos.yaml").read_text(encoding="utf-8"))
VALIDEZ_MS = PLAZOS["validez_orden_ms"]


def comando(nombre: str, **cambios) -> dict:
    """Un ejemplo del contrato tal como lo entrega la política: sin received ni t_command_ms."""
    datos = json.loads((EJEMPLOS / nombre).read_text(encoding="utf-8"))
    datos.pop("received")
    datos.pop("t_command_ms")
    datos.update(cambios)
    return datos


def leer_registro(adaptador: AdaptadorVirtual) -> list[dict]:
    lineas = adaptador.ruta_registro.read_text(encoding="utf-8").splitlines()
    return [json.loads(linea) for linea in lineas]


# --- registro ---------------------------------------------------------------


def test_escribe_una_linea_con_received_y_t_command_ms(tmp_path):
    adaptador = AdaptadorVirtual(tmp_path, VALIDEZ_MS)
    adaptador.enviar(comando("avanzar.json"), ahora_ms=43.5)

    registro = leer_registro(adaptador)
    assert len(registro) == 1
    assert registro[0]["received"] is True
    assert registro[0]["t_command_ms"] == 43.5
    assert registro[0]["action"] == "AVANZAR"


def test_cada_comando_agrega_una_linea(tmp_path):
    adaptador = AdaptadorVirtual(tmp_path, VALIDEZ_MS)
    adaptador.enviar(comando("avanzar.json"), ahora_ms=43.5)
    adaptador.enviar(comando("stop.json"), ahora_ms=439.4)
    adaptador.enviar(comando("reloj.json"), ahora_ms=1100.2)

    registro = leer_registro(adaptador)
    assert [c["action"] for c in registro] == ["AVANZAR", "STOP", "STOP"]
    assert [c["t_command_ms"] for c in registro] == [43.5, 439.4, 1100.2]


def test_lo_registrado_cumple_el_contrato_de_comando(tmp_path):
    adaptador = AdaptadorVirtual(tmp_path, VALIDEZ_MS)
    for nombre, ahora_ms in [("avanzar.json", 43.5), ("stop.json", 439.4), ("reloj.json", 1100.2)]:
        adaptador.enviar(comando(nombre), ahora_ms=ahora_ms)

    for linea in leer_registro(adaptador):
        assert validar_comando(linea) == []


def test_no_modifica_el_comando_recibido(tmp_path):
    original = comando("stop.json", speed=0.5)
    AdaptadorVirtual(tmp_path, VALIDEZ_MS).enviar(original, ahora_ms=439.4)

    assert original["speed"] == 0.5
    assert "received" not in original


# --- vigencia ---------------------------------------------------------------


def test_valid_until_se_cuenta_desde_el_envio(tmp_path):
    adaptador = AdaptadorVirtual(tmp_path, VALIDEZ_MS)
    escrito = adaptador.enviar(comando("avanzar.json"), ahora_ms=43.5)

    assert escrito["valid_until_ms"] == 43.5 + VALIDEZ_MS
    assert leer_registro(adaptador)[0]["valid_until_ms"] == 43.5 + VALIDEZ_MS


def test_un_comando_que_llega_tarde_no_sale_vencido(tmp_path):
    # Decidido en 43 ms y enviado en 1000 ms: contado desde t_decision_ms ya habría vencido.
    adaptador = AdaptadorVirtual(tmp_path, VALIDEZ_MS)
    escrito = adaptador.enviar(comando("avanzar.json"), ahora_ms=1000.0)

    assert escrito["t_decision_ms"] + VALIDEZ_MS < 1000.0
    assert escrito["valid_until_ms"] == 1000.0 + VALIDEZ_MS
    assert validar_comando(escrito) == []


# --- STOP -------------------------------------------------------------------


def test_stop_fuerza_velocidad_y_direccion_cero(tmp_path):
    adaptador = AdaptadorVirtual(tmp_path, VALIDEZ_MS)
    adaptador.enviar(comando("stop.json", speed=0.5, steering=0.3), ahora_ms=439.4)

    escrito = leer_registro(adaptador)[0]
    assert escrito["speed"] == 0
    assert escrito["steering"] == 0
    assert adaptador.activo["speed"] == 0


def test_stop_cancela_un_avanzar_previo(tmp_path):
    adaptador = AdaptadorVirtual(tmp_path, VALIDEZ_MS)
    adaptador.enviar(comando("avanzar.json"), ahora_ms=43.5)
    assert adaptador.activo["action"] == "AVANZAR"

    adaptador.enviar(comando("stop.json"), ahora_ms=439.4)
    assert adaptador.activo["action"] == "STOP"
    assert adaptador.activo["speed"] == 0
    assert adaptador.activo["t_command_ms"] == 439.4


def test_sin_comandos_no_hay_orden_activa(tmp_path):
    assert AdaptadorVirtual(tmp_path, VALIDEZ_MS).activo is None


def test_un_nan_falla_sin_escribir_ni_cambiar_la_orden_activa(tmp_path):
    """allow_nan=False: NaN no es JSON, así que no queda una línea a medias en el registro."""
    adaptador = AdaptadorVirtual(tmp_path, VALIDEZ_MS)
    adaptador.enviar(comando("avanzar.json"), ahora_ms=43.5)

    con_nan = comando("avanzar.json", speed=math.nan)
    with pytest.raises(ValueError):
        adaptador.enviar(con_nan, ahora_ms=80.0)

    assert len(leer_registro(adaptador)) == 1
    assert adaptador.activo["t_command_ms"] == 43.5


# --- carpeta ----------------------------------------------------------------


def test_la_carpeta_de_salida_es_configurable(tmp_path):
    carpeta = tmp_path / "corridas" / "run-01"
    adaptador = AdaptadorVirtual(carpeta, VALIDEZ_MS)
    adaptador.enviar(comando("avanzar.json"), ahora_ms=43.5)

    assert adaptador.ruta_registro == carpeta / "comandos.jsonl"
    assert len(leer_registro(adaptador)) == 1


def test_empieza_con_el_registro_vacio(tmp_path):
    adaptador = AdaptadorVirtual(tmp_path, VALIDEZ_MS)

    assert adaptador.ruta_registro.exists()
    assert leer_registro(adaptador) == []


def test_dos_corridas_en_la_misma_carpeta_no_se_mezclan(tmp_path):
    primera = AdaptadorVirtual(tmp_path, VALIDEZ_MS)
    primera.enviar(comando("avanzar.json"), ahora_ms=43.5)
    primera.enviar(comando("stop.json"), ahora_ms=439.4)

    segunda = AdaptadorVirtual(tmp_path, VALIDEZ_MS)
    segunda.enviar(comando("reloj.json"), ahora_ms=1100.2)

    registro = leer_registro(segunda)
    assert len(registro) == 1
    assert registro[0]["event"] == "clock"


def test_acepta_la_carpeta_como_texto(tmp_path):
    adaptador = AdaptadorVirtual(str(tmp_path / "salida"), VALIDEZ_MS)
    adaptador.enviar(comando("avanzar.json"), ahora_ms=43.5)

    assert (tmp_path / "salida" / "comandos.jsonl").exists()
