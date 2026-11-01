# casos/

Los diez casos C1–C10 (entregable **E5**, grupo B). Cada caso vive en `casos/Cn/` con su entrada,
sus acciones y su expectativa, y `casos/runner.py` los corre todos (T15, T17).

| Paso | Ticket | Qué deja |
|---|---|---|
| Qué debe pasar | **T15** | `casos/Cn/expectativa.yaml` (este formato). |
| Con qué se prueba | Por asignar | La entrada de cada caso, con las secuencias de A (P5-09, P5-12). |
| Correrlo y comparar | T17 | `casos/runner.py`: corre `python -m control` y juzga cada caso con su expectativa. |
| Revisión | T24 | Ale revisa las expectativas. |

## La regla: la expectativa va primero y no se cambia para que pase

Las expectativas se escribieron **antes de correr ningún caso**. Salen del enunciado de cada caso,
del contrato (`config/contrato/CONTRATO.md`) y de los plazos que declara B
(`config/control/plazos.yaml`), no de lo que hace el código hoy. Si un caso falla, se arregla el
código o se explica en el reporte por qué falla. **No se relaja la expectativa.**

Para que un cambio no pase desapercibido, `casos/expectativas.sha256` guarda el SHA-256 de cada
`expectativa.yaml` y del esquema, y `tests/test_expectativas.py` falla si alguno cambia. Si una
expectativa de verdad está mal (por ejemplo, contradice el contrato), se corrige en **un PR
aparte** que explique el motivo y actualice el hash. Nunca va junto con el cambio de código o de
configuración que la haría pasar. Ese PR lo revisa Ale (T24).

## Resumen

| Caso | Qué se espera | Plazo |
|---|---|---|
| C1 · Vía libre | AVANZAR con `speed > 0`; nunca STOP ni giros. | 500 ms desde la captura |
| C2 · Obstáculo central | STOP o giro hacia una zona libre; nunca AVANZAR. | 500 ms desde la captura |
| C3 · Obstáculo izquierdo | Nunca GIRAR_IZQ. | — |
| C4 · Obstáculo derecho | Nunca GIRAR_DER. | — |
| C5 · Sin zona libre | Solo STOP. | 500 ms desde la captura |
| C6 · Confianza | Debajo del umbral avanza; encima del umbral reacciona. | 500 ms desde la captura |
| C7 · Libre → bloqueo → libre | Reacciona al bloqueo y reanuda al despejarse. Un cuadro libre suelto no cambia la decisión. | 500 ms al bloqueo; 1000 ms para reanudar |
| C8 · Sin cuadros | STOP con `event=clock`; el cuadro viejo da STOP y queda registrado. | 600 ms desde el último cuadro |
| C9 · Errores | Cada `error.code` del contrato da STOP y queda en `errores.jsonl`. | La orden de ese mismo cuadro |
| C10 · Emergencia | STOP en el acto y enclavado; tras el rearme solo un cuadro fresco reanuda; STOP al cerrar. | 0 ms desde el evento |

De dónde salen los plazos:

- **500 ms** es `max_frame_age_ms`: reaccionar después sería decidir con un cuadro que B ya debe
  rechazar.
- **600 ms** es `watchdog_ms`: el plazo declarado sin ningún evento.
- **1000 ms** son cinco cuadros a 5 fps. El carrito tiene que reanudar, pero no con el primer
  cuadro libre.
- **0 ms** desde la emergencia y el cierre: el reloj es virtual, así que el STOP sale en el mismo
  instante del evento.

Los números se copiaron en cada expectativa y no se leen de `plazos.yaml`. Si un plazo cambia
después, la expectativa no cambia con él: `tests/test_expectativas.py` avisa si un plazo de B queda
más holgado que lo que pide la expectativa.

## Formato de `expectativa.yaml`

El esquema es [`expectativa.v1.schema.json`](expectativa.v1.schema.json).

