"""Supervisor base (T03): revisa cada evento de percepción y le pregunta a la política qué hacer.

`procesar_evento(evento, ahora_ms)`:
1. Si `schema_version` no es `"1"`, STOP (`version_no_reconocida`): B rechaza las versiones que no
   reconoce antes de producir comandos.
2. Si `status` es `error`, STOP con el código en la razón (`error_detector:<code>`), también si el
   código es desconocido (C9, T04). Va antes del paso 3 porque el esquema rechaza los códigos
   desconocidos y la razón perdería el código.
3. Si `contrato.validar_evento` devuelve errores, STOP (`evento_invalido`).
4. Si `status` es `stale`, STOP (`stale`): rechaza la entrada vieja y cancela la orden previa (C8).
5. Si el cuadro `ok` es más viejo que `max_frame_age_ms` (`ahora_ms − t_capture_ms`), STOP
   (`cuadro_viejo`): B lo rechaza por edad aunque A no lo haya marcado `stale` (DC-3, T05).
6. Si el evento es `ok`, llama a la política y manda su decisión al adaptador. Si la política lanza
   una excepción (`politica_excepcion`) o su comando no cumple el contrato (`politica_invalida`),
   STOP. Un `ok` con `detections: []` no es error: sigue a la política.

La política es una función `decidir(evento, estado, config) -> (comando, estado_nuevo)`. De su
comando el supervisor toma `action`, `speed`, `steering` y `reason`; el resto de los campos lo pone
él. El estado es un diccionario con la clave `nombre` (DETENIDO, AVANZANDO, GIRANDO_IZQ o
GIRANDO_DER) más lo que la política necesite guardar, p. ej. `{"nombre": "AVANZANDO",
"libres_seguidos": 0}`. El supervisor guarda el diccionario completo, se lo pasa a la política en el
siguiente cuadro y usa `estado["nombre"]` para `state_before` y `state_after`. Empieza en
`{"nombre": "DETENIDO"}`, y cada STOP del supervisor lo regresa ahí: se descartan los datos de la
política para que no reanude con una cuenta vieja.

`tick(ahora_ms)` es el watchdog (C8, T05): si la orden activa no es STOP y pasaron más de
`watchdog_ms` desde el último cuadro aceptado (`watchdog_vencido`), o ya venció su
`valid_until_ms` (`orden_vencida`), manda STOP con `event=clock` y `frame_id=null`. Lo manda una
sola vez: con la orden activa ya en STOP, los siguientes ticks no repiten nada.

`valid_until_ms` lo calcula el adaptador con el `ahora_ms` del envío (T02). Cada STOP por falla
queda en `<carpeta del adaptador>/errores.jsonl` con `run_id` y `frame_id`. El supervisor no lee el
reloj del sistema: todos los métodos reciben `ahora_ms`.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable
from typing import Any

from contrato import validar_comando, validar_evento

from .adaptador_virtual import AdaptadorVirtual

Estado = dict[str, Any]
Politica = Callable[[dict[str, Any], Estado, Any], tuple[dict[str, Any], Estado]]

NOMBRE_ERRORES = "errores.jsonl"
VERSION_RECONOCIDA = "1"
NOMBRES_DE_ESTADO = ("DETENIDO", "AVANZANDO", "GIRANDO_IZQ", "GIRANDO_DER")
ESTADO_INICIAL: Estado = {"nombre": "DETENIDO"}
# Cuando el evento no trae un run_id o frame_id que cumpla el contrato.
ID_DESCONOCIDO = "desconocido"
CAMPOS_DE_LA_POLITICA = ("action", "speed", "steering", "reason")
# error.code del contrato (C9). Cualquier otro también da STOP, pero se marca como desconocido.
CODIGOS_DE_ERROR = ("unreadable_image", "detector_exception", "detector_timeout", "invalid_output")

_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def politica_de_prueba(
    _evento: dict[str, Any], _estado: Estado, _config: Any
) -> tuple[dict[str, Any], Estado]:
    """Mientras no exista la política real (T09): siempre AVANZAR a velocidad 0.5."""
    comando = {"action": "AVANZAR", "speed": 0.5, "steering": 0.0, "reason": "politica_de_prueba"}
    return comando, {"nombre": "AVANZANDO"}


class Supervisor:
    def __init__(
        self,
        politica: Politica,
        adaptador: AdaptadorVirtual,
        plazos: dict[str, Any],
        config_politica: Any,
    ) -> None:
        self.politica = politica
        self.adaptador = adaptador
        self.plazos = plazos
        self.config_politica = config_politica
        self.estado: Estado = dict(ESTADO_INICIAL)
        self.ruta_errores = adaptador.carpeta_salida / NOMBRE_ERRORES
        # Igual que comandos.jsonl: cada supervisor es una corrida y empieza sin errores.
        self.ruta_errores.write_text("", encoding="utf-8")
        self._ultimo_run_id = ID_DESCONOCIDO
        # ahora_ms del último cuadro ok aceptado (no stale ni viejo); lo vigila el watchdog.
        self._ultimo_cuadro_ms: float | None = None

    def procesar_evento(self, evento: Any, ahora_ms: float) -> dict[str, Any]:
        """Decide con un evento de percepción. Devuelve el comando que quedó registrado."""
        version = evento.get("schema_version") if isinstance(evento, dict) else None
        if version != VERSION_RECONOCIDA:
            return self._stop_por_evento(
                evento, ahora_ms, "version_no_reconocida",
                [f"schema_version: {version!r} no es {VERSION_RECONOCIDA!r}"],
            )

        if evento.get("status") == "error":
            return self._stop_por_error_del_detector(evento, ahora_ms)

        errores = validar_evento(evento)
        if errores:
            return self._stop_por_evento(evento, ahora_ms, "evento_invalido", errores)

        self._ultimo_run_id = evento["run_id"]
        if evento["status"] == "stale":
            edad_ms = evento["t_emit_ms"] - evento["t_capture_ms"]
            detalle = [f"status=stale: cuadro de {edad_ms} ms; se rechaza y se cancela la orden previa"]
            return self._stop_por_evento(evento, ahora_ms, "stale", detalle)

        edad_ms = ahora_ms - evento["t_capture_ms"]
        if edad_ms > self.plazos["max_frame_age_ms"]:
            detalle = [
                f"edad del cuadro {edad_ms} ms (ahora_ms − t_capture_ms) > "
                f"max_frame_age_ms {self.plazos['max_frame_age_ms']} ms"
            ]
            return self._stop_por_evento(evento, ahora_ms, "cuadro_viejo", detalle)

        self._ultimo_cuadro_ms = ahora_ms
        return self._decidir(evento, ahora_ms)

    def tick(self, ahora_ms: float) -> dict[str, Any] | None:
        """Watchdog. Devuelve el STOP de reloj si lo mandó; `None` si no hizo falta."""
        activo = self.adaptador.activo
        if activo is None or activo["action"] == "STOP":
            return None

        # Una orden activa sin cuadro registrado no debería pasar; si pasa, frena.
        ultimo = self._ultimo_cuadro_ms if self._ultimo_cuadro_ms is not None else float("-inf")
        sin_cuadro_ms = ahora_ms - ultimo
        if sin_cuadro_ms > self.plazos["watchdog_ms"]:
            detalle = [
                f"{sin_cuadro_ms} ms sin cuadro nuevo > watchdog_ms {self.plazos['watchdog_ms']} ms"
            ]
            return self._stop_por_reloj(ahora_ms, "watchdog_vencido", detalle)
        if ahora_ms > activo["valid_until_ms"]:
            detalle = [f"la orden {activo['action']} valía hasta {activo['valid_until_ms']} ms"]
            return self._stop_por_reloj(ahora_ms, "orden_vencida", detalle)
        return None

    def emergencia(self, ahora_ms: float) -> None:
        """Paro de emergencia. Se llena en T06 (#26)."""

    def rearmar(self, ahora_ms: float) -> None:
        """Rearme tras un paro. Se llena en T06 (#26)."""

    def cerrar(self, ahora_ms: float) -> None:
        """Fin del run. Se llena en T06 (#26)."""

    def _decidir(self, evento: dict[str, Any], ahora_ms: float) -> dict[str, Any]:
        """Llama a la política. Si falla o devuelve un comando o estado fuera de lo acordado, STOP."""
        try:
            # Una copia: si la política cambia el estado y luego falla, el guardado no se toca.
            estado = copy.deepcopy(self.estado)
            decision, estado_nuevo = self.politica(evento, estado, self.config_politica)
            accion = {campo: decision[campo] for campo in CAMPOS_DE_LA_POLITICA}
        except Exception as exc:  # cualquier falla de la política termina en STOP, no tumba el programa
            detalle = [f"{type(exc).__name__}: {exc}"]
            return self._stop_por_evento(evento, ahora_ms, "politica_excepcion", detalle)

        errores = _errores_del_estado(estado_nuevo)
        if not errores:
            comando = self._comando(
                evento["run_id"], evento["frame_id"], estado_nuevo["nombre"], ahora_ms
            )
            comando.update(accion)
            errores = validar_comando(self._como_se_enviaria(comando, ahora_ms))
        if errores:
            return self._stop_por_evento(evento, ahora_ms, "politica_invalida", errores)
        return self._enviar(comando, estado_nuevo, ahora_ms)

    def _como_se_enviaria(self, comando: dict[str, Any], ahora_ms: float) -> dict[str, Any]:
        """El comando con los campos que agrega el adaptador, para validarlo antes de enviarlo."""
        return {
            **comando,
            "received": True,
            "t_command_ms": ahora_ms,
            "valid_until_ms": ahora_ms + self.adaptador.validez_orden_ms,
        }

    def _stop_por_error_del_detector(self, evento: dict[str, Any], ahora_ms: float) -> dict[str, Any]:
        error = evento.get("error")
        codigo = error.get("code") if isinstance(error, dict) else None
        mensaje = error.get("message") if isinstance(error, dict) else None
        detalle = [f"error.code: {codigo!r}", f"error.message: {mensaje!r}"]
        if codigo not in CODIGOS_DE_ERROR:
            detalle.append("error.code desconocido: se trata como error")
        return self._stop_por_evento(evento, ahora_ms, f"error_detector:{codigo}", detalle)

    def _stop_por_evento(
        self, evento: Any, ahora_ms: float, motivo: str, errores: list[str]
    ) -> dict[str, Any]:
        run_id = self._id_del_evento(evento, "run_id") or self._ultimo_run_id
        frame_id = self._id_del_evento(evento, "frame_id") or ID_DESCONOCIDO
        self._registrar_error(run_id, frame_id, ahora_ms, motivo, errores)

        return self._stop(run_id, frame_id, "frame", motivo, ahora_ms)

    def _stop_por_reloj(self, ahora_ms: float, motivo: str, errores: list[str]) -> dict[str, Any]:
        """STOP sin cuadro: `event=clock` y `frame_id=null`."""
        self._registrar_error(self._ultimo_run_id, None, ahora_ms, motivo, errores)
        return self._stop(self._ultimo_run_id, None, "clock", motivo, ahora_ms)

    def _stop(
        self, run_id: str, frame_id: str | None, evento: str, motivo: str, ahora_ms: float
    ) -> dict[str, Any]:
        detenido = dict(ESTADO_INICIAL)
        comando = self._comando(run_id, frame_id, detenido["nombre"], ahora_ms, evento)
        comando.update({"action": "STOP", "speed": 0, "steering": 0.0, "reason": motivo})
        return self._enviar(comando, detenido, ahora_ms)

    def _comando(
        self,
        run_id: str,
        frame_id: str | None,
        nombre_nuevo: str,
        ahora_ms: float,
        evento: str = "frame",
    ) -> dict[str, Any]:
        return {
            "schema_version": VERSION_RECONOCIDA,
            "run_id": run_id,
            "frame_id": frame_id,
            "event": evento,
            "state_before": self.estado["nombre"],
            "state_after": nombre_nuevo,
            "t_decision_ms": ahora_ms,
        }

    def _enviar(self, comando: dict[str, Any], estado_nuevo: Estado, ahora_ms: float) -> dict[str, Any]:
        self.estado = estado_nuevo
        return self.adaptador.enviar(comando, ahora_ms)

    def _registrar_error(
        self, run_id: str, frame_id: str | None, ahora_ms: float, motivo: str, errores: list[str]
    ) -> None:
        linea = {
            "run_id": run_id,
            "frame_id": frame_id,
            "t_ms": ahora_ms,
            "motivo": motivo,
            "errores": errores,
        }
        with self.ruta_errores.open("a", encoding="utf-8") as registro:
            registro.write(json.dumps(linea, ensure_ascii=False) + "\n")

    @staticmethod
    def _id_del_evento(evento: Any, campo: str) -> str | None:
        if not isinstance(evento, dict):
            return None
        valor = evento.get(campo)
        return valor if isinstance(valor, str) and _ID.match(valor) else None


def _errores_del_estado(estado: Any) -> list[str]:
    """El estado que devuelve la política: un diccionario con un `nombre` acordado."""
    if not isinstance(estado, dict) or "nombre" not in estado:
        return [f"estado: debe ser un diccionario con la clave 'nombre', llegó {estado!r}"]
    if estado["nombre"] not in NOMBRES_DE_ESTADO:
        return [f"estado.nombre: {estado['nombre']!r} no es uno de {', '.join(NOMBRES_DE_ESTADO)}"]
    return []
