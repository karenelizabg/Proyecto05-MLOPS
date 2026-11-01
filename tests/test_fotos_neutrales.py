"""Preparación de copias de ensayo sin revelar nombres de clase."""

from __future__ import annotations

import csv
import hashlib
import runpy
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def preparar_fotos():
    ruta = Path(__file__).resolve().parents[1] / "resultados" / "p5-05-preparar-fotos.py"
    return runpy.run_path(str(ruta))["preparar_fotos"]


def _originales(tmp_path: Path, *, duplicado: bool = False):
    originales = tmp_path / "originales"
    originales.mkdir()
    manifiesto = tmp_path / "manifiesto.csv"
    filas = []
    for indice in range(29):
        nombre = f"clase_{indice:04d}.jpg"
        contenido = f"JPEG de prueba {0 if duplicado and indice == 28 else indice}".encode()
        (originales / nombre).write_bytes(contenido)
        filas.append((nombre, hashlib.sha256(contenido).hexdigest(), len(contenido)))
    with manifiesto.open("w", newline="", encoding="utf-8") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(["archivo", "sha256", "bytes"])
        escritor.writerows(filas)
    return originales, manifiesto, filas


def test_copias_neutrales_ordenadas_por_sha_y_bytes_intactos(tmp_path, preparar_fotos):
    originales, manifiesto, filas = _originales(tmp_path)
    copias = tmp_path / "ensayo"
    tabla = tmp_path / "correspondencias.csv"
    correspondencias = preparar_fotos(originales, manifiesto, copias, tabla)
    assert len(correspondencias) == 29
    assert [sha for _, sha in correspondencias] == sorted(fila[1] for fila in filas)
    assert [nombre for nombre, _ in correspondencias] == [
        f"ensayo-{indice:04d}.jpg" for indice in range(1, 30)
    ]
    with tabla.open(newline="", encoding="utf-8") as archivo:
        filas_tabla = list(csv.DictReader(archivo))
    assert set(filas_tabla[0]) == {"neutral_name", "sha256"}
    assert [(fila["neutral_name"], fila["sha256"]) for fila in filas_tabla] == correspondencias
    assert "clase_" not in tabla.read_text(encoding="utf-8")
    for nombre, sha in correspondencias:
        assert hashlib.sha256((copias / nombre).read_bytes()).hexdigest() == sha
    for nombre, sha, _ in filas:
        assert hashlib.sha256((originales / nombre).read_bytes()).hexdigest() == sha


def test_rechaza_hash_duplicado_sin_crear_copias_ni_tabla(tmp_path, preparar_fotos):
    originales, manifiesto, _ = _originales(tmp_path, duplicado=True)
    copias = tmp_path / "ensayo"
    tabla = tmp_path / "correspondencias.csv"
    with pytest.raises(ValueError, match="duplicados"):
        preparar_fotos(originales, manifiesto, copias, tabla)
    assert not copias.exists() and not tabla.exists()


def test_rechaza_original_alterado_sin_crear_evidencia(tmp_path, preparar_fotos):
    originales, manifiesto, filas = _originales(tmp_path)
    (originales / filas[0][0]).write_bytes(b"alterado")
    copias = tmp_path / "ensayo"
    tabla = tmp_path / "correspondencias.csv"
    with pytest.raises(ValueError, match="SHA-256"):
        preparar_fotos(originales, manifiesto, copias, tabla)
    assert not copias.exists() and not tabla.exists()


def test_rechaza_destino_existente_sin_sobrescribir(tmp_path, preparar_fotos):
    originales, manifiesto, _ = _originales(tmp_path)
    copias = tmp_path / "ensayo"
    copias.mkdir()
    previo = copias / "previo.txt"
    previo.write_text("intacto", encoding="utf-8")
    with pytest.raises(FileExistsError):
        preparar_fotos(originales, manifiesto, copias, tmp_path / "correspondencias.csv")
    assert previo.read_text(encoding="utf-8") == "intacto"
