"""P5-22 parte 3: los 9 fallos de la matriz, cada uno con su tiempo, contra el carro simulado.

Corren el supervisor, la política y los plazos reales de control con UDP real en localhost
(`simulador.matriz`). La tabla con los tiempos medidos está en docs/carro/emergencia.md.
"""

from __future__ import annotations

import pytest

from simulador.matriz import FALLOS, correr


@pytest.mark.parametrize("numero", sorted(FALLOS))
def test_fallo(numero, tmp_path):
    r = correr(numero, tmp_path)
    assert r.pasa, r
    assert r.medido_ms is not None
    assert r.medido_ms <= r.limite_ms == 600


def test_son_los_nueve_del_ticket():
    assert sorted(FALLOS) == list(range(1, 10))
