# Contrato de percepción A → B · v1 (borrador)

> **Estado: borrador para aceptación de ambos PM** (ticket P5-02). A1 y B3 mantienen el esquema y los
> ejemplos; cualquier cambio lo aprueban PM A y PM B.
> Alcance: el evento que el detector (grupo A) entrega por cuadro a la política (grupo B).
> El contrato B → adaptador (comando de control) es del grupo B y no está aquí.

| Archivo | Qué es |
|---|---|
| [`percepcion.v1.schema.json`](percepcion.v1.schema.json) | Esquema JSON del evento. |
| [`ejemplos/valido.json`](ejemplos/valido.json) | Dos detecciones. |
| [`ejemplos/vacio.json`](ejemplos/vacio.json) | Cuadro sin objetos: `ok` con lista vacía. |
| [`ejemplos/fallido.json`](ejemplos/fallido.json) | `error`: imagen ilegible. |
| [`ejemplos/stale.json`](ejemplos/stale.json) | Cuadro tardío. |
| [`ejemplos/flujo.jsonl`](ejemplos/flujo.jsonl) | Una secuencia de cinco cuadros que mezcla los casos anteriores. |

Los hashes de los ejemplos (`aaaa…`, `bbbb…`) y las clases (`lata`, `mochila`) son de ejemplo, no reales.

## Reglas que no se negocian

1. **Un cuadro procesado sin objetos es `status=ok` con `detections: []`.** Solo eso significa "el detector no vio obstáculos".
2. **`stale` y `error` nunca equivalen a vía libre.** B los trata como pérdida de percepción: STOP.
3. **La ausencia de eventos tampoco es vía libre.** El watchdog de B vence aunque no llegue un cuadro nuevo.
4. **Solo `status=ok` trae detecciones.** Con `stale` o `error`, `detections` es siempre `[]`.
5. **Solo viajan clases del dominio.** A descarta las demás antes de emitir; B no ve clases desconocidas.
6. **Todo evento identifica el modelo y la configuración por hash.** Un run usa un solo modelo y una sola configuración.

## Campos

| Campo | Tipo | Obligatorio | Significado y unidad |
|---|---|---|---|
| `schema_version` | `"1"` | sí | Versión del contrato. B la reconoce antes de producir comandos. |
| `run_id` | texto | sí | Una ejecución completa. `[A-Za-z0-9._-]`, hasta 64. |
| `sequence_id` | texto | sí | Secuencia del cuadro. Neutro: no codifica clase ni caso. |
| `frame_id` | texto | sí | Único dentro del run. Neutro. |
| `t_capture_ms` | número ≥ 0 | sí | Instante de captura, **ms**, reloj monotónico relativo al inicio del run (no hora de pared). Estrictamente creciente por secuencia. |
| `t_emit_ms` | número ≥ 0 | sí | Instante en que A publica el evento, mismo reloj y unidad. Nunca anterior a `t_capture_ms`. Edad del dato = `t_emit_ms − t_capture_ms`. |
| `image_width`, `image_height` | entero ≥ 1 | sí | Píxeles del cuadro **original**, no del redimensionado. `null` solo si la imagen no se pudo leer (`status=error`). |
| `model_sha256` | 64 hex en minúsculas | sí | Pesos cargados. Si el error ocurre antes de cargar, el hash configurado. |
| `config_sha256` | 64 hex en minúsculas | sí | Parámetros efectivos: umbrales, NMS, clases, resolución. |
| `status` | `ok` · `stale` · `error` | sí | Ver la tabla siguiente. |
| `bbox_format` | `xyxy` · `xywh` | sí | `xyxy` = `[x1, y1, x2, y2]`; `xywh` = `[x, y, ancho, alto]`. |
| `bbox_unit` | `"px"` | sí | Píxeles del cuadro original. |
| `detections[]` | lista | sí | Ver más abajo. |
| `error` | objeto | solo con `status=error` | `code` + `message`. Prohibido en los demás estados. |

**`detections[]`:** `class_id` (entero ≥ 0, según `modelo/clases.json`), `confidence` (0 a 1), `bbox` (4 números ≥ 0) y, opcional, `class_name` (solo para leer; B decide con `class_id`).

**`error.code`:** `unreadable_image` · `detector_exception` · `detector_timeout` · `invalid_output` (los fallos de C9). Un código desconocido se trata como error: STOP.

## Estados

| `status` | Cuándo lo emite A | Contenido | Qué hace B |
|---|---|---|---|
| `ok` | El cuadro se leyó, se infirió y la salida es válida. | `detections` con 0 o más objetos. | Decide con la política. Lista vacía = despejado. |
| `stale` | El cuadro llega más viejo que `max_frame_age_ms` (lo declara B en los plazos). | `detections: []`, sin `error`. | Rechaza la entrada vieja, cancela la orden previa y emite STOP (C8). |
| `error` | Imagen ilegible, excepción, tiempo agotado o salida inválida del detector. | `detections: []` y `error`. | Registra el error y emite STOP (C9). |

