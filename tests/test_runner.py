"""T17 · casos/runner.py: corre C1 a C10 con python -m control y los juzga con su expectativa.

Las expectativas del repo están congeladas (T15): las pruebas que las cambian trabajan en una
copia temporal de casos/.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[1]
CASOS = RAIZ / "casos"
CONFIG = RAIZ / "config" / "control"
NOMBRES = [f"C{n}" for n in range(1, 11)]

# casos/ no es un paquete: se carga el archivo.
_spec = importlib.util.spec_from_file_location("runner_de_casos", CASOS / "runner.py")
runner = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = runner
_spec.loader.exec_module(runner)

CONFIG_POLITICA = runner.cargar_config_politica(CONFIG / "politica.yaml")
LIBRE = json.loads((RAIZ / "config/contrato/ejemplos/vacio.json").read_text(encoding="utf-8"))


def leer(ruta: Path) -> list[dict]:
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines() if linea]


def correr(*argv: str) -> int:
    return runner.main(list(argv))


@pytest.fixture
def copia(tmp_path) -> Path:
    """Copia temporal de casos/ (expectativas, entradas, tramos y acciones)."""
    destino = tmp_path / "casos"
    shutil.copytree(CASOS, destino, ignore=shutil.ignore_patterns("__pycache__"))
    return destino


def cambiar_expectativa(casos: Path, caso: str, cambio) -> None:
    ruta = casos / caso / "expectativa.yaml"
    expectativa = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    cambio(expectativa)
    ruta.write_text(yaml.safe_dump(expectativa, allow_unicode=True), encoding="utf-8")


def cuadro(n: int, **cambios) -> dict:
    """Cuadro despejado n a 5 fps: capturado cada 200 ms y recibido 40 ms después."""
    evento = {**LIBRE, "run_id": "prueba", "sequence_id": "S01", "frame_id": f"S01_f{n:04d}"}
    evento.update(t_capture_ms=200 * n, t_emit_ms=200 * n + 40)
    evento.update(cambios)
    return evento


BOTELLA = 39  # bottle: una de las clases_obstaculo de config/control/politica.yaml


def obstaculo(x1: float, x2: float, confianza: float = 0.9) -> list[dict]:
    return [{"class_id": BOTELLA, "confidence": confianza, "bbox": [x1, 100.0, x2, 400.0]}]


def armar_caso(casos: Path, caso: str, eventos: list[dict], tramos: dict, entrada="real") -> None:
    carpeta = casos / caso
    texto = "".join(json.dumps(e) + "\n" for e in eventos)
    (carpeta / "entrada.jsonl").write_text(texto, encoding="utf-8")
    datos = {"entrada": entrada, "tramos": tramos}
    (carpeta / "tramos.yaml").write_text(yaml.safe_dump(datos), encoding="utf-8")


def veredicto(salida: Path, caso: str) -> dict:
    return json.loads((salida / caso / "veredicto.json").read_text(encoding="utf-8"))


# --- los casos del repo ------------------------------------------------------------


def test_c8_y_c9_armados_pasan(tmp_path):
    salida = tmp_path / "salida"
    assert correr("C8", "C9", "--salida", str(salida)) == 0
    for caso in ("C8", "C9"):
        assert veredicto(salida, caso)["pasa"], veredicto(salida, caso)["motivos"]


def test_tabla_de_los_diez_casos_y_sale_1_si_alguno_falla(tmp_path, capsys):
    salida = tmp_path / "salida"
    assert correr("--salida", str(salida)) == 1
    impreso = capsys.readouterr().out
    filas = [linea.split() for linea in impreso.splitlines()[1:11]]
    assert [f[0] for f in filas] == NOMBRES
    assert all(f[-1] in ("PASA", "FALLA") for f in filas)
    assert (salida / "resumen.txt").read_text(encoding="utf-8") == impreso
    for caso in NOMBRES:
        assert (salida / caso / "veredicto.json").is_file()


def test_el_detalle_apunta_a_la_carpeta_de_salida_que_se_uso(tmp_path, capsys):
    """T18: con --salida fuera del repo, el aviso no manda a buscar en resultados/casos/."""
    salida = tmp_path / "salida"
    correr("C1", "--salida", str(salida))
    assert f"(detalle en {salida / 'Cn' / 'veredicto.json'}):" in capsys.readouterr().out


def test_dentro_del_repo_el_detalle_va_relativo():
    """Así resumen.txt, que se sube, no trae la ruta de la máquina de quien lo corrió."""
    fallo = {"caso": "C1", "entrada": None, "tramos": [], "pasa": False, "motivos": ["x"]}
    assert "(detalle en resultados/casos/Cn/veredicto.json):" in runner.tabla([fallo])


def test_los_registros_quedan_en_resultados_casos_cn(tmp_path):
    salida = tmp_path / "salida"
    correr("C10", "--salida", str(salida))
    for nombre in runner.REGISTROS:
        assert (salida / "C10" / nombre).is_file(), nombre
    run = json.loads((salida / "C10" / "run.json").read_text(encoding="utf-8"))
    assert [a["accion"] for a in run["acciones"]["hechas"]] == ["emergencia", "rearmar", "cerrar"]


@pytest.mark.parametrize("caso", ["C1", "C2", "C3", "C4", "C5", "C7"])
def test_sin_secuencia_real_el_caso_falla_y_lo_dice(tmp_path, caso):
    """Mientras A no entregue las secuencias (P5-09, P5-12), estos casos no pueden pasar."""
    salida = tmp_path / "salida"
    if (CASOS / caso / "entrada.jsonl").is_file():
        pytest.skip(f"{caso} ya tiene entrada")
    assert correr(caso, "--salida", str(salida)) == 1
    [motivo] = veredicto(salida, caso)["motivos"]
    assert "falta entrada.jsonl" in motivo
    assert "secuencia real" in motivo


def test_c10_pasa_porque_el_rearme_solo_quita_la_emergencia(tmp_path):
    """Desde #71 (T06) el rearme manda STOP y reanuda el siguiente cuadro fresco, como pide C10."""
    salida = tmp_path / "salida"
    assert correr("C10", "--salida", str(salida)) == 0
    v = veredicto(salida, "C10")
    assert v["pasa"] is True
    assert v["motivos"] == []


