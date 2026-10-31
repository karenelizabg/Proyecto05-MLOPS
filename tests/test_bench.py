import csv
import hashlib
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

from bench import (
    ETAPAS,
    DetectorFalso,
    ErrorBench,
    EtapaPolitica,
    arnes,
    cargar_entradas,
    ejecutar_una,
    medir,
    percentil,
    resumir_etapas,
    verificar_procedencia,
)
from bench.__main__ import main
from bench.arnes import energia, hardware

FALSO = DetectorFalso()
RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def en_corriente(monkeypatch):
    # Las pruebas no dependen de si la compu que las corre está en batería.
    monkeypatch.setattr("bench.__main__.energia", lambda: "corriente")


@pytest.fixture
def imagenes(tmp_path):
    carpeta = tmp_path / "cuadros"
    carpeta.mkdir()
    for i in range(5):
        cuerpo = hashlib.sha256(str(i).encode()).digest() * 4
        (carpeta / f"f{i:02d}.jpg").write_bytes(b"\xff\xd8" + cuerpo + b"\xff\xd9")
    return carpeta


def leer_csv(ruta):
    with ruta.open(encoding="utf-8", newline="") as archivo:
        return list(csv.DictReader(archivo))


def correr(imagenes, salida, *extra):
    return main(
        [
            "--entradas",
            str(imagenes),
            "--salida",
            str(salida),
            "--equipo",
            "pruebas",
            "--model-sha256",
            FALSO.model_sha256,
            "--config-sha256",
            FALSO.config_sha256,
            # El detector falso no tiene pesos: solo se puede medir en modo de prueba.
            "--prueba",
            *extra,
        ]
    )


# --- Criterio 1: 10 calentamientos + 100 válidas, y rechaza una configuración distinta ----------


def test_diez_calentamientos_y_cien_validas(imagenes, tmp_path):
    salida = tmp_path / "run"
    # 1: el detector falso siempre deja la advertencia de que no es la medición final.
    assert correr(imagenes, salida) == 1

    ejecuciones = leer_csv(salida / "ejecuciones.csv")
    assert [e["fase"] for e in ejecuciones] == ["calentamiento"] * 10 + ["medicion"] * 100
    assert leer_csv(salida / "fallos.csv") == []

    resumen = json.loads((salida / "resumen.json").read_text(encoding="utf-8"))
    assert resumen["estado"] == "completo"
    assert resumen["conteos"] == {"calentamientos": 10, "mediciones": 100, "fallos": 0}
    assert set(resumen["etapas"]) == set(ETAPAS)
    for etapa in resumen["etapas"].values():
        assert etapa["n"] == 100
        assert etapa["minimo"] <= etapa["p50"] <= etapa["p95"] <= etapa["maximo"]
    assert resumen["procedencia"]["detector"]["comprobada"] is False
    assert resumen["advertencias"] == [
        "modo de prueba (--prueba): no es la medición del entregable",
        "detector falso: prueba el arnés, no es la medición del entregable",
        "pesos no verificados: el detector no tiene archivo de pesos",
    ]
    assert (
        resumen["archivos"]["ejecuciones.csv"]
        == hashlib.sha256((salida / "ejecuciones.csv").read_bytes()).hexdigest()
    )


def test_rechaza_una_configuracion_distinta(imagenes, tmp_path):
    salida = tmp_path / "run"
    # El umbral cambia config_sha256: ya no es la configuración congelada.
    assert correr(imagenes, salida, "--opcion", "umbral=0.4") == 2
    assert not salida.exists()


def test_en_bateria_mide_pero_avisa(imagenes, tmp_path, monkeypatch):
    monkeypatch.setattr("bench.__main__.energia", lambda: "bateria")
    salida = tmp_path / "run"
    assert correr(imagenes, salida) == 1
    resumen = json.loads((salida / "resumen.json").read_text(encoding="utf-8"))
    assert resumen["energia"] == "bateria"
    assert any("batería" in a for a in resumen["advertencias"])


