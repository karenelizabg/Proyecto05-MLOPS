"""Adaptador virtual (T02): recibe los comandos de la política y los registra sin mover motores.

Cada comando se escribe como una línea JSON en `<carpeta_salida>/comandos.jsonl`, con
`received=true`, `t_command_ms` igual al `ahora_ms` con que llegó y
`valid_until_ms = ahora_ms + validez_orden_ms` (config/control/plazos.yaml). La vigencia se
cuenta desde el envío y no desde `t_decision_ms`: un comando que llega tarde no sale ya vencido.

Al crearse, el adaptador deja ese archivo vacío: una corrida nueva no se mezcla con la anterior.
Guarda el último comando como orden activa; un STOP la reemplaza y siempre queda con `speed=0`
y `steering=0`. Escribe con `allow_nan=False`: con un NaN o un infinito falla en vez de dejar
una línea que no es JSON. No importa ni llama hardware.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

NOMBRE_REGISTRO = "comandos.jsonl"


class AdaptadorVirtual:
    def __init__(self, carpeta_salida: Path | str, validez_orden_ms: float) -> None:
        self.carpeta_salida = Path(carpeta_salida)
        self.validez_orden_ms = validez_orden_ms
        # La carpeta la elige quien corre `python -m control --salida` (ver su docstring, S8707).
        self.carpeta_salida.mkdir(parents=True, exist_ok=True)  # NOSONAR (S8707)
        self.ruta_registro = self.carpeta_salida / NOMBRE_REGISTRO
        # Cada adaptador es una corrida: empieza con el registro vacío para no mezclar corridas.
        self.ruta_registro.write_text("", encoding="utf-8")  # NOSONAR (S8707)
        self._activo: dict[str, Any] | None = None

    @property
    def activo(self) -> dict[str, Any] | None:
        """Último comando recibido; `None` antes del primero."""
        return self._activo

    def enviar(self, comando: dict[str, Any], ahora_ms: float) -> dict[str, Any]:
        """Registra el comando y lo deja como orden activa. Devuelve lo que quedó escrito."""
        registrado = dict(comando)
        registrado["received"] = True
        registrado["t_command_ms"] = ahora_ms
        registrado["valid_until_ms"] = ahora_ms + self.validez_orden_ms
        if registrado["action"] == "STOP":
            registrado["speed"] = 0
            registrado["steering"] = 0.0

        with self.ruta_registro.open("a", encoding="utf-8") as registro:
            registro.write(json.dumps(registrado, ensure_ascii=False, allow_nan=False) + "\n")
        self._activo = registrado
        return registrado
