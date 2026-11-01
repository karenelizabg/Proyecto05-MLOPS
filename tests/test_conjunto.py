"""P5-11: manifiesto y verify_dataset sobre un conjunto armado en una carpeta temporal."""

from __future__ import annotations

import hashlib
import io
import json
import os
from functools import lru_cache
from pathlib import Path

import pytest
from PIL import Image

import conjunto.__main__ as cli
from conjunto import ErrorManifiesto, construir, verificar, zonas_de
from control.config import cargar_config_politica

CONFIG = cargar_config_politica()
BOTELLA, TAZA = 39, 41

# Cajas en píxeles de un cuadro de 640x480.
IZQ = [10.0, 30.0, 105.0, 330.0]
CENTRO = [250.0, 220.0, 390.0, 460.0]
DER = [540.0, 10.0, 635.0, 310.0]


@lru_cache
def jpeg(n: int) -> bytes:
    """JPEG real de 640x480, con un color distinto por cuadro."""
    salida = io.BytesIO()
    color = ((n * 37) % 256, (n * 91) % 256, (n * 13) % 256)
    Image.new("RGB", (640, 480), color).save(salida, "JPEG")
    return salida.getvalue()


def sin_datos() -> bytes:
    """SOI, SOF con el tamaño correcto y EOI, sin datos de imagen (caso de Heri en #68)."""
    sof = b"\xff\xc0\x00\x11\x08" + (480).to_bytes(2, "big") + (640).to_bytes(2, "big")
    return b"\xff\xd8" + sof + b"\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01\xff\xd9"


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
    assert s05["estado_esperado"] == "despejado"
    assert s05["zonas_ocupadas"] == []
    assert s03["estado_esperado"] == "obstaculo"
    assert s03["zonas_ocupadas"] == ["izq"]
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


@pytest.mark.parametrize(
    "archivo",
    ["../S02/S01_f0001.jpg", "..\\S02\\S01_f0001.jpg", "/etc/S01_f0001.jpg", "S01_f0001.png", 7],
)
def test_el_manifiesto_rechaza_un_archivo_fuera_de_la_secuencia(tmp_path, archivo):
    anotaciones = armar(tmp_path, {"S01": [[]]})
    registro = tmp_path / "datos" / "cuadros" / "S01" / "captura.jsonl"
    captura = json.loads(registro.read_text(encoding="utf-8"))
    captura["archivo"] = archivo
    registro.write_text(json.dumps(captura) + "\n", encoding="utf-8")

    with pytest.raises(ErrorManifiesto, match=r"S01_f0001: archivo .* no es un nombre"):
        construir(tmp_path / "datos" / "cuadros", anotaciones, tmp_path, CONFIG)


def test_el_manifiesto_rechaza_una_anotacion_repetida(tmp_path):
    anotaciones = armar(tmp_path, {"S01": [[], []]})
    with pytest.raises(ErrorManifiesto, match=r"frame_id 'S01_f0001' repetido"):
        construir(tmp_path / "datos" / "cuadros", [*anotaciones, anotaciones[0]], tmp_path, CONFIG)


def test_el_manifiesto_rechaza_un_cuadro_repetido_en_la_captura(tmp_path):
    anotaciones = armar(tmp_path, {"S01": [[], []]})
    registro = tmp_path / "datos" / "cuadros" / "S01" / "captura.jsonl"
    registro.write_text(registro.read_text() + registro.read_text().splitlines()[0] + "\n")
    with pytest.raises(ErrorManifiesto, match="S01_f0001: frame_id repetido en la captura"):
        construir(tmp_path / "datos" / "cuadros", anotaciones, tmp_path, CONFIG)


def test_el_manifiesto_rechaza_una_caja_fuera_de_la_imagen(tmp_path):
    anotaciones = armar(tmp_path, {"S01": [[(TAZA, CENTRO)]]})
    anotaciones[0]["objetos"][0]["bbox"] = [600.0, 10.0, 900.0, 50.0]
    with pytest.raises(ErrorManifiesto, match="la caja sale de la imagen"):
        construir(tmp_path / "datos" / "cuadros", anotaciones, tmp_path, CONFIG)


def test_el_manifiesto_rechaza_cuadros_fuera_de_la_raiz(tmp_path):
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    anotaciones = armar(tmp_path, {"S01": [[]]})
    with pytest.raises(ErrorManifiesto, match="S01_f0001: el cuadro queda fuera de la raíz"):
        construir(tmp_path / "datos" / "cuadros", anotaciones, raiz, CONFIG)


