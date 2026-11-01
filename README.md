# Proyecto 5 · Mini Tesla

Un carro pequeño detecta obstáculos en cuadros de cámara y decide **avanzar, girar o frenar**. Todo se evalúa
desde archivos y código, **offline y en CPU**; el control es virtual: los comandos se registran y **nunca mueven
motores** (`config/ejecucion.yaml`).

- **Grupo A · Percepción y datos:** detector, secuencias etiquetadas, métricas y benchmark ([TICKETS.md](TICKETS.md)).
- **Grupo B · Control y verificación:** política, supervisor, adaptador virtual y casos C1–C10 (issues `T01`–`T19`).
- **Frontera entre grupos:** el contrato de percepción v1, en [config/contrato/CONTRATO.md](config/contrato/CONTRATO.md).

Versión: `0.1.0` (`pyproject.toml`). Responsables y comandos del grupo A: se completan en P5-18. Grupo B: ver
[Grupo B · Control y verificación](#grupo-b--control-y-verificación).

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
| Resultados por cuadro y recálculo (P5-14) | `uv run python -m trazabilidad construir --corrida resultados/<run>/ --anotaciones datos/anotaciones.jsonl --salida resultados/<run>/trazabilidad/` · `… recalcular <carpeta>` · `… cuadro <carpeta> <frame_id>` (ver [`resultados/`](resultados/README.md)) |
| Benchmark (P5-15) | `uv run python -m bench --entradas datos/cuadros/ --salida mediciones/<run>/ --equipo "laptop de A3" --detector … --model-sha256 … --config-sha256 …` (ver [`mediciones/`](mediciones/README.md)) |
| Capturar una secuencia del carro (P5-09) | `uv run python -m captura --url http://IP:81/stream --secuencia S01 [--cuadros 12]` (guarda en `datos/cuadros/S01/` solo si sale completa; un intento fallido va a `datos/cuadros/_fallidas/`; ver [`datos/DOMINIO.md`](datos/DOMINIO.md)) |
| Manifiesto y `verify_dataset` (P5-11) | `uv run python -m conjunto manifiesto` · `uv run python -m conjunto verificar [--sha256 HASH_CONGELADO]` · `uv run python -m conjunto hojas --salida <carpeta nueva>` (leen `datos/cuadros/`, `datos/anotaciones.jsonl` y `datos/manifiesto.jsonl`) |
| Inferir (P5-05) | `uv run --locked python -m infer --input <JPEG o carpeta> --weights <ruta local>/yolo11n.pt --output <archivo .jsonl> --run-id <run> [--sequence-id S01] [--capture-ms …]` (ver [`config/DETECTOR.md`](config/DETECTOR.md)) |
| Correr el control con una secuencia (grupo B) | `uv run python -m control --entrada <eventos.jsonl> --config config/control/ --salida <carpeta>/` (ver [Grupo B](#grupo-b--control-y-verificación)) |
| Casos C1–C10 (grupo B) | `uv run python casos/runner.py` |

Para agregar una dependencia: `uv add paquete` (o `uv add --dev paquete`) y sube `pyproject.toml` y `uv.lock` en el
mismo PR. Sin paquetes de GPU: una prueba de humo lo revisa.

## Estructura

| Carpeta | Contenido |
|---|---|
| `modelo/` | Detector: decisión, ficha, licencia, pesos o su descarga con SHA-256 (E2). |
| `config/` | Contrato A → B, modo de ejecución y configuración de política y plazos. |
| `datos/` | Cuadros, anotaciones, manifiesto y dominio (E3). |
| `src/` | Código: `contrato/` (validador), `control/` (grupo B), `metricas/` y `bench/` (grupo A). |
| `casos/` | Casos C1–C10 y su runner (E5). |
| `resultados/` | Detecciones, decisiones y comandos por cuadro; métricas (E6). |
| `mediciones/` | Benchmark y límites (E7). |
| `tests/` | Pruebas (`pytest`). |

## Grupo B · Control y verificación

Recibe los eventos de percepción del grupo A, decide **AVANZAR, GIRAR_IZQ, GIRAR_DER o STOP** y verifica
los casos C1–C10. Nada mueve motores: el adaptador virtual solo **registra** los comandos.

### Integrantes

| Rol | Nombre | Qué hace | Tickets |
|---|---|---|---|
| PM B | Alejandra Viera | Coordina al grupo, aprueba clases y expectativas con el PM A y revisa los PR. | — |
| B1 · Política | Hannah Chenoa | Política: configuración, zonas, decisión, umbral de confianza, histéresis y su documento ([`docs/politica.md`](docs/politica.md)). | T07–T12 |
| B2 · Paradas | Stephy Borrego | Plazos, adaptador virtual, supervisor, fallas del detector, watchdog, emergencia, rearme y cierre. | T01–T06 |
| B3 · Integración | Luis Santana | Formato del comando, `python -m control`, expectativas de los casos, recorrido real, runner y copia limpia. | T13–T19 |

### Instalación

Igual que arriba: `uv sync --locked`. Las versiones fijadas de todo están en `uv.lock` y Python 3.12 en
`.python-version`; no se sube un `requirements.txt` aparte para no tener dos listas que se desfasen. Todos
los comandos se corren **desde la raíz del repo**.

**Con `pip` en vez de uv.** La parte B solo necesita `jsonschema` y `pyyaml`. Saca de `uv.lock` la lista
con sus versiones fijadas e instálala en un entorno de Python 3.12:

```bash
uv export --locked --no-hashes --no-dev --no-emit-project -o requirements.txt
python -m pip install -r requirements.txt
```

`requirements.txt` está en `.gitignore`: se genera, no se sube. Con `pip`, cambia `uv run python` por
`PYTHONPATH=src python` en los comandos de abajo (en PowerShell: `$env:PYTHONPATH = "src"` y luego
`python ...`).

### Qué se configura

| Archivo | Qué trae |
|---|---|
| [`config/control/politica.yaml`](config/control/politica.yaml) | Zonas, clases de obstáculo, umbral de confianza, histéresis y velocidades. Explicado en [`docs/politica.md`](docs/politica.md). |
| [`config/control/plazos.yaml`](config/control/plazos.yaml) | Edad máxima del cuadro, watchdog, validez de cada orden y paso del reloj. |
| [`config/contrato/`](config/contrato/CONTRATO.md) | Contrato de percepción A → B y de comando. **No se cambia.** |

Sin llaves ni secretos: nada de esto se conecta a la red.

### 1. Validar eventos contra el contrato

```bash
uv run python -m contrato config/contrato/ejemplos/flujo.jsonl
# config/contrato/ejemplos/flujo.jsonl: OK (5 eventos)
```

Acepta `.json` o `.jsonl`. Sale con **0** si todo cumple y con **1** si algo no cumple; en ese caso imprime
cada problema con el número de evento.

### 2. Correr una secuencia

```bash
uv run python -m control --entrada config/contrato/ejemplos/flujo.jsonl \
  --config config/control/ --salida resultados/ejemplo-01/
# resultados/ejemplo-01: 5 eventos, 6 comandos, 2 errores
```

Las tres rutas son tuyas: `--entrada` puede ser cualquier archivo de eventos (por ejemplo, la salida del
detector de A) y `--salida` cualquier carpeta. Ahí quedan:

| Archivo | Qué es |
|---|---|
| `detecciones.jsonl` | Cada evento tal como llegó del detector. |
| `decisiones.jsonl` | Qué se decidió en cada cuadro o tic de reloj, quién lo decidió (política o supervisor) y el estado. |
| `comandos.jsonl` | Lo que registró el adaptador virtual. |
| `errores.jsonl` | Cada STOP por falla (stale, error, watchdog, etc.). |
| `run.json` | SHA-256 de la entrada y de la configuración, hashes del detector, versiones y conteos. |

Todo se enlaza por `run_id` y `frame_id`. No se lee el reloj del sistema: la misma entrada deja siempre los
mismos archivos. Con `--acciones acciones.yaml` se agregan `tick`, `emergencia`, `rearmar` y `cerrar` en
instantes fijos (C10); el formato está en [`casos/README.md`](casos/README.md).

### 3. Correr los casos C1–C10

```bash
uv run python casos/runner.py            # los diez
uv run python casos/runner.py C8 C9      # solo esos
```

Imprime una tabla PASA/FALLA y, debajo, por qué falla cada caso. Sale con **0** si todos pasan, **1** si
alguno falla y **2** si la configuración no se puede leer. Opciones: `--casos` (carpeta de casos),
`--config` (carpeta `config/control/`) y `--salida` (por omisión, `resultados/casos/`).

Por caso quedan en `resultados/casos/Cn/` los mismos archivos de `python -m control` más `veredicto.json`
(cada tramo con su motivo), y la tabla en `resultados/casos/resumen.txt`. Qué se espera de cada caso y cómo
se juzga: [`casos/README.md`](casos/README.md).

> Hoy pasan **3 de 10**: C8, C9 y C10, cuyas entradas están armadas a mano porque prueban fallas sin
> video (sin cuadros, errores del detector y emergencia). C1 a C7 salen de las secuencias S01 a S08
> (`datos/cuadros/`) pasadas por `infer`, pero se arman cuando el conjunto esté congelado (P5-11) y
> exista `datos/MAPA_CASOS.md` (P5-12). Mientras tanto, el runner los marca FALLA con "falta
> entrada.jsonl".

### 4. Comprobar que una expectativa alterada se detecta

Las expectativas (`casos/Cn/expectativa.yaml`) se escribieron antes de correr los casos y **no se cambian
para que pasen**. Hay dos candados:

```bash
# a) El hash: falla si alguien edita una expectativa o el esquema.
uv run pytest -q tests/test_expectativas.py

# b) El runner: en una copia, cambia lo permitido en un tramo y córrelo.
cp -r casos /tmp/casos-copia
#    en /tmp/casos-copia/C8/expectativa.yaml, tramo "hueco": acciones_permitidas: [AVANZAR]
uv run python casos/runner.py C8 --casos /tmp/casos-copia --salida /tmp/casos-salida
#    C8    armada   2/3     FALLA
#      - hueco: ninguna orden con AVANZAR en el plazo de 600 ms
```

En PowerShell, el paso (b) es:

```powershell
Copy-Item -Recurse casos "$env:TEMP\casos-copia"
#    en $env:TEMP\casos-copia\C8\expectativa.yaml, tramo "hueco": acciones_permitidas: [AVANZAR]
uv run python casos/runner.py C8 --casos "$env:TEMP\casos-copia" --salida "$env:TEMP\casos-salida"
```

En la copia, `sha256sum -c expectativas.sha256` (dentro de la carpeta, en Git Bash) también marca
`C8/expectativa.yaml: FAILED`. La prueba (a) funciona igual en todos lados.

### Dónde quedan los resultados

| Qué corriste | Dónde queda |
|---|---|
| `python -m control` | En la carpeta que diste con `--salida`. |
| `casos/runner.py` | En `resultados/casos/Cn/` (o en la carpeta de `--salida`), más la tabla en `resumen.txt`. |
| Lo que se sube al repo | `resultados/casos/`, la última corrida de los casos. Tus corridas de prueba no hace falta subirlas. |

### Pruebas del grupo B

```bash
uv run pytest -q tests/test_config_politica.py tests/test_zonas.py tests/test_decision.py \
  tests/test_umbral.py tests/test_histeresis.py tests/test_supervisor.py tests/test_watchdog.py \
  tests/test_fallas.py tests/test_emergencia.py tests/test_adaptador_virtual.py tests/test_comando.py \
  tests/test_correr.py tests/test_expectativas.py tests/test_runner.py tests/test_readme_b.py
```

## Cómo contribuir

Un ticket = una rama = un PR. Ramas `p5-NN-...` (grupo A) o `p5-tNN-...` (grupo B); títulos `P5-NN: ...` o
`TNN: ...`. El CI corre Ruff y pytest en cada PR. Detalles en [CONTRIBUTING.md](CONTRIBUTING.md).
