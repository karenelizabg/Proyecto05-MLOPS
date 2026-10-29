import hashlib
import itertools
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

import control.__main__ as correr
from contrato import leer_eventos, validar_comando
from control import Supervisor
from control.__main__ import main
from control.config import cargar_config_politica

RAIZ = Path(__file__).resolve().parents[1]
FLUJO = RAIZ / "config" / "contrato" / "ejemplos" / "flujo.jsonl"
CONFIG = RAIZ / "config" / "control"
PASO_MS = yaml.safe_load((CONFIG / "plazos.yaml").read_text(encoding="utf-8"))["paso_reloj_ms"]
ARCHIVOS = ("detecciones.jsonl", "decisiones.jsonl", "comandos.jsonl", "errores.jsonl")


def leer(ruta: Path) -> list[dict]:
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines() if linea]


def correr_flujo(salida: Path, entrada: Path = FLUJO) -> int:
    return main(["--entrada", str(entrada), "--config", str(CONFIG), "--salida", str(salida)])


def escribir(ruta: Path, eventos: list[dict]) -> Path:
    ruta.write_text("".join(json.dumps(e) + "\n" for e in eventos), encoding="utf-8")
    return ruta


def con_hueco(tmp_path: Path) -> Path:
    """Dos cuadros despejados que B recibe a los 200 y a los 1800 ms: un hueco de 1600 ms."""
    base = leer_eventos(FLUJO)[0]
    eventos = [
        {**base, "frame_id": "S02_f0001", "t_capture_ms": 160, "t_emit_ms": 200},
        {**base, "frame_id": "S02_f0002", "t_capture_ms": 1760, "t_emit_ms": 1800},
    ]
    return escribir(tmp_path / "hueco.jsonl", eventos)


def espiar_reloj(monkeypatch) -> list[tuple[str, float]]:
    llamadas: list[tuple[str, float]] = []
    monkeypatch.setattr(Supervisor, "tick", lambda self, t: llamadas.append(("tick", t)))
    monkeypatch.setattr(Supervisor, "cerrar", lambda self, t: llamadas.append(("cerrar", t)))
    return llamadas


@pytest.fixture
def salida(tmp_path):
    carpeta = tmp_path / "resultados" / "ejemplo-01"
    assert correr_flujo(carpeta) == 0
    return carpeta


# --- corre el flujo de ejemplo ----------------------------------------------


def test_deja_los_cuatro_registros_y_run_json(salida):
    for nombre in (*ARCHIVOS, "run.json"):
        assert (salida / nombre).is_file(), nombre


def test_cada_frame_id_llega_a_un_comando_y_a_una_decision(salida):
    frames = {(e["run_id"], e["frame_id"]) for e in leer(salida / "detecciones.jsonl")}
    assert len(frames) == 5
    for nombre in ("comandos.jsonl", "decisiones.jsonl"):
        enlazados = {(c["run_id"], c["frame_id"]) for c in leer(salida / nombre)}
        assert frames <= enlazados, nombre


def test_todos_los_registros_traen_run_id_y_frame_id(salida):
    for nombre in ARCHIVOS:
        for linea in leer(salida / nombre):
            assert linea["run_id"] == "ejemplo-01", nombre
            assert "frame_id" in linea, nombre


def test_detecciones_son_los_eventos_tal_como_llegaron(salida):
    assert leer(salida / "detecciones.jsonl") == leer_eventos(FLUJO)


def test_todos_los_comandos_cumplen_el_contrato(salida):
    comandos = leer(salida / "comandos.jsonl")
    assert comandos
    for comando in comandos:
        assert validar_comando(comando) == []


