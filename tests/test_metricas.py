import copy
import csv
import json
import math
from fractions import Fraction
from pathlib import Path

import pytest

from metricas import Conteo, EntradaInvalida, Objeto, Prediccion, emparejar, evaluar, iou, metricas
from metricas.__main__ import main
from metricas.calculo import a_xyxy, contar, puntaje_1_4

RAIZ = Path(__file__).resolve().parents[1]
EVENTO_BASE = json.loads(
    (RAIZ / "config" / "contrato" / "ejemplos" / "valido.json").read_text(encoding="utf-8")
)
MODELO = EVENTO_BASE["model_sha256"]
CONFIG = EVENTO_BASE["config_sha256"]

CAJA = (100.0, 100.0, 200.0, 200.0)


def pred(class_id=0, confidence=0.9, caja=CAJA):
    return Prediccion(class_id, confidence, caja)


def real(class_id=0, caja=CAJA):
    return Objeto(class_id, caja)


def conteo(predicciones, reales):
    return contar(emparejar(predicciones, reales))


# --- IoU y emparejamiento: los casos armados a mano del ticket ---------------


def test_iou():
    assert iou(CAJA, CAJA) == 1.0
    assert iou(CAJA, (200.0, 200.0, 300.0, 300.0)) == 0.0  # solo se tocan en una esquina
    assert iou(CAJA, (150.0, 100.0, 250.0, 200.0)) == pytest.approx(1 / 3)


def test_caja_perfecta_es_tp():
    assert conteo([pred()], [real()]) == Conteo(tp=1)


def test_caja_desplazada_por_debajo_de_0_5_es_fp_y_fn():
    desplazada = (150.0, 100.0, 250.0, 200.0)  # IoU 1/3
    pares = emparejar([pred(caja=desplazada)], [real()])
    assert contar(pares) == Conteo(fp=1, fn=1)
    assert pares[0].iou == pytest.approx(1 / 3)  # el FP guarda el mejor IoU que tuvo


def test_iou_justo_en_0_5_cuenta():
    # Unión 200 x 100 = 20000, intersección 100 x 100 = 10000.
    assert conteo([pred(caja=(100.0, 100.0, 300.0, 200.0))], [real()]) == Conteo(tp=1)


def test_duplicado_es_un_tp_y_un_fp():
    assert conteo([pred(confidence=0.9), pred(confidence=0.8)], [real()]) == Conteo(tp=1, fp=1)


def test_clase_equivocada_es_un_fp_y_un_fn():
    assert conteo([pred(class_id=1)], [real(class_id=0)]) == Conteo(fp=1, fn=1)


def test_cuadro_negativo_con_falso_positivo():
    assert conteo([pred()], []) == Conteo(fp=1)


def test_objeto_sin_prediccion_es_fn():
    assert conteo([], [real(), real(caja=(300.0, 300.0, 400.0, 400.0))]) == Conteo(fn=2)


def test_conjunto_sin_objetos_ni_predicciones():
    resultado = metricas(conteo([], []))
    assert resultado == {
        "tp": 0,
        "fp": 0,
        "fn": 0,
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
        "sin_soporte": ["precision", "recall", "f1"],
    }


def test_gana_la_prediccion_de_mayor_confianza_aunque_tenga_menos_iou():
    casi = (105.0, 105.0, 205.0, 205.0)
    pares = emparejar([pred(confidence=0.6, caja=CAJA), pred(confidence=0.9, caja=casi)], [real()])
    tp = next(p for p in pares if p.tipo == "TP")
    assert tp.confidence == 0.9 and tp.caja_predicha == casi
    assert contar(pares) == Conteo(tp=1, fp=1)


def test_cada_prediccion_toma_el_objeto_libre_de_mayor_iou():
    izquierda, derecha = (100.0, 100.0, 200.0, 200.0), (180.0, 100.0, 280.0, 200.0)
    cerca_de_derecha = (170.0, 100.0, 270.0, 200.0)
    pares = emparejar(
        [pred(confidence=0.9, caja=cerca_de_derecha), pred(confidence=0.8, caja=izquierda)],
        [real(caja=izquierda), real(caja=derecha)],
    )
    assert [(p.caja_predicha, p.caja_real) for p in pares if p.tipo == "TP"] == [
        (cerca_de_derecha, derecha),
        (izquierda, izquierda),
    ]


