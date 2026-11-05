"""P5-22 parte 1: el carro simulado se porta como el firmware, con UDP real en localhost.

Del lado de la PC se usa el emisor de prueba de P5-20 (`carro.emisor.Emisor`).
"""

from __future__ import annotations

import ast
import json
import time
from pathlib import Path

import pytest

from carro.emisor import Emisor
from carro.protocolo import MINIMO_PWM, TECHO_PWM, a_pwm, lados
from simulador import CarroSimulado, Fallos
from simulador.__main__ import main

MARGEN_MS = 60  # holgura del planificador del sistema en CI


@pytest.fixture
def carro():
    with CarroSimulado(puerto=0, semilla=1) as c:
        yield c


@pytest.fixture
def emisor(carro):
    host, puerto = carro.direccion
    e = Emisor(host, puerto, sesion=7)
    e.recibir(50)  # respuesta al STOP inicial
    yield e
    e.cerrar()


def _esperar(condicion, limite_ms: float = 1000) -> bool:
    fin = time.perf_counter() + limite_ms / 1000
    while time.perf_counter() < fin:
        if condicion():
            return True
        time.sleep(0.002)
    return condicion()


def _avanzar(emisor: Emisor, vigencia_ms: int = 400):
    emisor.enviar(emisor.orden("AVANZAR", 0.4, 0.0, vigencia_ms))
    return emisor.recibir(50)


# -- comportamiento del firmware ---------------------------------------------------------
def test_arranca_detenido_y_sin_sesion():
    with CarroSimulado(puerto=0) as c:
        assert c.estado == {
            "estado": "DETENIDO",
            "pwm_izq": 0,
            "pwm_der": 0,
            "sesion": 0,
            "ultima_seq": 0,
        }


def test_sesion_nueva_solo_con_stop(carro):
    host, puerto = carro.direccion
    e = Emisor(host, puerto, sesion=9)
    try:
        e.recibir(50)
        e.seq = 0  # otra sesión que no empieza con STOP
        e.sesion = 10
        e.enviar(e.orden("AVANZAR", 0.4, 0.0))
        r = e.recibir(50)
        assert r[-1].respuesta.motivo == "SESION"
        assert carro.estado["estado"] == "DETENIDO"
    finally:
        e.cerrar()


def test_avanza_con_el_pwm_de_la_placa(carro, emisor):
    r = _avanzar(emisor)
    assert r[-1].respuesta.motivo == "OK"
    assert r[-1].respuesta.estado == "MOVIENDO"
    esperado = a_pwm(0.4, TECHO_PWM, MINIMO_PWM)
    assert (carro.estado["pwm_izq"], carro.estado["pwm_der"]) == (esperado, esperado)


def test_respeta_el_techo():
    with CarroSimulado(puerto=0, techo=120, minimo=80) as c:
        e = Emisor(*c.direccion, sesion=3)
        try:
            e.enviar(e.orden("GIRAR_DER", 1.0, 0.5))
            r = e.recibir(50)[-1].respuesta
            izq, der = lados(1.0, 0.5)
            assert (r.pwm_izq, r.pwm_der) == (a_pwm(izq, 120, 80), a_pwm(der, 120, 80))
            assert max(r.pwm_izq, r.pwm_der) == 120
        finally:
            e.cerrar()


def test_paro_automatico_al_vencer_la_orden(carro, emisor):
    _avanzar(emisor, vigencia_ms=400)
    t_orden = carro.registro[-1]["t_placa_ms"]
    avisos = [r for r in emisor.recibir(700) if r.respuesta.motivo == "VENCIDA"]
    assert len(avisos) == 1
    assert avisos[0].respuesta.estado == "DETENIDO"
    vencida = next(r for r in carro.registro if r["evento"] == "vencida")
    assert 400 <= vencida["t_placa_ms"] - t_orden <= 400 + 10 + MARGEN_MS