def test_decisiones_del_flujo(tmp_path):
    # En el flujo del contrato la mochila de ejemplo es class_id 1. Con las clases definitivas
    # (T12, #32) ese id ya no es obstáculo, así que se cambia por una clase real de politica.yaml.
    obstaculo = min(cargar_config_politica().clases_obstaculo)
    eventos = leer_eventos(FLUJO)
    for evento in eventos:
        for det in evento["detections"]:
            det["class_id"] = obstaculo
    salida = tmp_path / "s"
    assert correr_flujo(salida, escribir(tmp_path / "flujo.jsonl", eventos)) == 0
    decisiones = leer(salida / "decisiones.jsonl")
    assert [(d["frame_id"], d["action"], d["decidio"]) for d in decisiones] == [
        ("S02_f0001", "AVANZAR", "politica"),
        ("S02_f0002", "GIRAR_IZQ", "politica"),
        ("S02_f0003", "GIRAR_IZQ", "politica"),
        ("S02_f0004", "STOP", "supervisor"),
        ("S02_f0005", "STOP", "supervisor"),
        (None, "STOP", "supervisor"),  # cerrar (T06)
    ]
    assert decisiones[-1]["event"] == "shutdown"
    assert decisiones[0]["state_before"] == "DETENIDO"
    assert decisiones[0]["estado"]["nombre"] == "AVANZANDO"
    assert decisiones[3]["propuesta_politica"] is None


def test_errores_del_flujo(salida):
    errores = leer(salida / "errores.jsonl")
    assert [(e["frame_id"], e["motivo"]) for e in errores] == [
        ("S02_f0004", "error_detector:unreadable_image"),
        ("S02_f0005", "stale"),
    ]


def test_run_json_trae_hashes_y_conteos(salida):
    run = json.loads((salida / "run.json").read_text(encoding="utf-8"))
    assert run["run_ids"] == ["ejemplo-01"]
    assert run["entrada"]["sha256"] == hashlib.sha256(FLUJO.read_bytes()).hexdigest()
    for nombre in ("plazos.yaml", "politica.yaml"):
        esperado = hashlib.sha256((CONFIG / nombre).read_bytes()).hexdigest()
        assert run["config"][nombre]["sha256"] == esperado
    assert run["detector"]["model_sha256"] == ["a" * 64]
    assert run["conteos"] == {
        "eventos": 5,
        "comandos": 6,  # 5 cuadros + el STOP de cerrar (T06)
        "comandos_fuera_de_contrato": 0,
        "errores": 2,
    }


def test_la_misma_entrada_deja_los_mismos_archivos(salida, tmp_path):
    otra = tmp_path / "otra"
    assert correr_flujo(otra) == 0
    for nombre in ARCHIVOS:
        assert (otra / nombre).read_text(encoding="utf-8") == (salida / nombre).read_text(
            encoding="utf-8"
        )


def test_correr_dos_veces_en_la_misma_carpeta_no_mezcla(salida):
    assert correr_flujo(salida) == 0
    for nombre, lineas in [("detecciones.jsonl", 5), ("comandos.jsonl", 6), ("errores.jsonl", 2)]:
        assert len(leer(salida / nombre)) == lineas, nombre


def test_entrada_y_salida_en_cualquier_carpeta(tmp_path):
    """El evaluador puede usar sus propias carpetas, fuera del repo."""
    entrada = tmp_path / "evaluador" / "entrada" / "eventos.jsonl"
    entrada.parent.mkdir(parents=True)
    shutil.copy(FLUJO, entrada)
    salida = tmp_path / "evaluador" / "salida" / "run-01"
    assert correr_flujo(salida, entrada) == 0
    assert len(leer(salida / "comandos.jsonl")) == 6


# --- reloj: t_emit_ms, tics cada paso_reloj_ms y cerrar al final ------------------


def test_el_reloj_es_t_emit_ms(salida):
    eventos = leer_eventos(FLUJO)
    comandos = leer(salida / "comandos.jsonl")
    # El último es el STOP de cerrar (T06), en el instante del último cuadro.
    assert [c["t_command_ms"] for c in comandos[:-1]] == [e["t_emit_ms"] for e in eventos]
    assert comandos[-1]["event"] == "shutdown"
    assert comandos[-1]["t_command_ms"] == eventos[-1]["t_emit_ms"]


def test_tics_entre_cuadros_y_cerrar_al_final(tmp_path, monkeypatch):
    llamadas = espiar_reloj(monkeypatch)
    assert correr_flujo(tmp_path / "s") == 0
    tics = [t for nombre, t in llamadas if nombre == "tick"]
    llegadas = [e["t_emit_ms"] for e in leer_eventos(FLUJO)]

    assert tics == sorted(tics)
    assert set(llegadas) <= set(tics)  # un tic justo antes de cada cuadro
    assert all(b - a <= PASO_MS + 1e-9 for a, b in itertools.pairwise(tics))
    assert llamadas[-1] == ("cerrar", llegadas[-1])
    assert [n for n, _ in llamadas].count("cerrar") == 1