def test_xywh_se_convierte_antes_de_comparar():
    assert a_xyxy([100, 100, 100, 100], "xywh") == CAJA
    assert a_xyxy([100, 100, 200, 200], "xyxy") == CAJA


# --- P/R/F1 y puntaje 1.4 ------------------------------------------------------


def test_formulas():
    resultado = metricas(Conteo(tp=6, fp=2, fn=4))
    assert resultado["precision"] == 6 / 8
    assert resultado["recall"] == 6 / 10
    assert resultado["f1"] == 12 / 18
    assert resultado["sin_soporte"] == []


@pytest.mark.parametrize(
    ("tp", "fp_fn", "f1", "puntos"),
    [(1, 2, "0.50", 3.0), (7, 6, "0.70", 4.0), (4, 2, "0.80", 4.5), (9, 2, "0.90", 5.0)],
)
def test_puntaje_1_4_de_la_tabla_de_la_rubrica(tp, fp_fn, f1, puntos):
    c = Conteo(tp=tp, fp=fp_fn)
    assert Fraction(2 * c.tp, 2 * c.tp + c.fp) == Fraction(f1)
    assert puntaje_1_4(c) == puntos


def test_puntaje_1_4_extremos():
    assert puntaje_1_4(Conteo(tp=5)) == 6.0
    assert puntaje_1_4(Conteo()) == 0.0
    # F1 = 0.75: con flotantes 12 * F1 puede quedar en 8.999… y bajar medio punto.
    assert puntaje_1_4(Conteo(tp=3, fp=1, fn=1)) == 4.5


# --- evaluar un run completo ---------------------------------------------------


def anotacion(frame, secuencia="S01", objetos=(), ancho=640, alto=480):
    return {
        "frame_id": frame,
        "sequence_id": secuencia,
        "image_width": ancho,
        "image_height": alto,
        "objetos": [{"class_id": c, "bbox": list(caja)} for c, caja in objetos],
    }


def evento(frame, t, secuencia="S01", detecciones=(), status="ok", **cambios):
    ev = copy.deepcopy(EVENTO_BASE)
    ev.update(
        frame_id=frame,
        sequence_id=secuencia,
        t_capture_ms=t,
        t_emit_ms=t + 30,
        status=status,
        detections=[
            {"class_id": c, "confidence": conf, "bbox": list(caja)} for c, conf, caja in detecciones
        ],
    )
    if status == "error":
        ev.update(image_width=None, image_height=None)
        ev["error"] = {"code": "unreadable_image", "message": "JPEG truncado"}
    ev.update(cambios)
    return ev


def conjunto_completo():
    """60 cuadros, 6 secuencias, 30 con objeto y 30 despejados, con detecciones perfectas."""
    anotaciones, eventos = [], []
    for s in range(6):
        for f in range(10):
            frame, secuencia = f"S{s}_f{f:02d}", f"S{s}"
            objetos = [(s % 2, CAJA)] if f % 2 == 0 else []
            anotaciones.append(anotacion(frame, secuencia, objetos))
            detecciones = [(c, 0.9, caja) for c, caja in objetos]
            eventos.append(evento(frame, f * 200, secuencia, detecciones))
    return anotaciones, eventos


def test_run_perfecto_que_cumple_e3_no_tiene_advertencias():
    anotaciones, eventos = conjunto_completo()
    resumen = evaluar(anotaciones, eventos, MODELO, CONFIG).resumen

    assert resumen["advertencias"] == []
    assert resumen["micro"]["f1"] == 1.0
    assert resumen["conjunto"]["cumple_minimos_e3"]
    assert resumen["criterio_1_4"] == {
        "formula": "floor(12 * F1 micro) / 2",
        "puntaje": 6.0,
        "puntaje_con_tope_e3": 6.0,
        "procedencia_comprobada": True,
        "cobertura_completa": True,
    }
    assert resumen["por_clase"]["0"]["soporte"] == 15
    assert resumen["por_clase"]["1"]["soporte"] == 15


def test_sin_minimos_de_e3_el_puntaje_se_limita_a_3():
    anotaciones = [anotacion("S01_f01", objetos=[(0, CAJA)])]
    eventos = [evento("S01_f01", 0, detecciones=[(0, 0.9, CAJA)])]
    resumen = evaluar(anotaciones, eventos, MODELO, CONFIG).resumen

    assert resumen["criterio_1_4"]["puntaje"] == 6.0
    assert resumen["criterio_1_4"]["puntaje_con_tope_e3"] == 3.0
    assert any("mínimos de E3" in a for a in resumen["advertencias"])


