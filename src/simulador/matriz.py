"""P5-22 parte 3: matriz de fallos contra el carro simulado.

Cada fallo corre el lazo de la PC con el supervisor, la política y los plazos reales de
`control`: los plazos de config/control/ y la política como la va a usar el carro
(`cargar_politica_vivo`, con el `umbral_lateral` de config/vivo.yaml). Del lado de la PC va el
puente UDP (`puente.AdaptadorPuente`) y del otro, el carro simulado. Se mide, con el reloj de la
placa, cuánto pasa desde el fallo hasta que el carro queda en
`DETENIDO`. El límite es el watchdog del proyecto (`watchdog_ms`, 600 ms).

`python -m simulador.matriz` imprime la tabla y, con `--salida`, guarda `matriz.json` y las
bitácoras de cada fallo. Las pruebas de `tests/test_matriz_fallos.py` corren lo mismo.

Lo que no mide: la latencia real del WiFi ni el frenado físico (P5-23).
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from control import Supervisor
from control.config import cargar_politica_vivo
from control.politica import decidir
from control.supervisor import CODIGOS_DE_ERROR

from .carro import CarroSimulado, Fallos
from .puente import AdaptadorPuente

RAIZ = Path(__file__).resolve().parents[2]
RUTA_PLAZOS = RAIZ / "config" / "control" / "plazos.yaml"
PERIODO_CUADRO_MS = 200  # ≈ 5 fps, el ritmo de plazos.yaml
PERIODO_LAZO_MS = 10  # cada cuánto el lazo de prueba revisa el reloj
EDAD_NORMAL_MS = 100  # edad de un cuadro sano al llegar (p50 de P5-14: 104 ms)
HASH_FALSO = "0" * 64


def cargar_plazos(ruta: Path = RUTA_PLAZOS) -> dict[str, Any]:
    return yaml.safe_load(ruta.read_text(encoding="utf-8"))


@dataclass
class Resultado:
    numero: int
    fallo: str
    esperado: str
    limite_ms: float
    medido_ms: float | None
    pasa: bool
    detalle: list[str] = field(default_factory=list)


class Lazo:
    """Supervisor + política + puente + carro simulado, con reloj real en milisegundos."""

    def __init__(
        self,
        carpeta: Path,
        fallos: Fallos | None = None,
        politica: Callable[..., Any] = decidir,
    ) -> None:
        self.plazos = cargar_plazos()
        self.carpeta = carpeta
        carpeta.mkdir(parents=True, exist_ok=True)
        self.carro = CarroSimulado(puerto=0, fallos=fallos, bitacora=carpeta / "carro.jsonl")
        self.carro.iniciar()
        ip, puerto = self.carro.direccion
        self.avisos: list[dict[str, Any]] = []
        self.adaptador = AdaptadorPuente(
            carpeta, self.plazos["validez_orden_ms"], ip, puerto, al_avisar=self.avisos.append
        )
        self.supervisor = Supervisor(politica, self.adaptador, self.plazos, cargar_politica_vivo())
        self._t0 = time.perf_counter()
        self._n = 0
        self._ultimo_tick = -math.inf
        self._ultimo_cuadro = -math.inf
        self.t_placa_ultimo_cuadro = 0.0

    # -- reloj y entradas --------------------------------------------------------------
    def ahora(self) -> float:
        return (time.perf_counter() - self._t0) * 1000

    def evento(self, edad_ms: float = EDAD_NORMAL_MS, **campos: Any) -> dict[str, Any]:
        """Un evento del contrato v1, capturado `edad_ms` antes de ahora. Libre por omisión."""
        self._n += 1
        ahora = self.ahora()
        evento = {
            "schema_version": "1",
            "run_id": "matriz-p5-22",
            "sequence_id": "M01",
            "frame_id": f"M01_f{self._n:04d}",
            "t_capture_ms": round(ahora - edad_ms, 3),
            "t_emit_ms": round(ahora, 3),
            "image_width": 640,
            "image_height": 480,
            "model_sha256": HASH_FALSO,
            "config_sha256": HASH_FALSO,
            "status": "ok",
            "bbox_format": "xyxy",
            "bbox_unit": "px",
            "detections": [],
        }
        evento.update(campos)
        return evento

    def cuadro(self, evento: dict[str, Any] | None = None) -> dict[str, Any]:
        """Pasa un evento por el supervisor (y de ahí al carro). Devuelve el comando."""
        self._ultimo_cuadro = self.ahora()
        self.t_placa_ultimo_cuadro = self.t_placa()
        return self.supervisor.procesar_evento(evento or self.evento(), self.ahora())

    def paso(self) -> None:
        """Lo que el lazo hace en cada vuelta sin cuadro: watchdog cada 100 ms y respuestas."""
        ahora = self.ahora()
        if ahora - self._ultimo_tick >= self.plazos["paso_reloj_ms"]:
            self._ultimo_tick = ahora
            self.supervisor.tick(ahora)
        self.adaptador.revisar(ahora)

    def correr(self, duracion_ms: float, cuadros: bool = True) -> None:
        """Corre el lazo `duracion_ms`. Con `cuadros`, llega un cuadro libre cada 200 ms."""
        fin = self.ahora() + duracion_ms
        while self.ahora() < fin:
            if cuadros and self.ahora() - self._ultimo_cuadro >= PERIODO_CUADRO_MS:
                self.cuadro()
            self.paso()
            time.sleep(PERIODO_LAZO_MS / 1000)

    def arrancar(self) -> None:
        """Lleva el carro a MOVIENDO con cuadros libres (la histéresis pide varios)."""
        self.correr(4 * PERIODO_CUADRO_MS)
        if self.carro.estado["estado"] != "MOVIENDO":
            raise AssertionError(f"el carro no arrancó: {self.carro.estado}")

    # -- medición ----------------------------------------------------------------------
    def t_placa(self) -> float:
        return self.carro.reloj_ms()

    def detenido_desde(self, t_fallo: float) -> float | None:
        """Milisegundos (reloj de la placa) desde `t_fallo` hasta el primer DETENIDO."""
        for r in self.carro.registro:
            if r["t_placa_ms"] >= t_fallo and r.get("estado") == "DETENIDO":
                return r["t_placa_ms"] - t_fallo
        return None

    def esperar_detenido(
        self, t_fallo: float, limite_ms: float, cuadros: bool = False, evento: Any = None
    ) -> float | None:
        """Sigue corriendo el lazo hasta que el carro se detenga o pase el límite (+100 ms)."""
        fin = self.ahora() + limite_ms + 100
        while self.ahora() < fin:
            medido = self.detenido_desde(t_fallo)
            if medido is not None:
                return medido
            if cuadros and self.ahora() - self._ultimo_cuadro >= PERIODO_CUADRO_MS:
                self.cuadro(evento() if callable(evento) else None)
            self.paso()
            time.sleep(PERIODO_LAZO_MS / 1000)
        return self.detenido_desde(t_fallo)

    def comandos(self) -> list[dict[str, Any]]:
        texto = self.adaptador.ruta_registro.read_text(encoding="utf-8")
        return [json.loads(x) for x in texto.splitlines()]

    def cerrar(self) -> None:
        try:
            self.supervisor.cerrar(self.ahora())
            self.adaptador.cerrar()
        finally:
            self.carro.detener()


# -- los nueve fallos --------------------------------------------------------------------
def _resultado(
    numero: int,
    fallo: str,
    esperado: str,
    limite: float,
    medido: float | None,
    detalle: list[str],
    extra_ok: bool = True,
) -> Resultado:
    pasa = medido is not None and medido <= limite and extra_ok
    return Resultado(numero, fallo, esperado, limite, _redondear(medido), pasa, detalle)


def _redondear(x: float | None) -> float | None:
    return None if x is None else round(x, 1)


def f1_camara_cortada(carpeta: Path) -> Resultado:
    lazo = Lazo(carpeta)
    try:
        lazo.arrancar()
        t = lazo.t_placa_ultimo_cuadro  # después de este cuadro ya no llega ninguno
        medido = lazo.esperar_detenido(t, lazo.plazos["watchdog_ms"])
        lazo.correr(lazo.plazos["watchdog_ms"], cuadros=False)
        razones = [c["reason"] for c in lazo.comandos() if c["event"] == "clock"]
        ok = bool(razones) and lazo.carro.estado["estado"] == "DETENIDO"
        return _resultado(
            1,
            "Cámara cortada",
            "STOP por watchdog o por orden vencida; el carro para",
            lazo.plazos["watchdog_ms"],
            medido,
            [f"STOP de reloj del supervisor: {razones}"],
            ok,
        )
    finally:
        lazo.cerrar()


def f2_cuadro_viejo(carpeta: Path) -> Resultado:
    medidos, detalle, ok = [], [], True
    limite = 0.0
    for nombre, construir in (
        ("ok con 600 ms de edad", lambda lz: lz.evento(edad_ms=600)),
        ("status=stale", lambda lz: lz.evento(edad_ms=520, status="stale")),
    ):
        lazo = Lazo(carpeta / nombre.split()[0].replace("=", "-"))
        try:
            lazo.arrancar()
            t = lazo.t_placa()
            comando = lazo.cuadro(construir(lazo))
            medido = lazo.esperar_detenido(t, lazo.plazos["watchdog_ms"])
            limite = lazo.plazos["watchdog_ms"]
            ok &= comando["action"] == "STOP" and comando["reason"] in ("cuadro_viejo", "stale")
            medidos.append(medido)
            detalle.append(
                f"{nombre} (máximo {lazo.plazos['max_frame_age_ms']} ms): {comando['reason']}"
            )
        finally:
            lazo.cerrar()
    return _resultado(
        2,
        "Cuadro con más de 500 ms de edad",
        "STOP al recibirlo",
        limite,
        _peor(medidos),
        detalle,
        ok,
    )


def f3_detector(carpeta: Path) -> Resultado:
    medidos, detalle, ok = [], [], True
    limite = 0.0
    for codigo in CODIGOS_DE_ERROR:
        lazo = Lazo(carpeta / codigo)
        try:
            lazo.arrancar()
            t = lazo.t_placa()
            evento = lazo.evento(
                status="error",
                image_width=None,
                image_height=None,
                error={"code": codigo, "message": f"inyectado por la matriz ({codigo})"},
            )
            comando = lazo.cuadro(evento)
            medido = lazo.esperar_detenido(t, lazo.plazos["watchdog_ms"])
            limite = lazo.plazos["watchdog_ms"]
            ok &= comando["action"] == "STOP" and comando["reason"] == f"error_detector:{codigo}"
            medidos.append(medido)
            detalle.append(f"{codigo}: {comando['reason']}, {_redondear(medido)} ms")
        finally:
            lazo.cerrar()
    return _resultado(
        3,
        "Detector con excepción, timeout, imagen ilegible o salida inválida",
        "STOP al recibir el error",
        limite,
        _peor(medidos),
        detalle,
        ok,
    )


def f4_carro_no_responde(carpeta: Path) -> Resultado:
    """Dos variantes: el carro no oye (no le llega nada) y el carro oye pero no contesta."""
    medidos, detalle, ok = [], [], True
    limite = 0.0
    for variante in ("no_oye", "mudo"):
        lazo = Lazo(carpeta / variante)
        try:
            lazo.arrancar()
            t = lazo.t_placa()
            # La PC sigue viendo vía libre: la política sigue proponiendo AVANZAR.
            if variante == "no_oye":
                lazo.carro.fallos.perdida = 1.0
            else:
                lazo.carro.fallos.mudo = True
            medido = lazo.esperar_detenido(t, lazo.plazos["watchdog_ms"], cuadros=True)
            lazo.correr(3 * PERIODO_CUADRO_MS)  # con cuadros libres, ¿vuelve a arrancar?
            limite = lazo.plazos["watchdog_ms"]
            despues = [r for r in lazo.carro.registro if r["t_placa_ms"] >= t]
            vencida = any(r["evento"] == "vencida" for r in despues)
            stop_de_la_pc = any(
                r["evento"] == "orden" and r["motivo"] == "OK" and ",STOP," in r["datos"]
                for r in despues
            )
            avisos = sorted({a["motivo"] for a in lazo.avisos})
            quieto = lazo.carro.estado["estado"] == "DETENIDO"
            ok &= "carro_sin_respuesta" in avisos and quieto
            # Sin oír, solo lo para la placa; oyendo, lo para el STOP que manda la PC.
            ok &= vencida if variante == "no_oye" else stop_de_la_pc
            medidos.append(medido)
            como = "VENCIDA de la placa" if variante == "no_oye" else "STOP de la PC tras el aviso"
            detalle.append(
                f"{variante}: {_redondear(medido)} ms, paro por {como}; avisos {avisos}; "
                f"{'sigue DETENIDO' if quieto else 'SE VOLVIÓ A MOVER'} con cuadros libres"
            )
        finally:
            lazo.cerrar()
    return _resultado(
        4,
        "El carro no responde",
        "la PC avisa y manda STOP; si el carro no oye, para solo por su paro automático",
        limite,
        _peor(medidos),
        detalle,
        ok,
    )


def f5_repetida_o_desordenada(carpeta: Path) -> Resultado:
    medidos, detalle, ok = [], [], True
    limite = 0.0
    for fallo in ("duplicar", "desordenar"):
        lazo = Lazo(carpeta / fallo)
        try:
            lazo.arrancar()
            t = lazo.t_placa()
            setattr(lazo.carro.fallos, fallo, True)
            lazo.correr(3 * PERIODO_CUADRO_MS)
            limite = lazo.plazos["watchdog_ms"]
            ordenes = [r for r in lazo.carro.registro if r["evento"] == "orden"]
            viejas = [r for r in ordenes if r["motivo"] == "SEQ_VIEJA"]
            aceptadas = [r["seq"] for r in ordenes if r["motivo"] == "OK"]
            ok &= bool(viejas) and aceptadas == sorted(set(aceptadas))
            medidos.append(lazo.detenido_desde(t))
            detalle.append(
                f"{fallo}: {len(viejas)} SEQ_VIEJA, ninguna aplicada; la seq aceptada solo sube"
            )
        finally:
            lazo.cerrar()
    detalle.append("según el protocolo v1, la orden vieja no se aplica y además frena")
    return _resultado(
        5,
        "Orden repetida o fuera de orden",
        "el carro ignora la vieja (y frena)",
        limite,
        _peor(medidos),
        detalle,
        ok,
    )


def _politica_corrupta(valor: float) -> Callable[..., Any]:
    def politica(evento: Any, estado: Any, config: Any) -> Any:
        comando, nuevo = decidir(evento, estado, config)
        comando = copy.deepcopy(comando)
        comando["speed"] = valor
        return comando, nuevo

    return politica


def f6_comando_fuera_de_rango(carpeta: Path) -> Resultado:
    medidos, detalle, ok = [], [], True
    limite = 0.0
    for nombre, valor in (("1.5", 1.5), ("nan", math.nan), ("inf", math.inf)):
        lazo = Lazo(carpeta / f"speed-{nombre}")
        try:
            lazo.arrancar()
            t = lazo.t_placa()
            lazo.supervisor.politica = _politica_corrupta(valor)
            comando = lazo.cuadro()
            medido = lazo.esperar_detenido(t, lazo.plazos["watchdog_ms"])
            limite = lazo.plazos["watchdog_ms"]
            ok &= comando["action"] == "STOP" and comando["reason"] == "politica_invalida"
            medidos.append(medido)
            detalle.append(f"speed={nombre} en la PC: {comando['reason']}")
        finally:
            lazo.cerrar()
    # Y si un comando fuera de rango llegara al carro por otra vía, la placa también frena.
    lazo = Lazo(carpeta / "en-la-placa")
    try:
        lazo.arrancar()
        t = lazo.t_placa()
        sesion = lazo.carro.estado["sesion"]
        seq = lazo.carro.estado["ultima_seq"] + 1
        lazo.adaptador._emisor.enviar(f"P5C1,{sesion},{seq},AVANZAR,1.500,0.000,400".encode())
        medido = lazo.esperar_detenido(t, lazo.plazos["watchdog_ms"])
        motivo = next(
            (r["motivo"] for r in reversed(lazo.carro.registro) if r["evento"] == "orden"), None
        )
        ok &= motivo == "FUERA_RANGO"
        medidos.append(medido)
        detalle.append(f"velocidad 1.5 directo a la placa: {motivo}")
    finally:
        lazo.cerrar()
    return _resultado(
        6,
        "Comando fuera de rango o no finito",
        "se rechaza y hay STOP",
        limite,
        _peor(medidos),
        detalle,
        ok,
    )


def f7_emergencia(carpeta: Path) -> Resultado:
    lazo = Lazo(carpeta)
    try:
        lazo.arrancar()
        t = lazo.t_placa()
        lazo.supervisor.emergencia(lazo.ahora())
        medido = lazo.esperar_detenido(t, lazo.plazos["watchdog_ms"])
        detalle = []
        # Enclavado: con cuadros libres sigue en STOP.
        lazo.correr(3 * PERIODO_CUADRO_MS)
        enclavado = lazo.carro.estado["estado"] == "DETENIDO"
        enclavado &= lazo.comandos()[-1]["reason"] == "emergencia_activa"
        detalle.append(f"con cuadros libres: {lazo.comandos()[-1]['reason']}")
        # Rearme con un cuadro viejo: rechazado.
        lazo.cuadro(lazo.evento(edad_ms=600))
        rechazo = lazo.supervisor.rearmar(lazo.ahora())
        detalle.append(f"rearme con cuadro viejo: {rechazo['reason'] if rechazo else None}")
        # Rearme con un cuadro fresco: STOP rearmado y luego vuelve a moverse.
        lazo.cuadro()
        rearme = lazo.supervisor.rearmar(lazo.ahora())
        detalle.append(f"rearme con cuadro fresco: {rearme['reason'] if rearme else None}")
        quieto_al_rearmar = lazo.carro.estado["estado"] == "DETENIDO"
        lazo.correr(6 * PERIODO_CUADRO_MS)
        se_mueve = lazo.carro.estado["estado"] == "MOVIENDO"
        detalle.append(f"después del rearme, con cuadros libres: {lazo.carro.estado['estado']}")
        ok = (
            enclavado
            and rechazo is not None
            and rechazo["reason"] == "rearme_rechazado"
            and rearme is not None
            and rearme["reason"] == "rearmado"
            and quieto_al_rearmar
            and se_mueve
        )
        return _resultado(
            7,
            "Emergencia",
            "STOP inmediato, enclavado hasta un rearme explícito con percepción fresca",
            lazo.plazos["watchdog_ms"],
            medido,
            detalle,
            ok,
        )
    finally:
        lazo.cerrar()


def f8_cierre(carpeta: Path) -> Resultado:
    medidos, detalle, ok = [], [], True
    limite = 0.0
    # a) Cierre normal del programa.
    lazo = Lazo(carpeta / "cierre")
    lazo.arrancar()
    t = lazo.t_placa()
    lazo.supervisor.cerrar(lazo.ahora())
    lazo.adaptador.cerrar()
    medidos.append(lazo.esperar_detenido(t, 600))
    limite = lazo.plazos["watchdog_ms"]
    ok &= lazo.comandos()[-1]["reason"] == "cierre"
    detalle.append(f"cierre: {lazo.comandos()[-1]['reason']} y 3 STOP del emisor")
    lazo.carro.detener()
    # b) Excepción en el lazo: el `finally` del programa manda STOP antes de salir. Este
    # `finally` lo escribe la matriz; el del lazo de P5-21 se prueba en sus propias pruebas.
    lazo = Lazo(carpeta / "excepcion")
    t = 0.0
    try:
        lazo.arrancar()
        t = lazo.t_placa()
        raise RuntimeError("falla inyectada en el lazo")
    except RuntimeError as exc:
        detalle.append(f"excepción: {exc} (el finally es de la matriz, no del lazo de P5-21)")
    finally:
        lazo.supervisor.cerrar(lazo.ahora())
        lazo.adaptador.cerrar()
        medidos.append(lazo.esperar_detenido(t, 600))
        lazo.carro.detener()
    return _resultado(
        8,
        "Cierre del programa o excepción",
        "STOP antes de salir",
        limite,
        _peor(medidos),
        detalle,
        ok,
    )


def f9_wifi_cortado(carpeta: Path) -> Resultado:
    lazo = Lazo(carpeta)
    try:
        lazo.arrancar()
        # A mitad de una orden: la última AVANZAR acaba de llegar y vale 400 ms.
        lazo.correr(PERIODO_CUADRO_MS / 2, cuadros=False)
        t = lazo.t_placa()
        lazo.carro.fallos.wifi_cortado = True
        medido = lazo.esperar_detenido(t, lazo.plazos["watchdog_ms"], cuadros=True)
        lazo.correr(300)
        avisos = [a["motivo"] for a in lazo.avisos]
        return _resultado(
            9,
            "WiFi cortado a mitad de una orden",
            "el carro para solo",
            lazo.plazos["watchdog_ms"],
            medido,
            [f"avisos de la PC: {avisos}", "ver también el fallo 4 (red sin paquetes)"],
            "carro_sin_respuesta" in avisos,
        )
    finally:
        lazo.cerrar()


def _peor(medidos: list[float | None]) -> float | None:
    return None if any(m is None for m in medidos) else max(medidos, default=None)


FALLOS: dict[int, Callable[[Path], Resultado]] = {
    1: f1_camara_cortada,
    2: f2_cuadro_viejo,
    3: f3_detector,
    4: f4_carro_no_responde,
    5: f5_repetida_o_desordenada,
    6: f6_comando_fuera_de_rango,
    7: f7_emergencia,
    8: f8_cierre,
    9: f9_wifi_cortado,
}


def correr(numero: int, carpeta: Path) -> Resultado:
    return FALLOS[numero](carpeta / f"fallo-{numero}")


def tabla(resultados: list[Resultado]) -> str:
    filas = [
        "| # | Fallo | Qué debe pasar | Medido | Límite | Resultado |",
        "|---|---|---|---|---|---|",
    ]
    for r in resultados:
        medido = "—" if r.medido_ms is None else f"{r.medido_ms:.0f} ms"
        filas.append(
            f"| {r.numero} | {r.fallo} | {r.esperado} | {medido} | {r.limite_ms:.0f} ms | "
            f"{'PASA' if r.pasa else 'FALLA'} |"
        )
    return "\n".join(filas)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m simulador.matriz", description=__doc__)
    p.add_argument("--salida", type=Path, help="carpeta nueva para matriz.json y las bitácoras")
    p.add_argument("fallos", nargs="*", type=int, choices=sorted(FALLOS), help="todos si no se da")
    args = p.parse_args(argv)
    numeros = args.fallos or sorted(FALLOS)
    with tempfile.TemporaryDirectory() as tmp:
        carpeta = args.salida or Path(tmp)
        resultados = []
        for n in numeros:
            r = correr(n, carpeta)
            resultados.append(r)
            print(f"{n}. {'PASA ' if r.pasa else 'FALLA'} {r.medido_ms} ms  {r.fallo}")
            for d in r.detalle:
                print(f"     {d}")
            sys.stdout.flush()
        if args.salida is not None:
            args.salida.mkdir(parents=True, exist_ok=True)
            (args.salida / "matriz.json").write_text(
                json.dumps([asdict(r) for r in resultados], ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        print()
        print(tabla(resultados))
    return 0 if all(r.pasa for r in resultados) else 1


if __name__ == "__main__":
    raise SystemExit(main())
