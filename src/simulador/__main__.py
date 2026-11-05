"""`python -m simulador`: corre el carro simulado hasta Ctrl+C.

Escucha en 127.0.0.1:4210 por omisión, así que el lazo (P5-21) apunta a `--ip 127.0.0.1`.
Imprime cada orden con su motivo y cada cambio de los motores. Los fallos se fijan al arrancar;
desde código (pruebas) se cambian con el simulador corriendo en `CarroSimulado.fallos`.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from . import formato
from .carro import CarroSimulado, Fallos


def _fraccion(texto: str) -> float:
    valor = float(texto)
    if not 0 <= valor <= 1:
        raise argparse.ArgumentTypeError("debe estar entre 0 y 1")
    return valor


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m simulador",
        description="Carro simulado: contesta el protocolo P5C1/P5R1 como el firmware.",
    )
    p.add_argument("--host", default="127.0.0.1", help="IP donde escucha (0.0.0.0 = todas)")
    p.add_argument("--puerto", type=int, default=formato.PUERTO)
    p.add_argument("--bitacora", help="JSONL con cada datagrama y cada cambio de los motores")
    p.add_argument("--techo", type=int, default=formato.TECHO_PWM, help="PWM máximo (0 a 255)")
    p.add_argument("--minimo", type=int, default=formato.MINIMO_PWM, help="zona muerta del PWM")
    g = p.add_argument_group("fallos")
    g.add_argument("--mudo", action="store_true", help="aplica las órdenes pero no contesta")
    g.add_argument("--retardo-ms", type=float, default=0.0, help="contesta tarde")
    g.add_argument("--perdida", type=_fraccion, default=0.0, help="fracción de órdenes perdidas")
    g.add_argument("--duplicar", action="store_true", help="cada orden llega dos veces")
    g.add_argument("--desordenar", action="store_true", help="cada par de órdenes llega al revés")
    g.add_argument(
        "--espera-desorden-ms",
        type=float,
        default=Fallos.espera_desorden_ms,
        help="con --desordenar, cuánto se retiene una orden esperando la siguiente",
    )
    g.add_argument("--semilla", type=int, help="semilla de la pérdida, para repetir una corrida")
    return p


def _imprimir(r: dict[str, Any]) -> None:
    t = f"{r['t_placa_ms']:>10.1f} ms"
    if r["evento"] == "orden":
        print(
            f"{t}  seq={r['seq']:<6} {r['motivo']:<13} {r['estado']:<9} "
            f"pwm={r['pwm_izq']}/{r['pwm_der']}  {r['datos']}"
        )
    else:
        resto = {k: v for k, v in r.items() if k not in ("t_placa_ms", "evento")}
        print(f"{t}  {r['evento'].upper():<20} {resto}")
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not 0 <= args.minimo <= args.techo <= 255:
        print("se requiere 0 <= --minimo <= --techo <= 255", file=sys.stderr)
        return 2
    fallos = Fallos(
        mudo=args.mudo,
        retardo_ms=args.retardo_ms,
        perdida=args.perdida,
        duplicar=args.duplicar,
        desordenar=args.desordenar,
        espera_desorden_ms=args.espera_desorden_ms,
    )
    carro = CarroSimulado(
        host=args.host,
        puerto=args.puerto,
        techo=args.techo,
        minimo=args.minimo,
        fallos=fallos,
        bitacora=args.bitacora,
        semilla=args.semilla,
        al_registrar=_imprimir,
    )
    host, puerto = carro.direccion
    print(f"carro simulado en {host}:{puerto} (Ctrl+C para salir); fallos: {fallos}")
    with carro:
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