```yaml
version: 1
caso: C2
titulo: Obstáculo central
objetivo: Qué se prueba, en una o dos frases.
entrada: Qué debe traer la entrada del caso.
tramos:
  - nombre: obstaculo
    origen: cuadros
    cuadros: Los cuadros en que el obstáculo ocupa el centro.
    acciones_permitidas: [STOP, GIRAR_IZQ, GIRAR_DER]
    acciones_prohibidas: [AVANZAR]
    plazo_reaccion_ms: 500
    plazo_desde: captura
    condiciones: [giro_hacia_zona_libre]
stop_con_evento: []
```

### Campos del caso

| Campo | Qué es |
|---|---|
| `version` | Versión del formato: `1`. |
| `caso` | `C1` a `C10`. Coincide con el nombre de la carpeta. |
| `titulo` | Nombre corto del caso. |
| `objetivo` | Qué se prueba, en palabras. |
| `entrada` | Qué debe traer la entrada del caso. Es la guía para armarla: secuencia, estados y orden de los cuadros. |
| `tramos` | Partes del caso, en orden. Cada una dice qué órdenes se esperan. |
| `stop_con_evento` | Eventos sin cuadro (`clock`, `emergency`, `shutdown`) que deben dejar al menos una orden STOP con ese `event` en el run. |

### Campos de cada tramo

| Campo | Qué es |
|---|---|
| `nombre` | Identificador del tramo, en minúsculas con `_`. La entrada del caso dice qué `frame_id` le toca a cada tramo por este nombre. |
| `origen` | Qué órdenes se juzgan en el tramo. Con `cuadros`, las órdenes con `event=frame` de los cuadros del tramo. Con `clock`, `emergency`, `rearm` o `shutdown`, las órdenes con ese `event` que salen entre el tramo anterior y el siguiente. |
| `cuadros` | En palabras, qué cuadros o eventos forman el tramo. |
| `acciones_permitidas` | Acciones aceptadas una vez que el carrito reaccionó (ver abajo). No puede estar vacía. |
| `acciones_prohibidas` | Acciones que ninguna orden del tramo puede tener, ni siquiera dentro del plazo. |
| `plazo_reaccion_ms` | Tiempo máximo para la primera orden con una acción permitida, en ms del mismo reloj que el contrato. `null` si no hay reacción que medir: entonces todas las órdenes del tramo deben estar permitidas desde la primera. |
| `plazo_desde` | Desde dónde se mide el plazo. `null` si no hay plazo. |
| `mantener_accion_cuadros` | Opcional. Los primeros N cuadros del tramo dejan la misma acción que la última orden antes del tramo. |
| `condiciones` | Opcional. Revisiones extra (ver abajo). |

`plazo_desde` puede ser:

| Valor | Desde | Para |
|---|---|---|
| `captura` | `t_capture_ms` del primer cuadro del tramo. | Cuadros: mide de punta a punta, detector incluido. |
| `llegada` | `t_emit_ms` del primer cuadro del tramo. | Cuadros: mide solo a B. |
| `ultimo_cuadro` | `t_emit_ms` del último cuadro antes del tramo. | `clock`: cuánto tarda el reloj en frenar sin cuadros. |
| `evento` | El instante del evento (`ahora_ms` con que se llama a la emergencia, al rearme o al cierre). | `emergency`, `rearm`, `shutdown`. |

`condiciones` puede tener:

| Condición | Qué revisa |
|---|---|
| `avanzar_con_velocidad` | Cada AVANZAR del tramo lleva `speed > 0`. |
| `giro_hacia_zona_libre` | Cada GIRAR_IZQ o GIRAR_DER del tramo va hacia una zona sin obstáculo en ese cuadro, con las zonas, clases y umbral de `config/control/politica.yaml`. |
| `error_registrado` | Cada cuadro del tramo deja una línea en `errores.jsonl` con su `run_id` y su `frame_id`. |
| `es_el_ultimo_comando` | La orden del tramo es la última del run. |

## Cómo se juzga un tramo (T17)

Con las órdenes de `comandos.jsonl` que le tocan al tramo, en orden:

