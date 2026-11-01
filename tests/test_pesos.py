"""Carga de pesos locales: SHA-256, errores y aislamiento de la copia verificada."""

from __future__ import annotations

import hashlib
import os
from dataclasses import replace
from pathlib import Path

import pytest

from infer import pesos
from infer.config import cargar_config_detector


def _config_para(contenido: bytes):
    return replace(
        cargar_config_detector(), expected_model_sha256=hashlib.sha256(contenido).hexdigest()
    )


def _carga_falsa(monkeypatch: pytest.MonkeyPatch, inspeccionar):
    """Mantiene la ruta real de copia/hash y sustituye solo la deserialización."""
    monkeypatch.setattr(pesos, "verificar_versiones_runtime", lambda _config: None)
    monkeypatch.setattr(pesos, "_construir_yolo", inspeccionar)
    monkeypatch.setattr(pesos, "_preparar_cpu", lambda _modelo, _config: None)


def test_checkpoint_valido_usa_copia_de_bytes_verificados(tmp_path: Path, monkeypatch):
    contenido = b"checkpoint de prueba, no un modelo"
    ruta = tmp_path / "checkpoint.pt"
    ruta.write_bytes(contenido)
    config = _config_para(contenido)
    visto = []

    def construir(copia, _config):
        assert copia != ruta
        assert copia.is_file() and copia.suffix == ".pt"
        visto.append(copia.read_bytes())
        return object()

    _carga_falsa(monkeypatch, construir)
    cargado = pesos.cargar_pesos(ruta, config)
    assert visto == [contenido]
    assert cargado.model_sha256 == hashlib.sha256(contenido).hexdigest()
    assert cargado.config_sha256 == config.config_sha256
    assert cargado.modelo is not None


def test_checkpoint_alterado_no_llega_al_constructor(tmp_path: Path, monkeypatch):
    ruta = tmp_path / "checkpoint.pt"
    ruta.write_bytes(b"bytes alterados")

    def prohibido(_ruta, _config):
        pytest.fail("se intentó cargar un checkpoint con hash incorrecto")

    _carga_falsa(monkeypatch, prohibido)
    with pytest.raises(pesos.ErrorCargaPesos, match="SHA-256 del checkpoint no coincide"):
        pesos.cargar_pesos(ruta, _config_para(b"bytes originales"))


@pytest.mark.parametrize("ruta", ["inexistente.pt", "yolo11n.pt", "https://host/model.pt"])
def test_ruta_ausente_o_nombre_de_modelo_no_dispara_descarga(tmp_path: Path, monkeypatch, ruta):
    def prohibido(_ruta, _config):
        pytest.fail("se intentó construir o descargar un modelo ausente")

    _carga_falsa(monkeypatch, prohibido)
    with pytest.raises(pesos.ErrorCargaPesos, match="no se pudo abrir"):
        pesos.cargar_pesos(tmp_path / ruta, _config_para(b"contenido"))


def test_archivo_inaccesible_da_error_controlado(tmp_path: Path, monkeypatch):
    ruta = tmp_path / "checkpoint.pt"
    ruta.write_bytes(b"contenido")
    abrir_original = pesos.os.open

    def sin_permiso(path, flags, *args, **kwargs):
        if Path(path) == ruta:
            raise PermissionError("acceso denegado")
        return abrir_original(path, flags, *args, **kwargs)

    monkeypatch.setattr(pesos.os, "open", sin_permiso)
    with pytest.raises(pesos.ErrorCargaPesos, match=r"no se pudo abrir.*acceso denegado"):
        pesos.cargar_pesos(ruta, _config_para(b"contenido"))


@pytest.mark.parametrize("sha", ["abc", "G" * 64, "0" * 63, 123, None])
def test_hash_esperado_malformado_se_rechaza_antes_de_leer(tmp_path: Path, sha, monkeypatch):
    ruta = tmp_path / "checkpoint.pt"
    ruta.write_bytes(b"contenido")

    def prohibido(_ruta, _config):
        pytest.fail("no se debe intentar construir el modelo")

    _carga_falsa(monkeypatch, prohibido)
    config = replace(cargar_config_detector(), expected_model_sha256=sha)
    with pytest.raises(pesos.ErrorCargaPesos, match="SHA-256 esperado"):
        pesos.cargar_pesos(ruta, config)


