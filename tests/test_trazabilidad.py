"""P5-14 · Resultados por cuadro: del frame_id al comando, hashes y recálculo desde cero.

Las corridas pasan por el mismo `python -m control` que el recorrido real (T16), con eventos del
contrato v1 armados aquí, y la de T16 (`resultados/recorrido-real/izq/`) se une tal cual.
"""

import json
from pathlib import Path

import pytest

from control.__main__ import main as correr
from trazabilidad import ErrorTrazabilidad, construir, leer_corrida
from trazabilidad.__main__ import main

RAIZ = Path(__file__).resolve().parents[1]
CONFIG = RAIZ / "config" / "control"
RECORRIDO_REAL = RAIZ / "resultados" / "recorrido-real" / "izq"
BASE = json.loads((RAIZ / "config/contrato/ejemplos/valido.json").read_text("utf-8"))
FALLIDO = json.loads((RAIZ / "config/contrato/ejemplos/fallido.json").read_text("utf-8"))
MODELO, CONFIG_SHA = "a" * 64, "b" * 64
TAZA, BOTELLA = 41, 39
CAJA_TAZA = [250.0, 200.0, 390.0, 420.0]


def evento(i, detecciones, **cambios):
    return {
        **BASE,
        "run_id": "p5-14",
        "sequence_id": "S01",
        "frame_id": f"S01_f{i:04d}",
        "t_capture_ms": 200 * i,
        "t_emit_ms": 200 * i + 40,
        "model_sha256": MODELO,
        "config_sha256": CONFIG_SHA,
        "detections": detecciones,
        **cambios,
    }


def eventos():
    """Libre, tres con la taza, uno donde el detector falla y uno con un falso positivo."""
    taza = [{"class_id": TAZA, "confidence": 0.9, "bbox": CAJA_TAZA}]
    falso = [{"class_id": BOTELLA, "confidence": 0.8, "bbox": [10.0, 10.0, 60.0, 200.0]}]
    fallo = {k: FALLIDO[k] for k in ("image_width", "image_height", "status", "error")}
    return [
        evento(0, []),
        evento(1, taza),
        evento(2, taza),
        evento(3, taza),
        evento(4, [], **fallo),
        evento(5, falso),
    ]


def anotaciones():
    """La verdad: la taza en 1 a 4 y en 6, que el detector nunca emitió; nada en 0 y 5."""
    filas = []
    for i in range(7):
        objetos = [{"class_id": TAZA, "bbox": CAJA_TAZA}] if i not in (0, 5) else []
        filas.append(
            {
                "frame_id": f"S01_f{i:04d}",
                "sequence_id": "S01",
                "image_width": 640,
                "image_height": 480,
                "objetos": objetos,
            }
        )
    return filas


def escribir_jsonl(ruta, filas):
    ruta.write_text("".join(json.dumps(f) + "\n" for f in filas), encoding="utf-8")
    return ruta


@pytest.fixture
def corrida(tmp_path):
    entrada = escribir_jsonl(tmp_path / "detector.jsonl", eventos())
    salida = tmp_path / "corrida"
    assert (
        correr(["--entrada", str(entrada), "--config", str(CONFIG), "--salida", str(salida)]) == 0
    )
    return salida


@pytest.fixture
def unida(corrida, tmp_path):
    anot = escribir_jsonl(tmp_path / "anotaciones.jsonl", anotaciones())
    salida = tmp_path / "traza"
    argumentos = [
        "construir", "--corrida", str(corrida), "--anotaciones", str(anot), "--salida", str(salida),
        "--model-sha256", MODELO, "--config-sha256", CONFIG_SHA,
    ]  # fmt: skip
    # El cuadro 6 anotado sin evento es una advertencia: sale con 1, pero escribe todo.
    assert main(argumentos) == 1
    return salida


def filas_de(carpeta):
    lineas = (carpeta / "por_cuadro.jsonl").read_text("utf-8").splitlines()
    return {f["frame_id"]: f for f in map(json.loads, lineas)}


def resumen_de(carpeta):
    return json.loads((carpeta / "resumen.json").read_text("utf-8"))


