# Primer recorrido con el detector real (T16, con P5-08)

Una foto real pasa por el detector del grupo A y termina en un comando del grupo B. Todo corre
offline, en CPU y **sin mover motores**: el comando solo queda escrito en `comandos.jsonl`.

```
cuadro real → infer (A, P5-05) → eventos .jsonl → python -m contrato → python -m control → comandos.jsonl
```

> **Estado (2026-11-01):** **izquierda** (S09) y **derecha** (S10) corrieron con el `infer` de
> `main` (`d3a2f1c`, #75), que ya calienta el predictor antes de arrancar el reloj. Los comandos
> salen opuestos: `GIRAR_DER` en los 12 cuadros de S09 y `GIRAR_IZQ` en 10 de S10. Los otros 2
> de S10 llegaron con más de 500 ms y B los paró por `cuadro_viejo` (ver
> [Tiempos](#diferencias-encontradas)). Falta **centro**. Lo de [Ya comprobado](#ya-comprobado)
> se probó con secuencias armadas.

## Qué hace falta de A1

- [x] El comando `infer` (P5-05), en `main` desde #75 (`d3a2f1c`).
- [x] Los pesos `yolo11n.pt` (release v8.3.0 de Ultralytics) con el SHA-256 que exige
  `config/detector.json`, y su `config_sha256`.
- [x] Que `infer` caliente el predictor antes de arrancar el reloj del run (`detector.calentar()`
  en `src/infer/eventos.py`, desde #75).
- [ ] Tres secuencias reales: **izquierda** (S09, lista), **derecha** (S10, lista) y **centro**.
  - S09 y S10 son las secuencias de prueba del grupo B de `datos/DOMINIO.md`: la taza toca el
    centro, cargada a la izquierda y a la derecha.
  - Para **centro** se usa una **toma de prueba aparte**: S02 a S08 no se usan hasta que se
    congelen.
  - En las de izquierda y derecha, el obstáculo debe **tocar el centro**, cargado hacia un lado.
    Un obstáculo que solo está a un lado deja el centro libre y la política avanza recto en los
    dos casos, así que no habría comandos opuestos que comparar (ver
    [docs/politica.md](politica.md), sección 4).
  - Por eso **S3 y S4 no sirven** para este recorrido: en el plan de `datos/DOMINIO.md` la
    botella va en el tercio de un lado con el centro libre.
  - El obstáculo es una botella (39) o una taza (41). En las fotos de P5-04 la taza se detectó
    al centro de cerca (0.96) y la botella al centro de cerca no pasó de 0.29, así que la taza
    es la mejor opción para tocar el centro.

## Comandos exactos

Desde la raíz del repo, para cada secuencia (`izq`, `der`, `centro`):

```bash
# 1. Detector (A, P5-05). Un --capture-ms por JPEG, en el orden de los nombres, copiados de
#    t_capture_ms en captura.jsonl de la secuencia (S09):
uv run --locked python -m infer --input <carpeta con los JPEG de S09> \
    --config config/detector.json --weights <ruta local>/yolo11n.pt \
    --output resultados/recorrido-real/izq/detector.jsonl \
    --run-id recorrido-real-izq --sequence-id S09 \
    --capture-ms 0 --capture-ms 203 --capture-ms 484 --capture-ms 687 \
    --capture-ms 906 --capture-ms 1140 --capture-ms 1390 --capture-ms 1593 \
    --capture-ms 1812 --capture-ms 2031 --capture-ms 2297 --capture-ms 2531

#    Para der (S10): --output resultados/recorrido-real/der/detector.jsonl
#    --run-id recorrido-real-der --sequence-id S10 y los t_capture_ms de su captura.jsonl:
#    0 250 500 750 985 1188 1391 1688 1954 2157 2360 2563

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
| izq (S09) | `recorrido-real-izq` | 12 | 0 (12 eventos OK) | 0 (13 comandos, 0 errores) | GIRAR_DER 12 |
| der (S10) | `recorrido-real-der` | 12 | 0 (12 eventos OK) | 0 (13 comandos, 2 errores) | GIRAR_IZQ 10, STOP 2 por `cuadro_viejo` |
| centro | PENDIENTE (toma de prueba aparte) | | | | |

El comando 13 de cada corrida es el STOP de cierre (`shutdown`).

- `model_sha256`: `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`
- `config_sha256`: `6428a259f22939fe5055dc101cec4517612dad5fb573d5852187932f39954e08`. Cambió
  respecto a la primera corrida (`bd736aff…`, con `bfe7644`) porque #75 fija `torch_threads: 2`
  en `config/detector.json`.
- Código: `infer` y B en `main` (`d3a2f1c`), el mismo en S09 y S10.
- Los JPEG de S09 y S10, su `captura.jsonl` y sus anotaciones no están en el repo: son de A
  (P5-09; van en `datos/pruebas-b/` cuando entren). Antes de correr se comprobó que el SHA-256
  de cada JPEG coincide con el de `captura.jsonl`.

**`frame_id`:** desde #75, `infer` usa el nombre del JPEG sin extensión (`config/DETECTOR.md`):
`S09_f0001` a `S09_f0012` y `S10_f0001` a `S10_f0012`, los mismos de `captura.jsonl`. Siguen
iguales en `detecciones.jsonl`, `decisiones.jsonl`, `comandos.jsonl` y `errores.jsonl`: los 24
cuadros llegan a su comando.

### Izquierda y derecha: ¿comandos opuestos?

Lo esperado: con el obstáculo en el centro cargado a la **izquierda**, `GIRAR_DER`
(`steering > 0`); cargado a la **derecha**, `GIRAR_IZQ` (`steering < 0`). Si salen al revés, las
coordenadas `x` están invertidas en algún punto (por ejemplo, la imagen volteada o un error al
deshacer el *letterbox*).

- **Izquierda (S09):** la taza aparece a la izquierda del centro en la foto, y la caja también:
  `x` de 211 a 360 en el primer cuadro (zona `centro`) y de 177 a 343 en el último (`izq` y
  `centro`). El centro de la caja queda entre x = 260 y 296. **`GIRAR_DER` con `steering 0.5`
  en los 12 cuadros**, decidido por la política.
- **Derecha (S10):** la taza aparece a la derecha del centro, y la caja también: `x` de 220 a
  473 en el primer cuadro (`centro` y `der`) y de 208 a 466 en el último (`centro`). El centro
  de la caja queda entre x = 337 y 347. **`GIRAR_IZQ` con `steering -0.5` en los cuadros
  `S10_f0001` a `S10_f0010`**. `S10_f0011` y `S10_f0012` llegaron viejos y el supervisor mandó
  STOP; con las mismas detecciones, la política sola también da `GIRAR_IZQ`.

Los comandos salen **opuestos**: `GIRAR_DER` en S09 y `GIRAR_IZQ` en S10, con `steering` del
mismo tamaño y signo contrario. Las `x` no están invertidas.

### Un cuadro seguido de punta a punta

`python -m control.traza --salida resultados/recorrido-real/izq/ --frame-id S09_f0012`:

```
S09_f0012 · run recorrido-real-izq · status ok · captura 2531.0 ms · llegada 2640.9999998286366 ms · 640x480 px (xyxy)
  detección: class_id 41 · confianza 0.9309038519859314 · bbox [177.42332458496094, 224.3782501220703, 343.102294921875, 351.24249267578125] -> izq, centro
  decisión: GIRANDO_DER -> GIRANDO_DER · GIRAR_DER (decidió politica) · esperando_cuadros_libres 0/3: sigue girando hacia la derecha, que está libre. Obstáculo en el centro (class_id 41, confianza 0.930904); la derecha está libre: gira hacia allá.
  comando: GIRAR_DER · speed 0.4 · steering 0.5 · t_command 2640.9999998286366 ms · vale hasta 3040.9999998286366 ms
```

## Diferencias encontradas

| Qué | Cómo se revisa | Encontrado (izq S09 y der S10) |
|---|---|---|
| Coordenadas | Las cajas están en píxeles del cuadro **original**, con `image_width` e `image_height` reales; la caja cae del lado en que se ve el objeto en la foto. | Sin diferencia: 640×480, `xyxy` en píxeles, y la caja cae donde se ve la taza. Contra las anotaciones de A, el IoU va de 0.87 a 0.96 en S09 y de 0.91 a 0.98 en S10. |
| Clases | Cada `class_id` está en `modelo/clases.json`, y el obstáculo filmado tiene un `class_id` de `clases_obstaculo` (`[39, 41]`: botella y taza, definitivas desde T12). | Sin diferencia: `cup` (41) en los 12 cuadros de cada una, con confianza de 0.76 a 0.93 en S09 y de 0.88 a 0.95 en S10. |
| Tiempos | `t_capture_ms` crece por secuencia, `t_emit_ms ≥ t_capture_ms` y la edad `t_emit_ms − t_capture_ms` queda debajo de `max_frame_age_ms` (500 ms). | S09: sin diferencia (79 a 188 ms). S10: **2 cuadros pasan de 500 ms** (515 y 609 ms, ver abajo). |
| Hashes | Un solo `model_sha256` y un solo `config_sha256` por run. | Sin diferencia, y los mismos en las dos. |

**Tiempos.** Con `bfe7644`, el reloj de `infer` arrancaba antes de la primera inferencia, que
prepara el predictor de Ultralytics y en esta laptop Windows tarda decenas de segundos: todos los
cuadros llegaban con 32 a 35 s de edad y terminaban en STOP. #75 lo arregló con
`detector.calentar()` antes de fijar el origen. Ahora el primer cuadro de S09 sale a los 125 ms.

En S10 cada inferencia tardó de 190 a 360 ms, más que la separación entre capturas (unos 200 a
300 ms). El atraso se fue juntando: 218 ms en `S10_f0006`, 390 en `S10_f0010`, 515 en
`S10_f0011` y 609 en `S10_f0012`. B hizo lo que debe: rechazó esos dos por edad y mandó STOP. Al
repetir las dos secuencias en la misma laptop (fuera de los registros), todos los cuadros
quedaron entre 202 y 281 ms. El margen depende de la carga de la máquina: con inferencias de
unos 250 ms y cuadros cada 200 a 250 ms, la cola puede crecer. Va como dato para los límites y
plazos (P5-16); no se toca `max_frame_age_ms` ni se escoge la corrida que salió mejor.

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