def test_tope_de_vigencia_de_500_ms(carro, emisor):
    # La placa no acepta más de 500 ms: la orden sale FUERA_RANGO y frena.
    emisor.enviar(emisor.orden("AVANZAR", 0.4, 0.0, 501))
    assert emisor.recibir(50)[-1].respuesta.motivo == "FUERA_RANGO"
    assert carro.estado["estado"] == "DETENIDO"


@pytest.mark.parametrize(
    ("datos", "motivo"),
    [
        (b"P5C1,basura", "MAL_FORMADA"),
        (b"P5C1,7,99,AVANZAR,1.500,0.000,400", "FUERA_RANGO"),
        (b"P5C1,7,99,AVANZAR,0.400,0.500,400", "INCONSISTENTE"),
        (b"P5C1,7,99,AVANZAR,nan,0.000,400", "MAL_FORMADA"),
    ],
)
def test_rechazo_frena(carro, emisor, datos, motivo):
    _avanzar(emisor)
    assert carro.estado["estado"] == "MOVIENDO"
    emisor.enviar(datos)
    r = emisor.recibir(50)[-1].respuesta
    assert (r.motivo, r.estado) == (motivo, "DETENIDO")
    assert carro.estado["estado"] == "DETENIDO"


@pytest.mark.parametrize("cual", ["repetida", "vieja"])
def test_secuencia_repetida_o_vieja_no_se_aplica(carro, emisor, cual):
    _avanzar(emisor)
    _avanzar(emisor)
    ultima = emisor.seq
    seq = ultima if cual == "repetida" else ultima - 1
    emisor.enviar(f"P5C1,7,{seq},AVANZAR,0.400,0.000,400".encode())
    r = emisor.recibir(50)[-1].respuesta
    assert (r.motivo, r.estado) == ("SEQ_VIEJA", "DETENIDO")
    assert carro.estado["ultima_seq"] == ultima


def test_registra_cada_orden_con_su_hora(carro, emisor, tmp_path):
    _avanzar(emisor)
    emisor.enviar(b"P5C1,basura")
    emisor.recibir(50)
    ordenes = [r for r in carro.registro if r["evento"] == "orden"]
    assert [r["motivo"] for r in ordenes] == ["OK", "OK", "MAL_FORMADA"]
    assert all(isinstance(r["t_placa_ms"], float) for r in ordenes)
    tiempos = [r["t_placa_ms"] for r in ordenes]
    assert tiempos == sorted(tiempos)


def test_bitacora_jsonl(tmp_path):
    ruta = tmp_path / "sim" / "bitacora.jsonl"
    with CarroSimulado(puerto=0, bitacora=ruta) as c:
        e = Emisor(*c.direccion, sesion=5)
        e.recibir(50)
        e.cerrar()
    lineas = [json.loads(x) for x in ruta.read_text(encoding="utf-8").splitlines()]
    assert lineas[0]["evento"] == "encendido"
    assert lineas[-1]["evento"] == "apagado"
    assert sum(1 for x in lineas if x["evento"] == "orden") == 4  # STOP inicial + 3 al cerrar


# -- fallos inyectables ------------------------------------------------------------------
def test_mudo_aplica_pero_no_contesta_y_frena_solo(carro, emisor):
    carro.fallos.mudo = True
    assert _avanzar(emisor) == []
    assert carro.estado["estado"] == "MOVIENDO"
    assert _esperar(lambda: carro.estado["estado"] == "DETENIDO", 400 + MARGEN_MS + 50)
    assert emisor.recibir(50) == []


def test_contesta_tarde(carro, emisor):
    carro.fallos.retardo_ms = 120
    emisor.enviar(emisor.orden("STOP"))
    assert emisor.recibir(60) == []
    r = emisor.recibir(200)
    assert len(r) == 1
    assert r[0].rtt_ms is not None and r[0].rtt_ms >= 120


def test_pierde_todas_las_ordenes(carro, emisor):
    carro.fallos.perdida = 1.0
    assert _avanzar(emisor) == []
    assert carro.estado["estado"] == "DETENIDO"
    assert carro.registro[-1]["evento"] == "perdido"