@pytest.mark.parametrize("falta", ["--model-sha256", "--config-sha256"])
def test_sin_hashes_no_mide(imagenes, tmp_path, falta):
    argumentos = {
        "--model-sha256": FALSO.model_sha256,
        "--config-sha256": FALSO.config_sha256,
    }
    del argumentos[falta]
    salida = tmp_path / "run"
    with pytest.raises(SystemExit) as error:
        main(
            ["--entradas", str(imagenes), "--salida", str(salida)]
            + [x for par in argumentos.items() for x in par]
        )
    assert error.value.code == 2
    assert not salida.exists()


def test_modo_de_prueba_sin_hashes(imagenes, tmp_path):
    salida = tmp_path / "run"
    argumentos = ["--entradas", str(imagenes), "--salida", str(salida), "--prueba"]
    assert main(argumentos) == 1
    resumen = json.loads((salida / "resumen.json").read_text(encoding="utf-8"))
    assert resumen["protocolo"]["prueba"] is True
    assert resumen["procedencia"]["detector"]["comprobada"] is False
    assert any("modo de prueba" in a for a in resumen["advertencias"])


def test_registra_la_configuracion_de_b(imagenes, tmp_path):
    original = RAIZ / "config" / "control"
    copia = tmp_path / "control"
    copia.mkdir()
    for nombre in ("plazos.yaml", "politica.yaml"):
        (copia / nombre).write_bytes((original / nombre).read_bytes())

    correr(imagenes, tmp_path / "a", "--config-control", str(copia))
    texto = (copia / "politica.yaml").read_text(encoding="utf-8")
    (copia / "politica.yaml").write_text(texto + "\n# cambio\n", encoding="utf-8")
    correr(imagenes, tmp_path / "b", "--config-control", str(copia))

    def config_b(run):
        resumen = json.loads((tmp_path / run / "resumen.json").read_text(encoding="utf-8"))
        return resumen["procedencia"]["config_b"]

    a, b = config_b("a"), config_b("b")
    assert a["carpeta"] == "control"
    assert a["comparada_con_referencia"] is False
    assert a["plazos.yaml"] == b["plazos.yaml"]
    assert a["politica.yaml"] != b["politica.yaml"]
    assert (
        a["politica.yaml"] == hashlib.sha256((original / "politica.yaml").read_bytes()).hexdigest()
    )


def test_configuracion_de_b_que_no_se_puede_leer(imagenes, tmp_path):
    salida = tmp_path / "run"
    assert correr(imagenes, salida, "--config-control", str(tmp_path / "no-existe")) == 2
    assert not salida.exists()


class DetectorConPesos:
    """Un detector cualquiera (no el falso) con archivo de pesos, para la ruta oficial."""

    def __init__(self, ruta_pesos):
        self._falso = DetectorFalso()
        self.ruta_pesos = ruta_pesos
        self.model_sha256 = hashlib.sha256(Path(ruta_pesos).read_bytes()).hexdigest()
        self.config_sha256 = self._falso.config_sha256

    def __getattr__(self, nombre):
        return getattr(self._falso, nombre)


@pytest.fixture
def detector_con_pesos(tmp_path, monkeypatch):
    pesos = tmp_path / "pesos.onnx"
    pesos.write_bytes(b"pesos congelados")
    modulo = types.ModuleType("detector_con_pesos")
    modulo.crear = lambda **opciones: DetectorConPesos(pesos)
    monkeypatch.setitem(sys.modules, "detector_con_pesos", modulo)
    return hashlib.sha256(b"pesos congelados").hexdigest()


def oficial(imagenes, salida, model_sha256, *extra):
    return main(
        [
            "--entradas", str(imagenes), "--salida", str(salida), "--equipo", "pruebas",
            "--detector", "detector_con_pesos",
            "--model-sha256", model_sha256, "--config-sha256", FALSO.config_sha256,
            *extra,
        ]
    )  # fmt: skip


