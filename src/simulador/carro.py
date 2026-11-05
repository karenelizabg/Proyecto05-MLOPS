"""P5-22: carro simulado. Escucha el protocolo por UDP y se porta como el firmware.

Sirve para probar el adaptador WiFi (P5-21) y la matriz de fallos sin el carro real. Las reglas
de cada orden son las de `Placa` (vía `formato`); aquí se agregan la red, el reloj de la placa,
la bitácora y los fallos que se pueden inyectar mientras corre.

Lo que no reproduce: la latencia ni las pérdidas reales del WiFi (para eso están los retardos y
la pérdida inyectables), la inercia del carro ni el tiempo que tardan los motores en pararse.
"""

from __future__ import annotations

import json
import random
import selectors
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import formato

PERIODO_REVISION_MS = 5  # el firmware revisa vencimientos cada 10 ms o menos
# UDP no pasa de 65 507 bytes de datos. Con un búfer menor, Windows lanza OSError en vez de
# truncar, y el datagrama largo no llegaría a la placa como MAL_FORMADA.
MAX_DATAGRAMA = 65535


def _ahora_ms() -> float:
    # perf_counter y no monotonic: en Windows monotonic avanza en saltos de ~15 ms.
    return time.perf_counter() * 1000


@dataclass
class Fallos:
    """Fallos que se pueden cambiar con el simulador corriendo."""

    mudo: bool = False
    """Recibe y aplica las órdenes, pero no contesta nada (tampoco el aviso VENCIDA)."""
    retardo_ms: float = 0.0
    """Cada respuesta sale este tiempo después de aplicar la orden."""
    perdida: float = 0.0
    """Fracción (0 a 1) de datagramas entrantes que se pierden antes de llegar a la placa."""
    duplicar: bool = False
    """Cada datagrama entrante llega dos veces seguidas. Con `desordenar` a la vez, manda
    `desordenar` y no se duplica nada."""
    desordenar: bool = False
    """Cada par de datagramas entrantes llega al revés."""
    espera_desorden_ms: float = 250.0
    """Con `desordenar`, cuánto se retiene un datagrama esperando al siguiente. Si no llega
    otro, el retenido se entrega solo (tarde). Por omisión es más que el periodo del lazo
    (200 ms a 5 fps), para que de verdad lleguen dos y se inviertan."""
    wifi_cortado: bool = False
    """No entra ni sale nada. Al cortarse, la placa frena de inmediato."""


