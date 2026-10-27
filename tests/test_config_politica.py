"""Pruebas de la configuración de la política (T07, #27)."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from control.config import (
    RUTA_CONFIG_POLITICA,
    ErrorConfigPolitica,
    cargar_config_politica,
    validar_config_politica,
)


@pytest.fixture
def datos() -> dict:
    """Copia de config/control/politica.yaml para modificarla en cada prueba."""
    return yaml.safe_load(RUTA_CONFIG_POLITICA.read_text(encoding="utf-8"))


def test_carga_el_archivo_del_repo():
    config = cargar_config_politica()
    assert config.zonas == {"izq": (0.0, 0.33), "centro": (0.33, 0.67), "der": (0.67, 1.0)}
    assert 0 < config.traslape_minimo <= 1
    assert 0 <= config.umbral_confianza <= 1
    assert config.cuadros_libres_para_reanudar >= 1
    assert 0 < config.velocidad_avance <= 1
    assert 0 <= config.giro <= 1
    assert isinstance(config.permitir_giro, bool)


def test_clases_provisionales_estan_marcadas():
    # Hasta que las PM aprueben modelo/clases.json (T12, #32) las clases siguen provisionales.
    config = cargar_config_politica()
    assert config.clases_obstaculo == frozenset({0, 1})
    assert config.clases_provisionales is True


def test_acepta_ruta_como_texto():
    assert cargar_config_politica(str(RUTA_CONFIG_POLITICA)) == cargar_config_politica()


def test_config_es_inmutable():
    config = cargar_config_politica()
    with pytest.raises(AttributeError):
        config.umbral_confianza = 0.1  # type: ignore[misc]


def test_archivo_inexistente(tmp_path: Path):
    with pytest.raises(ErrorConfigPolitica, match="no se pudo leer"):
        cargar_config_politica(tmp_path / "no_existe.yaml")


def test_yaml_roto(tmp_path: Path):
    ruta = tmp_path / "roto.yaml"
    ruta.write_text("zonas: [0, 1\n", encoding="utf-8")
    with pytest.raises(ErrorConfigPolitica, match="no es YAML válido"):
        cargar_config_politica(ruta)


def test_falta_una_clave(datos):
    del datos["umbral_confianza"]
    with pytest.raises(ErrorConfigPolitica, match="faltan claves"):
        validar_config_politica(datos)


def test_clave_desconocida(datos):
    datos["umbral_confianza_x"] = 0.5
    with pytest.raises(ErrorConfigPolitica, match="claves desconocidas"):
        validar_config_politica(datos)


@pytest.mark.parametrize(
    ("clave", "valor"),
    [
        ("traslape_minimo", 0),
        ("traslape_minimo", 1.5),
        ("umbral_confianza", -0.1),
        ("umbral_confianza", 1.1),
        ("umbral_confianza", "0.5"),
        ("velocidad_avance", 0),
        ("velocidad_avance", 2),
        ("giro", 1.5),
        ("giro", 0),  # con permitir_giro: true, girar exige steering distinto de 0
        ("cuadros_libres_para_reanudar", 0),
        ("cuadros_libres_para_reanudar", 2.5),
        ("cuadros_libres_para_reanudar", True),
        ("permitir_giro", "si"),
        ("clases_provisionales", 1),
        ("clases_obstaculo", []),
        ("clases_obstaculo", [0, -1]),
        ("clases_obstaculo", ["mochila"]),
        ("clases_obstaculo", [1, 1]),
    ],
)
def test_valores_fuera_de_rango(datos, clave, valor):
    datos[clave] = valor
    with pytest.raises(ErrorConfigPolitica, match=clave):
        validar_config_politica(datos)


def test_giro_cero_valido_si_no_se_permite_girar(datos):
    datos["giro"] = 0
    datos["permitir_giro"] = False
    assert validar_config_politica(datos).giro == 0.0


@pytest.mark.parametrize(
    "zonas",
    [
        {"izq": [0, 0.33], "centro": [0.33, 0.67]},  # falta der
        {"izq": [0.1, 0.33], "centro": [0.33, 0.67], "der": [0.67, 1]},  # no empieza en 0
        {"izq": [0, 0.33], "centro": [0.33, 0.67], "der": [0.67, 0.9]},  # no termina en 1
        {"izq": [0, 0.3], "centro": [0.33, 0.67], "der": [0.67, 1]},  # hueco
        {"izq": [0, 0.4], "centro": [0.33, 0.67], "der": [0.67, 1]},  # traslape
        {"izq": [0.33, 0], "centro": [0.33, 0.67], "der": [0.67, 1]},  # al revés
        {"izq": [0, 0.33, 0.5], "centro": [0.33, 0.67], "der": [0.67, 1]},  # tres números
    ],
)
def test_zonas_invalidas(datos, zonas):
    datos["zonas"] = zonas
    with pytest.raises(ErrorConfigPolitica, match="zonas"):
        validar_config_politica(datos)


def test_reporta_todos_los_errores_juntos(datos):
    datos["umbral_confianza"] = 3
    datos["giro"] = -1
    with pytest.raises(ErrorConfigPolitica) as info:
        validar_config_politica(datos)
    assert "umbral_confianza" in str(info.value)
    assert "giro" in str(info.value)


def test_no_modifica_los_datos_de_entrada(datos):
    original = copy.deepcopy(datos)
    validar_config_politica(datos)
    assert datos == original