def test_hueco_de_200_a_1800_tiene_tics_cada_paso(tmp_path, monkeypatch):
    llamadas = espiar_reloj(monkeypatch)
    assert correr_flujo(tmp_path / "s", con_hueco(tmp_path)) == 0
    tics = [t for nombre, t in llamadas if nombre == "tick"]
    assert tics == pytest.approx([200.0 + PASO_MS * n for n in range(int(1600 / PASO_MS) + 1)])


def test_sin_tics_si_el_reloj_no_avanza(tmp_path, monkeypatch):
    base = leer_eventos(FLUJO)[0]
    eventos = [
        {**base, "frame_id": "S02_f0001", "t_emit_ms": 500},
        {**base, "frame_id": "S02_f0002", "t_emit_ms": 100},  # otra secuencia: reloj atrás
    ]
    llamadas = espiar_reloj(monkeypatch)
    assert correr_flujo(tmp_path / "s", escribir(tmp_path / "e.jsonl", eventos)) == 0
    assert llamadas == [("tick", 500.0), ("tick", 100.0), ("cerrar", 100.0)]


def test_el_stop_de_reloj_sale_a_tiempo_en_un_hueco(tmp_path, monkeypatch):
    """Con un watchdog que vence a los 800 ms (como T05), el STOP sale a los 800, no a los 1800."""

    def tick(self, ahora_ms):
        if ahora_ms < 800 or self.estado["nombre"] == "DETENIDO":
            return None
        comando = {
            "schema_version": "1",
            "run_id": "ejemplo-01",
            "frame_id": None,
            "event": "clock",
            "state_before": self.estado["nombre"],
            "state_after": "DETENIDO",
            "action": "STOP",
            "reason": "watchdog_vencido",
            "speed": 0,
            "steering": 0.0,
            "t_decision_ms": ahora_ms,
        }
        self.estado = {"nombre": "DETENIDO"}
        return self.adaptador.enviar(comando, ahora_ms)

    monkeypatch.setattr(Supervisor, "tick", tick)
    salida = tmp_path / "s"
    assert correr_flujo(salida, con_hueco(tmp_path)) == 0

    reloj = [d for d in leer(salida / "decisiones.jsonl") if d["event"] == "clock"]
    assert len(reloj) == 1
    assert reloj[0]["t_ms"] == pytest.approx(800.0)
    assert reloj[0]["frame_id"] is None
    assert reloj[0]["decidio"] == "supervisor"
    comandos = leer(salida / "comandos.jsonl")
    assert [c["action"] for c in comandos] == ["AVANZAR", "STOP", "AVANZAR", "STOP"]
    assert comandos[-1]["event"] == "shutdown"
    assert all(validar_comando(c) == [] for c in comandos)


def test_rechazo_por_edad_usa_t_emit_ms(tmp_path, monkeypatch):
    """El supervisor recibe ahora_ms = t_emit_ms, así puede medir la edad del cuadro (T05)."""
    edades = []
    original = Supervisor.procesar_evento

    def procesar(self, evento, ahora_ms):
        edades.append(ahora_ms - evento["t_capture_ms"])
        return original(self, evento, ahora_ms)

    monkeypatch.setattr(Supervisor, "procesar_evento", procesar)
    assert correr_flujo(tmp_path / "s") == 0
    assert edades == pytest.approx(
        [e["t_emit_ms"] - e["t_capture_ms"] for e in leer_eventos(FLUJO)]
    )


# --- fallas --------------------------------------------------------------------


def test_comando_fuera_de_contrato_sale_1_y_queda_en_errores(tmp_path, monkeypatch):
    monkeypatch.setattr(correr, "validar_comando", lambda comando: ["speed: inventado"])
    salida = tmp_path / "s"
    assert correr_flujo(salida) == 1
    motivos = [e["motivo"] for e in leer(salida / "errores.jsonl")]
    assert motivos.count("comando_fuera_de_contrato") == 6  # incluye el STOP de cerrar