def test_perdida_parcial_repetible():
    def corrida() -> list[str]:
        with CarroSimulado(puerto=0, fallos=Fallos(perdida=0.5), semilla=42) as c:
            e = Emisor(*c.direccion, sesion=1)
            for _ in range(20):
                e.enviar(e.orden("STOP"))
            e.recibir(100)
            e.cerrar()
            return [r["evento"] for r in c.registro if r["evento"] in ("orden", "perdido")]

    primera = corrida()
    assert "perdido" in primera and "orden" in primera
    assert primera == corrida()


def test_duplicada_se_rechaza_y_frena(carro, emisor):
    carro.fallos.duplicar = True
    motivos = [r.respuesta.motivo for r in _avanzar(emisor)]
    assert motivos == ["OK", "SEQ_VIEJA"]
    assert carro.estado["estado"] == "DETENIDO"


def test_desordenadas_la_vieja_no_se_aplica(carro, emisor):
    _avanzar(emisor)
    carro.fallos.desordenar = True
    vieja = emisor.orden("GIRAR_IZQ", 0.4, -0.5)
    nueva = emisor.orden("AVANZAR", 0.4, 0.0)
    emisor.enviar(vieja)
    emisor.enviar(nueva)
    r = emisor.recibir(80)
    assert [(x.respuesta.seq, x.respuesta.motivo) for x in r] == [
        (nueva.seq, "OK"),
        (vieja.seq, "SEQ_VIEJA"),
    ]
    assert carro.estado["ultima_seq"] == nueva.seq
    assert carro.estado["estado"] == "DETENIDO"  # la vieja no se aplica y además frena


def test_retenido_sin_pareja_se_entrega(carro, emisor):
    carro.fallos.desordenar = True
    emisor.enviar(emisor.orden("STOP"))
    assert emisor.recibir(150) == []  # sigue retenido
    r = emisor.recibir(250)
    assert [x.respuesta.motivo for x in r] == ["OK"]


def test_desordenar_por_omision_invierte_ordenes_a_5_fps(carro, emisor):
    carro.fallos.desordenar = True
    for _ in range(4):
        emisor.enviar(emisor.orden("AVANZAR", 0.4, 0.0))
        time.sleep(0.2)
    emisor.recibir(300)
    motivos = [r["motivo"] for r in carro.registro if r["evento"] == "orden"]
    assert "SEQ_VIEJA" in motivos


def test_wifi_cortado_descarta_lo_retenido(carro, emisor):
    carro.fallos.desordenar = True
    emisor.enviar(emisor.orden("AVANZAR", 0.4, 0.0))
    assert _esperar(lambda: carro.registro[-1]["evento"] == "retenido", 50)
    carro.fallos.wifi_cortado = True
    time.sleep(0.35)  # más que espera_desorden_ms
    assert carro.estado["estado"] == "DETENIDO"
    assert not any(
        r["evento"] == "orden" and r["motivo"] == "OK" and "AVANZAR" in r["datos"]
        for r in carro.registro
    )


def test_wifi_cortado_frena_de_inmediato_y_no_contesta(carro, emisor):
    _avanzar(emisor, vigencia_ms=500)
    carro.fallos.wifi_cortado = True
    assert _esperar(lambda: carro.estado["estado"] == "DETENIDO", 30)
    assert _avanzar(emisor) == []
    assert carro.estado["estado"] == "DETENIDO"
    carro.fallos.wifi_cortado = False
    assert _esperar(lambda: carro.registro[-1]["evento"] == "wifi_vuelve", 50)
    emisor.enviar(emisor.orden("STOP"))
    assert emisor.recibir(50)[-1].respuesta.motivo == "OK"


def test_mudo_calla_tambien_lo_que_estaba_en_cola(carro, emisor):
    carro.fallos.retardo_ms = 100
    emisor.enviar(emisor.orden("STOP"))
    time.sleep(0.02)
    carro.fallos.mudo = True
    assert emisor.recibir(200) == []


