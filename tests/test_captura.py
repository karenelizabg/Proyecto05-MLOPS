"""P5-09: lectura del stream de la ESP32-CAM y selección de cuadros, sin red."""

from __future__ import annotations

import io
import json
from contextlib import contextmanager

import pytest

import captura.__main__ as cli
from captura import capturar, dimensiones_jpeg, huecos_mayores, jpeg_completo, leer_partes

SEPARADOR = b"\r\n--123456789000000000000987654321\r\n"


def jpeg(ancho: int = 640, alto: int = 480, contenido: bytes = b"x") -> bytes:
    """JPEG mínimo: SOI, APP0, SOF0 con el tamaño, SOS, datos y EOI."""
    app0 = b"\xff\xe0\x00\x04ab"
    sof = (
        b"\xff\xc0\x00\x11\x08"
        + alto.to_bytes(2, "big")
        + ancho.to_bytes(2, "big")
        + b"\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    )
    return b"\xff\xd8" + app0 + sof + b"\xff\xda\x00\x02" + contenido + b"\xff\xd9"


def stream(*partes: bytes) -> bytes:
    """Lo que manda el firmware por cada cuadro: encabezado, JPEG y separador."""
    return b"".join(
        b"Content-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(p) + p + SEPARADOR
        for p in partes
    )


def reloj(*tiempos: float):
    valores = iter(tiempos)
    return lambda: next(valores)


# --- stream y JPEG ---------------------------------------------------------------------


def test_leer_partes_devuelve_cada_jpeg_completo():
    a, b = jpeg(contenido=b"a"), jpeg(contenido=b"b")
    assert list(leer_partes(io.BytesIO(stream(a, b)))) == [a, b]


def test_leer_partes_termina_si_el_stream_se_corta():
    datos = stream(jpeg(contenido=b"a"), jpeg(contenido=b"b"))
    cortado = datos[: -len(SEPARADOR) - 5]  # el segundo JPEG llega a medias
    assert list(leer_partes(io.BytesIO(cortado))) == [jpeg(contenido=b"a")]


def test_dimensiones_jpeg_salta_los_segmentos_previos():
    assert dimensiones_jpeg(jpeg(320, 240)) == (320, 240)
    assert dimensiones_jpeg(b"\xff\xd8no es jpeg") is None


def test_jpeg_completo_acepta_relleno_despues_del_eoi():
    assert jpeg_completo(jpeg() + b"\x00\x00")
    assert not jpeg_completo(jpeg()[:-2])
    assert not jpeg_completo(b"\x89PNG")


# --- selección de cuadros --------------------------------------------------------------


def test_descarta_los_primeros_y_respeta_la_separacion():
    partes = [jpeg(contenido=bytes([n])) for n in range(7)]
    # Los dos primeros se tiran; luego 0, 100 (muy pronto), 250, 300 (muy pronto), 460.
    captura = capturar(partes, reloj(0, 50, 100, 200, 350, 400, 560), 3, 200, (640, 480))

    assert [c.t_ms for c in captura.cuadros] == [0, 250, 460]
    assert [c.datos for c in captura.cuadros] == [partes[2], partes[4], partes[6]]


def test_rechaza_incompletos_otro_tamano_y_duplicados():
    bueno = jpeg(contenido=b"a")
    partes = [bueno, jpeg()[:-2], jpeg(320, 240), bueno, jpeg(contenido=b"b")]
    captura = capturar(partes, reloj(0, 300, 600, 900, 1200), 5, 200, (640, 480), descartar=0)

    assert [c.datos for c in captura.cuadros] == [bueno, jpeg(contenido=b"b")]
    assert [motivo for motivo, _ in captura.rechazados] == ["jpeg_incompleto", "tamano_320x240"]
    assert captura.duplicados == 1


def test_se_detiene_al_juntar_los_cuadros_pedidos():
    partes = (jpeg(contenido=bytes([n])) for n in range(100))
    captura = capturar(partes, reloj(*range(0, 100_000, 300)), 4, 200, (640, 480), descartar=0)
    assert len(captura.cuadros) == 4


def test_huecos_mayores():
    partes = [jpeg(contenido=bytes([n])) for n in range(4)]
    captura = capturar(partes, reloj(0, 200, 700, 900), 4, 100, (640, 480), descartar=0)
    assert huecos_mayores(captura.cuadros, 400) == [(2, 500)]


# --- comando ---------------------------------------------------------------------------


@pytest.fixture
def camara(monkeypatch):
    """Sustituye la red y el reloj: `camara(partes, tiempos_ms)`."""

    def preparar(partes: list[bytes], tiempos_ms: list[int]):
        @contextmanager
        def urlopen(url, timeout):
            yield io.BytesIO(stream(*partes))

        ns = iter(t * 1_000_000 for t in tiempos_ms)
        monkeypatch.setattr(cli.urllib.request, "urlopen", urlopen)
        monkeypatch.setattr(cli.time, "monotonic_ns", lambda: next(ns))

    return preparar


def correr(tmp_path, *extra: str) -> int:
    fijos = ["--url", "http://carro:81/stream", "--secuencia", "S01", "--sin-pausa"]
    return cli.main([*fijos, "--salida", str(tmp_path), "--descartar", "0", *extra])


def test_comando_guarda_los_cuadros_tal_como_llegan(tmp_path, camara):
    partes = [jpeg(contenido=bytes([n])) for n in range(3)]
    camara(partes, [1000, 1200, 1400])

    assert correr(tmp_path, "--cuadros", "3") == 0
    carpeta = tmp_path / "S01"
    filas = [json.loads(linea) for linea in (carpeta / "captura.jsonl").read_text().splitlines()]
    assert [f["frame_id"] for f in filas] == ["S01_f0001", "S01_f0002", "S01_f0003"]
    assert [f["t_capture_ms"] for f in filas] == [0, 200, 400]
    assert (carpeta / "S01_f0002.jpg").read_bytes() == partes[1]
    assert filas[0]["image_width"] == 640
    assert filas[0]["image_height"] == 480


def test_comando_avisa_huecos_y_cuadros_faltantes(tmp_path, camara, capsys):
    camara([jpeg(contenido=bytes([n])) for n in range(2)], [0, 900])

    assert correr(tmp_path, "--cuadros", "3") == 1
    err = capsys.readouterr().err
    assert "hueco de 900 ms" in err
    assert "solo 2 de 3" in err


def test_comando_guarda_los_rechazados(tmp_path, camara):
    camara([jpeg(contenido=b"a"), jpeg()[:-2], jpeg(contenido=b"b")], [0, 200, 400])

    correr(tmp_path, "--cuadros", "2")
    assert [p.name for p in (tmp_path / "S01" / "rechazados").iterdir()] == [
        "001_jpeg_incompleto.bin"
    ]


def test_comando_no_sobrescribe_una_secuencia(tmp_path, camara):
    (tmp_path / "S01").mkdir()
    camara([jpeg()], [0])
    assert correr(tmp_path) == 2


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://carro/stream", "http:///stream"])
def test_comando_solo_acepta_urls_http(tmp_path, url):
    with pytest.raises(SystemExit):
        cli.main(["--url", url, "--secuencia", "S01", "--sin-pausa", "--salida", str(tmp_path)])
    assert not (tmp_path / "S01").exists()