def test_medicion_oficial_con_pesos_verificados(imagenes, tmp_path, detector_con_pesos):
    salida = tmp_path / "run"
    assert oficial(imagenes, salida, detector_con_pesos) == 0
    resumen = json.loads((salida / "resumen.json").read_text(encoding="utf-8"))
    detector = resumen["procedencia"]["detector"]
    assert detector["comprobada"] is True
    assert detector["pesos"] == {
        "ruta": "pesos.onnx",
        "bytes": len(b"pesos congelados"),
        "sha256": detector_con_pesos,
    }
    assert resumen["protocolo"]["prueba"] is False
    assert resumen["advertencias"] == []


def test_medicion_oficial_sin_pesos_no_se_hace(imagenes, tmp_path):
    # El caso de la revisión: hashes que coinciden, pero ningún checkpoint que comprobar.
    salida = tmp_path / "run"
    argumentos = [
        "--entradas", str(imagenes), "--salida", str(salida), "--equipo", "pruebas",
        "--model-sha256", FALSO.model_sha256, "--config-sha256", FALSO.config_sha256,
    ]  # fmt: skip
    assert main(argumentos) == 2
    assert not salida.exists()


def test_pesos_que_no_existen(tmp_path):
    detector = DetectorFalso()
    detector.ruta_pesos = tmp_path / "no-existe.onnx"
    with pytest.raises(ErrorBench, match="no existe el archivo de pesos"):
        verificar_procedencia(detector, None, None)


def test_rechaza_otro_modelo():
    with pytest.raises(ErrorBench, match="model_sha256"):
        verificar_procedencia(FALSO, "0" * 64, FALSO.config_sha256, prueba=True)


def test_sin_hashes_mide_pero_avisa():
    procedencia, advertencias = verificar_procedencia(FALSO, None, None, prueba=True)
    assert procedencia["comprobada"] is False
    assert len(advertencias) == 3


def test_pesos_que_no_coinciden_con_el_detector(tmp_path):
    pesos = tmp_path / "pesos.onnx"
    pesos.write_bytes(b"otros pesos")
    detector = DetectorFalso()
    detector.ruta_pesos = pesos
    with pytest.raises(ErrorBench, match="SHA-256"):
        verificar_procedencia(detector, None, None, prueba=True)


def test_pesos_se_registran_con_tamano_y_hash(tmp_path):
    pesos = tmp_path / "pesos.onnx"
    pesos.write_bytes(b"pesos")
    detector = DetectorFalso()
    detector.ruta_pesos = pesos
    detector.model_sha256 = hashlib.sha256(b"pesos").hexdigest()
    procedencia, _ = verificar_procedencia(detector, detector.model_sha256, None)
    assert procedencia["pesos"]["bytes"] == 5
    # Sin rutas personales: fuera del repo solo queda el nombre del archivo.
    assert procedencia["pesos"]["ruta"] == "pesos.onnx"
    assert procedencia["pesos"]["sha256"] == detector.model_sha256


# --- Criterio 2: una ejecución fallida queda aparte y no entra en p50/p95 ------------------------


def test_fallos_quedan_aparte(imagenes):
    detector = DetectorFalso(fallar_en=frozenset({3, 50}), salida_invalida_en=frozenset({70}))
    entradas = cargar_entradas(detector, sorted(imagenes.iterdir()))
    medicion = medir(detector, entradas)

    assert medicion.completa
    assert len(medicion.ejecuciones) == 110
    assert [(f["intento"], f["fase"], f["etapa"]) for f in medicion.fallos] == [
        (3, "calentamiento", "inferencia"),
        (50, "medicion", "inferencia"),
        (70, "medicion", "salida"),
    ]
    assert medicion.fallos[0]["error"] == "FalloInyectado"
    intentos_validos = {e["intento"] for e in medicion.ejecuciones}
    assert intentos_validos.isdisjoint({3, 50, 70})
    assert resumir_etapas(medicion.ejecuciones)["total_ms"]["n"] == 100


def test_un_fallo_al_armar_el_evento_queda_aparte(imagenes, monkeypatch):
    llamadas = []

    def dimensiones(self, imagen):
        llamadas.append(1)
        if len(llamadas) == 5:
            raise RuntimeError("no se pudo leer el tamaño")
        return 640, 480

    monkeypatch.setattr(DetectorFalso, "dimensiones", dimensiones)
    entradas = cargar_entradas(FALSO, sorted(imagenes.iterdir()))
    medicion = medir(DetectorFalso(), entradas)
    assert medicion.completa
    assert [(f["intento"], f["etapa"], f["error"]) for f in medicion.fallos] == [
        (5, "evento", "RuntimeError")
    ]