def test_datagrama_largo_es_mal_formada_y_frena(carro, emisor):
    _avanzar(emisor)
    emisor.enviar(b"P5C1," + b"9" * 295)  # 300 bytes: en Windows no cabía en el búfer de 256
    r = emisor.recibir(50)[-1].respuesta
    assert (r.motivo, r.estado) == ("MAL_FORMADA", "DETENIDO")
    assert carro.estado["estado"] == "DETENIDO"


def test_byte_no_ascii_y_quien_escucha_falla_no_lo_dejan_sordo():
    def falla(_registro):
        raise UnicodeEncodeError("cp1252", "�", 0, 1, "como print en Windows")

    with CarroSimulado(puerto=0, al_registrar=falla) as c:
        e = Emisor(*c.direccion, sesion=4)
        try:
            e.recibir(50)
            e.enviar(bytes([0xFF]))
            assert e.recibir(50)[-1].respuesta.motivo == "MAL_FORMADA"
            assert c.registro[-1]["datos"] == "\\xff"  # backslashreplace: siempre ASCII
            e.enviar(e.orden("AVANZAR", 0.4, 0.0, 200))
            assert e.recibir(50)[-1].respuesta.motivo == "OK"
            # El paro automático sigue corriendo en el hilo del carro.
            assert _esperar(lambda: c.estado["estado"] == "DETENIDO", 200 + MARGEN_MS + 50)
        finally:
            e.cerrar()


def test_cerrarse_de_golpe(carro, emisor):
    _avanzar(emisor)
    carro.matar()
    assert _avanzar(emisor) == []
    assert carro.registro[-1]["evento"] == "muerto"
    assert carro.estado["estado"] == "DETENIDO"


# -- formato aislado y CLI ---------------------------------------------------------------
def test_solo_formato_conoce_el_protocolo():
    paquete = Path(__file__).resolve().parents[1] / "src" / "simulador"
    for archivo in paquete.glob("*.py"):
        arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        modulos = {
            n.module
            for n in ast.walk(arbol)
            # level 0: import absoluto (`from .carro` es el módulo propio del simulador)
            if isinstance(n, ast.ImportFrom) and n.module is not None and n.level == 0
        } | {a.name for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names}
        usa_carro = any(m == "carro" or m.startswith("carro.") for m in modulos)
        assert usa_carro == (archivo.name == "formato.py"), archivo.name


def test_cli_rechaza_techo_invalido(capsys):
    assert main(["--puerto", "0", "--techo", "300"]) == 2
    assert "--techo" in capsys.readouterr().err


def test_cli_rechaza_perdida_fuera_de_rango():
    with pytest.raises(SystemExit):
        main(["--perdida", "1.5"])


# -- puente de la matriz ---------------------------------------------------------------
def test_puente_mide_el_silencio_desde_el_envio_real(carro, tmp_path):
    """El `ahora_ms` del supervisor se toma antes de procesar el cuadro (el primero tarda
    ~300 ms): con él, el puente avisaba sin que el carro hubiera dejado de contestar."""
    from simulador.puente import AdaptadorPuente

    avisos = []
    puente = AdaptadorPuente(tmp_path, 400, *carro.direccion, al_avisar=avisos.append)
    try:
        stop = {"action": "STOP", "speed": 0, "steering": 0.0}
        puente.enviar(stop, ahora_ms=0.0)  # un ahora_ms muy atrasado
        time.sleep(0.05)
        puente.revisar(ahora_ms=10_000.0)
        assert avisos == []
        carro.fallos.mudo = True
        puente.enviar(stop, ahora_ms=10_000.0)
        assert _esperar(lambda: (puente.revisar(0.0), avisos)[1] != [], 400)
        assert avisos[0]["motivo"] == "carro_sin_respuesta"
        assert avisos[0]["sin_respuesta_ms"] >= 250
    finally:
        puente.cerrar()
