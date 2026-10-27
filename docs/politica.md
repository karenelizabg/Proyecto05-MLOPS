# Política del grupo B

Cómo decide el carrito, cuadro por cuadro, si **avanza, gira o frena**. El código está en
[`src/control/politica.py`](../src/control/politica.py) (`decidir`) y todos los números en
[`config/control/politica.yaml`](../config/control/politica.yaml). Nada de esto mueve motores:
el comando va al adaptador virtual, que solo lo registra.

## Resumen en una tabla

| Situación | Acción | Caso |
|---|---|---|
| `status` `stale` o `error`, versión desconocida o evento fuera de contrato | **STOP** | C8, C9 |
| Centro libre | **AVANZAR** recto | C1 |
| Obstáculo solo a la izquierda o solo a la derecha | **AVANZAR** recto | C3, C4 |
| Obstáculo al centro y un lado libre | **GIRAR** hacia el lado libre | C2 |
| Obstáculo al centro sin lado libre, o con el giro desactivado | **STOP** | C2, C5 |
| Obstáculo con confianza debajo del umbral | Se ignora y queda en `reason` | C6 |
| Después de un STOP por obstáculo | Sigue en STOP hasta ver N cuadros libres seguidos | C7 |

Cada comando explica en `reason` qué regla se aplicó y qué detecciones la activaron
(`class_id` y confianza).

## 1. Zonas

La imagen se divide en tres franjas verticales, como **fracción del ancho**:

| Zona | Desde | Hasta | En 640 px | En 320 px |
|---|---|---|---|---|
| `izq` | 0.00 | 0.33 | 0 – 211 px | 0 – 106 px |
| `centro` | 0.33 | 0.67 | 211 – 429 px | 106 – 214 px |
| `der` | 0.67 | 1.00 | 429 – 640 px | 214 – 320 px |

- Los píxeles se calculan con el `image_width` **de cada evento**. Nunca se fija un ancho a
  mano, así que funciona con cualquier resolución.
- Las cajas llegan en píxeles del cuadro original, con origen arriba a la izquierda. Se aceptan
  `xyxy` (`[x1, y1, x2, y2]`) y `xywh` (`[x, y, ancho, alto]`); todo se convierte a `xyxy`.
- **Una caja ocupa una zona** si al menos `traslape_minimo` (15 %) de **su ancho** cae dentro de
  esa zona. Una caja que apenas roza la orilla de otra zona no la ocupa, y una caja ancha puede
  ocupar dos o tres zonas.
- Solo se mira el eje horizontal: la altura de la caja no cambia la zona.

## 2. Qué cuenta como obstáculo

Una detección cuenta solo si cumple **las dos** condiciones:

1. Su `class_id` está en `clases_obstaculo`. Se decide con `class_id`, **nunca** con
   `class_name`, que es solo para leer.
2. Su `confidence` es mayor o igual que `umbral_confianza`.

**Objetos que el carrito puede pasar por encima** (más bajos que la llanta: borrador, cable,
tapa) **no son obstáculos**. No van en `clases_obstaculo`, para que no provoquen STOP; si no,
el carrito "siempre se detendría". La regla con las medidas reales es de P5-03 (`datos/DOMINIO.md`).

> **Clases provisionales.** Hoy `clases_obstaculo: [0, 1]` (lata y mochila de los ejemplos del
> contrato) y `clases_provisionales: true`. Las clases reales salen de `modelo/clases.json`,
> que publica el grupo A en P5-04 (decisión DC-5 del contrato). Cuando exista, se ponen aquí
> sus `class_id` de obstáculo y `clases_provisionales` pasa a `false`. La lista debe ser un
> subconjunto de las clases de ese archivo.

## 3. Umbral de confianza (C6)

- `umbral_confianza: 0.5`, inclusivo: 0.5 cuenta y 0.49 no.
- Una detección de una clase de obstáculo con menos confianza **no cuenta** para decidir, pero
  queda en `reason` como `ignorada_por_confianza`, con su `class_id` y su confianza.
- **Poca confianza no es lo mismo que una falla de percepción.** Con poca confianza el cuadro
  llegó bien (`status=ok`) y el detector solo duda de un objeto: se decide normal. Una falla de
  percepción (`stale` o `error`) significa que no hay cuadro confiable, y siempre es STOP.

## 4. Cuándo gira y cuándo frena

- **Centro libre → AVANZAR** recto con `velocidad_avance` (0.4) y `steering 0`, aunque haya
  algo a un lado: un obstáculo lateral no está en el camino.
- **Centro ocupado:**
  - con `permitir_giro: true` y un lado libre → **GIRAR** hacia ese lado. `GIRAR_IZQ` lleva
    `steering = -giro` y `GIRAR_DER` lleva `steering = +giro` (giro 0.5). La velocidad es la de
    avance.
  - **nunca gira hacia una zona ocupada.**
  - si los dos lados están libres, gira al lado **contrario** de donde está el obstáculo: si
    el obstáculo está cargado a la izquierda del centro, gira a la derecha. Si queda justo a la
    mitad, gira a la izquierda.
  - sin ningún lado libre, o con `permitir_giro: false` → **STOP**.
- **STOP siempre lleva `speed = 0` y `steering = 0`.**

## 5. Histéresis (C7)

Sirve para no arrancar y frenar a cada cuadro cuando la detección parpadea.

