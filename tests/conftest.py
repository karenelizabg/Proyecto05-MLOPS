import sys
from pathlib import Path

# Hasta que P5-01 deje el paquete instalable, las pruebas importan desde src/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
