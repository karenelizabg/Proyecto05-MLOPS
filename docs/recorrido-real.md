# Primer recorrido con el detector real (T16, con P5-08)

Una foto real pasa por el detector del grupo A y termina en un comando del grupo B. Todo corre
offline, en CPU y **sin mover motores**: el comando solo queda escrito en `comandos.jsonl`.

```
cuadro real → infer (A, P5-05) → eventos .jsonl → python -m contrato → python -m control → comandos.jsonl
```

> **Estado:** falta la salida real del detector. En `main` todavía no existen el comando `infer`
> (P5-05), los pesos (`modelo/`) ni las secuencias reales (`datos/`, P5-09). Lo que está marcado
> como **PENDIENTE** se llena con A1 cuando haya salida real. Lo de [Ya comprobado](#ya-comprobado)
> se probó con secuencias armadas con el formato exacto del contrato.

## Qué hace falta de A1

- [ ] El comando `infer` (P5-05), con el commit o la rama donde está.
- [ ] Los pesos con su SHA-256 (`model_sha256`) y la configuración (`config_sha256`).
- [ ] Tres secuencias reales: **izquierda**, **derecha** y **centro**.
  - En las de izquierda y derecha, el obstáculo debe **tocar el centro**, cargado hacia un lado.
    Un obstáculo que solo está a un lado deja el centro libre y la política avanza recto en los
    dos casos, así que no habría comandos opuestos que comparar (ver
    [docs/politica.md](politica.md), sección 4).

## Comandos exactos

Desde la raíz del repo, para cada secuencia (`izq`, `der`, `centro`):

```bash
# 1. Detector (A1). PENDIENTE: el comando exacto de P5-05.
<comando infer de A1> --entrada <cuadros de la secuencia> --salida resultados/recorrido-real/izq/

# 2. Validar la salida del detector contra el contrato v1. Debe salir 0.
PYTHONPATH=src python -m contrato resultados/recorrido-real/izq/detector.jsonl

# 3. Pasarla por el control de B. Debe salir 0.
PYTHONPATH=src python -m control --entrada resultados/recorrido-real/izq/detector.jsonl \
    --config config/control/ --salida resultados/recorrido-real/izq/

# 4. Seguir cada cuadro de punta a punta (o uno solo con --frame-id).
PYTHONPATH=src python -m control.traza --salida resultados/recorrido-real/izq/
PYTHONPATH=src python -m control.traza --salida resultados/recorrido-real/izq/ --frame-id <frame_id>
```

Con `uv`, cambia `PYTHONPATH=src python` por `uv run python`.

`python -m control.traza` une `detecciones.jsonl`, `decisiones.jsonl`, `comandos.jsonl` y
`errores.jsonl` por `run_id` y `frame_id`. Por cada cuadro muestra:

- qué vio el detector: clase, confianza, caja y zonas que ocupa;
- qué se decidió y quién lo decidió;
- qué comando quedó;
- si se registró un error.

Al final van las órdenes sin cuadro y cuántas veces salió cada acción. Sale con 1 si algún cuadro
no llegó a una decisión o a un comando.

## Resultados

PENDIENTE: llenar con A1 después de correr los comandos.

| Secuencia | `run_id` | Cuadros | `contrato` | `control` | Acciones por cuadro |
|---|---|---|---|---|---|
| izq | | | | | |
| der | | | | | |
| centro | | | | | |

- `model_sha256`: PENDIENTE
- `config_sha256`: PENDIENTE
- Commit del repo: PENDIENTE

### Izquierda y derecha: ¿comandos opuestos?

PENDIENTE. Lo esperado: con el obstáculo en el centro cargado a la **izquierda**, `GIRAR_DER`
(`steering > 0`); cargado a la **derecha**, `GIRAR_IZQ` (`steering < 0`). Si salen al revés, las
coordenadas `x` están invertidas en algún punto (por ejemplo, la imagen volteada o un error al
deshacer el *letterbox*).

### Un cuadro seguido de punta a punta

PENDIENTE: pegar la salida de `python -m control.traza --frame-id <frame_id>` de un cuadro con
obstáculo de cada secuencia.

## Diferencias encontradas

PENDIENTE. Revisar sobre todo:

| Qué | Cómo se revisa | Encontrado |
|---|---|---|
| Coordenadas | Las cajas están en píxeles del cuadro **original**, con `image_width` e `image_height` reales; la caja cae del lado en que se ve el objeto en la foto. | |
| Clases | Cada `class_id` está en `modelo/clases.json`, y el obstáculo filmado tiene un `class_id` de `clases_obstaculo` (hoy `[0, 1]`, provisional, DC-5). | |
| Tiempos | `t_capture_ms` crece por secuencia, `t_emit_ms ≥ t_capture_ms` y la edad `t_emit_ms − t_capture_ms` queda debajo de `max_frame_age_ms` (500 ms). | |
| Hashes | Un solo `model_sha256` y un solo `config_sha256` por run. | |

Si aparece una diferencia, **no se corrige a mano** en los archivos de salida ni en el código de B
para que cuadre. Se corrige donde está el problema, y si toca al contrato, con el contrato
versionado: sube `schema_version` y lo aprueban los dos PM (`config/contrato/CONTRATO.md`,
"Versionado").

## Ya comprobado

Sin el detector real, `tests/test_recorrido.py` pasa secuencias armadas con el formato exacto del
contrato por los mismos pasos 2 y 3 (`python -m contrato` y `python -m control`):

- Con anchos de 320, 640 y 800 px (las resoluciones QVGA, VGA y SVGA del OV2640 de la ESP32-CAM)
  y cajas `xyxy` y `xywh`, un obstáculo en el centro cargado a la izquierda da `GIRAR_DER` en
  todos los cuadros y, cargado a la derecha, `GIRAR_IZQ`. Pasa lo mismo si además tapa ese lado.
- Un obstáculo solo de un lado da `AVANZAR` en los dos casos. Por eso las secuencias reales deben
  tocar el centro.
- Para muchas cajas en distintas posiciones, el cuadro en espejo invierte el giro y el signo de
  `steering`.
- `python -m control.traza` sigue cada cuadro de `config/contrato/ejemplos/flujo.jsonl` hasta su
  decisión y su comando, y avisa si a un cuadro le falta el comando.