def test_cuadros_sin_prediccion_valida_siguen_en_el_denominador():
    anotaciones = [
        anotacion("S01_f01", objetos=[(0, CAJA)]),
        anotacion("S01_f02", objetos=[(0, CAJA)]),
        anotacion("S01_f03", objetos=[(0, CAJA)]),
        anotacion("S01_f04", objetos=[(0, CAJA)]),
    ]
    eventos = [
        evento("S01_f01", 0, detecciones=[(0, 0.9, CAJA)]),
        evento("S01_f02", 200, status="error"),
        evento("S01_f03", 400, status="stale"),
        # S01_f04 no tiene evento.
    ]
    resultado = evaluar(anotaciones, eventos, MODELO, CONFIG)

    assert resultado.resumen["micro"]["tp"] == 1
    assert resultado.resumen["micro"]["fn"] == 3
    assert [f["estado"] for f in resultado.por_cuadro] == ["ok", "error", "stale", "sin_evento"]
    assert resultado.resumen["cuadros"]["sin_evento"] == ["S01_f04"]
    assert resultado.resumen["cuadros"]["error_o_stale"] == ["S01_f02", "S01_f03"]
    assert not resultado.resumen["criterio_1_4"]["cobertura_completa"]


def test_evento_de_un_cuadro_sin_anotacion_se_avisa_y_no_cuenta():
    anotaciones = [anotacion("S01_f01")]
    eventos = [evento("S01_f01", 0), evento("S01_f99", 200, detecciones=[(0, 0.9, CAJA)])]
    resumen = evaluar(anotaciones, eventos, MODELO, CONFIG).resumen

    assert resumen["micro"]["fp"] == 0
    assert resumen["cuadros"]["eventos_sin_anotacion"] == ["S01_f99"]


def test_dimensiones_distintas_se_avisan():
    anotaciones = [anotacion("S01_f01", ancho=1280, alto=960)]
    resumen = evaluar(anotaciones, [evento("S01_f01", 0)], MODELO, CONFIG).resumen
    assert resumen["cuadros"]["dimensiones_distintas"] == ["S01_f01"]


def test_procedencia():
    anotaciones, eventos = [anotacion("S01_f01")], [evento("S01_f01", 0)]

    sin_hashes = evaluar(anotaciones, eventos).resumen
    assert not sin_hashes["procedencia"]["comprobada"]
    assert sum("procedencia no comprobada" in a for a in sin_hashes["advertencias"]) == 2

    otro_modelo = evaluar(anotaciones, eventos, "c" * 64, CONFIG).resumen
    assert not otro_modelo["criterio_1_4"]["procedencia_comprobada"]
    assert any("model_sha256" in a for a in otro_modelo["advertencias"])


def test_detecciones_xywh():
    anotaciones = [anotacion("S01_f01", objetos=[(0, CAJA)])]
    eventos = [
        evento("S01_f01", 0, detecciones=[(0, 0.9, (100, 100, 100, 100))], bbox_format="xywh")
    ]
    assert evaluar(anotaciones, eventos, MODELO, CONFIG).resumen["micro"]["tp"] == 1


@pytest.mark.parametrize(
    ("anotaciones", "eventos", "mensaje"),
    [
        ([anotacion("S01_f01"), anotacion("S01_f01")], [], "repetido"),
        ([anotacion("S01_f01", objetos=[(0, (600, 400, 700, 470))])], [], "sale de la imagen"),
        ([anotacion("S01_f01", objetos=[(0, (200, 200, 100, 100))])], [], "ancho y alto"),
        ([anotacion("S01_f01", objetos=[(0, (1, 1, math.nan, 9))])], [], "finitos"),
        ([{"frame_id": "S01_f01"}], [], "required"),
        ([anotacion("S01_f01")], [{"frame_id": "S01_f01"}], "detecciones"),
        (
            [anotacion("S01_f01")],
            [evento("S01_f01", 0), evento("S01_f02", 200, run_id="otro-run")],
            "varios run_id",
        ),
    ],
    ids=["frame repetido", "caja fuera", "caja invertida", "nan", "sin campos", "evento", "2 runs"],
)
def test_entradas_invalidas(anotaciones, eventos, mensaje):
    with pytest.raises(EntradaInvalida) as exc:
        evaluar(anotaciones, eventos)
    assert any(mensaje in e for e in exc.value.errores)


