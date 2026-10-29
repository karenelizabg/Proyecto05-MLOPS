# Proyecto 5 · Mini Tesla

Un carro pequeño detecta obstáculos en cuadros de cámara y decide **avanzar, girar o frenar**. Todo se evalúa
desde archivos y código, **offline y en CPU**; el control es virtual: los comandos se registran y **nunca mueven
motores** (`config/ejecucion.yaml`).

- **Grupo A · Percepción y datos:** detector, secuencias etiquetadas, métricas y benchmark ([TICKETS.md](TICKETS.md)).
- **Grupo B · Control y verificación:** política, supervisor, adaptador virtual y casos C1–C10 (issues `T01`–`T19`).
- **Frontera entre grupos:** el contrato de percepción v1, en [config/contrato/CONTRATO.md](config/contrato/CONTRATO.md).

Versión: `0.1.0` (`pyproject.toml`). Responsables y comandos de cada grupo: se completan en P5-18 y T18.

## Instalación

Requiere [uv](https://docs.astral.sh/uv/) (el CI usa la 0.12.13). Python 3.12 queda fijado en `.python-version`
y uv lo descarga si no está instalado. Las versiones exactas de todo están en `uv.lock`.

```bash
# Una vez, si no tienes uv (o el instalador oficial de la página de uv):
python -m pip install "uv==0.12.13"

# En la raíz del repo: crea .venv con exactamente lo que dice uv.lock
uv sync --locked
```

Funciona igual en Windows, macOS y Linux. En Windows, los comandos con `bash` necesitan Git Bash.

## Comandos

| Para qué | Comando |
|---|---|
| Pruebas | `uv run pytest -q` |
| Lint y formato | `uv run ruff check .` · `uv run ruff format --check .` |
| Validar eventos del contrato | `uv run python -m contrato config/contrato/ejemplos/flujo.jsonl` |
| Métricas de detección (P5-13) | `uv run python -m metricas --detecciones run.jsonl --anotaciones anotaciones.jsonl --salida resultados/metricas/ --model-sha256 … --config-sha256 …` (ver [`config/anotaciones/`](config/anotaciones/README.md)) |
| Benchmark (P5-15) | `uv run python -m bench --entradas datos/cuadros/ --salida mediciones/<run>/ --equipo "laptop de A3" --detector … --model-sha256 … --config-sha256 …` (ver [`mediciones/`](mediciones/README.md)) |
| Capturar una secuencia del carro (P5-09) | `uv run python -m captura --url http://IP:81/stream --secuencia S01 [--cuadros 12]` (guarda en `datos/cuadros/S01/` solo si sale completa; un intento fallido va a `datos/cuadros/_fallidas/`; ver [`datos/DOMINIO.md`](datos/DOMINIO.md)) |
| Inferir, reproducir | Se agregan con sus tickets: `infer` (P5-05), `python -m control` (T14). |

Para agregar una dependencia: `uv add paquete` (o `uv add --dev paquete`) y sube `pyproject.toml` y `uv.lock` en el
mismo PR. Sin paquetes de GPU: una prueba de humo lo revisa.

## Estructura

| Carpeta | Contenido |
|---|---|
| `modelo/` | Detector: decisión, ficha, licencia, pesos o su descarga con SHA-256 (E2). |
| `config/` | Contrato A → B, modo de ejecución y configuración de política y plazos. |
| `datos/` | Cuadros, anotaciones, manifiesto y dominio (E3). |
| `src/` | Código: `contrato/` (validador) y los paquetes que vienen (detector, `control/`, ...). |
| `casos/` | Casos C1–C10 y su runner (E5). |
| `resultados/` | Detecciones, decisiones y comandos por cuadro; métricas (E6). |
| `mediciones/` | Benchmark y límites (E7). |
| `tests/` | Pruebas (`pytest`). |

## Cómo contribuir

Un ticket = una rama = un PR. Ramas `p5-NN-...` (grupo A) o `p5-tNN-...` (grupo B); títulos `P5-NN: ...` o
`TNN: ...`. El CI corre Ruff y pytest en cada PR. Detalles en [CONTRIBUTING.md](CONTRIBUTING.md).