def test_entrada_que_no_existe_sale_2_sin_escribir_nada(tmp_path):
    salida = tmp_path / "s"
    assert correr_flujo(salida, tmp_path / "no_existe.jsonl") == 2
    assert not salida.exists()


def test_entrada_que_no_es_json_sale_2(tmp_path):
    mala = tmp_path / "malo.jsonl"
    mala.write_text("{no es json\n", encoding="utf-8")
    assert correr_flujo(tmp_path / "s", mala) == 2


@pytest.mark.parametrize(
    ("archivo", "contenido"),
    [
        ("plazos.yaml", None),
        ("plazos.yaml", "max_frame_age_ms: 500\n"),
        ("plazos.yaml", "[no, es, un, mapa]\n"),
        ("politica.yaml", "umbral_confianza: 2\n"),
    ],
)
def test_configuracion_mala_sale_2(tmp_path, archivo, contenido):
    config = tmp_path / "config"
    shutil.copytree(CONFIG, config)
    if contenido is None:
        (config / archivo).unlink()
    else:
        (config / archivo).write_text(contenido, encoding="utf-8")
    salida = tmp_path / "s"
    assert main(["--entrada", str(FLUJO), "--config", str(config), "--salida", str(salida)]) == 2
    assert not salida.exists()


@pytest.mark.parametrize("valor", [0, -100, "100", True])
def test_paso_reloj_invalido_sale_2(tmp_path, valor):
    config = tmp_path / "config"
    shutil.copytree(CONFIG, config)
    plazos = yaml.safe_load((config / "plazos.yaml").read_text(encoding="utf-8"))
    plazos["paso_reloj_ms"] = valor
    (config / "plazos.yaml").write_text(yaml.safe_dump(plazos), encoding="utf-8")
    assert (
        main(["--entrada", str(FLUJO), "--config", str(config), "--salida", str(tmp_path / "s")])
        == 2
    )


def test_un_evento_invalido_tambien_llega_a_un_stop(tmp_path):
    eventos = leer_eventos(FLUJO)[:1]
    eventos.append(
        {
            **eventos[0],
            "frame_id": "S02_f0002",
            "t_capture_ms": 200,
            "t_emit_ms": 230,
            "status": "raro",
        }
    )
    salida = tmp_path / "s"
    assert correr_flujo(salida, escribir(tmp_path / "e.jsonl", eventos)) == 0
    *_, ultimo, cierre = leer(salida / "comandos.jsonl")
    assert (ultimo["frame_id"], ultimo["action"]) == ("S02_f0002", "STOP")
    assert cierre["event"] == "shutdown"


# --- NaN e infinito no son JSON --------------------------------------------------


def no_es_json(constante):
    raise ValueError(f"{constante} no es JSON")


def leer_estricto(ruta: Path) -> list[dict]:
    """Como `leer`, pero falla si una línea trae NaN o Infinity."""
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    return [json.loads(linea, parse_constant=no_es_json) for linea in lineas]


def correr_con(salida: Path, politica) -> correr.Corrida:
    corrida = correr.Corrida(salida, correr.cargar_plazos(CONFIG / "plazos.yaml"), {}, politica)
    for evento in leer_eventos(FLUJO):
        corrida.cuadro(evento)
    corrida.cerrar()
    corrida.escribir_run(FLUJO, CONFIG)
    return corrida


@pytest.mark.parametrize(
    "valor", [math.nan, math.inf, -math.inf], ids=["NaN", "Infinity", "-Infinity"]
)
def test_entrada_con_nan_o_infinity_sale_2_sin_escribir_nada(tmp_path, valor):
    """`json.loads` los acepta, pero no son JSON: la entrada no se puede leer."""
    eventos = leer_eventos(FLUJO)
    eventos[1]["t_emit_ms"] = valor
    salida = tmp_path / "s"
    assert correr_flujo(salida, escribir(tmp_path / "e.jsonl", eventos)) == 2
    assert not salida.exists()


