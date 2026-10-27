"""Control del grupo B: política, paradas y adaptador virtual. Ver config/contrato/CONTRATO.md."""

from .adaptador_virtual import AdaptadorVirtual
from .supervisor import Supervisor, politica_de_prueba

__all__ = ["AdaptadorVirtual", "Supervisor", "politica_de_prueba"]