class CarroSimulado:
    """Carro falso en un hilo propio. `with CarroSimulado() as carro:` lo arranca y lo apaga."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        puerto: int = formato.PUERTO,
        techo: int = formato.TECHO_PWM,
        minimo: int = formato.MINIMO_PWM,
        fallos: Fallos | None = None,
        bitacora: Path | str | None = None,
        semilla: int | None = None,
        al_registrar: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.fallos = fallos if fallos is not None else Fallos()
        self._placa = formato.Placa(techo=techo, minimo=minimo)
        self._azar = random.Random(semilla)
        self._candado = threading.Lock()
        self._registro: list[dict[str, Any]] = []
        self._al_registrar = al_registrar
        self._ultimo_emisor: tuple[str, int] | None = None
        self._pendientes: list[tuple[float, bytes, tuple[str, int]]] = []
        self._retenido: tuple[float, bytes, tuple[str, int]] | None = None
        self._wifi_estaba_cortado = False
        self._parar = threading.Event()
        self._hilo: threading.Thread | None = None
        self._bitacora = None
        if bitacora is not None:
            # La ruta la elige quien corre `python -m simulador --bitacora`.
            ruta = Path(bitacora)
            ruta.parent.mkdir(parents=True, exist_ok=True)  # NOSONAR (S8707)
            self._bitacora = ruta.open("w", encoding="utf-8", newline="\n")  # NOSONAR (S8707)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind((host, puerto))
        self._sock.setblocking(False)
        self._t0 = _ahora_ms()

    # -- ciclo de vida -----------------------------------------------------------------
    @property
    def direccion(self) -> tuple[str, int]:
        """IP y puerto donde escucha (con `puerto=0`, el que eligió el sistema)."""
        host, puerto = self._sock.getsockname()[:2]
        return host, puerto

    def iniciar(self) -> CarroSimulado:
        self._anotar({"evento": "encendido", **self._motores()})
        self._hilo = threading.Thread(target=self._bucle, name="carro-simulado", daemon=True)
        self._hilo.start()
        return self

    def detener(self) -> None:
        """Apaga el simulador en orden: frena, termina el hilo y cierra la bitácora."""
        self._terminar(evento="apagado")

    def matar(self) -> None:
        """Cierra el simulador de golpe: deja de escuchar y no contesta nada más."""
        self._terminar(evento="muerto")

    def __enter__(self) -> CarroSimulado:
        return self.iniciar()

    def __exit__(self, *_: object) -> None:
        self.detener()

    def _terminar(self, evento: str) -> None:
        if self._parar.is_set():
            return
        self._parar.set()
        if self._hilo is not None:
            self._hilo.join(timeout=1)
        with self._candado:
            formato.frenar(self._placa)
        self._anotar({"evento": evento, **self._motores()})
        self._sock.close()
        if self._bitacora is not None:
            self._bitacora.close()
            self._bitacora = None

    # -- consulta ----------------------------------------------------------------------
    def reloj_ms(self) -> float:
        """Reloj de la placa: milisegundos desde que se creó el simulador (como `millis()`)."""
        return _ahora_ms() - self._t0

    @property
    def estado(self) -> dict[str, Any]:
        """Motores, sesión activa y última `seq` aceptada, en este instante."""
        with self._candado:
            return {
                **self._motores(),
                "sesion": self._placa.sesion,
                "ultima_seq": self._placa.ultima_seq,
            }

    @property
    def registro(self) -> list[dict[str, Any]]:
        """Copia de todo lo anotado: cada datagrama con su hora, su motivo y los motores."""
        with self._candado:
            return list(self._registro)

    # -- bucle -------------------------------------------------------------------------
    def _bucle(self) -> None:
        selector = selectors.DefaultSelector()
        selector.register(self._sock, selectors.EVENT_READ)
        try:
            while not self._parar.is_set():
                selector.select(timeout=PERIODO_REVISION_MS / 1000)
                self._leer_entrantes()
                self._revisar_wifi()
                self._entregar_retenido_viejo()
                self._revisar_vencimiento()
                self._mandar_pendientes()
        finally:
            selector.close()

    def _leer_entrantes(self) -> None:
        while True:
            try:
                datos, origen = self._sock.recvfrom(MAX_DATAGRAMA)
            except (BlockingIOError, InterruptedError):
                return
            except ConnectionResetError:  # Windows: ICMP de una respuesta que no llegó
                continue
            except OSError as exc:
                if self._parar.is_set() or self._sock.fileno() == -1:
                    return  # socket cerrado por matar() o detener()
                # Otro error de red: se anota y se sigue; el paro automático no se detiene.
                self._anotar({"evento": "error_red", "error": f"{type(exc).__name__}: {exc}"})
                return
            self._llega(datos, origen)

    def _llega(self, datos: bytes, origen: tuple[str, int]) -> None:
        f = self.fallos
        texto = datos.decode("ascii", "backslashreplace")
        if f.wifi_cortado:
            self._anotar({"evento": "descartado_sin_wifi", "datos": texto})
            return
        if f.perdida > 0 and self._azar.random() < f.perdida:
            self._anotar({"evento": "perdido", "datos": texto})
            return
        if f.desordenar:
            if self._retenido is None:
                self._retenido = (self.reloj_ms(), datos, origen)
                self._anotar({"evento": "retenido", "datos": texto})
                return
            _, viejo, origen_viejo = self._retenido
            self._retenido = None
            self._aplicar(datos, origen)
            self._aplicar(viejo, origen_viejo)
            return
        self._aplicar(datos, origen)
        if f.duplicar:
            self._aplicar(datos, origen)

    def _entregar_retenido_viejo(self) -> None:
        if self._retenido is None:
            return
        t, datos, origen = self._retenido
        if not self.fallos.desordenar or self.reloj_ms() - t >= self.fallos.espera_desorden_ms:
            self._retenido = None
            self._aplicar(datos, origen)

    def _aplicar(self, datos: bytes, origen: tuple[str, int]) -> None:
        with self._candado:
            r = self._placa.recibir(datos, self.reloj_ms())
            if r.motivo == "OK":
                self._ultimo_emisor = origen
        self._anotar(
            {
                "evento": "orden",
                "datos": datos.decode("ascii", "backslashreplace"),
                "de": f"{origen[0]}:{origen[1]}",
                "sesion": r.sesion,
                "seq": r.seq,
                "motivo": r.motivo,
                "estado": r.estado,
                "pwm_izq": r.pwm_izq,
                "pwm_der": r.pwm_der,
            }
        )
        self._contestar(r, origen)

    def _revisar_vencimiento(self) -> None:
        with self._candado:
            aviso = self._placa.tick(self.reloj_ms())
            destino = self._ultimo_emisor
        if aviso is None:
            return
        self._anotar(
            {"evento": "vencida", "sesion": aviso.sesion, "seq": aviso.seq, "estado": aviso.estado}
        )
        if destino is not None:
            self._contestar(aviso, destino)

    def _revisar_wifi(self) -> None:
        cortado = self.fallos.wifi_cortado
        if cortado == self._wifi_estaba_cortado:
            return
        self._wifi_estaba_cortado = cortado
        if cortado:
            with self._candado:
                formato.frenar(self._placa)
            self._pendientes.clear()
            self._retenido = None  # lo que venía en camino tampoco llega
        self._anotar({"evento": "wifi_cortado" if cortado else "wifi_vuelve", **self._motores()})

    def _contestar(self, r: formato.Respuesta, destino: tuple[str, int]) -> None:
        if self.fallos.mudo or self.fallos.wifi_cortado:
            return
        sale = self.reloj_ms() + max(self.fallos.retardo_ms, 0.0)
        self._pendientes.append((sale, formato.codificar_respuesta(r), destino))
        self._mandar_pendientes()

    def _mandar_pendientes(self) -> None:
        if not self._pendientes:
            return
        ahora = self.reloj_ms()
        listos = [p for p in self._pendientes if p[0] <= ahora]
        self._pendientes = [p for p in self._pendientes if p[0] > ahora]
        for _, datos, destino in listos:
            if self.fallos.wifi_cortado or self.fallos.mudo:
                return  # mudo también calla lo que ya estaba en cola por retardo_ms
            try:
                self._sock.sendto(datos, destino)
            except OSError:
                return

    # -- bitácora ----------------------------------------------------------------------
    def _motores(self) -> dict[str, Any]:
        p = self._placa
        return {"estado": p.estado, "pwm_izq": p.pwm_izq, "pwm_der": p.pwm_der}

    def _anotar(self, registro: dict[str, Any]) -> None:
        registro = {"t_placa_ms": round(self.reloj_ms(), 3), **registro}
        with self._candado:
            self._registro.append(registro)
        if self._bitacora is not None:
            self._bitacora.write(json.dumps(registro, ensure_ascii=False) + "\n")
            self._bitacora.flush()
        if self._al_registrar is not None:
            try:
                self._al_registrar(registro)
            except Exception:  # NOSONAR: nada de quien escucha puede tumbar el bucle del carro
                # Si tumbara el hilo, el carro dejaría de contestar y de frenar al vencer.
                self._al_registrar = None