@pytest.mark.parametrize("campo", ["speed", "steering"])
def test_politica_que_propone_nan_da_stop_y_todo_queda_en_json(tmp_path, campo):
    def politica(evento, estado, config):
        propuesta = {"action": "AVANZAR", "speed": 0.5, "steering": 0.0, "reason": "x"}
        propuesta[campo] = math.nan
        return propuesta, {"nombre": "AVANZANDO"}

    corrida = correr_con(tmp_path, politica)

    for nombre in ARCHIVOS:
        leer_estricto(tmp_path / nombre)
    json.loads((tmp_path / "run.json").read_text(encoding="utf-8"), parse_constant=no_es_json)
    comandos = leer(tmp_path / "comandos.jsonl")
    assert all(c["action"] == "STOP" and c["speed"] == 0 for c in comandos)
    assert corrida.invalidos == 0
    primera = leer(tmp_path / "decisiones.jsonl")[0]
    assert (primera["decidio"], primera["reason"]) == ("supervisor", "politica_invalida")
    assert primera["propuesta_politica"][campo] == "nan"


def test_un_estado_con_infinito_queda_como_texto_en_decisiones(tmp_path):
    def politica(evento, estado, config):
        comando = {"action": "AVANZAR", "speed": 0.5, "steering": 0.0, "reason": "x"}
        return comando, {"nombre": "AVANZANDO", "distancia": math.inf}

    correr_con(tmp_path, politica)

    primera = leer_estricto(tmp_path / "decisiones.jsonl")[0]
    assert (primera["decidio"], primera["action"]) == ("politica", "AVANZAR")
    assert primera["estado"] == {"nombre": "AVANZANDO", "distancia": "inf"}


# --- línea de comandos real ----------------------------------------------------