## Coordenadas y tiempo

- **Cajas:** píxeles del cuadro original, origen arriba a la izquierda, x hacia la derecha, y hacia abajo. A deshace cualquier redimensionado o *letterbox* antes de emitir, y recorta las cajas a la imagen. Dentro de un run no cambia `bbox_format`.
- **Izquierda / centro / derecha** se calculan sobre `image_width`; B no debe fijar el ancho a mano.
- **Reloj:** `t_capture_ms` y `t_emit_ms` comparten origen y unidad con los tiempos de B (`t_decision_ms`, `t_command_ms`, `valid_until_ms`). En la reproducción de secuencias guardadas es el tiempo relativo del manifiesto; en vivo, un reloj monotónico.

## Versionado

- `schema_version` cambia (`"2"`) ante cualquier cambio de significado, unidad o campo obligatorio, o al quitar un valor de un enum.
- Se puede agregar un campo **opcional** o un `error.code` nuevo sin subir la versión, avisando a B por escrito.
- B rechaza (STOP) los eventos con una versión que no reconoce.
- A1 y B3 mantienen los ejemplos válidos y los de error en este directorio; el PR de un cambio lo aprueban ambos PM.

## Cómo validar

Desde la raíz del repo (requiere `jsonschema`):

```bash
PYTHONPATH=src python -m contrato config/contrato/ejemplos/valido.json
PYTHONPATH=src python -m contrato config/contrato/ejemplos/flujo.jsonl
```

Salida 0 si cumple, 1 si hay eventos inválidos, 2 si un archivo no se puede leer. Además del esquema, comprueba que
las cajas caben en la imagen, que `t_emit_ms ≥ t_capture_ms`, y entre eventos: `frame_id` único por run, `t_capture_ms`
creciente por secuencia y un solo modelo y configuración por run. Las pruebas están en `tests/test_contrato.py`.

## Decisiones abiertas para los PM

Cada una tiene un valor por omisión; si nadie dice otra cosa, rige el valor por omisión.

| ID | Decisión | Por omisión |
|---|---|---|
| DC-1 | Formato de caja. | `xyxy`, píxeles del cuadro original. |
| DC-2 | Origen del reloj en vivo y en reproducción. | Reproducción: tiempo relativo del manifiesto. En vivo: reloj monotónico desde el inicio del run. |
| DC-3 | Quién emite `stale`. | A, cuando la edad del cuadro supera `max_frame_age_ms`; el watchdog de B cubre la ausencia total de cuadros. |
| DC-4 | `max_frame_age_ms` y plazo de inferencia (`detector_timeout`). | Los declara B antes de medir, relacionados con el ritmo de entrada (PEND-09). |
| DC-5 | Lista de clases del dominio y su `class_id`. | Sale de `modelo/clases.json` (A1, P5-04). La lista de clases relevantes de B1 debe ser un subconjunto. |
| DC-6 | Si A cuenta las detecciones descartadas por clase o NMS (`num_filtradas`). | No; se puede agregar como campo opcional. |

## Aceptación

- [ ] PM A acepta el contrato v1.
- [ ] PM B acepta el contrato v1.
- [ ] B3 reprodujo con el detector real un ejemplo y obtuvo el mismo evento (P5-08).

## Contrato de comando B → adaptador · v1

Es del grupo B y aparte del contrato de percepción: el comando que la política entrega al adaptador virtual,
que lo registra **sin mover motores**.

| Archivo | Qué es |
|---|---|
| [`comando.v1.schema.json`](comando.v1.schema.json) | Esquema JSON del comando. |
| [`ejemplos_comando/avanzar.json`](ejemplos_comando/avanzar.json) | Cuadro despejado: AVANZAR. |
| [`ejemplos_comando/stop.json`](ejemplos_comando/stop.json) | Obstáculo al centro: STOP. |
| [`ejemplos_comando/reloj.json`](ejemplos_comando/reloj.json) | Watchdog vencido sin cuadro (`event=clock`, `frame_id: null`): STOP. |

- **`action=STOP` siempre lleva `speed=0` y `steering=0`.**
- `AVANZAR` lleva `speed > 0` (C1). `GIRAR_IZQ` lleva `steering < 0` y `GIRAR_DER` `steering > 0` (C4): negativo es izquierda.
- `event=frame` trae el `frame_id` del cuadro; `event=clock` lleva `frame_id: null`.
- `t_decision_ms ≤ t_command_ms ≤ valid_until_ms`, en el mismo reloj que `t_capture_ms` y `t_emit_ms`.

`validar_comando` (en `src/contrato/comando.py`) devuelve la lista de errores, vacía si el comando cumple.
Las pruebas están en `tests/test_comando.py`.