# --- cambiar una expectativa a propósito -------------------------------------------


def test_la_copia_sin_cambios_pasa(copia, tmp_path):
    """Control de las pruebas siguientes: lo que falle es por el cambio, no por la copia."""
    assert correr("C8", "C9", "--casos", str(copia), "--salida", str(tmp_path / "s")) == 0


def test_cambiar_una_expectativa_hace_que_el_runner_salga_distinto_de_0(copia, tmp_path):
    """Como proceso: `python casos/runner.py` sale con 1 si una expectativa ya no se cumple."""

    def pedir_avanzar_con_un_error(expectativa):
        tramo = expectativa["tramos"][0]  # unreadable_image
        tramo["acciones_permitidas"] = ["AVANZAR"]
        tramo["acciones_prohibidas"] = ["STOP"]

    cambiar_expectativa(copia, "C9", pedir_avanzar_con_un_error)
    proceso = subprocess.run(
        [
            sys.executable,
            str(CASOS / "runner.py"),
            "C9",
            *("--casos", str(copia), "--salida", str(tmp_path / "s")),
        ],
        cwd=RAIZ,
        # En Windows la salida a un tubo va en cp1252 si no se pide UTF-8.
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proceso.returncode != 0
    assert proceso.returncode == 1, proceso.stderr
    assert "C9    armada   3/4     FALLA" in proceso.stdout
    assert "unreadable_image: orden 2 (STOP" in proceso.stdout


def _plazo_del_hueco_100(e):
    e["tramos"][1]["plazo_reaccion_ms"] = 100


def _antes_del_hueco_solo_stop(e):
    e["tramos"][0].update(acciones_permitidas=["STOP"], acciones_prohibidas=["AVANZAR"])


def _pedir_stop_de_emergencia(e):
    e["stop_con_evento"] = ["clock", "emergency"]
    e["tramos"].append({**e["tramos"][1], "nombre": "emergencia", "origen": "emergency"})
    e["tramos"][-1].update(plazo_reaccion_ms=0, plazo_desde="evento")


def _error_registrado_en_el_hueco(e):
    e["tramos"][0]["condiciones"] = ["avanzar_con_velocidad", "error_registrado"]


@pytest.mark.parametrize(
    "cambio",
    [
        _plazo_del_hueco_100,
        _antes_del_hueco_solo_stop,
        _pedir_stop_de_emergencia,
        _error_registrado_en_el_hueco,
    ],
)
def test_cualquier_cambio_que_no_se_cumple_falla(copia, tmp_path, cambio):
    cambiar_expectativa(copia, "C8", cambio)
    salida = tmp_path / "s"
    assert correr("C8", "--casos", str(copia), "--salida", str(salida)) == 1
    assert veredicto(salida, "C8")["motivos"]


# --- la carpeta del caso ---------------------------------------------------------


def test_caso_que_pide_secuencia_real_con_entrada_armada_falla(copia, tmp_path):
    eventos = [cuadro(1, detections=obstaculo(250, 400)), cuadro(2, detections=obstaculo(250, 400))]
    tramos = {"obstaculo": ["S01_f0001", "S01_f0002"]}
    salida = tmp_path / "s"

    armar_caso(copia, "C2", eventos, tramos, entrada="real")
    assert correr("C2", "--casos", str(copia), "--salida", str(salida)) == 0

    armar_caso(copia, "C2", eventos, tramos, entrada="armada")
    assert correr("C2", "--casos", str(copia), "--salida", str(salida)) == 1
    [motivo] = veredicto(salida, "C2")["motivos"]
    assert "pide una secuencia real" in motivo


@pytest.mark.parametrize(
    ("tramos", "dice"),
    [
        ({"libre": ["S01_f0001"], "otro": ["S01_f0002"]}, "lista los cuadros"),
        ({}, "lista los cuadros"),
        ({"libre": []}, "al menos un frame_id"),
        ({"libre": ["S01_f0009"]}, "no está en entrada.jsonl"),
    ],
)
def test_tramos_que_no_corresponden_fallan_sin_correr(copia, tmp_path, tramos, dice):
    armar_caso(copia, "C1", [cuadro(1), cuadro(2)], tramos)
    salida = tmp_path / "s"
    assert correr("C1", "--casos", str(copia), "--salida", str(salida)) == 1
    v = veredicto(salida, "C1")
    assert dice in v["motivos"][0]
    assert v["tramos"] == []
    assert not (salida / "C1" / "comandos.jsonl").exists()


def test_cuadro_en_dos_tramos_falla(copia, tmp_path):
    expectativa = yaml.safe_load((copia / "C6" / "expectativa.yaml").read_text(encoding="utf-8"))
    assert [t["nombre"] for t in expectativa["tramos"]] == ["bajo_umbral", "sobre_umbral"]
    armar_caso(
        copia, "C6", [cuadro(1)], {"bajo_umbral": ["S01_f0001"], "sobre_umbral": ["S01_f0001"]}
    )
    salida = tmp_path / "s"
    assert correr("C6", "--casos", str(copia), "--salida", str(salida)) == 1
    assert "más de un tramo" in veredicto(salida, "C6")["motivos"][0]


def test_entrada_fuera_de_contrato_falla(copia, tmp_path):
    armar_caso(copia, "C1", [cuadro(1, status="raro")], {"libre": ["S01_f0001"]})
    salida = tmp_path / "s"
    assert correr("C1", "--casos", str(copia), "--salida", str(salida)) == 1
    assert "no cumple el contrato" in veredicto(salida, "C1")["motivos"][0]


def test_sin_tramos_yaml_falla(copia, tmp_path):
    (copia / "C9" / "tramos.yaml").unlink()
    salida = tmp_path / "s"
    assert correr("C9", "--casos", str(copia), "--salida", str(salida)) == 1
    assert veredicto(salida, "C9")["motivos"] == ["falta tramos.yaml"]


def test_un_caso_que_no_corre_borra_los_registros_anteriores(copia, tmp_path):
    salida = tmp_path / "s"
    assert correr("C9", "--casos", str(copia), "--salida", str(salida)) == 0
    (copia / "C9" / "entrada.jsonl").unlink()
    assert correr("C9", "--casos", str(copia), "--salida", str(salida)) == 1
    assert sorted(p.name for p in (salida / "C9").iterdir()) == ["veredicto.json"]


def test_caso_desconocido_es_un_error_de_uso():
    with pytest.raises(SystemExit) as salida:
        correr("C11")
    assert salida.value.code == 2


def test_configuracion_que_no_se_lee_sale_2(tmp_path):
    assert correr("--config", str(tmp_path / "no_existe"), "--salida", str(tmp_path / "s")) == 2


# --- casos C1 a C7 con eventos armados: el runner juzga cada regla -------------------
# Solo prueban al runner. Las secuencias reales de esos casos las entrega A (P5-12).


def test_c1_via_libre_pasa(copia, tmp_path):
    armar_caso(
        copia,
        "C1",
        [cuadro(n) for n in range(1, 6)],
        {"libre": [f"S01_f{n:04d}" for n in range(1, 6)]},
    )
    assert correr("C1", "--casos", str(copia), "--salida", str(tmp_path / "s")) == 0


def test_c1_falla_si_el_cuadro_llega_tarde(copia, tmp_path):
    """El primer cuadro llega a los 520 ms de su captura: la orden sale fuera del plazo de 500."""
    eventos = [cuadro(1, t_emit_ms=200 + 520), cuadro(2, t_emit_ms=400 + 460)]
    armar_caso(copia, "C1", eventos, {"libre": ["S01_f0001", "S01_f0002"]})
    salida = tmp_path / "s"
    assert correr("C1", "--casos", str(copia), "--salida", str(salida)) == 1
    motivos = veredicto(salida, "C1")["motivos"]
    # El supervisor lo rechaza por viejo (STOP, prohibido en C1) y el AVANZAR sale tarde.
    assert any("STOP está prohibida" in m for m in motivos)
    assert any("el plazo es 500" in m for m in motivos)


def test_c3_un_obstaculo_a_la_izquierda_no_hace_girar_a_la_izquierda(copia, tmp_path):
    # Toca el centro cargado a la izquierda: la política gira a la derecha (T16).
    eventos = [cuadro(n, detections=obstaculo(100, 300)) for n in (1, 2)]
    armar_caso(copia, "C3", eventos, {"obstaculo_izq": ["S01_f0001", "S01_f0002"]})
    salida = tmp_path / "s"
    assert correr("C3", "--casos", str(copia), "--salida", str(salida)) == 0
    comandos = leer(salida / "C3" / "comandos.jsonl")
    assert [c["action"] for c in comandos[:2]] == ["GIRAR_DER", "GIRAR_DER"]


def test_c5_sin_zona_libre_pasa(copia, tmp_path):
    eventos = [cuadro(n, detections=obstaculo(0, 640)) for n in (1, 2, 3)]
    armar_caso(copia, "C5", eventos, {"sin_zona_libre": ["S01_f0001", "S01_f0002", "S01_f0003"]})
    assert correr("C5", "--casos", str(copia), "--salida", str(tmp_path / "s")) == 0


def test_c6_debajo_y_encima_del_umbral(copia, tmp_path):
    umbral = CONFIG_POLITICA.umbral_confianza
    eventos = [cuadro(1, detections=obstaculo(250, 400, umbral - 0.1))]
    eventos += [cuadro(2, detections=obstaculo(250, 400, umbral))]
    armar_caso(copia, "C6", eventos, {"bajo_umbral": ["S01_f0001"], "sobre_umbral": ["S01_f0002"]})
    assert correr("C6", "--casos", str(copia), "--salida", str(tmp_path / "s")) == 0


def c7(bloqueo: list[dict]) -> tuple[list[dict], dict]:
    """C7 a 5 fps: 3 libres, 3 de bloqueo, 1 libre, 2 de bloqueo y 5 libres."""
    partes = [("libre", 3, []), ("bloqueo", 3, bloqueo), ("un_cuadro_libre", 1, [])]
    partes += [("bloqueo_otra_vez", 2, bloqueo), ("libre_otra_vez", 5, [])]
    eventos, tramos, n = [], {}, 1
    for nombre, cuantos, detecciones in partes:
        tramos[nombre] = []
        for _ in range(cuantos):
            eventos.append(cuadro(n, detections=detecciones))
            tramos[nombre].append(f"S01_f{n:04d}")
            n += 1
    return eventos, tramos


def test_c7_con_un_bloqueo_que_tapa_todo_pasa(copia, tmp_path):
    armar_caso(copia, "C7", *c7(obstaculo(0, 640)))
    salida = tmp_path / "s"
    assert correr("C7", "--casos", str(copia), "--salida", str(salida)) == 0, veredicto(
        salida, "C7"
    )


def test_c7_un_bloqueo_que_deja_girar_pasa(copia, tmp_path):
    """Tras un giro, la espera de N cuadros libres también empieza (#69) y, mientras espera,
    la política repite la última acción (#72): el cuadro libre suelto sigue girando hacia el
    lado libre, no avanza ni da STOP. Con un bloqueo que deja girar, C7 pasa completo."""
    armar_caso(copia, "C7", *c7(obstaculo(250, 400)))
    salida = tmp_path / "s"
    assert correr("C7", "--casos", str(copia), "--salida", str(salida)) == 0
    assert [t["tramo"] for t in veredicto(salida, "C7")["tramos"] if t["motivos"]] == []


# --- cada regla del juez, con órdenes escritas a mano -------------------------------


def orden(action: str, t: float, event: str = "frame", frame_id: str | None = None, **extra):
    speed = 0.4 if action != "STOP" else 0
    return {
        "action": action,
        "event": event,
        "frame_id": frame_id,
        "t_command_ms": t,
        "speed": speed,
        **extra,
    }


def registros(comandos, eventos=(), errores=(), acciones=()):
    eventos = list(eventos)
    return runner.Registros(
        comandos=list(comandos),
        errores=list(errores),
        eventos={e["frame_id"]: e for e in eventos},
        llegada={e["frame_id"]: n for n, e in enumerate(eventos)},
        acciones=list(acciones),
    )


def tramo(**campos):
    base = {
        "nombre": "t",
        "origen": "cuadros",
        "cuadros": "x",
        "acciones_permitidas": ["STOP"],
        "acciones_prohibidas": ["AVANZAR"],
        "plazo_reaccion_ms": None,
        "plazo_desde": None,
    }
    return {**base, **campos}


def juzgar(tramos, reg, cuadros):
    expectativa = {"tramos": tramos, "stop_con_evento": []}
    return {
        r["tramo"]: r["motivos"] for r in runner.juzgar(expectativa, cuadros, reg, CONFIG_POLITICA)
    }


def test_antes_de_reaccionar_vale_lo_no_prohibido_y_despues_solo_lo_permitido():
    eventos = [cuadro(n) for n in (1, 2, 3, 4)]
    t = tramo(
        acciones_permitidas=["AVANZAR"],
        acciones_prohibidas=[],
        plazo_reaccion_ms=500,
        plazo_desde="captura",
    )
    ids = [e["frame_id"] for e in eventos]
    bien = [orden("STOP", 240, frame_id=ids[0]), orden("AVANZAR", 440, frame_id=ids[1])]
    bien += [orden("AVANZAR", 640, frame_id=ids[2]), orden("AVANZAR", 840, frame_id=ids[3])]
    assert juzgar([t], registros(bien, eventos), {"t": ids}) == {"t": []}

    mal = [*bien[:2], orden("STOP", 640, frame_id=ids[2]), bien[3]]
    [motivo] = juzgar([t], registros(mal, eventos), {"t": ids})["t"]
    assert "orden 3" in motivo
    assert "después de reaccionar" in motivo


def test_sin_plazo_cada_cuadro_deja_una_orden():
    eventos = [cuadro(1), cuadro(2)]
    reg = registros([orden("STOP", 240, frame_id="S01_f0001")], eventos)
    [motivo] = juzgar([tramo()], reg, {"t": ["S01_f0001", "S01_f0002"]})["t"]
    assert motivo == "el cuadro S01_f0002 no dejó ninguna orden"


def test_tramo_de_evento_sin_ordenes_y_sin_plazo_pasa():
    eventos = [cuadro(1), cuadro(2)]
    t1, t3 = tramo(nombre="a"), tramo(nombre="c")
    rearme = tramo(nombre="b", origen="rearm")
    comandos = [orden("STOP", 240, frame_id="S01_f0001"), orden("STOP", 440, frame_id="S01_f0002")]
    resultado = juzgar(
        [t1, rearme, t3], registros(comandos, eventos), {"a": ["S01_f0001"], "c": ["S01_f0002"]}
    )
    assert resultado == {"a": [], "b": [], "c": []}


def test_tramo_de_evento_solo_toma_las_ordenes_entre_sus_vecinos():
    eventos = [cuadro(1), cuadro(2)]
    reloj = tramo(
        nombre="hueco", origen="clock", plazo_reaccion_ms=600, plazo_desde="ultimo_cuadro"
    )
    comandos = [
        orden("AVANZAR", 240, frame_id="S01_f0001"),
        orden("STOP", 740, event="clock"),
        orden("AVANZAR", 1040, frame_id="S01_f0002"),
        orden("AVANZAR", 1500, event="clock"),  # después del tramo siguiente: no se juzga aquí
    ]
    antes = tramo(nombre="antes", acciones_permitidas=["AVANZAR"], acciones_prohibidas=[])
    despues = tramo(nombre="despues", acciones_permitidas=["AVANZAR"], acciones_prohibidas=[])
    cuadros = {"antes": ["S01_f0001"], "despues": ["S01_f0002"]}
    reg = registros(comandos, eventos)
    assert juzgar([antes, reloj, despues], reg, cuadros) == {
        "antes": [],
        "hueco": [],
        "despues": [],
    }

    tarde = [comandos[0], orden("STOP", 900, event="clock"), *comandos[2:]]
    [motivo] = juzgar([antes, reloj, despues], registros(tarde, eventos), cuadros)["hueco"]
    assert "sale a los 660 ms; el plazo es 600" in motivo  # medido desde t_emit_ms del cuadro 1


def test_plazo_desde_el_evento_usa_el_instante_de_la_accion():
    eventos = [cuadro(1)]
    emergencia = tramo(nombre="e", origen="emergency", plazo_reaccion_ms=0, plazo_desde="evento")
    a_tiempo = [orden("AVANZAR", 240, frame_id="S01_f0001"), orden("STOP", 300, event="emergency")]
    acciones = [{"accion": "emergencia", "t_ms": 300, "comando": 1}]
    antes = tramo(nombre="a", acciones_permitidas=["AVANZAR"], acciones_prohibidas=[])
    assert (
        juzgar(
            [antes, emergencia],
            registros(a_tiempo, eventos, acciones=acciones),
            {"a": ["S01_f0001"]},
        )["e"]
        == []
    )

    sin_accion = registros(a_tiempo, eventos)
    [motivo] = juzgar([antes, emergencia], sin_accion, {"a": ["S01_f0001"]})["e"]
    assert "no hay desde dónde medir el plazo" in motivo


def test_mantener_accion_compara_con_la_orden_anterior_al_tramo():
    eventos = [cuadro(1), cuadro(2), cuadro(3)]
    previo = tramo(nombre="p")
    mantener = tramo(
        nombre="m",
        acciones_permitidas=["AVANZAR"],
        acciones_prohibidas=[],
        plazo_reaccion_ms=1000,
        plazo_desde="captura",
        mantener_accion_cuadros=1,
    )
    cuadros = {"p": ["S01_f0001"], "m": ["S01_f0002", "S01_f0003"]}
    bien = [
        orden("STOP", 240, frame_id="S01_f0001"),
        orden("STOP", 440, frame_id="S01_f0002"),
        orden("AVANZAR", 640, frame_id="S01_f0003"),
    ]
    assert juzgar([previo, mantener], registros(bien, eventos), cuadros)["m"] == []

    mal = [bien[0], orden("AVANZAR", 440, frame_id="S01_f0002"), bien[2]]
    [motivo] = juzgar([previo, mantener], registros(mal, eventos), cuadros)["m"]
    assert "los primeros 1 cuadros mantienen STOP" in motivo


@pytest.mark.parametrize(
    ("accion", "steering", "pasa"), [("GIRAR_DER", 0.5, True), ("GIRAR_IZQ", -0.5, False)]
)
def test_giro_hacia_zona_libre_usa_las_zonas_de_politica_yaml(accion, steering, pasa):
    # Obstáculo al centro y a la izquierda: solo la derecha está libre.
    eventos = [cuadro(1, detections=obstaculo(100, 400))]
    t = tramo(
        acciones_permitidas=["STOP", "GIRAR_IZQ", "GIRAR_DER"],
        condiciones=["giro_hacia_zona_libre"],
    )
    reg = registros([orden(accion, 240, frame_id="S01_f0001", steering=steering)], eventos)
    motivos = juzgar([t], reg, {"t": ["S01_f0001"]})["t"]
    assert (motivos == []) is pasa
    if not pasa:
        assert "zona izq, que está ocupada" in motivos[0]


def test_avanzar_con_velocidad_cero_falla():
    eventos = [cuadro(1)]
    t = tramo(
        acciones_permitidas=["AVANZAR"],
        acciones_prohibidas=[],
        condiciones=["avanzar_con_velocidad"],
    )
    reg = registros([orden("AVANZAR", 240, frame_id="S01_f0001", speed=0)], eventos)
    [motivo] = juzgar([t], reg, {"t": ["S01_f0001"]})["t"]
    assert "speed 0, no > 0" in motivo


def test_error_registrado_pide_run_id_y_frame_id():
    eventos = [cuadro(1, status="stale")]
    t = tramo(condiciones=["error_registrado"])
    comandos = [orden("STOP", 240, frame_id="S01_f0001")]
    otro_run = [{"run_id": "otro", "frame_id": "S01_f0001"}]
    [motivo] = juzgar([t], registros(comandos, eventos, otro_run), {"t": ["S01_f0001"]})["t"]
    assert "no quedó en errores.jsonl" in motivo
    mismo = [{"run_id": "prueba", "frame_id": "S01_f0001"}]
    assert juzgar([t], registros(comandos, eventos, mismo), {"t": ["S01_f0001"]})["t"] == []


def test_es_el_ultimo_comando():
    eventos = [cuadro(1)]
    antes = tramo(nombre="a", acciones_permitidas=["AVANZAR"], acciones_prohibidas=[])
    cierre = tramo(nombre="c", origen="shutdown", condiciones=["es_el_ultimo_comando"])
    comandos = [orden("AVANZAR", 240, frame_id="S01_f0001"), orden("STOP", 240, event="shutdown")]
    assert juzgar([antes, cierre], registros(comandos, eventos), {"a": ["S01_f0001"]})["c"] == []

    despues = [*comandos, orden("STOP", 300, event="clock")]
    [motivo] = juzgar([antes, cierre], registros(despues, eventos), {"a": ["S01_f0001"]})["c"]
    assert "no es la última del run" in motivo


def test_stop_con_evento():
    reg = registros([orden("STOP", 0, event="clock"), orden("AVANZAR", 10, event="emergency")])
    assert runner.revisar_stop_con_evento({"stop_con_evento": ["clock"]}, reg) == []
    motivos = runner.revisar_stop_con_evento({"stop_con_evento": ["emergency", "shutdown"]}, reg)
    assert motivos == [
        "stop_con_evento: ninguna orden STOP con event=emergency",
        "stop_con_evento: ninguna orden STOP con event=shutdown",
    ]