def test_python_m_control_desde_la_raiz(tmp_path):
    salida = tmp_path / "s"
    entorno = {**os.environ, "PYTHONPATH": "src"}
    proceso = subprocess.run(
        [
            sys.executable,
            "-m",
            "control",
            "--entrada",
            str(FLUJO),
            "--config",
            "config/control/",
            "--salida",
            str(salida),
        ],
        cwd=RAIZ,
        env=entorno,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proceso.returncode == 0, proceso.stderr
    assert "5 eventos, 6 comandos, 2 errores" in proceso.stdout
    assert len(leer(salida / "comandos.jsonl")) == 6


# --- acciones.yaml: tick, emergencia, rearmar y cerrar (T17) ----------------------


def con_acciones(tmp_path: Path, acciones: list[dict]) -> Path:
    ruta = tmp_path / "acciones.yaml"
    ruta.write_text(yaml.safe_dump({"acciones": acciones}), encoding="utf-8")
    return ruta


def correr_con_acciones(salida: Path, acciones: Path, entrada: Path = FLUJO) -> int:
    return main(
        [
            *("--entrada", str(entrada), "--config", str(CONFIG)),
            *("--salida", str(salida), "--acciones", str(acciones)),
        ]
    )


def libres(tmp_path: Path, n: int = 4) -> Path:
    """n cuadros despejados a 5 fps: capturados cada 200 ms, recibidos 40 ms después."""
    base = leer_eventos(FLUJO)[0]
    eventos = [
        {
            **base,
            "frame_id": f"S02_f{i + 1:04d}",
            "t_capture_ms": 200 * i,
            "t_emit_ms": 200 * i + 40,
        }
        for i in range(n)
    ]
    return escribir(tmp_path / "libres.jsonl", eventos)


def test_emergencia_y_rearme_en_su_instante_y_en_run_json(tmp_path):
    acciones = con_acciones(
        tmp_path, [{"t_ms": 300, "accion": "emergencia"}, {"t_ms": 500, "accion": "rearmar"}]
    )
    salida = tmp_path / "s"
    assert correr_con_acciones(salida, acciones, libres(tmp_path)) == 0

    comandos = leer(salida / "comandos.jsonl")
    pasos = [(c["event"], c["action"], c["t_command_ms"]) for c in comandos]
    assert pasos == [
        ("frame", "AVANZAR", 40.0),
        ("frame", "AVANZAR", 240.0),
        ("emergency", "STOP", 300.0),
        ("frame", "STOP", 440.0),  # emergencia_activa
        ("rearm", "AVANZAR", 500.0),  # T06: decide con el cuadro de 440, que es fresco
        ("frame", "AVANZAR", 640.0),
        ("shutdown", "STOP", 640.0),
    ]
    assert all(validar_comando(c) == [] for c in comandos)
    run = json.loads((salida / "run.json").read_text(encoding="utf-8"))
    assert run["acciones"]["archivo"]["sha256"] == hashlib.sha256(acciones.read_bytes()).hexdigest()
    assert run["acciones"]["hechas"] == [
        {"accion": "emergencia", "t_ms": 300.0, "comando": 2},
        {"accion": "rearmar", "t_ms": 500.0, "comando": 4},
        {"accion": "cerrar", "t_ms": 640.0, "comando": 6},
    ]
    rearme = leer(salida / "decisiones.jsonl")[4]
    assert (rearme["event"], rearme["decidio"]) == ("rearm", "politica")


def test_una_accion_va_despues_del_cuadro_de_su_mismo_instante(tmp_path):
    acciones = con_acciones(tmp_path, [{"t_ms": 240, "accion": "emergencia"}])
    salida = tmp_path / "s"
    assert correr_con_acciones(salida, acciones, libres(tmp_path, 2)) == 0
    eventos = [c["event"] for c in leer(salida / "comandos.jsonl")]
    assert eventos == ["frame", "frame", "emergency", "shutdown"]


def test_cerrar_en_acciones_no_se_repite_al_final(tmp_path):
    acciones = con_acciones(tmp_path, [{"t_ms": 300, "accion": "cerrar"}])
    salida = tmp_path / "s"
    assert correr_con_acciones(salida, acciones, libres(tmp_path)) == 0
    comandos = leer(salida / "comandos.jsonl")
    assert [c["event"] for c in comandos].count("shutdown") == 1
    cierre, *despues = comandos[2:]
    assert (cierre["event"], cierre["t_command_ms"]) == ("shutdown", 300.0)
    # Los cuadros que llegan después del cierre dan STOP (T06).
    assert [(c["action"], c["reason"]) for c in despues] == [("STOP", "supervisor_cerrado")] * 2


def test_tick_despues_del_ultimo_cuadro_deja_correr_el_reloj(tmp_path):
    """Un hueco al final de la entrada: sin un tick, el run cerraría antes de que venza la orden."""
    acciones = con_acciones(tmp_path, [{"t_ms": 1000, "accion": "tick"}])
    salida = tmp_path / "s"
    assert correr_con_acciones(salida, acciones, libres(tmp_path, 1)) == 0
    comandos = leer(salida / "comandos.jsonl")
    assert [(c["event"], c["action"]) for c in comandos] == [
        ("frame", "AVANZAR"),
        ("clock", "STOP"),
        ("shutdown", "STOP"),
    ]
    # La orden de 40 ms vale hasta 440; el primer tic después es el de 540.
    assert comandos[1]["t_command_ms"] == pytest.approx(540.0)
    hechas = json.loads((salida / "run.json").read_text(encoding="utf-8"))["acciones"]["hechas"]
    assert hechas[0] == {"accion": "tick", "t_ms": 1000.0, "comando": None}


def test_sin_acciones_run_json_solo_trae_el_cierre(salida):
    run = json.loads((salida / "run.json").read_text(encoding="utf-8"))
    assert run["acciones"] == {
        "archivo": None,
        "hechas": [{"accion": "cerrar", "t_ms": 1650.0, "comando": 5}],
    }


@pytest.mark.parametrize(
    "contenido",
    [
        "acciones: [{t_ms: 100, accion: frenar}]\n",
        "acciones: [{t_ms: 300, accion: tick}, {t_ms: 200, accion: tick}]\n",
        "acciones: [{t_ms: -1, accion: tick}]\n",
        "acciones: [{t_ms: .nan, accion: tick}]\n",
        "acciones: [{t_ms: 100}]\n",
        "acciones: [{t_ms: 100, accion: tick, extra: 1}]\n",
        "acciones: [{t_ms: true, accion: tick}]\n",
        "- {t_ms: 100, accion: tick}\n",
    ],
)
def test_acciones_mal_escritas_salen_2_sin_escribir_nada(tmp_path, contenido):
    ruta = tmp_path / "acciones.yaml"
    ruta.write_text(contenido, encoding="utf-8")
    salida = tmp_path / "s"
    assert correr_con_acciones(salida, ruta) == 2
    assert not salida.exists()
