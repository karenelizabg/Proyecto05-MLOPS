"""P5-22: puente mínimo PC → carro para la matriz de fallos. **No es el adaptador de P5-21.**

`AdaptadorPuente` hace todo lo que hace el `AdaptadorVirtual` de control (registra cada comando
en `comandos.jsonl`, con su vigencia) y además lo manda al carro por UDP con el emisor de P5-20.
Así la matriz prueba el supervisor y la política reales contra el carro simulado sin esperar al
lazo en vivo. Cuando P5-21 exista, la matriz se puede correr también con ese adaptador.

Si el carro deja de contestar, el puente lo anota en `avisos.jsonl` (`carro_sin_respuesta`),
avisa una vez por hueco y **manda STOP**. Mientras siga sin contestar, cambia cada orden de
movimiento por STOP (`orden_cambiada_por_stop`). Hay dos casos:

- El carro no oye (red caída o sin paquetes): el STOP no le llega, y lo detiene su paro
  automático al vencer la orden.
- El carro oye pero no contesta (`mudo`): sin este STOP seguiría obedeciendo los AVANZAR y no
  pararía nunca. Con él, para en cuanto llega.

Cuando vuelve a contestar, se reanudan las órdenes normales. El lazo de P5-21 tiene que hacer lo
mismo; está acordado como propuesta en el #104 (fallo 4 de docs/carro/emergencia.md).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from control import AdaptadorVirtual

from . import formato

NOMBRE_AVISOS = "avisos.jsonl"
# Más que un periodo del lazo (200 ms a 5 fps): un solo paquete perdido no debe frenar el carro.
ESPERA_RESPUESTA_MS = 250


def _ahora_ms() -> float:
    return time.perf_counter() * 1000


class AdaptadorPuente(AdaptadorVirtual):
    def __init__(
        self,
        carpeta_salida: Path | str,
        validez_orden_ms: float,
        ip: str,
        puerto: int = formato.PUERTO,
        espera_respuesta_ms: float = ESPERA_RESPUESTA_MS,
        al_avisar: Callable[[dict[str, Any]], None] | None = None,
        reloj: Callable[[], float] = _ahora_ms,
    ) -> None:
        super().__init__(carpeta_salida, validez_orden_ms)
        self.espera_respuesta_ms = espera_respuesta_ms
        self._al_avisar = al_avisar
        self.ruta_avisos = self.carpeta_salida / NOMBRE_AVISOS
        self.ruta_avisos.write_text("", encoding="utf-8")  # NOSONAR (S8707)
        # Sin pendientes: el emisor manda su STOP inicial al crearse.
        self._emisor = formato.Emisor(ip, puerto)
        # El silencio se mide con el reloj propio desde el envío real, no con el `ahora_ms` del
        # supervisor: ese se toma antes de procesar el cuadro, y el primero tarda ~300 ms.
        self._reloj = reloj
        self._sin_respuesta_desde: float | None = None
        self._avisado = False
        self._cerrado = False
        self.ultima_respuesta: Any = None

    def enviar(self, comando: dict[str, Any], ahora_ms: float) -> dict[str, Any]:
        registrado = super().enviar(comando, ahora_ms)
        if self._cerrado:
            return registrado
        comando = registrado
        if self._avisado and registrado["action"] != "STOP":
            # Un carro que no contesta no recibe órdenes de movimiento: puede estar oyendo.
            comando = {**registrado, "action": "STOP", "speed": 0, "steering": 0.0}
            self._avisar(ahora_ms, "orden_cambiada_por_stop", None, registrado["action"])
        orden = formato.orden_de_comando(self._emisor, comando, int(self.validez_orden_ms))
        self._emisor.enviar(orden)
        if self._sin_respuesta_desde is None:
            self._sin_respuesta_desde = self._reloj()
        self.revisar(ahora_ms)
        return registrado

    def revisar(self, ahora_ms: float) -> None:
        """Lee las respuestas que ya llegaron y avisa si el carro lleva rato sin contestar."""
        if self._cerrado:
            return
        # El aviso VENCIDA no prueba que el carro oiga: lo manda solo, aunque no le llegue nada.
        recibidas = [r for r in self._emisor.recibir(0) if r.respuesta.motivo != "VENCIDA"]
        if recibidas:
            self.ultima_respuesta = recibidas[-1].respuesta
            self._sin_respuesta_desde = None
            if self._avisado:
                self._avisar(ahora_ms, "carro_responde_otra_vez", None)
            self._avisado = False
            return
        desde = self._sin_respuesta_desde
        silencio = None if desde is None else self._reloj() - desde
        if silencio is None or self._avisado or silencio < self.espera_respuesta_ms:
            return
        self._avisado = True
        self._avisar(ahora_ms, "carro_sin_respuesta", silencio)
        self._emisor.enviar(self._emisor.orden("STOP"))

    def cerrar(self) -> None:
        """Manda los STOP de cierre del emisor y suelta el socket."""
        if not self._cerrado:
            self._cerrado = True
            self._emisor.cerrar()

    def _avisar(
        self,
        ahora_ms: float,
        motivo: str,
        sin_respuesta_ms: float | None,
        accion_original: str | None = None,
    ) -> None:
        aviso = {"t_ms": ahora_ms, "motivo": motivo, "sin_respuesta_ms": sin_respuesta_ms}
        if accion_original is not None:
            aviso["accion_original"] = accion_original
        with self.ruta_avisos.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(aviso, ensure_ascii=False) + "\n")
        if self._al_avisar is not None:
            self._al_avisar(aviso)