def test_de_un_frame_id_a_su_comando_en_un_paso(unida, capsys):
    fila = filas_de(unida)["S01_f0002"]
    assert fila["evento"]["detections"][0]["class_id"] == TAZA
    assert fila["anotacion"]["objetos"][0]["class_id"] == TAZA
    assert fila["conteo"] == {"tp": 1, "fp": 0, "fn": 0}
    assert fila["decision"]["action"] == fila["comando"]["action"]
    assert fila["comando"]["valid_until_ms"] > fila["comando"]["t_command_ms"]

    assert main(["cuadro", str(unida), "S01_f0002"]) == 0
    assert json.loads(capsys.readouterr().out)["comando"] == fila["comando"]
    assert main(["cuadro", str(unida), "S01_f9999"]) == 1


def test_cada_cuadro_lleva_lo_suyo(unida):
    filas = filas_de(unida)
    assert filas["S01_f0000"]["conteo"] == {"tp": 0, "fp": 0, "fn": 0}
    assert filas["S01_f0005"]["conteo"] == {"tp": 0, "fp": 1, "fn": 0}
    # El fallo del detector no se esconde: queda su evento, su error y el FN de la taza.
    fallo = filas["S01_f0004"]
    assert fallo["evento"]["status"] == "error"
    assert fallo["evento"]["error"]["code"] == "unreadable_image"
    assert fallo["conteo"] == {"tp": 0, "fp": 0, "fn": 1}
    assert fallo["comando"]["action"] == "STOP"
    assert [e["motivo"] for e in fallo["errores"]] == ["error_detector:unreadable_image"]
    # El cuadro anotado que el detector nunca emitió también está, sin evento ni comando.
    perdido = filas["S01_f0006"]
    assert perdido["evento"] is None and perdido["comando"] is None
    assert perdido["conteo"] == {"tp": 0, "fp": 0, "fn": 1}


def test_resumen_con_metricas_de_p5_13_y_conteos(unida):
    resumen = resumen_de(unida)
    micro = resumen["metricas"]["micro"]
    assert (micro["tp"], micro["fp"], micro["fn"]) == (3, 1, 2)
    assert resumen["metricas"]["procedencia"]["comprobada"] is True
    conteos = resumen["conteos"]
    assert conteos["cuadros"] == 7
    assert conteos["por_secuencia"]["S01"]["estados"] == {"error": 1, "ok": 5, "sin_evento": 1}
    assert conteos["errores"] == [
        {"frame_id": "S01_f0004", "motivo": "error_detector:unreadable_image"}
    ]
    assert conteos["ordenes_sin_cuadro"] == {"shutdown:STOP": 1}
    assert resumen["detector"] == {"model_sha256": [MODELO], "config_sha256": [CONFIG_SHA]}
    assert any("sin evento" in a for a in resumen["advertencias"])


def test_el_recalculo_da_las_mismas_cifras(unida):
    assert main(["recalcular", str(unida)]) == 0


def test_cifras_tocadas_a_mano_no_pasan(unida, capsys):
    resumen = resumen_de(unida)
    resumen["metricas"]["micro"]["f1"] = 0.99
    (unida / "resumen.json").write_text(json.dumps(resumen), encoding="utf-8")
    assert main(["recalcular", str(unida)]) == 1
    assert "metricas no coincide" in capsys.readouterr().err


def test_un_conteo_por_cuadro_tocado_no_pasa(unida, capsys):
    filas = list(filas_de(unida).values())
    filas[1]["conteo"]["tp"] = 0
    escribir_jsonl(unida / "por_cuadro.jsonl", filas)
    assert main(["recalcular", str(unida)]) == 1
    err = capsys.readouterr().err
    assert "por_cuadro.jsonl cambió" in err
    assert "conteo_por_cuadro no coincide" in err


def test_cambiar_el_modelo_o_la_config_cambia_los_hashes(tmp_path):
    for nombre, cambio in (("modelo", {"model_sha256": "c" * 64}), ("config", {})):
        cambios = cambio or {"config_sha256": "d" * 64}
        entrada = escribir_jsonl(
            tmp_path / f"{nombre}.jsonl", [{**e, **cambios} for e in eventos()]
        )
        salida = tmp_path / nombre
        assert (
            correr(["--entrada", str(entrada), "--config", str(CONFIG), "--salida", str(salida)])
            == 0
        )
        _, cifras, _ = construir(leer_corrida(salida), anotaciones(), MODELO, CONFIG_SHA)
        campo = next(iter(cambios))
        assert cifras["detector"][campo] == [cambios[campo]]
        assert cifras["metricas"]["procedencia"]["comprobada"] is False


