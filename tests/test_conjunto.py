"""P5-11: manifiesto y verify_dataset sobre un conjunto armado en una carpeta temporal."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import conjunto.__main__ as cli
from conjunto import ErrorManifiesto, construir, verificar, zonas_de
from control.config import cargar_config_politica

CONFIG = cargar_config_politica()
BOTELLA, TAZA = 39, 41

# Cajas en píxeles de un cuadro de 640x480.
IZQ = [10.0, 30.0, 105.0, 330.0]
CENTRO = [250.0, 220.0, 390.0, 460.0]
DER = [540.0, 10.0, 635.0, 310.0]


def jpeg(n: int, ancho: int = 640, alto: int = 480) -> bytes:
    """JPEG mínimo con tamaño y contenido distinto por cuadro."""
    sof = b"\xff\xc0\x00\x11\x08" + alto.to_bytes(2, "big") + ancho.to_bytes(2, "big")
    sof += b"\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    return b"\xff\xd8" + sof + b"\xff\xda\x00\x02" + n.to_bytes(4, "big") + b"\xff\xd9"


def armar(raiz: Path, secuencias: dict[str, list[list[tuple[int, list[float]]]]], paso_ms=200):
    """Escribe cuadros, captura.jsonl y anotaciones; devuelve las anotaciones."""
    anotaciones, n = [], 0
    for secuencia, cuadros in secuencias.items():
        carpeta = raiz / "datos" / "cuadros" / secuencia
        carpeta.mkdir(parents=True)
        registro = []
        for i, objetos in enumerate(cuadros, start=1):
            n += 1
            frame = f"{secuencia}_f{i:04d}"
            datos = jpeg(n)
            (carpeta / f"{frame}.jpg").write_bytes(datos)
            registro.append(
                {
                    "frame_id": frame,
                    "sequence_id": secuencia,
                    "archivo": f"{frame}.jpg",
                    "t_capture_ms": (i - 1) * paso_ms,
                    "sha256": hashlib.sha256(datos).hexdigest(),
                    "bytes": len(datos),
                    "image_width": 640,
                    "image_height": 480,
                }
            )
            anotaciones.append(
                {
                    "frame_id": frame,
                    "sequence_id": secuencia,
                    "image_width": 640,
                    "image_height": 480,
                    "objetos": [{"class_id": c, "bbox": b} for c, b in objetos],
                }
            )
        texto = "".join(json.dumps(r) + "\n" for r in registro)
        (carpeta / "captura.jsonl").write_text(texto, encoding="utf-8")
    return anotaciones


def conjunto_valido(raiz: Path):
    """6 secuencias de 10 cuadros: 3 con obstáculo y 3 despejadas (60, 30 y 30)."""
    secuencias = {
        "S01": [[]] * 10,
        "S02": [[(TAZA, CENTRO)]] * 10,
        "S03": [[(BOTELLA, IZQ)]] * 10,
        "S04": [[(BOTELLA, DER)]] * 10,
        "S05": [[]] * 10,
        "S06": [[]] * 10,
    }
    anotaciones = armar(raiz, secuencias)
    filas = construir(raiz / "datos" / "cuadros", anotaciones, raiz, CONFIG)
    return filas, anotaciones


def errores(filas, anotaciones, raiz):
    return verificar(filas, anotaciones, raiz, CONFIG, clases={BOTELLA, TAZA}, maximo_ms=400)


# --- manifiesto --------------------------------------------------------------------------


def test_el_manifiesto_tiene_una_fila_por_cuadro_con_su_estado(tmp_path):
    filas, _ = conjunto_valido(tmp_path)

    assert len(filas) == 60
    s05 = next(f for f in filas if f["frame_id"] == "S05_f0001")
    s03 = next(f for f in filas if f["frame_id"] == "S03_f0002")
    assert s05["estado_esperado"] == "despejado" and s05["zonas_ocupadas"] == []
    assert s03["estado_esperado"] == "obstaculo" and s03["zonas_ocupadas"] == ["izq"]
    assert s03["ruta"] == "datos/cuadros/S03/S03_f0002.jpg"
    assert s03["t_relativo_ms"] == 200
    assert {f["split"] for f in filas} == {"evaluacion"}


def test_las_zonas_usan_la_definicion_de_la_politica():
    anotacion = {
        "image_width": 640,
        "objetos": [
            {"class_id": BOTELLA, "bbox": IZQ},
            {"class_id": TAZA, "bbox": CENTRO},
            {"class_id": BOTELLA, "bbox": DER},
        ],
    }
    assert zonas_de(anotacion, CONFIG) == ["izq", "centro", "der"]


def test_el_manifiesto_exige_una_anotacion_por_cuadro(tmp_path):
    anotaciones = armar(tmp_path, {"S01": [[], []]})
    with pytest.raises(ErrorManifiesto, match="S01_f0002: el cuadro no tiene anotación"):
        construir(tmp_path / "datos" / "cuadros", anotaciones[:1], tmp_path, CONFIG)


# --- verify_dataset: pasa, y falla con cada regla rota (criterios de P5-11) ---------------


def test_un_conjunto_valido_pasa(tmp_path):
    filas, anotaciones = conjunto_valido(tmp_path)
    assert errores(filas, anotaciones, tmp_path) == []


def test_falla_si_se_quita_un_cuadro(tmp_path):
    filas, anotaciones = conjunto_valido(tmp_path)
    resultado = errores(filas[1:], anotaciones, tmp_path)
    assert any("cuadros = 59" in e for e in resultado)
    assert any("S01_f0001: anotación de un cuadro que no está" in e for e in resultado)


def test_falla_si_se_repite_una_imagen(tmp_path):
    filas, anotaciones = conjunto_valido(tmp_path)
    copia = tmp_path / filas[1]["ruta"]
    copia.write_bytes((tmp_path / filas[0]["ruta"]).read_bytes())
    filas[1]["sha256"] = filas[0]["sha256"]

    assert any("SHA-256 repetido" in e for e in errores(filas, anotaciones, tmp_path))


def test_falla_con_un_hueco_de_400_ms_o_mas(tmp_path):
    filas, anotaciones = conjunto_valido(tmp_path)
    for f in filas[5:10]:  # S01 desde su sexto cuadro
        f["t_relativo_ms"] += 400 - 200
    resultado = errores(filas, anotaciones, tmp_path)
    assert resultado == [
        "S01_f0006: hueco de 400 ms desde S01_f0005 (debe ser menor que 400; "
        "se vuelve a filmar la secuencia)"
    ]


def test_un_hueco_marcado_como_intencional_se_acepta(tmp_path):
    filas, anotaciones = conjunto_valido(tmp_path)
    for f in filas[5:10]:
        f["t_relativo_ms"] += 600
    filas[5]["hueco_intencional"] = True
    assert errores(filas, anotaciones, tmp_path) == []


def test_falla_si_una_secuencia_tiene_otro_split(tmp_path):
    filas, anotaciones = conjunto_valido(tmp_path)
    for f in filas[:10]:
        f["split"] = "ajuste"
    assert any("split 'ajuste'" in e for e in errores(filas, anotaciones, tmp_path))


def test_falla_si_un_archivo_cambio(tmp_path):
    filas, anotaciones = conjunto_valido(tmp_path)
    (tmp_path / filas[3]["ruta"]).write_bytes(jpeg(999))
    assert any("S01_f0004: el SHA-256" in e for e in errores(filas, anotaciones, tmp_path))


def test_falla_si_el_estado_no_coincide_con_las_cajas(tmp_path):
    filas, anotaciones = conjunto_valido(tmp_path)
    filas[0]["estado_esperado"] = "obstaculo"
    filas[15]["zonas_ocupadas"] = ["der"]
    resultado = errores(filas, anotaciones, tmp_path)
    assert any("S01_f0001: el estado esperado" in e for e in resultado)
    assert any("S02_f0006: las zonas ocupadas" in e for e in resultado)


def test_falla_con_una_clase_que_no_esta_en_el_modelo(tmp_path):
    filas, anotaciones = conjunto_valido(tmp_path)
    anotaciones[10]["objetos"][0]["class_id"] = 24
    assert any("class_id [24]" in e for e in errores(filas, anotaciones, tmp_path))


def test_falla_sin_los_minimos_de_e3(tmp_path):
    anotaciones = armar(tmp_path, {"S01": [[(TAZA, CENTRO)], []]})
    filas = construir(tmp_path / "datos" / "cuadros", anotaciones, tmp_path, CONFIG)
    resultado = errores(filas, anotaciones, tmp_path)
    assert any("secuencias = 1" in e for e in resultado)
    assert any("con_objetos = 1" in e for e in resultado)


# --- comando -------------------------------------------------------------------------------


def test_comando_arma_verifica_y_congela(tmp_path, capsys):
    _, anotaciones = conjunto_valido(tmp_path)
    ruta_anotaciones = tmp_path / "anotaciones.jsonl"
    ruta_anotaciones.write_text("".join(json.dumps(a) + "\n" for a in anotaciones))
    manifiesto = tmp_path / "manifiesto.jsonl"

    raiz = ["--raiz", str(tmp_path)]
    comunes = ["--anotaciones", str(ruta_anotaciones)]
    cuadros = ["--cuadros", str(tmp_path / "datos" / "cuadros")]
    assert cli.main([*raiz, "manifiesto", *cuadros, *comunes, "--salida", str(manifiesto)]) == 0
    assert cli.main([*raiz, "verificar", "--manifiesto", str(manifiesto), *comunes]) == 0
    salida = capsys.readouterr().out
    assert "cuadros: 60, secuencias: 6, con_objetos: 30, sin_objetos: 30" in salida

    sha = hashlib.sha256(manifiesto.read_bytes()).hexdigest()
    congelado = [*raiz, "verificar", "--manifiesto", str(manifiesto), *comunes, "--sha256"]
    assert cli.main([*congelado, sha]) == 0
    assert cli.main([*congelado, "0" * 64]) == 1