1. **Prohibidas:** ninguna orden tiene una acción de `acciones_prohibidas`.
2. **Sin plazo** (`plazo_reaccion_ms: null`): todas las órdenes tienen una acción permitida. Si el
   origen es `cuadros`, cada cuadro del tramo tiene al menos una orden. Un tramo de evento sin
   órdenes pasa (por ejemplo, un rearme que no deja orden).
3. **Con plazo:** hay una orden con acción permitida cuyo `t_command_ms` menos el instante de
   `plazo_desde` es menor o igual que `plazo_reaccion_ms`. Antes de esa orden se acepta cualquier
   acción no prohibida, y desde ella todas tienen que estar permitidas.
4. **`mantener_accion_cuadros`** y **`condiciones`**, si las hay.

Las órdenes que no caen en ningún tramo no se juzgan, salvo para `stop_con_evento` y
`es_el_ultimo_comando`. Por ejemplo, el STOP con `event=shutdown` al final de C1 no cuenta contra
"nunca STOP". El caso pasa si pasan todos sus tramos y cada evento de `stop_con_evento` dejó su
STOP.

## Cómo se corren los casos (T17)

```bash
uv run python casos/runner.py            # los diez casos
uv run python casos/runner.py C8 C10     # solo esos
```

Para cada caso, `casos/runner.py` revisa la carpeta, corre la entrada con `python -m control` (la
misma `main`, en el mismo proceso) y juzga lo que quedó en `resultados/casos/Cn/` con las reglas de
la sección anterior. Imprime la tabla PASA/FALLA y, debajo, el motivo de cada falla. La tabla queda
también en `resultados/casos/resumen.txt`, y el detalle de cada tramo, en
`resultados/casos/Cn/veredicto.json`. Sale con `0` si todos pasan, `1` si alguno falla y `2` si
no se puede leer `config/control/politica.yaml` o el esquema. En los motivos, "orden N" es la
línea N de `comandos.jsonl`.

Además de `expectativa.yaml`, cada carpeta trae:

| Archivo | Qué es |
|---|---|
| `entrada.jsonl` | Los eventos de percepción, uno por línea, que cumplen el contrato (`python -m contrato` sale con 0). C1 a C5 y C7 usan secuencias reales de A (`datos/MAPA_CASOS.md`, P5-12). C8 a C10 pueden usar eventos armados. |
| `tramos.yaml` | `entrada: real` o `entrada: armada`, y en `tramos` los `frame_id` de cada tramo con `origen: cuadros`. Los tramos de eventos sin cuadro no se listan. |
| `acciones.yaml` | Opcional. Eventos sin cuadro en instantes fijos del reloj de la entrada (`t_ms`, en ms): `tick`, `emergencia`, `rearmar` y `cerrar`. Se pasa a `python -m control --acciones`. |

```yaml
# tramos.yaml
entrada: armada
tramos:
  antes_del_hueco: [X01_f0001, X01_f0002, X01_f0003]
  cuadro_viejo: [X01_f0004, X01_f0005]
```

```yaml
# acciones.yaml
acciones:
  - {t_ms: 300, accion: emergencia}
  - {t_ms: 700, accion: rearmar}
  - {t_ms: 1800, accion: cerrar}
```

Una acción va después de los cuadros que llegan antes o en su mismo instante, y los tics de reloj
corren hasta ella. `tick` sirve para dejar correr el reloj después del último cuadro. Si
`acciones.yaml` no cierra el run, `python -m control` lo cierra con el último cuadro, como siempre.
Cada acción hecha queda en `run.json` (`acciones.hechas`) con su instante y la línea de
`comandos.jsonl` que dejó. De ahí sale el instante de `plazo_desde: evento`.

Un caso falla, aunque sus órdenes estén bien, si le falta `entrada.jsonl` o `tramos.yaml`, si su
entrada no cumple el contrato, si `tramos.yaml` no lista exactamente los tramos de cuadros de la
expectativa, o si es C1 a C5 o C7 y su entrada no es `real`. También falla si `python -m control`
no sale con `0`.

`tests/test_runner.py` prueba que el runner falla cuando se cambia una expectativa en una copia
temporal de `casos/`, y cada regla de la sección anterior con órdenes escritas a mano.
