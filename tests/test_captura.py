"""P5-09: lectura del stream de la ESP32-CAM y selección de cuadros, sin red."""

from __future__ import annotations

import io
import json
import random
import socket
import threading
import time
from contextlib import contextmanager

import pytest
from PIL import Image

import captura.__main__ as cli
from captura import (
    StreamDefectuoso,
    capturar,
    dimensiones_jpeg,
    huecos_excedidos,
    jpeg_completo,
    leer_partes,
    motivo_rechazo,
)
from captura.stream import MAX_CUADRO, MAX_ENCABEZADO, Cuadro

SEPARADOR = b"\r\n--123456789000000000000987654321\r\n"


def jpeg(ancho: int = 640, alto: int = 480, n: int = 0) -> bytes:
    """JPEG real que Pillow decodifica; `n` cambia el color para que no salgan duplicados."""
    salida = io.BytesIO()
    Image.new("RGB", (ancho, alto), (n % 256, (n * 7) % 256, 90)).save(salida, "JPEG")
    return salida.getvalue()


def sin_scan(ancho: int = 640, alto: int = 480) -> bytes:
    """SOI, SOF con el tamaño y EOI, sin tablas ni datos de imagen (caso de Heri en #67)."""
    sof = (
        b"\xff\xc0\x00\x11\x08"
        + alto.to_bytes(2, "big")
        + ancho.to_bytes(2, "big")
        + b"\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    )
    return b"\xff\xd8" + sof + b"\xff\xd9"


def con_ruido(semilla: int = 1) -> bytes:
    """JPEG con mucho detalle, como un cuadro real: el scan ocupa casi todo el archivo."""
    azar = random.Random(semilla)
    salida = io.BytesIO()
    Image.frombytes("RGB", (640, 480), azar.randbytes(640 * 480 * 3)).save(salida, "JPEG")
    return salida.getvalue()


def truncado_con_eoi(datos: bytes, fraccion: float) -> bytes:
    """El caso de Heri en #67: solo una parte de los bytes y un EOI agregado al final."""
    return datos[: int(len(datos) * fraccion)] + b"\xff\xd9"


def stream(*partes: bytes) -> bytes:
    """Lo que manda el firmware por cada cuadro: encabezado, JPEG y separador."""
    return b"".join(
        b"Content-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(p) + p + SEPARADOR
        for p in partes
    )


def reloj(*tiempos: float, inicio: float = 0):
    """`capturar` lee el reloj una vez al empezar (`inicio`) y luego una por cuadro."""
    valores = iter((inicio, *tiempos))
    return lambda: next(valores)


# --- stream y JPEG ---------------------------------------------------------------------


def test_leer_partes_devuelve_cada_jpeg_completo():
    a, b = jpeg(n=1), jpeg(n=2)
    assert list(leer_partes(io.BytesIO(stream(a, b)))) == [a, b]


def test_el_stream_puede_cortarse_justo_despues_de_un_cuadro():
    a = jpeg(n=1)
    for corte in (len(SEPARADOR), len(SEPARADOR) - 2):
        assert list(leer_partes(io.BytesIO(stream(a)[:-corte]))) == [a]


def test_cuerpo_cortado_es_error_y_conserva_lo_que_llego():
    a, b = jpeg(n=1), jpeg(n=2)
    cortado = stream(a, b)[: -len(SEPARADOR) - 5]  # el segundo JPEG llega a medias
    partes = leer_partes(io.BytesIO(cortado))
    assert next(partes) == a
    with pytest.raises(StreamDefectuoso, match="Content-Length") as error:
        next(partes)
    assert error.value.datos == b[:-5]


@pytest.mark.parametrize("sobran", [5, 40])
def test_content_length_mayor_que_el_cuerpo_es_error_aunque_decodifique(sobran):
    # Caso de Heri en #67: JPEG válido de 5429 bytes y el encabezado anuncia 5434.
    a = jpeg(n=1)
    mal = b"Content-Length: %d\r\n\r\n" % (len(a) + sobran) + a + SEPARADOR + b"X" * 100
    captura = capturar(leer_partes(io.BytesIO(mal)), reloj(), 1, 200, (640, 480), descartar=0)
    assert captura.cuadros == []
    assert "Content-Length" in captura.error
    assert [motivo for motivo, _ in captura.rechazados] == ["content_length"]


def test_content_length_mayor_y_el_stream_termina_es_error_aunque_decodifique():
    a = jpeg(n=1)
    mal = b"Content-Length: %d\r\n\r\n" % (len(a) + 5) + a
    captura = capturar(leer_partes(io.BytesIO(mal)), reloj(), 1, 200, (640, 480), descartar=0)
    assert captura.cuadros == []
    assert "Content-Length" in captura.error
    assert captura.rechazados == [("content_length", a)]


def test_content_length_menor_que_el_cuerpo_es_error():
    a = jpeg(n=1)
    mal = b"Content-Length: %d\r\n\r\n" % (len(a) - 5) + a + SEPARADOR
    captura = capturar(leer_partes(io.BytesIO(mal)), reloj(), 1, 200, (640, 480), descartar=0)
    assert captura.cuadros == []
    assert "separador" in captura.error


@pytest.mark.parametrize(
    ("encabezado", "mensaje"),
    [
        (b"Content-Length: abc\r\n\r\n", "no numérico"),
        (b"Content-Length: -5\r\n\r\n", "no numérico"),
        (b"Content-Length: %d\r\n\r\n" % (MAX_CUADRO + 1), "máximo"),
        (b"X" * 5000 + b"\r\n", "encabezado"),
        (b"X-Relleno: 1\r\n" * (MAX_ENCABEZADO // 10), "encabezado"),
    ],
)
def test_leer_partes_rechaza_encabezados_defectuosos(encabezado, mensaje):
    with pytest.raises(StreamDefectuoso, match=mensaje):
        list(leer_partes(io.BytesIO(encabezado + b"\xff" * 100)))


def test_dimensiones_jpeg_salta_los_segmentos_previos():
    assert dimensiones_jpeg(jpeg(320, 240)) == (320, 240)
    assert dimensiones_jpeg(b"\xff\xd8no es jpeg") is None


def test_jpeg_completo_acepta_relleno_despues_del_eoi():
    assert jpeg_completo(jpeg() + b"\x00\x00")
    assert not jpeg_completo(jpeg()[:-2])
    assert not jpeg_completo(b"\x89PNG")


def test_jpeg_sin_scan_no_cuenta_aunque_traiga_sof_y_eoi():
    assert dimensiones_jpeg(sin_scan()) == (640, 480)
    assert not jpeg_completo(sin_scan())
    assert motivo_rechazo(sin_scan(), (640, 480)) == "jpeg_no_decodifica"


@pytest.mark.parametrize("fraccion", [0.25, 0.5, 0.9, 0.999])
@pytest.mark.parametrize("original", [con_ruido(), jpeg(n=3)], ids=["ruido", "plano"])
def test_jpeg_truncado_con_eoi_no_cuenta_aunque_pillow_lo_decodifique(original, fraccion):
    datos = truncado_con_eoi(original, fraccion)
    Image.open(io.BytesIO(datos)).load()  # Pillow no se queja: rellena de gris
    assert not jpeg_completo(datos)
    assert motivo_rechazo(datos, (640, 480)) == "jpeg_truncado"


@pytest.mark.parametrize(
    "datos",
    [con_ruido(), con_ruido(2) + b"\x00\x00", jpeg(n=4)],
    ids=["ruido", "relleno_tras_eoi", "plano"],
)
def test_jpeg_completo_se_acepta(datos):
    assert motivo_rechazo(datos, (640, 480)) is None


@pytest.mark.parametrize("subsampling", [0, 1, 2], ids=["444", "422", "420"])
def test_el_conteo_sirve_con_cualquier_muestreo_de_color(subsampling):
    # Una imagen toda gris es válida: el relleno de Pillow se le parece, pero no le faltan datos.
    salida = io.BytesIO()
    Image.new("RGB", (640, 480), (128, 128, 128)).save(salida, "JPEG", subsampling=subsampling)
    datos = salida.getvalue()
    assert jpeg_completo(datos)
    assert not jpeg_completo(truncado_con_eoi(datos, 0.9))


def test_jpeg_progresivo_o_con_reinicios_no_es_del_firmware():
    salida = io.BytesIO()
    Image.new("RGB", (640, 480), (1, 2, 3)).save(salida, "JPEG", progressive=True)
    assert not jpeg_completo(salida.getvalue())
    salida = io.BytesIO()
    Image.new("RGB", (640, 480), (1, 2, 3)).save(salida, "JPEG", restart_marker_blocks=4)
    assert not jpeg_completo(salida.getvalue())


# --- selección de cuadros --------------------------------------------------------------


def test_descarta_los_primeros_y_respeta_la_separacion():
    partes = [jpeg(n=n) for n in range(7)]
    # Los dos primeros se tiran; luego 0, 100 (muy pronto), 250, 300 (muy pronto), 460.
    captura = capturar(partes, reloj(0, 50, 100, 200, 350, 400, 560), 3, 200, (640, 480))

    assert [c.t_capture_ms for c in captura.cuadros] == [0, 250, 460]
    assert [c.datos for c in captura.cuadros] == [partes[2], partes[4], partes[6]]


def test_rechaza_incompletos_sin_scan_otro_tamano_y_duplicados():
    bueno = jpeg(n=1)
    partes = [bueno, jpeg()[:-2], sin_scan(), jpeg(320, 240), bueno, jpeg(n=2)]
    tiempos = reloj(0, 300, 600, 900, 1200, 1500)
    captura = capturar(partes, tiempos, 6, 200, (640, 480), descartar=0)

    assert [c.datos for c in captura.cuadros] == [bueno, jpeg(n=2)]
    assert [motivo for motivo, _ in captura.rechazados] == [
        "jpeg_incompleto",
        "jpeg_no_decodifica",
        "tamano_320x240",
    ]
    assert captura.duplicados == 1


def test_rechaza_truncado_con_eoi_y_sigue_con_el_siguiente():
    bueno, truncado = jpeg(n=1), truncado_con_eoi(con_ruido(), 0.25)
    captura = capturar([truncado, bueno], reloj(0, 300), 1, 200, (640, 480), descartar=0)
    assert [c.datos for c in captura.cuadros] == [bueno]
    assert [motivo for motivo, _ in captura.rechazados] == ["jpeg_truncado"]


def test_guarda_pocos_rechazados_y_cuenta_los_demas():
    partes = [sin_scan()] * 30
    captura = capturar(partes, reloj(*range(0, 9000, 300)), 1, 200, (640, 480), descartar=0)
    assert len(captura.rechazados) == 20
    assert captura.rechazados_sin_guardar == 10


def test_se_detiene_al_juntar_los_cuadros_pedidos():
    partes = (jpeg(n=n) for n in range(100))
    captura = capturar(partes, reloj(*range(0, 100_000, 300)), 4, 200, (640, 480), descartar=0)
    assert len(captura.cuadros) == 4


def test_se_detiene_si_se_acaba_el_tiempo_sin_cuadros_validos():
    def sin_fin():
        while True:
            yield sin_scan()

    tiempos = iter(range(0, 10**9, 300))
    captura = capturar(sin_fin(), lambda: next(tiempos), 3, 200, (640, 480), limite_ms=5000)
    assert captura.tiempo_agotado
    assert not captura.cuadros


def test_un_stream_defectuoso_detiene_la_captura_con_el_motivo():
    datos = stream(jpeg(n=1)) + b"Content-Length: xyz\r\n\r\n"
    captura = capturar(
        leer_partes(io.BytesIO(datos)), reloj(0, 300), 3, 200, (640, 480), descartar=0
    )
    assert len(captura.cuadros) == 1
    assert "no numérico" in captura.error


def test_huecos_de_400_ms_o_mas_se_marcan():
    partes = [jpeg(n=n) for n in range(4)]
    captura = capturar(partes, reloj(0, 200, 600, 999.4), 4, 100, (640, 480), descartar=0)
    assert huecos_excedidos(captura.cuadros, 400) == [(2, 400)]


def test_el_redondeo_no_esconde_un_hueco():
    # Medido 399.8 ms, pero en captura.jsonl queda 100 -> 500: P5-11 lo rechazaría.
    cuadros = [Cuadro(b"", 100.4, 640, 480), Cuadro(b"", 500.2, 640, 480)]
    assert huecos_excedidos(cuadros, 400) == [(1, 400)]
    # Medido 399.6 ms y escrito 399: pasa.
    cuadros = [Cuadro(b"", 100.6, 640, 480), Cuadro(b"", 500.2, 640, 480)]
    assert huecos_excedidos(cuadros, 400) == []


# --- comando ---------------------------------------------------------------------------


@pytest.fixture
def camara(monkeypatch):
    """Sustituye la red y el reloj: `camara(partes, tiempos_ms)` o `camara(bytes_crudos, ...)`."""

    def preparar(partes: list[bytes] | bytes, tiempos_ms: list[int]):
        crudo = partes if isinstance(partes, bytes) else stream(*partes)

        @contextmanager
        def abrir(url, timeout, limite_s, cortado):
            yield io.BytesIO(crudo)

        ns = iter(t * 1_000_000 for t in [0, *tiempos_ms])
        monkeypatch.setattr(cli, "_abrir", abrir)
        monkeypatch.setattr(cli.time, "monotonic_ns", lambda: next(ns))

    return preparar


def correr(tmp_path, *extra: str) -> int:
    fijos = ["--url", "http://carro:81/stream", "--secuencia", "S01", "--sin-pausa"]
    return cli.main([*fijos, "--salida", str(tmp_path), "--descartar", "0", *extra])


def fallidas(tmp_path):
    return list((tmp_path / "_fallidas").iterdir())


def test_comando_guarda_los_cuadros_tal_como_llegan(tmp_path, camara):
    partes = [jpeg(n=n) for n in range(3)]
    camara(partes, [1000, 1200, 1400])

    assert correr(tmp_path, "--cuadros", "3") == 0
    carpeta = tmp_path / "S01"
    filas = [json.loads(linea) for linea in (carpeta / "captura.jsonl").read_text().splitlines()]
    assert [f["frame_id"] for f in filas] == ["S01_f0001", "S01_f0002", "S01_f0003"]
    assert [f["t_capture_ms"] for f in filas] == [0, 200, 400]
    assert (carpeta / "S01_f0002.jpg").read_bytes() == partes[1]
    assert filas[0]["image_width"] == 640
    assert filas[0]["image_height"] == 480
    assert sorted(p.name for p in tmp_path.iterdir()) == ["S01"]  # sin temporales


def test_comando_aparta_una_captura_con_huecos_y_cuadros_faltantes(tmp_path, camara, capsys):
    camara([jpeg(n=n) for n in range(2)], [0, 900])

    assert correr(tmp_path, "--cuadros", "3") == 1
    err = capsys.readouterr().err
    assert "hueco de 900 ms" in err
    assert "solo 2 de 3" in err
    assert not (tmp_path / "S01").exists()
    [intento] = fallidas(tmp_path)
    assert intento.name.startswith("S01_")
    assert not (intento / "captura.jsonl").exists()
    assert "hueco de 900 ms" in (intento / "FALLIDA.txt").read_text(encoding="utf-8")


def test_despues_de_un_intento_fallido_se_puede_repetir(tmp_path, camara):
    camara([jpeg(n=1)], [0])
    assert correr(tmp_path, "--cuadros", "2") == 1
    camara([jpeg(n=n) for n in range(2)], [0, 200])
    assert correr(tmp_path, "--cuadros", "2") == 0
    assert (tmp_path / "S01" / "captura.jsonl").exists()


def test_comando_guarda_los_rechazados(tmp_path, camara):
    camara([jpeg(n=1), jpeg()[:-2], jpeg(n=2)], [0, 200, 350])

    assert correr(tmp_path, "--cuadros", "2") == 0
    assert [p.name for p in (tmp_path / "S01" / "rechazados").iterdir()] == [
        "001_jpeg_incompleto.bin"
    ]


def test_comando_con_stream_defectuoso_termina_con_diagnostico(tmp_path, camara, capsys):
    camara(stream(jpeg(n=1)) + b"Content-Length: nope\r\n\r\n", [0])

    assert correr(tmp_path, "--cuadros", "3") == 1
    assert "Content-Length no numérico" in capsys.readouterr().err
    assert not (tmp_path / "S01").exists()


def test_comando_con_content_length_incumplido_aparta_la_captura(tmp_path, camara, capsys):
    a = jpeg(n=1)
    camara(b"Content-Length: %d\r\n\r\n" % (len(a) + 5) + a + SEPARADOR + b"X" * 50, [0])

    assert correr(tmp_path, "--cuadros", "1") == 1
    assert "Content-Length" in capsys.readouterr().err
    assert not (tmp_path / "S01").exists()
    [intento] = fallidas(tmp_path)
    assert [p.name for p in (intento / "rechazados").iterdir()] == ["001_content_length.bin"]


def test_el_limite_incluye_las_cabeceras_lentas(tmp_path, monkeypatch, capsys):
    # Servidor real en localhost: manda un byte de cabecera a cada rato, sin llegar al stream.
    monkeypatch.setattr(cli, "MARGEN_CORTE_S", 0)
    servidor = socket.create_server(("127.0.0.1", 0))
    fin = threading.Event()

    def goteo():
        conexion, _ = servidor.accept()
        with conexion:
            for byte in b"HTTP/1.1 200 OK\r\n" + b"X" * 1000:
                if fin.wait(0.05):
                    return
                conexion.sendall(bytes([byte]))

    hilo = threading.Thread(target=goteo, daemon=True)
    hilo.start()
    url = f"http://127.0.0.1:{servidor.getsockname()[1]}/stream"
    args = ["--url", url, "--secuencia", "S01", "--sin-pausa", "--salida", str(tmp_path)]
    inicio = time.monotonic()
    try:
        resultado = cli.main([*args, "--limite-s", "0.3"])
    finally:
        fin.set()
        hilo.join(5)
        servidor.close()

    assert resultado == 2
    assert time.monotonic() - inicio < 5
    assert "tiempo límite" in capsys.readouterr().err
    assert not (tmp_path / "S01").exists()


def test_una_falla_al_escribir_no_deja_nada_a_medias(tmp_path, camara, monkeypatch, capsys):
    camara([jpeg(n=n) for n in range(3)], [0, 200, 400])
    escritos = []
    original = cli.Path.write_bytes

    def falla_en_el_segundo(self, datos):
        escritos.append(self)
        if len(escritos) == 2:
            original(self, datos[:10])
            raise OSError("disco lleno")
        return original(self, datos)

    monkeypatch.setattr(cli.Path, "write_bytes", falla_en_el_segundo)

    assert correr(tmp_path, "--cuadros", "3") == 2
    assert "disco lleno" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_comando_no_sobrescribe_una_secuencia(tmp_path, camara):
    (tmp_path / "S01").mkdir()
    camara([jpeg()], [0])
    assert correr(tmp_path) == 2


def test_el_error_de_conexion_no_muestra_la_contrasena(tmp_path, monkeypatch, capsys):
    @contextmanager
    def abrir(url, timeout, limite_s, cortado):
        raise OSError("conexión rechazada")
        yield

    monkeypatch.setattr(cli, "_abrir", abrir)
    url = "http://andy:secreta123@carro:81/stream"
    args = ["--url", url, "--secuencia", "S01", "--sin-pausa", "--salida", str(tmp_path)]
    assert cli.main(args) == 2
    err = capsys.readouterr().err
    assert "secreta123" not in err
    assert "andy" not in err
    assert "http://***@carro:81/stream" in err


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "ftp://carro/stream", "http:///stream", "http://carro:xx/s"]
)
def test_comando_solo_acepta_urls_http(tmp_path, url):
    with pytest.raises(SystemExit):
        cli.main(["--url", url, "--secuencia", "S01", "--sin-pausa", "--salida", str(tmp_path)])
    assert not (tmp_path / "S01").exists()