1. Un **STOP por obstáculo** empieza la espera.
2. Mientras espera, la política sigue en **STOP**, aunque haya un lado libre para girar, con
   `reason` `esperando_cuadros_libres k/N`.
3. Cada cuadro con el centro libre suma 1. Un cuadro con el centro ocupado regresa la cuenta
   a 0: **un solo cuadro libre en medio de un bloqueo no reanuda.**
4. Al llegar a `cuadros_libres_para_reanudar` (N = 3) cuadros libres seguidos → **AVANZAR**,
   con `reason` "Reanuda tras 3/3 cuadros libres seguidos".

Ejemplo con N = 3 (L = libre, B = obstáculo al centro sin lado libre):

```
cuadro:  L  L  B     B     L     B     L     L     L
acción:  ▶  ▶  ■     ■     ■ 1/3 ■ 0/3 ■ 1/3 ■ 2/3 ▶ reanuda
```

Un GIRAR no es un STOP, así que no activa la espera. La histéresis empieza después de un STOP
por obstáculo: al arrancar el run se avanza con el primer cuadro libre.

## 6. Pérdida de percepción: `stale` y `error`

`stale`, `error`, una `schema_version` desconocida o un evento que no cumple el contrato son
**siempre STOP**. Nunca equivalen a vía libre (CONTRATO.md, reglas 2 y 4). La ausencia de
cuadros la cubre el watchdog del supervisor (T05).

El **supervisor** (`src/control/supervisor.py`, T03/T04) revisa estos casos **antes** de llamar
a la política, frena por su cuenta y registra la falla en `errores.jsonl`. La política repite
los mismos chequeos por seguridad, por si alguien la llama sin supervisor.

> **Punto abierto (supervisor y histéresis).** Cuando el supervisor hace su propio STOP,
> regresa el estado a `{"nombre": "DETENIDO"}` y se pierden los datos de la histéresis. Por
> eso, tras un bloqueo seguido de un `stale` o `error`, **un solo cuadro libre reanuda** en lugar
> de esperar N. Se puede corregir de dos maneras: que el supervisor conserve las claves de la
> política y solo cambie `nombre`, o que la política pida N cuadros libres siempre que salga de
> `DETENIDO`. Pendiente de decidir con la PM.

## 7. Estado entre cuadros

El estado es un diccionario con la clave `"nombre"` (acuerdo del grupo B):

| Acción | `nombre` después |
|---|---|
| STOP | `DETENIDO` |
| AVANZAR | `AVANZANDO` |
| GIRAR_IZQ | `GIRANDO_IZQ` |
| GIRAR_DER | `GIRANDO_DER` |

- Empieza en `{"nombre": "DETENIDO"}`. El supervisor guarda el diccionario completo y usa
  `estado["nombre"]` para `state_before` y `state_after`.
- La política guarda además `esperando_libres` (true o false) y `libres_seguidos` (la cuenta
  de la histéresis). Conserva cualquier otra clave y nunca modifica el estado que recibe.
- `decidir` es una función pura: no lee el reloj. `t_decision_ms` es el `t_capture_ms` del
  evento.

## 8. Parámetros

Todos están en `config/control/politica.yaml`. `cargar_config_politica()` revisa sus rangos al
cargar y, si algo no cumple, falla con un mensaje que dice qué valor corregir.

| Parámetro | Valor | Rango | Para qué |
|---|---|---|---|
| `zonas` | 0–0.33 / 0.33–0.67 / 0.67–1 | contiguas, de 0 a 1 | Franjas izquierda, centro y derecha. |
| `traslape_minimo` | 0.15 | 0 < x ≤ 1 | Fracción de la caja que debe caer en una zona para ocuparla. |
| `clases_obstaculo` | `[0, 1]` (provisional) | `class_id` ≥ 0, sin repetir | Qué clases son obstáculo. |
| `clases_provisionales` | `true` | true/false | Marca que las clases aún no son las definitivas. |
| `umbral_confianza` | 0.5 | 0 ≤ x ≤ 1 | Confianza mínima para que una detección cuente. |
| `cuadros_libres_para_reanudar` | 3 | entero ≥ 1 | N de la histéresis. |
| `velocidad_avance` | 0.4 | 0 < x ≤ 1 | Velocidad de AVANZAR y de los giros. |
| `giro` | 0.5 | 0 < x ≤ 1 (0 solo sin giro) | Magnitud del `steering` al girar. |
| `permitir_giro` | `true` | true/false | Con `false`, un obstáculo al centro siempre es STOP. |

Los plazos (`max_frame_age_ms`, `watchdog_ms`, etc.) no son de la política: están en
`config/control/plazos.yaml` (T01).

## Cómo se prueba

```bash
uv run pytest -q tests/test_config_politica.py tests/test_zonas.py \
  tests/test_decision.py tests/test_umbral.py tests/test_histeresis.py
```

| Archivo | Qué cubre |
|---|---|
| `test_config_politica.py` | Carga del YAML y rangos (T07). |
| `test_zonas.py` | Zonas con distintos anchos, `xyxy`/`xywh` y filtros de clase y confianza (T08). |
| `test_decision.py` | C1–C5, stale/error y forma del comando (T09). |
| `test_umbral.py` | C6, y que poca confianza no es falla de percepción (T10). |
| `test_histeresis.py` | C7 con la secuencia libre → bloqueo → libre (T11). |