def test_cambiar_la_config_de_b_cambia_sus_hashes(corrida, tmp_path, unida):
    otra = tmp_path / "otra-config"
    otra.mkdir()
    for nombre in ("plazos.yaml", "politica.yaml"):
        texto = (CONFIG / nombre).read_text("utf-8")
        (otra / nombre).write_text(texto + "\n# otra versión\n", encoding="utf-8")
    entrada = escribir_jsonl(tmp_path / "otra.jsonl", eventos())
    salida = tmp_path / "otra-corrida"
    assert correr(["--entrada", str(entrada), "--config", str(otra), "--salida", str(salida)]) == 0
    traza = tmp_path / "otra-traza"
    main(["construir", "--corrida", str(salida), "--salida", str(traza)])
    antes, despues = (
        resumen_de(unida)["corrida"]["config_b"],
        resumen_de(traza)["corrida"]["config_b"],
    )
    for nombre in ("plazos.yaml", "politica.yaml"):
        assert antes[nombre]["sha256"] != despues[nombre]["sha256"]


def test_frame_id_que_no_coincide_con_las_anotaciones(corrida, tmp_path, capsys):
    # Un detector que numera por posición (f000001) contra el conjunto (S01_f0001): no se une
    # nada. Era el caso de infer antes de #75, que ahora usa el nombre del archivo.
    posicionales = [{**a, "frame_id": f"f{n:06d}"} for n, a in enumerate(anotaciones(), 1)]
    anot = escribir_jsonl(tmp_path / "posicionales.jsonl", posicionales)
    salida = tmp_path / "traza"
    argumentos = ["construir", "--corrida", str(corrida), "--anotaciones", str(anot)]
    assert main([*argumentos, "--salida", str(salida)]) == 2
    assert "mismo frame_id" in capsys.readouterr().err
    assert not salida.exists()
    with pytest.raises(ErrorTrazabilidad, match="mismo frame_id"):
        construir(leer_corrida(corrida), posicionales)


def test_sin_anotaciones_solo_conteos_de_b(tmp_path):
    salida = tmp_path / "traza"
    assert main(["construir", "--corrida", str(RECORRIDO_REAL), "--salida", str(salida)]) == 1
    resumen = resumen_de(salida)
    assert resumen["metricas"] is None
    # La corrida real de T16: los 12 cuadros llegaron viejos y terminaron en STOP.
    assert resumen["conteos"]["por_secuencia"]["S09"]["acciones"] == {"STOP": 12}
    assert len(resumen["conteos"]["errores"]) == 12
    assert main(["recalcular", str(salida)]) == 0


def test_entradas_que_no_se_pueden_unir(tmp_path, corrida, capsys):
    assert main(["construir", "--corrida", str(tmp_path), "--salida", str(tmp_path / "x")]) == 2
    assert "no es una corrida de control" in capsys.readouterr().err
    ocupada = tmp_path / "ocupada"
    ocupada.mkdir()
    (ocupada / "algo.txt").write_text("x", encoding="utf-8")
    assert main(["construir", "--corrida", str(corrida), "--salida", str(ocupada)]) == 2
    assert main(["recalcular", str(tmp_path / "no-existe")]) == 2
    with pytest.raises(SystemExit):
        main(["construir", "--corrida", str(corrida), "--salida", "y", "--model-sha256", "abc"])


def test_con_crlf_del_clon_el_recalculo_da_lo_mismo(corrida, unida):
    # Git saca los archivos con CRLF en algunas máquinas, y control escribe con CRLF en Windows:
    # los hashes son del texto con LF, así que ni el recálculo ni los de la corrida cambian.
    escritos = sorted(unida.iterdir())
    assert all(b"\r" not in ruta.read_bytes() for ruta in escritos)
    for ruta in escritos:
        ruta.write_bytes(ruta.read_bytes().replace(b"\n", b"\r\n"))
    assert main(["recalcular", str(unida)]) == 0

    for ruta in corrida.iterdir():
        texto = ruta.read_bytes().replace(b"\r\n", b"\n")
        ruta.write_bytes(texto.replace(b"\n", b"\r\n"))
    otra = corrida.parent / "traza-crlf"
    main(["construir", "--corrida", str(corrida), "--salida", str(otra)])
    assert resumen_de(otra)["corrida"]["archivos"] == resumen_de(unida)["corrida"]["archivos"]