# --- línea de comandos -----------------------------------------------------------


def escribir_jsonl(ruta, filas):
    ruta.write_text("".join(json.dumps(f) + "\n" for f in filas), encoding="utf-8")
    return ruta


def correr(tmp_path, anotaciones, eventos, *extra):
    salida = tmp_path / "salida"
    codigo = main(
        [
            "--detecciones",
            str(escribir_jsonl(tmp_path / "detecciones.jsonl", eventos)),
            "--anotaciones",
            str(escribir_jsonl(tmp_path / "anotaciones.jsonl", anotaciones)),
            "--salida",
            str(salida),
            *extra,
        ]
    )
    return codigo, salida


def leer_csv(ruta):
    with ruta.open(encoding="utf-8", newline="") as archivo:
        return list(csv.DictReader(archivo))


def test_cli_run_en_orden_sale_con_0_y_otra_persona_recalcula_el_f1(tmp_path):
    anotaciones, eventos = conjunto_completo()
    eventos[0]["detections"] = []  # un FN
    eventos[1]["detections"] = [{"class_id": 0, "confidence": 0.7, "bbox": list(CAJA)}]  # un FP
    codigo, salida = correr(
        tmp_path, anotaciones, eventos, "--model-sha256", MODELO, "--config-sha256", CONFIG
    )
    assert codigo == 0

    resumen = json.loads((salida / "resumen.json").read_text(encoding="utf-8"))
    por_cuadro = leer_csv(salida / "por_cuadro.csv")
    detalle = leer_csv(salida / "detalle.csv")
    assert len(por_cuadro) == 60

    # Recalcular desde los archivos, sin usar el código del módulo.
    tp, fp, fn = (sum(int(f[k]) for f in por_cuadro) for k in ("tp", "fp", "fn"))
    assert (tp, fp, fn) == (29, 1, 1)
    assert [sum(f["tipo"] == t for f in detalle) for t in ("TP", "FP", "FN")] == [tp, fp, fn]
    assert resumen["micro"]["f1"] == 2 * tp / (2 * tp + fp + fn)
    assert resumen["criterio_1_4"]["puntaje"] == math.floor(12 * 58 / 60) / 2 == 5.5
    assert resumen["entradas"]["anotaciones"]["sha256"]


def test_cli_con_advertencias_sale_con_1(tmp_path):
    anotaciones, eventos = conjunto_completo()
    codigo, salida = correr(tmp_path, anotaciones, eventos)  # sin hashes congelados
    assert codigo == 1
    assert (salida / "resumen.json").is_file()


def test_cli_entrada_invalida_sale_con_2(tmp_path, capsys):
    codigo, salida = correr(tmp_path, [anotacion("S01_f01"), anotacion("S01_f01")], [])
    assert codigo == 2
    assert "repetido" in capsys.readouterr().err
    assert not salida.exists()


def test_cli_archivo_que_no_existe_sale_con_2(tmp_path):
    codigo = main(
        [
            "--detecciones",
            str(tmp_path / "no_existe.jsonl"),
            "--anotaciones",
            str(tmp_path / "tampoco.jsonl"),
            "--salida",
            str(tmp_path / "salida"),
        ]
    )
    assert codigo == 2


def test_cli_rechaza_un_hash_mal_escrito(tmp_path):
    with pytest.raises(SystemExit) as exc:
        correr(tmp_path, [anotacion("S01_f01")], [], "--model-sha256", "ABC")
    assert exc.value.code == 2


def test_ejemplo_del_repo(tmp_path):
    """Los ejemplos de config/ corren: el cuadro con error deja su mochila como FN."""
    codigo = main(
        [
            "--detecciones",
            str(RAIZ / "config" / "contrato" / "ejemplos" / "flujo.jsonl"),
            "--anotaciones",
            str(RAIZ / "config" / "anotaciones" / "ejemplos" / "anotaciones.jsonl"),
            "--salida",
            str(tmp_path),
            "--model-sha256",
            MODELO,
            "--config-sha256",
            CONFIG,
        ]
    )
    assert codigo == 1  # el cuadro con error y los mínimos de E3
    resumen = json.loads((tmp_path / "resumen.json").read_text(encoding="utf-8"))
    assert (resumen["micro"]["tp"], resumen["micro"]["fp"], resumen["micro"]["fn"]) == (2, 0, 2)
