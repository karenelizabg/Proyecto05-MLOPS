"""Carga y revisión de la configuración de la política (T07, #27).

`cargar_config_politica(ruta)` lee `config/control/politica.yaml`, revisa que cada valor
esté en su rango y devuelve un `ConfigPolitica` inmutable. Si algo no cumple, lanza
`ErrorConfigPolitica` con todos los problemas juntos, para corregirlos de una vez.

`cargar_politica_vivo()` (P5-22) es la misma configuración más la sección `politica` de
`config/vivo.yaml`, que solo puede agregar claves opcionales (`umbral_lateral`). Las corridas
calificadas usan `politica.yaml` sin esas claves, y la política se porta igual que siempre.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

RAIZ = Path(__file__).resolve().parents[2]
RUTA_CONFIG_POLITICA = RAIZ / "config" / "control" / "politica.yaml"
RUTA_CONFIG_VIVO = RAIZ / "config" / "vivo.yaml"

ZONAS = ("izq", "centro", "der")
_CLAVES = (
    "zonas",
    "traslape_minimo",
    "clases_obstaculo",
    "clases_provisionales",
    "umbral_confianza",
    "cuadros_libres_para_reanudar",
    "velocidad_avance",
    "giro",
    "permitir_giro",
)
# Claves que pueden faltar. Sin ellas, la política decide igual que antes de existir (P5-22).
_OPCIONALES = ("umbral_lateral",)
# Tolerancia para comparar fracciones en coma flotante (bordes de zonas).
_TOL = 1e-9


class ErrorConfigPolitica(ValueError):
    """La configuración de la política falta, no se puede leer o tiene valores fuera de rango."""


@dataclass(frozen=True)
class ConfigPolitica:
    """Valores de la política. Ver los comentarios de config/control/politica.yaml."""

    zonas: dict[str, tuple[float, float]]
    traslape_minimo: float
    clases_obstaculo: frozenset[int]
    clases_provisionales: bool
    umbral_confianza: float
    cuadros_libres_para_reanudar: int
    velocidad_avance: float
    giro: float
    permitir_giro: bool
    # P5-22: confianza mínima para que una detección deje un lado como "no comprobado libre".
    # None = igual que umbral_confianza, y entonces no cambia ninguna decisión.
    umbral_lateral: float | None = None

    @property
    def umbral_lateral_efectivo(self) -> float:
        """El umbral lateral en uso: `umbral_lateral`, o `umbral_confianza` si no está."""
        return self.umbral_confianza if self.umbral_lateral is None else self.umbral_lateral


def _es_numero(valor: Any) -> bool:
    # bool es subclase de int en Python; aquí no cuenta como número.
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def _revisar_zonas(zonas: Any, errores: list[str]) -> dict[str, tuple[float, float]]:
    if not isinstance(zonas, dict) or set(zonas) != set(ZONAS):
        errores.append(f"zonas: debe tener exactamente las claves {list(ZONAS)}")
        return {}
    resultado: dict[str, tuple[float, float]] = {}
    for nombre in ZONAS:
        par = zonas[nombre]
        if not (isinstance(par, list) and len(par) == 2 and all(_es_numero(v) for v in par)):
            errores.append(f"zonas.{nombre}: debe ser [inicio, fin] con dos números")
            continue
        inicio, fin = float(par[0]), float(par[1])
        if not 0.0 <= inicio < fin <= 1.0:
            errores.append(f"zonas.{nombre}: se requiere 0 <= inicio < fin <= 1, hay {par}")
        resultado[nombre] = (inicio, fin)
    if len(resultado) == len(ZONAS):
        izq, centro, der = (resultado[n] for n in ZONAS)
        if abs(izq[0]) > _TOL or abs(der[1] - 1.0) > _TOL:
            errores.append("zonas: deben empezar en 0 (izq) y terminar en 1 (der)")
        if abs(izq[1] - centro[0]) > _TOL or abs(centro[1] - der[0]) > _TOL:
            errores.append("zonas: deben ser contiguas, sin huecos ni traslapes entre ellas")
    return resultado


def _revisar_fraccion(
    datos: dict[str, Any], clave: str, errores: list[str], *, cero_valido: bool
) -> float:
    valor = datos[clave]
    minimo_ok = (lambda v: v >= 0.0) if cero_valido else (lambda v: v > 0.0)
    if not _es_numero(valor) or not (minimo_ok(valor) and valor <= 1.0):
        rango = "0 <= valor <= 1" if cero_valido else "0 < valor <= 1"
        errores.append(f"{clave}: se requiere {rango}, hay {valor!r}")
        return 0.0
    return float(valor)


def _revisar_bool(datos: dict[str, Any], clave: str, errores: list[str]) -> bool:
    valor = datos[clave]
    if not isinstance(valor, bool):
        errores.append(f"{clave}: debe ser true o false, hay {valor!r}")
        return False
    return valor


def _revisar_clases(clases: Any, errores: list[str]) -> frozenset[int]:
    validas = isinstance(clases, list) and all(
        isinstance(c, int) and not isinstance(c, bool) and c >= 0 for c in clases
    )
    if not validas:
        errores.append(
            f"clases_obstaculo: debe ser una lista de class_id enteros >= 0, hay {clases!r}"
        )
        return frozenset()
    if not clases:
        errores.append("clases_obstaculo: no puede estar vacía (nunca habría obstáculos)")
    if len(set(clases)) != len(clases):
        errores.append(f"clases_obstaculo: tiene class_id repetidos: {clases}")
    return frozenset(clases)


def validar_config_politica(datos: Any) -> ConfigPolitica:
    """Revisa un diccionario ya leído y devuelve la configuración, o lanza ErrorConfigPolitica."""
    if not isinstance(datos, dict):
        raise ErrorConfigPolitica("la configuración debe ser un mapa clave: valor")
    errores: list[str] = []
    faltan = [c for c in _CLAVES if c not in datos]
    sobran = sorted(set(datos) - set(_CLAVES) - set(_OPCIONALES))
    if faltan:
        errores.append(f"faltan claves: {faltan}")
    if sobran:
        errores.append(f"claves desconocidas (¿error de dedo?): {sobran}")
    if faltan:
        raise ErrorConfigPolitica("; ".join(errores))

    zonas = _revisar_zonas(datos["zonas"], errores)
    traslape = _revisar_fraccion(datos, "traslape_minimo", errores, cero_valido=False)
    clases = _revisar_clases(datos["clases_obstaculo"], errores)
    provisionales = _revisar_bool(datos, "clases_provisionales", errores)
    umbral = _revisar_fraccion(datos, "umbral_confianza", errores, cero_valido=True)
    velocidad = _revisar_fraccion(datos, "velocidad_avance", errores, cero_valido=False)
    permitir_giro = _revisar_bool(datos, "permitir_giro", errores)
    # Si se permite girar, el giro debe ser > 0: GIRAR_IZQ/DER exigen steering distinto de 0.
    giro = _revisar_fraccion(datos, "giro", errores, cero_valido=not permitir_giro)

    cuadros = datos["cuadros_libres_para_reanudar"]
    if not (isinstance(cuadros, int) and not isinstance(cuadros, bool) and cuadros >= 1):
        errores.append(f"cuadros_libres_para_reanudar: debe ser entero >= 1, hay {cuadros!r}")
        cuadros = 1

    umbral_lateral = None
    if "umbral_lateral" in datos:
        umbral_lateral = _revisar_fraccion(datos, "umbral_lateral", errores, cero_valido=True)
        if umbral_lateral > umbral:
            errores.append(
                f"umbral_lateral: no puede ser mayor que umbral_confianza ({umbral:g}), "
                f"hay {umbral_lateral:g}"
            )

    if errores:
        raise ErrorConfigPolitica("; ".join(errores))
    return ConfigPolitica(
        zonas=zonas,
        traslape_minimo=traslape,
        clases_obstaculo=clases,
        clases_provisionales=provisionales,
        umbral_confianza=umbral,
        cuadros_libres_para_reanudar=cuadros,
        velocidad_avance=velocidad,
        giro=giro,
        permitir_giro=permitir_giro,
        umbral_lateral=umbral_lateral,
    )


def _leer_yaml(ruta: Path) -> Any:
    try:
        return yaml.safe_load(ruta.read_text(encoding="utf-8"))
    except OSError as e:
        raise ErrorConfigPolitica(f"no se pudo leer {ruta}: {e}") from e
    except yaml.YAMLError as e:
        raise ErrorConfigPolitica(f"{ruta} no es YAML válido: {e}") from e


def cargar_config_politica(ruta: Path | str = RUTA_CONFIG_POLITICA) -> ConfigPolitica:
    """Lee el YAML de la política y lo revisa. Lanza ErrorConfigPolitica si algo falla."""
    return validar_config_politica(_leer_yaml(Path(ruta)))


def datos_politica_vivo(
    ruta_vivo: Path | str = RUTA_CONFIG_VIVO, ruta_politica: Path | str = RUTA_CONFIG_POLITICA
) -> dict[str, Any]:
    """`politica.yaml` más la sección `politica` de `vivo.yaml`, todavía sin revisar.

    `vivo.yaml` solo puede agregar claves opcionales (`umbral_lateral`). Los valores que ya
    están en `politica.yaml` se cambian ahí, con un PR, porque son los de las corridas
    calificadas.
    """
    ruta_vivo = Path(ruta_vivo)
    datos = _leer_yaml(Path(ruta_politica))
    vivo = _leer_yaml(ruta_vivo) or {}
    if not isinstance(datos, dict) or not isinstance(vivo, dict):
        raise ErrorConfigPolitica("politica.yaml y vivo.yaml deben ser mapas clave: valor")
    extra = vivo.get("politica") or {}
    if not isinstance(extra, dict):
        raise ErrorConfigPolitica(f"{ruta_vivo}: la sección politica debe ser un mapa")
    prohibidas = sorted(set(extra) - set(_OPCIONALES))
    if prohibidas:
        raise ErrorConfigPolitica(
            f"{ruta_vivo}: la sección politica solo admite {list(_OPCIONALES)}; "
            f"{prohibidas} se cambian en politica.yaml"
        )
    return {**datos, **extra}


def cargar_politica_vivo(
    ruta_vivo: Path | str = RUTA_CONFIG_VIVO, ruta_politica: Path | str = RUTA_CONFIG_POLITICA
) -> ConfigPolitica:
    """La configuración de la política para el lazo en vivo (P5-21 a P5-23)."""
    return validar_config_politica(datos_politica_vivo(ruta_vivo, ruta_politica))
