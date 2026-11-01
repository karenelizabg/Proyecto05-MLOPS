"""Entradas fallidas de C8 y C9 (P5-12): están completas y `captura` las rechaza."""

import hashlib
from pathlib import Path

import pytest

from captura import motivo_rechazo

FIXTURES = Path(__file__).resolve().parents[1] / "datos" / "fixtures"
TAMANO = (640, 480)
MOTIVOS = {
    "vacia.jpg": "jpeg_incompleto",
    "no_es_jpeg.jpg": "jpeg_incompleto",
    "sin_imagen.jpg": "jpeg_incompleto",
    "truncado.jpg": "jpeg_incompleto",
    "otras_dimensiones.jpg": "tamano_320x240",
}


def _sumas() -> dict[str, str]:
    lineas = (FIXTURES / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    return {nombre: suma for suma, nombre in (linea.split() for linea in lineas)}


def test_sha256sums_lista_exactamente_las_fixtures():
    assert set(_sumas()) == set(MOTIVOS)
    assert {p.name for p in FIXTURES.glob("*.jpg")} == set(MOTIVOS)


@pytest.mark.parametrize("nombre", sorted(MOTIVOS))
def test_cada_fixture_conserva_su_sha256(nombre):
    assert hashlib.sha256((FIXTURES / nombre).read_bytes()).hexdigest() == _sumas()[nombre]


@pytest.mark.parametrize(("nombre", "motivo"), sorted(MOTIVOS.items()))
def test_captura_rechaza_cada_fixture(nombre, motivo):
    assert motivo_rechazo((FIXTURES / nombre).read_bytes(), TAMANO) == motivo
