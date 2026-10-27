"""Política del grupo B: de un evento de percepción a una decisión.

- T08 (#28): `zonas_ocupadas` dice en qué zonas (izquierda, centro, derecha) hay obstáculo.
- T09 (#29): `decidir` convierte el evento en un comando AVANZAR / GIRAR_IZQ / GIRAR_DER / STOP.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from contrato import validar_evento

from .config import ZONAS, ConfigPolitica


def caja_a_xyxy(bbox: Sequence[float], bbox_format: str) -> tuple[float, float, float, float]:
    """Convierte una caja del contrato a `(x1, y1, x2, y2)` en píxeles.

    `xyxy` = [x1, y1, x2, y2]; `xywh` = [x, y, ancho, alto] con (x, y) la esquina superior
    izquierda (origen arriba a la izquierda, x hacia la derecha; CONTRATO.md).
    """
    a, b, c, d = (float(v) for v in bbox)
    if bbox_format == "xyxy":
        return a, b, c, d
    if bbox_format == "xywh":
        return a, b, a + c, b + d
    raise ValueError(f"bbox_format desconocido: {bbox_format!r} (se espera 'xyxy' o 'xywh')")


def _zonas_de_caja(x1: float, x2: float, ancho: float, config: ConfigPolitica) -> set[str]:
    """Zonas que ocupa una caja horizontal [x1, x2] en una imagen de `ancho` píxeles."""
    # A ya recorta las cajas a la imagen; se recorta otra vez por seguridad.
    x1, x2 = max(0.0, min(x1, ancho)), max(0.0, min(x2, ancho))
    ancho_caja = x2 - x1
    ocupadas: set[str] = set()
    if ancho_caja <= 0:
        # El contrato exige ancho y alto positivos (validar_evento lo rechaza antes).
        return ocupadas
    for nombre in ZONAS:
        inicio, fin = config.zonas[nombre]
        z1, z2 = inicio * ancho, fin * ancho
        traslape = min(x2, z2) - max(x1, z1)
        if traslape > 0 and traslape / ancho_caja >= config.traslape_minimo:
            ocupadas.add(nombre)
    return ocupadas


def detecciones_por_zona(
    evento: Mapping[str, Any], config: ConfigPolitica
) -> dict[str, list[Mapping[str, Any]]]:
    """Detecciones relevantes en cada zona: `{'izq': [...], 'centro': [...], 'der': [...]}`.

    Mismas reglas que `zonas_ocupadas`; sirve para explicar en `reason` qué detección
    activó la decisión. Una caja ancha aparece en todas las zonas que ocupa.
    """
    status = evento.get("status")
    if status != "ok":
        raise ValueError(
            f"zonas_ocupadas solo acepta status='ok', llegó {status!r}: stale/error son STOP"
        )
    ancho = evento["image_width"]
    if not isinstance(ancho, (int, float)) or isinstance(ancho, bool) or ancho <= 0:
        raise ValueError(f"image_width inválido: {ancho!r}")

    formato = evento["bbox_format"]
    por_zona: dict[str, list[Mapping[str, Any]]] = {nombre: [] for nombre in ZONAS}
    for det in evento["detections"]:
        if det["class_id"] not in config.clases_obstaculo:
            continue
        if det["confidence"] < config.umbral_confianza:
            continue
        x1, _, x2, _ = caja_a_xyxy(det["bbox"], formato)
        for nombre in _zonas_de_caja(x1, x2, float(ancho), config):
            por_zona[nombre].append(det)
    return por_zona


def zonas_ocupadas(evento: Mapping[str, Any], config: ConfigPolitica) -> set[str]:
    """Devuelve el conjunto de zonas con obstáculo: subconjunto de {'izq', 'centro', 'der'}.

    - Solo cuentan detecciones con `class_id` en `clases_obstaculo` y
      `confidence >= umbral_confianza`. Se decide con `class_id`, nunca con `class_name`.
    - Los límites de zona se calculan con `image_width` DEL EVENTO, nunca con un ancho fijo.
    - Una caja ocupa una zona si la fracción de SU ancho que cae en la zona es
      `>= traslape_minimo`; una caja ancha puede ocupar dos o tres zonas.

    Solo tiene sentido con `status=ok`. Con `stale` o `error` lanza `ValueError` en vez de
    devolver un conjunto vacío, porque vacío significaría "vía libre" y el contrato dice
    que esos estados son STOP (reglas 2 y 4). Quien llama debe revisar el `status` antes.
    El evento debe venir ya validado con `contrato.validar_evento`.
    """
    return {nombre for nombre, dets in detecciones_por_zona(evento, config).items() if dets}


# --- T09: decisión ---------------------------------------------------------------------

# Estado de la política: un diccionario con la clave "nombre" (acuerdo del grupo B) más lo
# que la política necesite guardar entre cuadros (p. ej. "libres_seguidos" en T11).
# El supervisor (T04) guarda el diccionario completo y usa estado["nombre"] para
# state_before y state_after.
DETENIDO = "DETENIDO"
AVANZANDO = "AVANZANDO"
GIRANDO_IZQ = "GIRANDO_IZQ"
GIRANDO_DER = "GIRANDO_DER"
NOMBRES_DE_ESTADO = (DETENIDO, AVANZANDO, GIRANDO_IZQ, GIRANDO_DER)
ESTADO_INICIAL: dict[str, Any] = {"nombre": DETENIDO}

# Estado al que lleva cada acción.
ESTADO_POR_ACCION = {
    "STOP": DETENIDO,
    "AVANZAR": AVANZANDO,
    "GIRAR_IZQ": GIRANDO_IZQ,
    "GIRAR_DER": GIRANDO_DER,
}

NOMBRE_ZONA = {"izq": "la izquierda", "centro": "el centro", "der": "la derecha"}


def _nombre_de(estado: Mapping[str, Any]) -> str:
    """Nombre del estado recibido. Sin "nombre" o con uno desconocido se toma DETENIDO."""
    nombre = estado.get("nombre") if isinstance(estado, Mapping) else None
    return nombre if nombre in NOMBRES_DE_ESTADO else DETENIDO


def _describir(dets: Sequence[Mapping[str, Any]]) -> str:
    partes = [f"class_id {d['class_id']}, confianza {d['confidence']:g}" for d in dets]
    return "; ".join(partes)


def _comando(
    evento: Mapping[str, Any],
    estado: Mapping[str, Any],
    accion: str,
    razon: str,
    speed: float,
    steering: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    # Copia: conserva lo que traiga el estado (p. ej. contadores) y nunca modifica el original.
    previo = estado if isinstance(estado, Mapping) else {}
    nuevo = {**previo, "nombre": ESTADO_POR_ACCION[accion]}
    t = evento.get("t_capture_ms")
    comando = {
        "schema_version": "1",
        "run_id": evento.get("run_id") or "desconocido",
        "frame_id": evento.get("frame_id") or "desconocido",
        "event": "frame",
        "state_before": _nombre_de(estado),
        "state_after": nuevo["nombre"],
        "action": accion,
        "reason": razon,
        "speed": float(speed),
        "steering": float(steering),
        # Función pura: no lee el reloj. Se decide "en el instante" del cuadro (DC-2).
        "t_decision_ms": float(t) if isinstance(t, (int, float)) and t >= 0 else 0.0,
    }
    return comando, nuevo


def _lado_para_girar(
    evento: Mapping[str, Any], por_zona: Mapping[str, Sequence[Mapping[str, Any]]]
) -> str | None:
    """Zona lateral LIBRE hacia la cual girar, o None. Nunca devuelve una zona ocupada."""
    libres = [z for z in ("izq", "der") if not por_zona[z]]
    if len(libres) != 2:
        return libres[0] if libres else None
    # Las dos están libres: gira al lado contrario de donde cae el centro de los
    # obstáculos del centro. Si quedan justo a la mitad, gira a la izquierda.
    formato = evento["bbox_format"]
    centros = []
    for det in por_zona["centro"]:
        x1, _, x2, _ = caja_a_xyxy(det["bbox"], formato)
        centros.append((x1 + x2) / 2)
    promedio = sum(centros) / len(centros)
    return "der" if promedio < evento["image_width"] / 2 else "izq"


def decidir(
    evento: Mapping[str, Any], estado: Mapping[str, Any], config: ConfigPolitica
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Decide el comando para un evento de percepción (casos C1 a C5). Función pura.

    `estado` es un diccionario con la clave "nombre" (empieza en `ESTADO_INICIAL`).
    Devuelve `(comando, estado_nuevo)`: el estado nuevo es una copia con el "nombre" según
    la acción y conserva las demás claves. El comando trae los campos de la política; el
    adaptador (T02) completa `t_command_ms`, `valid_until_ms` y `received`.

    Reglas, en orden:
    1. Evento que no cumple el contrato, `schema_version` desconocida o `status` distinto
       de `ok` -> STOP (stale y error nunca son vía libre).
    2. Centro libre -> AVANZAR recto con `velocidad_avance` (C1; también C3 y C4: un
       obstáculo solo a un lado no estorba el camino).
    3. Centro ocupado y `permitir_giro` con una zona lateral libre -> GIRAR hacia esa
       zona (C2). Nunca gira hacia una zona ocupada.
    4. Centro ocupado sin zona lateral libre, o sin permiso de girar -> STOP (C2, C5).

    STOP siempre lleva speed=0 y steering=0. No lee el reloj: `t_decision_ms` es el
    `t_capture_ms` del evento.
    """
    if evento.get("schema_version") != "1":
        version = evento.get("schema_version")
        return _stop(evento, estado, f"schema_version {version!r} no reconocida: STOP.")
    status = evento.get("status")
    if status == "stale":
        return _stop(evento, estado, "Cuadro stale (dato viejo): pérdida de percepción, STOP.")
    if status == "error":
        codigo = (evento.get("error") or {}).get("code", "desconocido")
        return _stop(evento, estado, f"Error del detector ({codigo}): STOP.")
    if status != "ok":
        return _stop(evento, estado, f"status {status!r} desconocido: STOP.")
    errores = validar_evento(evento)
    if errores:
        return _stop(evento, estado, f"Evento fuera de contrato: STOP ({errores[0]}).")

    por_zona = detecciones_por_zona(evento, config)
    if not por_zona["centro"]:
        laterales = [z for z in ("izq", "der") if por_zona[z]]
        if laterales:
            detalle = ", ".join(f"{NOMBRE_ZONA[z]} ({_describir(por_zona[z])})" for z in laterales)
            razon = f"Centro libre: avanza recto; obstáculo solo en {detalle}."
        else:
            razon = "Centro libre: sin obstáculos en el camino, avanza recto."
        return _comando(evento, estado, "AVANZAR", razon, config.velocidad_avance, 0)

    en_centro = _describir(por_zona["centro"])
    if config.permitir_giro:
        lado = _lado_para_girar(evento, por_zona)
        if lado is not None:
            accion = "GIRAR_IZQ" if lado == "izq" else "GIRAR_DER"
            steering = -config.giro if lado == "izq" else config.giro
            razon = (
                f"Obstáculo en el centro ({en_centro}); {NOMBRE_ZONA[lado]} está libre: "
                f"gira hacia allá."
            )
            return _comando(evento, estado, accion, razon, config.velocidad_avance, steering)
        return _stop(
            evento, estado, f"Obstáculo en el centro ({en_centro}) y ningún lado libre: STOP."
        )
    return _stop(evento, estado, f"Obstáculo en el centro ({en_centro}); giro desactivado: STOP.")


def _stop(
    evento: Mapping[str, Any], estado: Mapping[str, Any], razon: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    return _comando(evento, estado, "STOP", razon, 0, 0)
