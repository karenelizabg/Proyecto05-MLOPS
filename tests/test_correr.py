import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import control.__main__ as correr
from contrato import leer_eventos, validar_comando
from control import Supervisor
from control.__main__ import main

RAIZ = Path(__file__).resolve().parents[1]
# Relativas a la carpeta de trabajo: cada prueba corre en una copia de config/ (ver abajo).
FLUJO = Path("config") / "contrato" / "ejemplos" / "flujo.jsonl"
CONFIG = Path("config") / "control"
ARCHIVOS = ("detecciones.jsonl", "decisiones.jsonl", "comandos.jsonl", "errores.jsonl")


@pytest.fixture(autouse=True)
def carpeta_de_trabajo(tmp_path, monkeypatch):
    """El comando solo acepta rutas dentro de la carpeta de trabajo: se corre en tmp_path."""
    shutil.copytree(RAIZ / "config", tmp_path / "config")
    monkeypatch.chdir(tmp_path)


def leer(ruta: Path) -> list[dict]:
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines() if linea]


def correr_flujo(salida: Path, entrada: Path = FLUJO) -> int:
    return main(["--entrada", str(entrada), "--config", str(CONFIG), "--salida", str(salida)])


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


def test_decisiones_del_flujo(salida):
    decisiones = leer(salida / "decisiones.jsonl")
    assert [(d["frame_id"], d["action"], d["decidio"]) for d in decisiones] == [
        ("S02_f0001", "AVANZAR", "politica"),
        ("S02_f0002", "GIRAR_IZQ", "politica"),
        ("S02_f0003", "GIRAR_IZQ", "politica"),
        ("S02_f0004", "STOP", "supervisor"),
        ("S02_f0005", "STOP", "supervisor"),
    ]
    assert decisiones[0]["state_before"] == "DETENIDO"
    assert decisiones[0]["estado"]["nombre"] == "AVANZANDO"
    assert decisiones[3]["propuesta_politica"] is None


def test_el_reloj_es_t_capture_ms(salida):
    eventos = leer_eventos(FLUJO)
    comandos = leer(salida / "comandos.jsonl")
    assert [c["t_command_ms"] for c in comandos] == [e["t_capture_ms"] for e in eventos]


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
        "comandos": 5,
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
    for nombre, lineas in [("detecciones.jsonl", 5), ("comandos.jsonl", 5), ("errores.jsonl", 2)]:
        assert len(leer(salida / nombre)) == lineas, nombre


# --- reloj: tick entre cuadros y cerrar al final -----------------------------


def test_tick_antes_de_cada_cuadro_y_cerrar_al_final(tmp_path, monkeypatch):
    llamadas = []
    monkeypatch.setattr(Supervisor, "tick", lambda self, t: llamadas.append(("tick", t)))
    monkeypatch.setattr(Supervisor, "cerrar", lambda self, t: llamadas.append(("cerrar", t)))
    assert correr_flujo(tmp_path / "s") == 0
    assert llamadas == [("tick", t) for t in (0, 200, 400, 600, 800)] + [("cerrar", 800)]


def test_el_stop_de_reloj_queda_registrado(tmp_path, monkeypatch):
    """Cuando tick() mande su STOP (T05), queda en comandos y decisiones con frame_id null."""

    def tick(self, ahora_ms):
        if ahora_ms != 400:
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
    assert correr_flujo(salida) == 0
    reloj = [d for d in leer(salida / "decisiones.jsonl") if d["event"] == "clock"]
    assert len(reloj) == 1
    assert reloj[0]["frame_id"] is None
    assert reloj[0]["decidio"] == "supervisor"
    assert len(leer(salida / "comandos.jsonl")) == 6


# --- fallas --------------------------------------------------------------------


def test_comando_fuera_de_contrato_sale_1_y_queda_en_errores(tmp_path, monkeypatch):
    monkeypatch.setattr(correr, "validar_comando", lambda comando: ["speed: inventado"])
    salida = tmp_path / "s"
    assert correr_flujo(salida) == 1
    motivos = [e["motivo"] for e in leer(salida / "errores.jsonl")]
    assert motivos.count("comando_fuera_de_contrato") == 5


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
    config = tmp_path / "config_mala"
    shutil.copytree(CONFIG, config)
    if contenido is None:
        (config / archivo).unlink()
    else:
        (config / archivo).write_text(contenido, encoding="utf-8")
    salida = tmp_path / "s"
    assert main(["--entrada", str(FLUJO), "--config", str(config), "--salida", str(salida)]) == 2
    assert not salida.exists()


@pytest.mark.parametrize("opcion", ["--entrada", "--config", "--salida"])
@pytest.mark.parametrize("como", ["con_puntos", "absoluta"])
def test_ruta_fuera_de_la_carpeta_de_trabajo_sale_2(tmp_path, opcion, como):
    fuera = tmp_path.parent / f"fuera_{tmp_path.name}"
    # Una copia real fuera de la carpeta de trabajo: se rechaza aunque exista y sea válida.
    shutil.copytree(tmp_path / "config", fuera / "config")
    destino = {
        "--entrada": fuera / FLUJO,
        "--config": fuera / CONFIG,
        "--salida": fuera / "resultados",
    }[opcion]
    ruta = destino if como == "absoluta" else Path("..") / destino.relative_to(tmp_path.parent)
    args = {"--entrada": str(FLUJO), "--config": str(CONFIG), "--salida": "resultados/s"}
    args[opcion] = str(ruta)
    try:
        assert main([x for par in args.items() for x in par]) == 2
        assert not (fuera / "resultados").exists()
        assert not (tmp_path / "resultados").exists()
    finally:
        shutil.rmtree(fuera)


def test_rutas_relativas_dentro_de_la_carpeta_de_trabajo(tmp_path):
    salida = Path("resultados") / "otra" / ".." / "ejemplo-01"
    assert correr_flujo(salida) == 0
    run = json.loads((tmp_path / "resultados" / "ejemplo-01" / "run.json").read_text("utf-8"))
    assert run["entrada"]["ruta"] == FLUJO.as_posix()
    assert run["config"]["plazos.yaml"]["ruta"] == (CONFIG / "plazos.yaml").as_posix()


def test_un_evento_invalido_tambien_llega_a_un_stop(tmp_path):
    eventos = leer_eventos(FLUJO)[:1]
    eventos.append({**eventos[0], "frame_id": "S02_f0002", "t_capture_ms": 200, "status": "raro"})
    entrada = tmp_path / "e.jsonl"
    entrada.write_text("".join(json.dumps(e) + "\n" for e in eventos), encoding="utf-8")
    salida = tmp_path / "s"
    assert correr_flujo(salida, entrada) == 0
    ultimo = leer(salida / "comandos.jsonl")[-1]
    assert (ultimo["frame_id"], ultimo["action"]) == ("S02_f0002", "STOP")


# --- línea de comandos real ----------------------------------------------------


def test_python_m_control_desde_la_carpeta_de_trabajo(tmp_path):
    salida = Path("resultados") / "s"
    entorno = {**os.environ, "PYTHONPATH": str(RAIZ / "src")}
    proceso = subprocess.run(
        [sys.executable, "-m", "control", "--entrada", str(FLUJO), "--config", "config/control/",
         "--salida", str(salida)],
        cwd=tmp_path, env=entorno, capture_output=True, text=True, check=False,
    )
    assert proceso.returncode == 0, proceso.stderr
    assert "5 eventos, 5 comandos, 2 errores" in proceso.stdout
    assert len(leer(salida / "comandos.jsonl")) == 5
