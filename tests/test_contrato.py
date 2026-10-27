import copy
import json
import math
from decimal import Decimal
from pathlib import Path

import pytest

from contrato import validar_evento, validar_flujo
from contrato.__main__ import main
from control.config import cargar_config_politica
from control.politica import decidir

EJEMPLOS = Path(__file__).resolve().parents[1] / "config" / "contrato" / "ejemplos"

CAMPOS_OBLIGATORIOS = [
    "schema_version",
    "run_id",
    "sequence_id",
    "frame_id",
    "t_capture_ms",
    "t_emit_ms",
    "image_width",
    "image_height",
    "model_sha256",
    "config_sha256",
    "status",
    "bbox_format",
    "bbox_unit",
    "detections",
]

DETECCION = {"class_id": 0, "confidence": 0.9, "bbox": [10.0, 10.0, 100.0, 100.0]}


def cargar(nombre: str) -> dict:
    return json.loads((EJEMPLOS / nombre).read_text(encoding="utf-8"))


def mutar(nombre: str, cambios: dict | None = None, quitar: tuple[str, ...] = ()) -> dict:
    evento = copy.deepcopy(cargar(nombre))
    evento.update(cambios or {})
    for campo in quitar:
        evento.pop(campo)
    return evento


# --- ejemplos ---------------------------------------------------------------


@pytest.mark.parametrize("nombre", ["valido.json", "vacio.json", "fallido.json", "stale.json"])
def test_los_ejemplos_cumplen_el_contrato(nombre):
    assert validar_evento(cargar(nombre)) == []


def test_vacio_es_ok_con_lista_vacia():
    evento = cargar("vacio.json")
    assert evento["status"] == "ok"
    assert evento["detections"] == []


def test_fallido_es_error_con_causa_y_sin_detecciones():
    evento = cargar("fallido.json")
    assert evento["status"] == "error"
    assert evento["error"]["code"] == "unreadable_image"
    assert evento["detections"] == []


def test_el_flujo_de_ejemplo_cumple_el_contrato():
    assert main([str(EJEMPLOS / "flujo.jsonl")]) == 0


# --- eventos inválidos ------------------------------------------------------


@pytest.mark.parametrize("campo", CAMPOS_OBLIGATORIOS)
def test_falta_un_campo_obligatorio(campo):
    assert validar_evento(mutar("valido.json", quitar=(campo,)))


def _caja(formato: str, caja: list[float]) -> dict:
    return mutar(
        "valido.json",
        {"bbox_format": formato, "detections": [{**DETECCION, "bbox": caja}]},
    )


INVALIDOS = {
    "version distinta": mutar("valido.json", {"schema_version": "2"}),
    "status desconocido": mutar("valido.json", {"status": "unknown"}),
    "campo extra": mutar("valido.json", {"velocidad": 1}),
    "tiempo negativo": mutar("valido.json", {"t_capture_ms": -1}),
    "emision anterior a captura": mutar("valido.json", {"t_capture_ms": 500, "t_emit_ms": 400}),
    "hash corto": mutar("valido.json", {"model_sha256": "abc"}),
    "hash en mayusculas": mutar("valido.json", {"config_sha256": "A" * 64}),
    "id con espacios": mutar("valido.json", {"frame_id": "S02 f0003"}),
    "unidad distinta": mutar("valido.json", {"bbox_unit": "m"}),
    "formato de caja desconocido": mutar("valido.json", {"bbox_format": "cxcywh"}),
    "ok con error": mutar("valido.json", {"error": {"code": "invalid_output", "message": "x"}}),
    "ok con ancho null": mutar("valido.json", {"image_width": None}),
    "error sin objeto error": mutar("fallido.json", quitar=("error",)),
    "error con detecciones": mutar("fallido.json", {"detections": [DETECCION]}),
    "error con codigo desconocido": mutar(
        "fallido.json", {"error": {"code": "explotó", "message": "x"}}
    ),
    "stale con detecciones": mutar("stale.json", {"detections": [DETECCION]}),
    "stale con ancho null": mutar("stale.json", {"image_width": None}),
    "confianza mayor que 1": mutar(
        "valido.json", {"detections": [{**DETECCION, "confidence": 1.2}]}
    ),
    "class_id negativo": mutar("valido.json", {"detections": [{**DETECCION, "class_id": -1}]}),
    "caja con tres valores": _caja("xyxy", [1, 2, 3]),
    "xyxy invertida": _caja("xyxy", [100, 100, 10, 10]),
    "xyxy fuera de la imagen": _caja("xyxy", [10, 10, 700, 100]),
    "xywh sin alto": _caja("xywh", [10, 10, 50, 0]),
    "xywh fuera de la imagen": _caja("xywh", [600, 10, 100, 50]),
}


@pytest.mark.parametrize("nombre", INVALIDOS)
def test_evento_invalido_se_rechaza(nombre):
    assert validar_evento(INVALIDOS[nombre])


def test_xywh_valida_cuando_cabe():
    assert validar_evento(_caja("xywh", [10, 10, 90, 90])) == []


def test_lo_que_no_es_un_objeto_se_rechaza():
    assert validar_evento([]) and validar_evento(None)


RUTAS_NUMERICAS = [
    ("t_capture_ms",),
    ("t_emit_ms",),
    ("image_width",),
    ("image_height",),
    ("detections", 0, "class_id"),
    ("detections", 0, "confidence"),
    *(("detections", 0, "bbox", indice) for indice in range(4)),
]


