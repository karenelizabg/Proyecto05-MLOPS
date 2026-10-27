import json
from pathlib import Path

from contrato import validar_comando
from control import AdaptadorVirtual

EJEMPLOS = Path(__file__).resolve().parents[1] / "config" / "contrato" / "ejemplos_comando"


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
    adaptador = AdaptadorVirtual(tmp_path)
    adaptador.enviar(comando("avanzar.json"), ahora_ms=43.5)

    registro = leer_registro(adaptador)
    assert len(registro) == 1
    assert registro[0]["received"] is True
    assert registro[0]["t_command_ms"] == 43.5
    assert registro[0]["action"] == "AVANZAR"


def test_cada_comando_agrega_una_linea(tmp_path):
    adaptador = AdaptadorVirtual(tmp_path)
    adaptador.enviar(comando("avanzar.json"), ahora_ms=43.5)
    adaptador.enviar(comando("stop.json"), ahora_ms=439.4)
    adaptador.enviar(comando("reloj.json"), ahora_ms=1100.2)

    registro = leer_registro(adaptador)
    assert [c["action"] for c in registro] == ["AVANZAR", "STOP", "STOP"]
    assert [c["t_command_ms"] for c in registro] == [43.5, 439.4, 1100.2]


def test_lo_registrado_cumple_el_contrato_de_comando(tmp_path):
    adaptador = AdaptadorVirtual(tmp_path)
    for nombre, ahora_ms in [("avanzar.json", 43.5), ("stop.json", 439.4), ("reloj.json", 1100.2)]:
        adaptador.enviar(comando(nombre), ahora_ms=ahora_ms)

    for linea in leer_registro(adaptador):
        assert validar_comando(linea) == []


def test_no_modifica_el_comando_recibido(tmp_path):
    original = comando("stop.json", speed=0.5)
    AdaptadorVirtual(tmp_path).enviar(original, ahora_ms=439.4)

    assert original["speed"] == 0.5
    assert "received" not in original


# --- STOP -------------------------------------------------------------------


def test_stop_fuerza_velocidad_y_direccion_cero(tmp_path):
    adaptador = AdaptadorVirtual(tmp_path)
    adaptador.enviar(comando("stop.json", speed=0.5, steering=0.3), ahora_ms=439.4)

    escrito = leer_registro(adaptador)[0]
    assert escrito["speed"] == 0
    assert escrito["steering"] == 0
    assert adaptador.activo["speed"] == 0


def test_stop_cancela_un_avanzar_previo(tmp_path):
    adaptador = AdaptadorVirtual(tmp_path)
    adaptador.enviar(comando("avanzar.json"), ahora_ms=43.5)
    assert adaptador.activo["action"] == "AVANZAR"

    adaptador.enviar(comando("stop.json"), ahora_ms=439.4)
    assert adaptador.activo["action"] == "STOP"
    assert adaptador.activo["speed"] == 0
    assert adaptador.activo["t_command_ms"] == 439.4


def test_sin_comandos_no_hay_orden_activa(tmp_path):
    assert AdaptadorVirtual(tmp_path).activo is None


# --- carpeta ----------------------------------------------------------------


def test_la_carpeta_de_salida_es_configurable(tmp_path):
    carpeta = tmp_path / "corridas" / "run-01"
    adaptador = AdaptadorVirtual(carpeta)
    adaptador.enviar(comando("avanzar.json"), ahora_ms=43.5)

    assert adaptador.ruta_registro == carpeta / "comandos.jsonl"
    assert len(leer_registro(adaptador)) == 1


def test_empieza_con_el_registro_vacio(tmp_path):
    adaptador = AdaptadorVirtual(tmp_path)

    assert adaptador.ruta_registro.exists()
    assert leer_registro(adaptador) == []


def test_dos_corridas_en_la_misma_carpeta_no_se_mezclan(tmp_path):
    primera = AdaptadorVirtual(tmp_path)
    primera.enviar(comando("avanzar.json"), ahora_ms=43.5)
    primera.enviar(comando("stop.json"), ahora_ms=439.4)

    segunda = AdaptadorVirtual(tmp_path)
    segunda.enviar(comando("reloj.json"), ahora_ms=1100.2)

    registro = leer_registro(segunda)
    assert len(registro) == 1
    assert registro[0]["event"] == "clock"


def test_acepta_la_carpeta_como_texto(tmp_path):
    adaptador = AdaptadorVirtual(str(tmp_path / "salida"))
    adaptador.enviar(comando("avanzar.json"), ahora_ms=43.5)

    assert (tmp_path / "salida" / "comandos.jsonl").exists()
