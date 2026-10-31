# Primer recorrido con el detector real (T16, con P5-08)

Una foto real pasa por el detector del grupo A y termina en un comando del grupo B. Todo corre
offline, en CPU y **sin mover motores**: el comando solo queda escrito en `comandos.jsonl`.

```
cuadro real → infer (A, P5-05) → eventos .jsonl → python -m contrato → python -m control → comandos.jsonl
```

> **Estado (2026-10-31):** ya corrió la secuencia de **izquierda** (S09) con el detector real.
> El detector y las zonas salen bien, pero todos los cuadros llegan a B con unos 35 s de edad y
> terminan en STOP por `cuadro_viejo`: es un problema de tiempos de `infer` (ver
> [Diferencias encontradas](#diferencias-encontradas)). Faltan las secuencias de **derecha** y
> **centro**. Lo de [Ya comprobado](#ya-comprobado) se probó con secuencias armadas.

## Qué hace falta de A1

- [x] El comando `infer` (P5-05): rama `p5-05-detector-infer`, commit `bfe7644`, todavía sin
  mergear a `main`.
- [x] Los pesos `yolo11n.pt` (release v8.3.0 de Ultralytics) con el SHA-256 que exige
  `config/detector.json`, y su `config_sha256`.
- [ ] Que `infer` caliente el predictor antes de arrancar el reloj del run (ver
  [Tiempos](#diferencias-encontradas)).
- [ ] Tres secuencias reales: **izquierda** (S09, lista), **derecha** y **centro**.
  - En las de izquierda y derecha, el obstáculo debe **tocar el centro**, cargado hacia un lado.
    Un obstáculo que solo está a un lado deja el centro libre y la política avanza recto en los
    dos casos, así que no habría comandos opuestos que comparar (ver
    [docs/politica.md](politica.md), sección 4).
  - Por eso **S3 y S4 no sirven** para este recorrido: en el plan de `datos/DOMINIO.md` la
    botella va en el tercio de un lado con el centro libre. Hacen falta tomas aparte.
  - El obstáculo es una botella (39) o una taza (41). En las fotos de P5-04 la taza se detectó
    al centro de cerca (0.96) y la botella al centro de cerca no pasó de 0.29, así que la taza
    es la mejor opción para tocar el centro.

## Comandos exactos

Desde la raíz del repo, para cada secuencia (`izq`, `der`, `centro`):

```bash
# 1. Detector (A, P5-05), desde la rama p5-05-detector-infer. Un --capture-ms por JPEG, en el
#    orden de los nombres, copiados de t_capture_ms en captura.jsonl de la secuencia (S09):
uv run --locked python -m infer --input <carpeta con los JPEG de S09> \
    --config config/detector.json --weights <ruta local>/yolo11n.pt \
    --output resultados/recorrido-real/izq/detector.jsonl \
    --run-id recorrido-real-izq --sequence-id S09 \
    --capture-ms 0 --capture-ms 203 --capture-ms 484 --capture-ms 687 \
    --capture-ms 906 --capture-ms 1140 --capture-ms 1390 --capture-ms 1593 \
    --capture-ms 1812 --capture-ms 2031 --capture-ms 2297 --capture-ms 2531

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

Los archivos de cada corrida están en `resultados/recorrido-real/<secuencia>/`: `detector.jsonl`
(salida de `infer`), los registros de `python -m control` y `traza.txt`.

| Secuencia | `run_id` | Cuadros | `contrato` | `control` | Acciones por cuadro |
|---|---|---|---|---|---|
| izq (S09) | `recorrido-real-izq` | 12 | 0 (12 eventos OK) | 0 (13 comandos, 12 errores) | STOP 12, todos por `cuadro_viejo` |
| der | PENDIENTE | | | | |
| centro | PENDIENTE | | | | |

- `model_sha256`: `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`
- `config_sha256`: `bd736aff92ac6ae39348272ec48763764edf16b30c6ba0d3847cf9bae0658fdf`
- Código: `infer` en `bfe7644` (`p5-05-detector-infer`); B en la rama `p5-t16-recorrido-real`.
- Los JPEG de S09 y su `captura.jsonl` no están en el repo: son de A (P5-09). Antes de correr se
  comprobó que el SHA-256 de cada JPEG coincide con el de `captura.jsonl`.

**`frame_id`:** `infer` numera los cuadros `f000001` a `f000012` en el orden de los nombres de
los JPEG, sin usar el nombre (`config/DETECTOR.md`, paso 4). En S09, `f000001` es `S09_f0001.jpg`
y así hasta `f000012`. Los mismos `frame_id` siguen en `detecciones.jsonl`, `decisiones.jsonl`,
`comandos.jsonl` y `errores.jsonl`: los 12 llegan a su comando.

### Izquierda y derecha: ¿comandos opuestos?

Lo esperado: con el obstáculo en el centro cargado a la **izquierda**, `GIRAR_DER`
(`steering > 0`); cargado a la **derecha**, `GIRAR_IZQ` (`steering < 0`). Si salen al revés, las
coordenadas `x` están invertidas en algún punto (por ejemplo, la imagen volteada o un error al
deshacer el *letterbox*).

- **Izquierda (S09):** la taza aparece a la izquierda del centro en la foto, y la caja también:
  `x` de 211 a 360 en el primer cuadro (zona `centro`) y de 177 a 343 en el último (`izq` y
  `centro`). La orientación es correcta. En la corrida, el supervisor manda STOP en los 12
  cuadros porque llegan viejos. Como diagnóstico (fuera de los registros), las mismas
  detecciones pasadas directo a `control.politica.decidir` dan **`GIRAR_DER` con
  `steering 0.5` en los 12 cuadros**: es lo que saldrá cuando `infer` entregue cuadros frescos.
- **Derecha:** PENDIENTE, falta la secuencia.

### Un cuadro seguido de punta a punta

`python -m control.traza --salida resultados/recorrido-real/izq/ --frame-id f000012`:

```
f000012 · run recorrido-real-izq · status ok · captura 2531.0 ms · llegada 37562.000000150874 ms · 640x480 px (xyxy)
  detección: class_id 41 · confianza 0.9309038519859314 · bbox [177.42332458496094, 224.37826538085938, 343.102294921875, 351.2424621582031] -> izq, centro
  decisión: DETENIDO -> DETENIDO · STOP (decidió supervisor) · cuadro_viejo
  comando: STOP · speed 0 · steering 0.0 · t_command 37562.000000150874 ms · vale hasta 37962.000000150874 ms
  error registrado: cuadro_viejo
```

## Diferencias encontradas

| Qué | Cómo se revisa | Encontrado (izq, S09) |
|---|---|---|
| Coordenadas | Las cajas están en píxeles del cuadro **original**, con `image_width` e `image_height` reales; la caja cae del lado en que se ve el objeto en la foto. | Sin diferencia: 640×480, `xyxy` en píxeles, y la caja cae donde se ve la taza. |
| Clases | Cada `class_id` está en `modelo/clases.json`, y el obstáculo filmado tiene un `class_id` de `clases_obstaculo` (`[39, 41]`: botella y taza, definitivas desde T12). | Sin diferencia: `cup` (41) en los 12 cuadros, con confianza de 0.76 a 0.93. |
| Tiempos | `t_capture_ms` crece por secuencia, `t_emit_ms ≥ t_capture_ms` y la edad `t_emit_ms − t_capture_ms` queda debajo de `max_frame_age_ms` (500 ms). | **Diferencia.** La edad es de unos 35 000 ms en todos los cuadros (ver abajo). |
| Hashes | Un solo `model_sha256` y un solo `config_sha256` por run. | Sin diferencia. |

**Tiempos.** El primer cuadro sale con `t_emit_ms` de 35 797 ms. Después cada inferencia tarda
unos 150 ms, pero toda la secuencia ya va atrasada: el último cuadro se capturó a los 2 531 ms y
salió a los 37 562 ms. Al repetir el mismo comando, el atraso fue de unos 18 s. La causa está en
`src/infer/eventos.py` (`ejecutar_run`): el origen del reloj se fija después de cargar los pesos,
pero **antes de la primera inferencia**, que prepara el predictor de Ultralytics y en esta laptop
Windows tarda decenas de segundos. B hace lo que debe: rechaza los cuadros por edad (más de
500 ms) y manda STOP.

No toca el contrato, y no se corrige a mano ni en B: se arregla en `infer` (P5-05), por ejemplo
con una inferencia de calentamiento antes de fijar el origen. Después se vuelve a correr S09.

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