def test_una_falla_de_la_politica_queda_aparte(imagenes):
    def politica(evento, ahora_ms):
        raise RuntimeError("B se cayó")

    entradas = cargar_entradas(FALSO, sorted(imagenes.iterdir()))
    medicion = medir(DetectorFalso(), entradas, politica, max_fallos=2)
    assert not medicion.completa
    assert {f["etapa"] for f in medicion.fallos} == {"politica"}


def test_demasiados_fallos_deja_el_benchmark_incompleto(imagenes, tmp_path):
    detector = DetectorFalso(fallar_en=frozenset(range(1, 200)))
    entradas = cargar_entradas(detector, sorted(imagenes.iterdir()))
    medicion = medir(detector, entradas, max_fallos=3)
    assert not medicion.completa
    assert len(medicion.fallos) == 4
    assert medicion.ejecuciones == []


def test_incompleto_por_cli(imagenes, tmp_path, monkeypatch):
    monkeypatch.setattr(DetectorFalso, "inferir", _siempre_falla)
    salida = tmp_path / "run"
    assert correr(imagenes, salida, "--max-fallos", "2") == 1
    resumen = json.loads((salida / "resumen.json").read_text(encoding="utf-8"))
    assert resumen["estado"] == "incompleto"
    assert resumen["etapas"] == {}
    assert len(leer_csv(salida / "fallos.csv")) == 3


def _siempre_falla(self, entrada):
    raise RuntimeError("se cayó")


def test_los_calentamientos_no_entran_en_la_estadistica():
    filas = [
        {"fase": "calentamiento", **dict.fromkeys(ETAPAS, 1000.0)},
        *({"fase": "medicion", **dict.fromkeys(ETAPAS, float(i))} for i in range(1, 101)),
    ]
    resumen = resumir_etapas(filas)
    assert resumen["total_ms"]["maximo"] == 100.0
    assert resumen["total_ms"]["p95"] == pytest.approx(95.05)


# --- Una ejecución --------------------------------------------------------------------------------


def test_el_total_es_de_pared_y_cubre_todas_las_etapas(imagenes, tmp_path):
    entrada = cargar_entradas(FALSO, [imagenes / "f00.jpg"])[0]
    fila = ejecutar_una(FALSO, entrada, 1, EtapaPolitica(tmp_path / "b"))
    etapas = [e for e in ETAPAS if e != "total_ms"]
    assert fila["evento_ms"] > 0
    # Tiempo de pared: incluye cada etapa y lo que pasa entre ellas, así que nunca es menor.
    assert fila["total_ms"] >= sum(fila[e] for e in etapas)
    assert fila["accion"] in {"AVANZAR", "GIRAR_IZQ", "GIRAR_DER", "STOP"}
    # El comando lo registró el adaptador virtual de B.
    assert (tmp_path / "b" / "comandos.jsonl").read_text(encoding="utf-8").count("\n") == 1


def test_sin_politica(imagenes, tmp_path):
    salida = tmp_path / "run"
    assert correr(imagenes, salida, "--sin-politica") == 1
    resumen = json.loads((salida / "resumen.json").read_text(encoding="utf-8"))
    assert "politica_ms" not in resumen["etapas"]
    assert resumen["protocolo"]["con_politica"] is False
    assert any("sin la etapa de política" in a for a in resumen["advertencias"])


def test_entradas_en_ciclo(imagenes):
    entradas = cargar_entradas(FALSO, sorted(imagenes.iterdir()))
    medicion = medir(DetectorFalso(), entradas)
    ids = [e["entrada_id"] for e in medicion.ejecuciones[:7]]
    assert ids == ["f00", "f01", "f02", "f03", "f04", "f00", "f01"]


# --- Argumentos y entradas ------------------------------------------------------------------------