def test_el_manifiesto_rechaza_un_enlace_a_un_cuadro_externo(tmp_path):
    raiz = tmp_path / "raiz"
    anotaciones = armar(raiz, {"S01": [[]]})
    cuadro = raiz / "datos" / "cuadros" / "S01" / "S01_f0001.jpg"
    externo = tmp_path / "externo.jpg"
    externo.write_bytes(cuadro.read_bytes())
    cuadro.unlink()
    try:
        os.symlink(externo, cuadro)
    except OSError:
        pytest.skip("este sistema no permite crear enlaces simbólicos")
    with pytest.raises(ErrorManifiesto, match="S01_f0001: el cuadro queda fuera de la raíz"):
        construir(raiz / "datos" / "cuadros", anotaciones, raiz, CONFIG)


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


@pytest.mark.parametrize("como", ["relativa", "absoluta"])
def test_falla_con_una_ruta_fuera_de_la_raiz(tmp_path, como):
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    filas, anotaciones = conjunto_valido(raiz)
    externo = tmp_path / "externo.jpg"
    externo.write_bytes(jpeg(999))
    filas[0]["sha256"] = hashlib.sha256(jpeg(999)).hexdigest()
    filas[0]["ruta"] = "../externo.jpg" if como == "relativa" else externo.as_posix()

    assert errores(filas, anotaciones, raiz) == [
        f"S01_f0001: la ruta {filas[0]['ruta']!r} debe ser relativa y estar dentro de la raíz"
    ]


def test_falla_con_una_ruta_con_diagonal_invertida(tmp_path):
    # En Windows sería un separador y en otro sistema parte del nombre: no se reproduce igual.
    filas, anotaciones = conjunto_valido(tmp_path)
    ruta = filas[0]["ruta"].replace("/", "\\")
    filas[0]["ruta"] = ruta

    assert errores(filas, anotaciones, tmp_path) == [
        f"S01_f0001: la ruta {ruta!r} debe ser relativa y estar dentro de la raíz"
    ]


@pytest.mark.parametrize("valor", ["false", "true", 1, 0, None])
def test_falla_si_hueco_intencional_no_es_booleano(tmp_path, valor):
    filas, anotaciones = conjunto_valido(tmp_path)
    filas[5]["hueco_intencional"] = valor

    assert errores(filas, anotaciones, tmp_path) == ["fila 6: hueco_intencional debe ser booleano"]


@pytest.mark.parametrize("valor", [float("nan"), float("inf"), 300.5, "300", None, True])
def test_falla_si_el_tiempo_no_es_entero(tmp_path, valor):
    # Con NaN ninguna comparación se cumple: el hueco pasaba sin error.
    filas, anotaciones = conjunto_valido(tmp_path)
    filas[5]["t_relativo_ms"] = valor

    assert errores(filas, anotaciones, tmp_path) == [
        f"fila 6: t_relativo_ms debe ser entero, llegó {valor!r}"
    ]


@pytest.mark.parametrize("campo", ["frame_id", "sequence_id", "sha256"])
def test_falla_sin_romperse_si_un_identificador_no_es_texto(tmp_path, campo):
    filas, anotaciones = conjunto_valido(tmp_path)
    filas[5][campo] = ["x"]

    assert errores(filas, anotaciones, tmp_path) == [f"fila 6: {campo} debe ser texto, llegó ['x']"]


def test_falla_con_un_jpeg_sin_datos_de_imagen(tmp_path):
    filas, anotaciones = conjunto_valido(tmp_path)
    (tmp_path / filas[0]["ruta"]).write_bytes(sin_datos())
    filas[0]["sha256"] = hashlib.sha256(sin_datos()).hexdigest()

    assert errores(filas, anotaciones, tmp_path) == [
        f"S01_f0001: {filas[0]['ruta']} no es un cuadro válido (jpeg_no_decodifica)"
    ]