def test_ruta_no_regular_y_enlace_simbolico(tmp_path: Path):
    config = _config_para(b"contenido")
    directorio = tmp_path / "carpeta.pt"
    directorio.mkdir()
    with pytest.raises(pesos.ErrorCargaPesos):
        pesos.cargar_pesos(directorio, config)
    archivo = tmp_path / "archivo.pt"
    archivo.write_bytes(b"contenido")
    enlace = tmp_path / "enlace.pt"
    try:
        enlace.symlink_to(archivo)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"el entorno no permite crear enlaces simbólicos: {exc}")
    with pytest.raises(pesos.ErrorCargaPesos, match="enlace simbólico"):
        pesos.cargar_pesos(enlace, config)


def test_checkpoint_en_directorio_padre_enlazado_conserva_hash(tmp_path: Path, monkeypatch):
    contenido = b"checkpoint local aprobado en la prueba"
    directorio = tmp_path / "real"
    directorio.mkdir()
    (directorio / "checkpoint.pt").write_bytes(contenido)
    enlace_padre = tmp_path / "enlace-padre"
    try:
        enlace_padre.symlink_to(directorio, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"el entorno no permite crear enlaces simbólicos: {exc}")

    def construir(copia, _config):
        assert copia.read_bytes() == contenido
        return object()

    _carga_falsa(monkeypatch, construir)
    cargado = pesos.cargar_pesos(enlace_padre / "checkpoint.pt", _config_para(contenido))
    assert cargado.model_sha256 == hashlib.sha256(contenido).hexdigest()


def test_cambio_del_original_entre_hash_y_carga_no_cambia_la_copia(tmp_path: Path, monkeypatch):
    original = b"checkpoint original"
    ruta = tmp_path / "checkpoint.pt"
    ruta.write_bytes(original)
    config = _config_para(original)

    def construir(copia, _config):
        ruta.write_bytes("checkpoint reemplazado después de la verificación".encode())
        assert copia.read_bytes() == original
        return object()

    _carga_falsa(monkeypatch, construir)
    cargado = pesos.cargar_pesos(ruta, config)
    assert ruta.read_bytes() != original
    assert cargado.model_sha256 == hashlib.sha256(original).hexdigest()


def test_copia_temporal_desaparecida_no_activa_descarga(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("YOLO_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("MPLCONFIGDIR", str(tmp_path / "matplotlib"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    import ultralytics
    from ultralytics.utils import downloads

    ruta = tmp_path / "copia.pt"
    ruta.write_bytes(b"contenido")

    def yolo_falso(path, **_kwargs):
        Path(path).unlink()
        downloads.attempt_download_asset(path)
        pytest.fail("se intentó descargar el archivo desaparecido")

    monkeypatch.setattr(ultralytics, "YOLO", yolo_falso)
    with pytest.raises(pesos.ErrorCargaPesos, match="descarga automática de pesos prohibida"):
        pesos._construir_yolo(ruta, cargar_config_detector())


def test_carga_real_yolo11n_cpu_si_existe_checkpoint(monkeypatch, tmp_path: Path):
    ruta_texto = os.environ.get("P5_05_YOLO11N_PT")
    if not ruta_texto:
        pytest.skip("definir P5_05_YOLO11N_PT para probar el checkpoint real")
    ruta = Path(ruta_texto)
    antes = hashlib.sha256(ruta.read_bytes()).hexdigest()
    monkeypatch.setenv("YOLO_CONFIG_DIR", str(tmp_path / "ultralytics"))
    monkeypatch.setenv("MPLCONFIGDIR", str(tmp_path / "matplotlib"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    from ultralytics.utils import downloads

    def prohibido(*_args, **_kwargs):
        pytest.fail("se intentó usar red o descargar pesos durante la carga")

    monkeypatch.setattr(downloads, "safe_download", prohibido)
    monkeypatch.setattr(downloads, "get_github_assets", prohibido)
    config = cargar_config_detector()
    cargado = pesos.cargar_pesos(ruta, config)
    assert cargado.model_sha256 == antes == config.expected_model_sha256
    assert cargado.config_sha256 == config.config_sha256
    assert str(cargado.modelo.device) == "cpu"
    assert cargado.modelo.task == "detect"
    assert cargado.modelo.model.training is False
    assert hashlib.sha256(ruta.read_bytes()).hexdigest() == antes
