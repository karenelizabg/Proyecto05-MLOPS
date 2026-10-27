"""Supervisor base (T03): revisa cada evento de percepción y le pregunta a la política qué hacer.

`procesar_evento(evento, ahora_ms)`:
1. Si `schema_version` no es `"1"`, STOP (`version_no_reconocida`): B rechaza las versiones que no
   reconoce antes de producir comandos.
2. Si `contrato.validar_evento` devuelve errores, STOP (`evento_invalido`).
3. Si el evento es válido, llama a la política y manda su decisión al adaptador.

La política es una función `decidir(evento, estado, config) -> (comando, estado_nuevo)`. De su
comando el supervisor toma `action`, `speed`, `steering` y `reason`; el resto de los campos lo pone
él. `valid_until_ms` lo calcula el adaptador con el `ahora_ms` del envío (T02). Los errores quedan
en `<carpeta del adaptador>/errores.jsonl` con `run_id` y `frame_id`. El supervisor no lee el reloj
del sistema: todos los métodos reciben `ahora_ms`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from contrato import validar_evento

from .adaptador_virtual import AdaptadorVirtual

Politica = Callable[[dict[str, Any], str, Any], tuple[dict[str, Any], str]]

NOMBRE_ERRORES = "errores.jsonl"
VERSION_RECONOCIDA = "1"
ESTADO_INICIAL = "DETENIDO"
# Cuando el evento no trae un run_id o frame_id que cumpla el contrato.
ID_DESCONOCIDO = "desconocido"
CAMPOS_DE_LA_POLITICA = ("action", "speed", "steering", "reason")

_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def politica_de_prueba(evento: dict[str, Any], estado: str, config: Any) -> tuple[dict[str, Any], str]:
    """Mientras no exista la política real (T09): siempre AVANZAR a velocidad 0.5."""
    comando = {"action": "AVANZAR", "speed": 0.5, "steering": 0.0, "reason": "politica_de_prueba"}
    return comando, "AVANZANDO"


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
        self.estado = ESTADO_INICIAL
        self.ruta_errores = adaptador.carpeta_salida / NOMBRE_ERRORES
        # Igual que comandos.jsonl: cada supervisor es una corrida y empieza sin errores.
        self.ruta_errores.write_text("", encoding="utf-8")
        self._ultimo_run_id = ID_DESCONOCIDO

    def procesar_evento(self, evento: Any, ahora_ms: float) -> dict[str, Any]:
        """Decide con un evento de percepción. Devuelve el comando que quedó registrado."""
        version = evento.get("schema_version") if isinstance(evento, dict) else None
        if version != VERSION_RECONOCIDA:
            return self._stop_por_evento(
                evento, ahora_ms, "version_no_reconocida",
                [f"schema_version: {version!r} no es {VERSION_RECONOCIDA!r}"],
            )

        errores = validar_evento(evento)
        if errores:
            return self._stop_por_evento(evento, ahora_ms, "evento_invalido", errores)

        self._ultimo_run_id = evento["run_id"]
        decision, estado_nuevo = self.politica(evento, self.estado, self.config_politica)
        comando = self._comando(evento["run_id"], evento["frame_id"], estado_nuevo, ahora_ms)
        comando.update({campo: decision[campo] for campo in CAMPOS_DE_LA_POLITICA})
        return self._enviar(comando, estado_nuevo, ahora_ms)

    def tick(self, ahora_ms: float) -> None:
        """Reloj y watchdog. Se llena en T05 (#25)."""

    def emergencia(self, ahora_ms: float) -> None:
        """Paro de emergencia. Se llena en T06 (#26)."""

    def rearmar(self, ahora_ms: float) -> None:
        """Rearme tras un paro. Se llena en T06 (#26)."""

    def cerrar(self, ahora_ms: float) -> None:
        """Fin del run. Se llena en T06 (#26)."""

    def _stop_por_evento(
        self, evento: Any, ahora_ms: float, motivo: str, errores: list[str]
    ) -> dict[str, Any]:
        run_id = self._id_del_evento(evento, "run_id") or self._ultimo_run_id
        frame_id = self._id_del_evento(evento, "frame_id") or ID_DESCONOCIDO
        self._registrar_error(run_id, frame_id, ahora_ms, motivo, errores)

        comando = self._comando(run_id, frame_id, "DETENIDO", ahora_ms)
        comando.update({"action": "STOP", "speed": 0, "steering": 0.0, "reason": motivo})
        return self._enviar(comando, "DETENIDO", ahora_ms)

    def _comando(
        self, run_id: str, frame_id: str, estado_nuevo: str, ahora_ms: float
    ) -> dict[str, Any]:
        return {
            "schema_version": VERSION_RECONOCIDA,
            "run_id": run_id,
            "frame_id": frame_id,
            "event": "frame",
            "state_before": self.estado,
            "state_after": estado_nuevo,
            "t_decision_ms": ahora_ms,
        }

    def _enviar(self, comando: dict[str, Any], estado_nuevo: str, ahora_ms: float) -> dict[str, Any]:
        self.estado = estado_nuevo
        return self.adaptador.enviar(comando, ahora_ms)

    def _registrar_error(
        self, run_id: str, frame_id: str, ahora_ms: float, motivo: str, errores: list[str]
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