def test_falla_con_un_jpeg_truncado(tmp_path):
    filas, anotaciones = conjunto_valido(tmp_path)
    truncado = jpeg(1)[: len(jpeg(1)) // 2] + b"\xff\xd9"
    (tmp_path / filas[0]["ruta"]).write_bytes(truncado)
    filas[0]["sha256"] = hashlib.sha256(truncado).hexdigest()

    assert any("(jpeg_truncado)" in e for e in errores(filas, anotaciones, tmp_path))


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
    assert salida.splitlines()[-1] == "OK con 0 excepciones"

    sha = hashlib.sha256(manifiesto.read_bytes()).hexdigest()
    congelado = [*raiz, "verificar", "--manifiesto", str(manifiesto), *comunes, "--sha256"]
    assert cli.main([*congelado, sha]) == 0
    assert cli.main([*congelado, "0" * 64]) == 1


def test_comando_avisa_cada_hueco_intencional_y_cuenta_las_excepciones(tmp_path, capsys):
    filas, anotaciones = conjunto_valido(tmp_path)
    for f in filas[5:10]:
        f["t_relativo_ms"] += 600
    filas[5]["hueco_intencional"] = True
    filas[6]["hueco_intencional"] = True  # marcado, pero su hueco es normal: no es excepción
    manifiesto = tmp_path / "manifiesto.jsonl"
    manifiesto.write_text("".join(json.dumps(f) + "\n" for f in filas), encoding="utf-8")
    ruta_anotaciones = tmp_path / "anotaciones.jsonl"
    ruta_anotaciones.write_text("".join(json.dumps(a) + "\n" for a in anotaciones))

    argumentos = ["--raiz", str(tmp_path), "verificar", "--manifiesto", str(manifiesto)]
    assert cli.main([*argumentos, "--anotaciones", str(ruta_anotaciones)]) == 0

    salida = capsys.readouterr()
    assert salida.out.splitlines()[-1] == "OK con 1 excepciones"
    assert salida.err.splitlines() == [
        "aviso: S01_f0006: hueco intencional de 800 ms desde S01_f0005; "
        "requiere aprobación del PM A en #13"
    ]


def test_comando_no_dice_ok_si_otra_regla_se_rompe(tmp_path, capsys):
    filas, anotaciones = conjunto_valido(tmp_path)
    filas[0]["split"] = "ajuste"
    manifiesto = tmp_path / "manifiesto.jsonl"
    manifiesto.write_text("".join(json.dumps(f) + "\n" for f in filas), encoding="utf-8")
    ruta_anotaciones = tmp_path / "anotaciones.jsonl"
    ruta_anotaciones.write_text("".join(json.dumps(a) + "\n" for a in anotaciones))

    argumentos = ["--raiz", str(tmp_path), "verificar", "--manifiesto", str(manifiesto)]
    assert cli.main([*argumentos, "--anotaciones", str(ruta_anotaciones)]) == 1
    assert capsys.readouterr().out.splitlines()[-1] == "NO cumple"


def _argumentos_manifiesto(raiz: Path, anotaciones) -> list[str]:
    ruta = raiz / "anotaciones.jsonl"
    ruta.write_text("".join(json.dumps(a) + "\n" for a in anotaciones))
    return [
        "--raiz",
        str(raiz),
        "manifiesto",
        "--cuadros",
        str(raiz / "datos" / "cuadros"),
        "--anotaciones",
        str(ruta),
        "--salida",
        str(raiz / "manifiesto.jsonl"),
    ]


def test_comando_no_sobrescribe_el_manifiesto_sin_permiso(tmp_path, capsys):
    _, anotaciones = conjunto_valido(tmp_path)
    args = _argumentos_manifiesto(tmp_path, anotaciones)
    manifiesto = tmp_path / "manifiesto.jsonl"
    manifiesto.write_text("congelado")

    assert cli.main(args) == 2
    assert "--sobrescribir" in capsys.readouterr().err
    assert manifiesto.read_text() == "congelado"

    assert cli.main([*args, "--sobrescribir"]) == 0
    assert manifiesto.read_text() != "congelado"


def test_una_falla_al_escribir_no_toca_el_manifiesto(tmp_path, monkeypatch, capsys):
    _, anotaciones = conjunto_valido(tmp_path)
    args = _argumentos_manifiesto(tmp_path, anotaciones)
    manifiesto = tmp_path / "manifiesto.jsonl"
    manifiesto.write_text("congelado")

    def falla(self, destino):
        raise OSError("disco lleno")

    monkeypatch.setattr(Path, "replace", falla)

    assert cli.main([*args, "--sobrescribir"]) == 2
    assert "disco lleno" in capsys.readouterr().err
    assert manifiesto.read_text() == "congelado"
    assert _temporales(tmp_path) == []


def _temporales(carpeta: Path) -> list[Path]:
    return list(carpeta.glob("*.parcial"))


def _enlazar(destino: Path, enlace: Path) -> None:
    try:
        os.symlink(destino, enlace)
    except OSError:
        pytest.skip("este sistema no permite crear enlaces simbólicos")


def test_un_temporal_viejo_con_el_nombre_anterior_no_se_toca(tmp_path):
    # Revisión de Heri en #68: el nombre fijo pisaba lo que hubiera en `<salida>.parcial`.
    _, anotaciones = conjunto_valido(tmp_path)
    ajeno = tmp_path / "manifiesto.jsonl.parcial"
    ajeno.write_text("ajeno")

    assert cli.main(_argumentos_manifiesto(tmp_path, anotaciones)) == 0
    assert ajeno.read_text() == "ajeno"
    assert (tmp_path / "manifiesto.jsonl").read_text() != "ajeno"


def test_un_enlace_con_el_nombre_anterior_no_se_sigue(tmp_path):
    _, anotaciones = conjunto_valido(tmp_path)
    externo = tmp_path / "externo.txt"
    externo.write_text("intacto")
    _enlazar(externo, tmp_path / "manifiesto.jsonl.parcial")

    assert cli.main(_argumentos_manifiesto(tmp_path, anotaciones)) == 0
    assert externo.read_text() == "intacto"


def test_el_temporal_no_sigue_un_enlace_aunque_adivinen_su_nombre(tmp_path, monkeypatch):
    externo = tmp_path / "externo.txt"
    externo.write_text("intacto")
    salida = tmp_path / "manifiesto.jsonl"
    monkeypatch.setattr(cli.secrets, "token_hex", lambda _: "fijo")
    _enlazar(externo, tmp_path / ".manifiesto.jsonl.fijo.parcial")

    with pytest.raises(FileExistsError):
        cli._escribir(salida, "nuevo", sobrescribir=False)
    assert externo.read_text() == "intacto"
    assert not salida.exists()


def test_un_temporal_que_ya_existe_no_se_borra(tmp_path, monkeypatch):
    ajeno = tmp_path / ".manifiesto.jsonl.fijo.parcial"
    ajeno.write_text("ajeno")
    monkeypatch.setattr(cli.secrets, "token_hex", lambda _: "fijo")

    with pytest.raises(FileExistsError):
        cli._escribir(tmp_path / "manifiesto.jsonl", "nuevo", sobrescribir=False)
    assert ajeno.read_text() == "ajeno"


def test_sin_permiso_no_se_pisa_una_salida_que_aparecio_a_medio_camino(tmp_path):
    # `_manifiesto` ya revisó que no existía; aquí aparece después de esa revisión.
    salida = tmp_path / "manifiesto.jsonl"
    salida.write_text("congelado")

    with pytest.raises(FileExistsError):
        cli._escribir(salida, "nuevo", sobrescribir=False)
    assert salida.read_text() == "congelado"
    assert _temporales(tmp_path) == []


def test_una_salida_que_aparece_a_medio_camino_da_error_en_el_comando(
    tmp_path, monkeypatch, capsys
):
    _, anotaciones = conjunto_valido(tmp_path)
    args = _argumentos_manifiesto(tmp_path, anotaciones)
    manifiesto = tmp_path / "manifiesto.jsonl"
    original = cli._escribir

    def aparece_antes(salida, texto, sobrescribir):
        manifiesto.write_text("congelado")
        original(salida, texto, sobrescribir)

    monkeypatch.setattr(cli, "_escribir", aparece_antes)

    assert cli.main(args) == 2
    assert "--sobrescribir" in capsys.readouterr().err
    assert manifiesto.read_text() == "congelado"


def test_un_enlace_roto_en_la_salida_cuenta_como_existente(tmp_path, capsys):
    _, anotaciones = conjunto_valido(tmp_path)
    args = _argumentos_manifiesto(tmp_path, anotaciones)
    externo = tmp_path / "todavia_no_existe.txt"
    _enlazar(externo, tmp_path / "manifiesto.jsonl")

    assert cli.main(args) == 2
    assert "--sobrescribir" in capsys.readouterr().err
    assert not externo.exists()
    assert (tmp_path / "manifiesto.jsonl").is_symlink()


def test_sobrescribir_reemplaza_el_enlace_sin_tocar_su_destino(tmp_path):
    _, anotaciones = conjunto_valido(tmp_path)
    externo = tmp_path / "externo.txt"
    externo.write_text("intacto")
    manifiesto = tmp_path / "manifiesto.jsonl"
    _enlazar(externo, manifiesto)

    assert cli.main([*_argumentos_manifiesto(tmp_path, anotaciones), "--sobrescribir"]) == 0
    assert externo.read_text() == "intacto"
    assert not manifiesto.is_symlink()


def test_una_falla_al_publicar_sin_sobrescribir_no_deja_nada(tmp_path, monkeypatch, capsys):
    _, anotaciones = conjunto_valido(tmp_path)
    args = _argumentos_manifiesto(tmp_path, anotaciones)

    def falla(origen, destino):
        raise OSError("sin enlaces duros")

    monkeypatch.setattr(cli.os, "link", falla)

    assert cli.main(args) == 2
    assert "sin enlaces duros" in capsys.readouterr().err
    assert not (tmp_path / "manifiesto.jsonl").exists()
    assert _temporales(tmp_path) == []


@pytest.mark.skipif(os.name == "nt", reason="los permisos POSIX no aplican en Windows")
@pytest.mark.parametrize("extra", [[], ["--sobrescribir"]])
def test_el_manifiesto_queda_con_los_permisos_de_un_archivo_normal(tmp_path, extra):
    _, anotaciones = conjunto_valido(tmp_path)
    normal = tmp_path / "normal.txt"
    normal.write_text("x")

    assert cli.main([*_argumentos_manifiesto(tmp_path, anotaciones), *extra]) == 0
    modo = (tmp_path / "manifiesto.jsonl").stat().st_mode
    assert modo == normal.stat().st_mode


def test_el_sha_impreso_es_el_del_archivo(tmp_path, capsys):
    _, anotaciones = conjunto_valido(tmp_path)

    assert cli.main(_argumentos_manifiesto(tmp_path, anotaciones)) == 0
    sha = hashlib.sha256((tmp_path / "manifiesto.jsonl").read_bytes()).hexdigest()
    assert sha in capsys.readouterr().out


def _anotacion(frame: str, secuencia: str, *cajas: list[float]) -> dict:
    return {
        "frame_id": frame,
        "sequence_id": secuencia,
        "image_width": 640,
        "image_height": 480,
        "objetos": [{"class_id": TAZA, "bbox": caja} for caja in cajas],
    }


def _hojas_de(tmp_path: Path, anotaciones: list[dict]) -> list[str]:
    """Cuadros de un solo color y sus anotaciones; devuelve los argumentos de `hojas`."""
    for anotacion in anotaciones:
        carpeta = tmp_path / "cuadros" / anotacion["sequence_id"]
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / f"{anotacion['frame_id']}.jpg").write_bytes(jpeg(0))
    ruta = tmp_path / "anotaciones.jsonl"
    ruta.write_text("".join(json.dumps(a) + "\n" for a in anotaciones), encoding="utf-8")
    return ["hojas", "--cuadros", str(tmp_path / "cuadros"), "--anotaciones", str(ruta)]


