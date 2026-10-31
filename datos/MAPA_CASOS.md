# Mapa de casos (P5-12)

Qué cuadros y qué entradas usa cada caso de `casos/`, y qué se espera de la percepción. **Borrador:**
las secuencias todavía no están congeladas y **S6 depende de que el PM A acepte la toma nueva** (ver
#13). Los tramos salen de las cajas anotadas (`datos/anotaciones.jsonl`) y de las zonas de
`config/control/politica.yaml`, no del detector.

## C1 a C7: cuadros reales

| Caso | Secuencia | Cuadros | Qué se espera de la percepción |
|---|---|---|---|
| C1 · Vía libre | S1 | `S01_f0001`–`f0012` | Sin `bottle` ni `cup` |
| C1 · Vía libre, transitables | S8 | `S08_f0001`–`f0012` | Sin `bottle` ni `cup`; tapa, borrador y cable no cuentan |
| C2 · Obstáculo central | S2 | `S02_f0001`–`f0012` | `cup` en el centro; en 10 cuadros también toca la derecha |
| C3 · Obstáculo izquierdo | S3 | `S03_f0001`–`f0012` | `bottle` solo a la izquierda |
| C4 · Obstáculo derecho | S4 | `S04_f0001`–`f0012` | `bottle` solo a la derecha |
| C5 · Sin zona libre | S5 | `S05_f0001`–`f0012` | Dos `bottle` y una `cup` en las tres zonas |
| C6 · Confianza | S7 | Pendiente | Ver [C6](#c6-pendiente-hasta-congelar) |
| C7 · Libre → bloqueo → libre | S6 | Ver [C7](#c7-tramos-de-s6) | `cup` que entra y sale del centro |

S1–S8 son evaluación. S9 y S10 no entran en este mapa: son solo para las pruebas del grupo B.

### C7: tramos de S6

Los nombres son los de `casos/C7/expectativa.yaml`.

| Tramo | Cuadros | Centro |
|---|---|---|
| `libre` | `S06_f0001` | Libre: la taza está a la izquierda |
| `bloqueo` | `S06_f0002`–`f0005` | Ocupado |
| `un_cuadro_libre` | `S06_f0006` | Libre: la taza está a la izquierda |
| `bloqueo_otra_vez` | `S06_f0007`–`f0008` | Ocupado |
| `libre_otra_vez` | `S06_f0009`–`f0020` | Libre: sin taza |

### C6: pendiente hasta congelar

Falta decir qué cuadros de S7 quedan bajo y sobre el umbral de 0.50, y con qué score. Sale de correr el
detector **después de congelar** (D-06). S7 no se refilma por ese resultado: si no aparece un `cup` entre
0.25 y 0.50, se reporta así.

## C8 y C9: entradas fallidas

Las fixtures están en [`fixtures/`](fixtures/), con su SHA-256 en `SHA256SUMS`. Son sintéticas: no parten
de cuadros del conjunto, y en `datos/` no hay ningún JPEG truncado real del stream que conservar.

| Fixture | Qué es | `python -m captura` la rechaza como | `python -m infer` (#75, `bfe7644`) |
|---|---|---|---|
| `no_es_jpeg.jpg` | Texto con extensión `.jpg` | `jpeg_incompleto` | `status=error`, `unreadable_image` |
| `sin_imagen.jpg` | Encabezado JPEG sin datos de imagen | `jpeg_incompleto` | `status=error`, `unreadable_image` |
| `truncado.jpg` | JPEG cortado a la mitad de los datos | `jpeg_incompleto` | `status=error`, `unreadable_image` |
| `vacia.jpg` | Archivo de 0 bytes | `jpeg_incompleto` | **Falla: termina con código 2 y sin evento** |
| `otras_dimensiones.jpg` | JPEG válido de 320×240 | `tamano_320x240` | `status=ok`, 320×240 |

`otras_dimensiones.jpg` no es un error para `infer`: el contrato pide los píxeles del cuadro original. Lo
detectan `captura` y las métricas, que avisan si el tamaño no coincide con la anotación.

### `error.code` del contrato

| `error.code` | Cómo se produce | Estado |
|---|---|---|
| `unreadable_image` | Fixtures de arriba | Comprobado, salvo `vacia.jpg` |
| `detector_exception` | Se fuerza una excepción en el detector | Sin archivo de entrada; pendiente de la lista de A1 (P5-06) |
| `invalid_output` | Se fuerza una salida inválida del detector | Sin archivo de entrada; pendiente de la lista de A1 (P5-06) |
| `detector_timeout` | Se fuerza un tiempo agotado | `infer` todavía no lo aplica (P5-06) |

C8 no necesita archivos: el hueco sin cuadros y los cuadros viejos (`status=stale`, o `status=ok` con
`t_emit_ms − t_capture_ms` mayor que `max_frame_age_ms`) son eventos armados en `casos/C8/entrada.jsonl`.
C10 puede usar cualquier secuencia.

## Falta

- [ ] Congelar S1–S8 y confirmar S6 con el PM A.
- [ ] Llenar C6 con los scores del detector congelado.
- [ ] Lista de errores de A1 y corrección de `vacia.jpg` en `infer`.
- [ ] B3 confirma que el mapa le sirve para armar C1–C9.