def test_los_errores_sin_cuadro_tambien_se_cuentan(tmp_path):
    # En C10 la orden de avanzar vence antes del cuadro viejo: orden_vencida no tiene frame_id.
    salida = tmp_path / "c10"
    entrada = RAIZ / "resultados" / "casos" / "C10" / "detecciones.jsonl"
    argumentos = ["--entrada", str(entrada), "--config", str(CONFIG), "--salida", str(salida)]
    assert correr(argumentos) == 0
    registrados = [json.loads(linea) for linea in (salida / "errores.jsonl").open(encoding="utf-8")]
    assert any(e["frame_id"] is None for e in registrados)

    traza = tmp_path / "traza"
    main(["construir", "--corrida", str(salida), "--salida", str(traza)])
    conteos = resumen_de(traza)["conteos"]
    assert len(conteos["errores"]) == len(registrados)
    assert {"frame_id": None, "motivo": "orden_vencida"} in conteos["errores"]
    assert conteos["errores_sin_cuadro"] == {"orden_vencida": 1}
    sin_cuadro = (traza / "errores_sin_cuadro.jsonl").read_text("utf-8").splitlines()
    assert [json.loads(linea)["motivo"] for linea in sin_cuadro] == ["orden_vencida"]
    assert main(["recalcular", str(traza)]) == 0

    # Quitar el error del archivo se nota en el recálculo.
    (traza / "errores_sin_cuadro.jsonl").write_text("", encoding="utf-8")
    assert main(["recalcular", str(traza)]) == 1


def test_eventos_fuera_del_contrato_no_se_unen(tmp_path, capsys):
    sin_frame = {k: v for k, v in eventos()[1].items() if k != "frame_id"}
    for nombre, malo in (("sin-frame", sin_frame), ("no-objeto", [1])):
        entrada = escribir_jsonl(tmp_path / f"{nombre}.jsonl", [*eventos()[:3], malo])
        salida = tmp_path / nombre
        assert (
            correr(["--entrada", str(entrada), "--config", str(CONFIG), "--salida", str(salida)])
            == 0
        )
        traza = tmp_path / f"traza-{nombre}"
        assert main(["construir", "--corrida", str(salida), "--salida", str(traza)]) == 2
        assert "evento 4" in capsys.readouterr().err
        assert not traza.exists()


def test_anotaciones_repetidas_no_se_unen(corrida, tmp_path, capsys):
    filas = anotaciones()
    anot = escribir_jsonl(tmp_path / "repetidas.jsonl", [*filas, {**filas[1], "objetos": []}])
    salida = tmp_path / "traza"
    argumentos = ["construir", "--corrida", str(corrida), "--anotaciones", str(anot)]
    assert main([*argumentos, "--salida", str(salida)]) == 2
    assert "repetido" in capsys.readouterr().err
    assert not salida.exists()


def test_resumen_incompleto_o_salida_que_es_un_archivo(corrida, unida, tmp_path):
    resumen = resumen_de(unida)
    del resumen["conteos"]
    (unida / "resumen.json").write_text(json.dumps(resumen), encoding="utf-8")
    assert main(["recalcular", str(unida)]) == 2

    archivo = tmp_path / "un-archivo.txt"
    archivo.write_text("x", encoding="utf-8")
    assert main(["construir", "--corrida", str(corrida), "--salida", str(archivo)]) == 2


def test_una_corrida_de_una_secuencia(corrida, tmp_path, capsys):
    # Las anotaciones de otra secuencia contarían como FN: con --secuencia se une solo la suya.
    otra = {**anotaciones()[1], "frame_id": "S02_f0001", "sequence_id": "S02"}
    anot = escribir_jsonl(tmp_path / "dos.jsonl", [*anotaciones(), otra])
    argumentos = ["construir", "--corrida", str(corrida), "--anotaciones", str(anot)]

    todas, solo_s01 = tmp_path / "todas", tmp_path / "s01"
    main([*argumentos, "--salida", str(todas)])
    main([*argumentos, "--salida", str(solo_s01), "--secuencia", "S01"])
    assert resumen_de(todas)["metricas"]["micro"]["fn"] == 3
    assert resumen_de(solo_s01)["metricas"]["micro"]["fn"] == 2
    assert resumen_de(solo_s01)["anotaciones"]["secuencias"] == ["S01"]
    assert main(["recalcular", str(solo_s01)]) == 0

    capsys.readouterr()
    assert main([*argumentos, "--salida", str(tmp_path / "x"), "--secuencia", "S02"]) == 2
    assert "S01" in capsys.readouterr().err
    assert main([*argumentos, "--salida", str(tmp_path / "y"), "--secuencia", "S03"]) == 2