def test_hojas_dibuja_las_cajas_a_resolucion_completa(tmp_path, capsys):
    caja = [100.0, 100.0, 200.0, 200.0]
    anotaciones = [_anotacion(f"S01_f000{n}", "S01", caja) for n in range(1, 6)]
    anotaciones[4]["objetos"] = []
    salida = tmp_path / "hojas"
    assert cli.main([*_hojas_de(tmp_path, anotaciones), "--salida", str(salida)]) == 0

    with Image.open(salida / "S01.png") as hoja:
        assert hoja.size == (640 * 4, 480 * 2)
        fondo = hoja.getpixel((150, 150))
        assert hoja.getpixel((100, 150)) != fondo  # el borde de la caja, en el píxel anotado
        assert hoja.getpixel((640 + 100, 150)) != fondo  # también en el segundo cuadro
        assert hoja.getpixel((100, 480 + 150)) == fondo  # el quinto cuadro no lleva caja
    assert "repetida en S01_f0001, S01_f0002, S01_f0003, S01_f0004" in capsys.readouterr().err


def test_hojas_no_avisa_si_las_cajas_son_distintas(tmp_path, capsys):
    anotaciones = [
        _anotacion("S01_f0001", "S01", [100.0, 100.0, 200.0, 200.0]),
        _anotacion("S01_f0002", "S01", [101.0, 100.0, 200.0, 200.0]),
        _anotacion("S02_f0001", "S02", [100.0, 100.0, 200.0, 200.0]),
    ]
    assert cli.main([*_hojas_de(tmp_path, anotaciones), "--salida", str(tmp_path / "h")]) == 0
    assert "repetida" not in capsys.readouterr().err


def test_hojas_no_escribe_en_una_carpeta_ocupada_ni_sin_cuadros(tmp_path, capsys):
    argumentos = _hojas_de(tmp_path, [_anotacion("S01_f0001", "S01")])
    ocupada = tmp_path / "ocupada"
    ocupada.mkdir()
    (ocupada / "algo.txt").write_text("x", encoding="utf-8")
    assert cli.main([*argumentos, "--salida", str(ocupada)]) == 2
    assert "no es una carpeta vacía" in capsys.readouterr().err

    (tmp_path / "cuadros" / "S01" / "S01_f0001.jpg").unlink()
    assert cli.main([*argumentos, "--salida", str(tmp_path / "h")]) == 2
    assert "no se pudieron armar" in capsys.readouterr().err