@pytest.mark.parametrize("ruta", RUTAS_NUMERICAS, ids=lambda ruta: "/".join(map(str, ruta)))
@pytest.mark.parametrize(
    "valor",
    [
        math.nan,
        math.inf,
        -math.inf,
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
    ids=["nan", "inf", "menos_inf", "decimal_nan", "decimal_inf", "decimal_menos_inf"],
)
def test_rechaza_numeros_no_finitos_en_diccionarios(ruta, valor):
    evento = cargar("valido.json")
    destino = evento
    for parte in ruta[:-1]:
        destino = destino[parte]
    destino[ruta[-1]] = valor

    assert validar_evento(evento) == [f"{'/'.join(map(str, ruta))}: debe ser un número finito"]


def test_informa_todos_los_numeros_no_finitos_antes_de_comprobar_geometria_y_tiempo():
    evento = cargar("valido.json")
    evento["t_capture_ms"] = math.nan
    evento["t_emit_ms"] = -math.inf
    evento["detections"][0]["confidence"] = math.inf
    evento["detections"][1]["bbox"][2] = math.nan

    assert validar_evento(evento) == [
        "t_capture_ms: debe ser un número finito",
        "t_emit_ms: debe ser un número finito",
        "detections/0/confidence: debe ser un número finito",
        "detections/1/bbox/2: debe ser un número finito",
    ]


def test_rechaza_diccionario_que_se_referencia_a_si_mismo():
    evento = cargar("valido.json")
    evento["ciclo"] = evento

    assert validar_evento(evento) == ["ciclo: estructura cíclica no permitida"]


def test_rechaza_lista_que_se_referencia_a_si_misma():
    lista = []
    lista.append(lista)

    assert validar_evento(lista) == ["0: estructura cíclica no permitida"]


def test_rechaza_ciclo_indirecto_entre_contenedores():
    evento = cargar("valido.json")
    evento["ciclo"] = {"siguiente": [evento]}

    assert validar_evento(evento) == ["ciclo/siguiente/0: estructura cíclica no permitida"]


def test_referencias_compartidas_sin_ciclo_son_validas():
    evento = cargar("valido.json")
    evento["detections"].append(evento["detections"][0])

    assert validar_evento(evento) == []


def test_politica_detiene_evento_con_geometria_no_finita():
    evento = cargar("valido.json")
    evento["detections"] = [evento["detections"][0]]
    evento["detections"][0]["bbox"][2] = math.nan

    comando, _ = decidir(evento, {"nombre": "DETENIDO"}, cargar_config_politica())

    assert comando["action"] == "STOP"
    assert comando["speed"] == 0


# --- reglas entre eventos ---------------------------------------------------


def _flujo() -> list[dict]:
    return [
        mutar("valido.json", {"frame_id": "S02_f0001", "t_capture_ms": 0, "t_emit_ms": 30}),
        mutar("valido.json", {"frame_id": "S02_f0002", "t_capture_ms": 200, "t_emit_ms": 230}),
        mutar("valido.json", {"frame_id": "S02_f0003", "t_capture_ms": 400, "t_emit_ms": 430}),
    ]


def test_flujo_valido():
    assert validar_flujo(_flujo()) == []


def test_flujo_con_frame_repetido():
    eventos = _flujo()
    eventos[2]["frame_id"] = "S02_f0001"
    assert any("repetido" in e for e in validar_flujo(eventos))


def test_flujo_con_tiempo_que_no_crece():
    eventos = _flujo()
    eventos[2]["t_capture_ms"] = 200
    eventos[2]["t_emit_ms"] = 230
    assert any("no crece" in e for e in validar_flujo(eventos))


def test_el_tiempo_se_compara_dentro_de_cada_secuencia():
    eventos = _flujo()
    eventos.append(
        mutar(
            "valido.json",
            {"sequence_id": "S03", "frame_id": "S03_f0001", "t_capture_ms": 0, "t_emit_ms": 30},
        )
    )
    assert validar_flujo(eventos) == []


def test_flujo_que_cambia_de_modelo_dentro_del_run():
    eventos = _flujo()
    eventos[1]["model_sha256"] = "c" * 64
    assert any("cambia de modelo" in e for e in validar_flujo(eventos))


# --- línea de comandos ------------------------------------------------------


def _escribir(tmp_path: Path, eventos: list[dict], nombre: str = "e.jsonl") -> Path:
    ruta = tmp_path / nombre
    ruta.write_text("\n".join(json.dumps(e) for e in eventos) + "\n", encoding="utf-8")
    return ruta


def test_cli_acepta_un_archivo_valido(tmp_path):
    assert main([str(_escribir(tmp_path, _flujo()))]) == 0


def test_cli_rechaza_un_archivo_con_eventos_invalidos(tmp_path, capsys):
    eventos = _flujo()
    eventos[1]["status"] = "unknown"
    assert main([str(_escribir(tmp_path, eventos))]) == 1
    assert "evento 2" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("valor", "constante"),
    [(math.nan, "NaN"), (math.inf, "Infinity"), (-math.inf, "-Infinity")],
)
@pytest.mark.parametrize("extension", ["json", "jsonl"])
def test_cli_rechaza_constantes_numericas_no_estandar(
    tmp_path, capsys, valor, constante, extension
):
    evento = cargar("valido.json")
    evento["detections"][0]["confidence"] = valor
    ruta = _escribir(tmp_path, [evento], f"no_finito.{extension}")
    assert constante in ruta.read_text(encoding="utf-8")

    assert main([str(ruta)]) == 1
    assert "detections/0/confidence: debe ser un número finito" in capsys.readouterr().err


def test_cli_distingue_archivo_ilegible(tmp_path):
    assert main([str(tmp_path / "no_existe.jsonl")]) == 2
    malo = tmp_path / "malo.jsonl"
    malo.write_text("{no es json\n", encoding="utf-8")
    assert main([str(malo)]) == 2