def test_menos_de_cien_mediciones_no_se_acepta(imagenes, tmp_path):
    with pytest.raises(SystemExit) as salida:
        correr(imagenes, tmp_path / "run", "--mediciones", "99")
    assert salida.value.code == 2


@pytest.mark.parametrize("archivo", ["resumen.json", "otra_cosa.txt"])
def test_la_salida_debe_estar_vacia(imagenes, tmp_path, archivo):
    salida = tmp_path / "run"
    salida.mkdir()
    (salida / archivo).write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        correr(imagenes, salida)
    assert error.value.code == 2


def test_una_carpeta_vacia_sirve(imagenes, tmp_path):
    salida = tmp_path / "run"
    salida.mkdir()
    assert correr(imagenes, salida) == 1


def test_hash_mal_escrito(imagenes, tmp_path):
    with pytest.raises(SystemExit):
        main(["--entradas", str(imagenes), "--salida", str(tmp_path), "--model-sha256", "ABC"])


def test_entradas_con_el_mismo_nombre(tmp_path):
    for carpeta in ("a", "b"):
        (tmp_path / carpeta).mkdir()
        (tmp_path / carpeta / "f.jpg").write_bytes(b"x" * 8)
    with pytest.raises(ErrorBench, match="mismo nombre"):
        cargar_entradas(FALSO, [tmp_path / "a" / "f.jpg", tmp_path / "b" / "f.jpg"])


@pytest.mark.parametrize(
    "contenido",
    [b"no es una imagen", b"\xff\xd8 cortado a la mitad", b"\x89PNG\r\n\x1a\n cortado"],
)
def test_imagen_corrupta(tmp_path, contenido):
    (tmp_path / "mala.jpg").write_bytes(contenido)
    with pytest.raises(ErrorBench, match="JPEG"):
        cargar_entradas(FALSO, [tmp_path / "mala.jpg"])
    assert correr(tmp_path / "mala.jpg", tmp_path / "run") == 2


def test_entrada_que_no_existe(tmp_path):
    assert correr(tmp_path / "no-existe.jpg", tmp_path / "run") == 2


def test_detector_que_no_existe(imagenes, tmp_path):
    assert correr(imagenes, tmp_path / "run", "--detector", "no_existe_este_modulo") == 2


def test_percentil_lineal():
    assert percentil([4.0, 1.0, 3.0, 2.0], 0.5) == 2.5
    assert percentil([7.0], 0.95) == 7.0
    with pytest.raises(ValueError):
        percentil([], 0.5)


def test_hardware_y_energia():
    datos = hardware()
    assert datos["nucleos_logicos"] >= 1
    assert datos["so"]
    assert energia() in {"corriente", "bateria", "desconocida"}


@pytest.mark.parametrize(
    ("pmset", "esperado"),
    [
        ("Now drawing from 'AC Power'\n -InternalBattery-0 100%; charged", "corriente"),
        ("Now drawing from 'Battery Power'\n -InternalBattery-0 80%; discharging", "bateria"),
        ("", "desconocida"),
    ],
)
def test_energia_en_mac(monkeypatch, pmset, esperado):
    # Para quien mida en una Mac: se simula pmset en cualquier SO.
    monkeypatch.setattr(arnes.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        arnes.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout=pmset),
    )
    assert energia() == esperado


def test_hardware_en_mac(monkeypatch):
    salidas = {"machdep.cpu.brand_string": "Apple M3\n", "hw.memsize": "17179869184\n"}
    monkeypatch.setattr(arnes.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        arnes.subprocess,
        "run",
        lambda comando, **k: subprocess.CompletedProcess(comando, 0, stdout=salidas[comando[-1]]),
    )
    datos = hardware()
    assert datos["cpu"] == "Apple M3"
    assert datos["ram_bytes"] == 16 * 1024**3


def test_el_resumen_declara_lo_que_no_se_mide(imagenes, tmp_path):
    salida = tmp_path / "run"
    correr(imagenes, salida)
    protocolo = json.loads((salida / "resumen.json").read_text(encoding="utf-8"))["protocolo"]
    assert "pausas de reproducción" in protocolo["excluye"]
    assert protocolo["calentamientos"] == 10
