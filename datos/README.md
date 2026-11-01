# datos/

Secuencias etiquetadas (entregable **E3**): cuadros extraídos como imágenes, anotaciones y
manifiesto.

## Qué hay aquí

| Ruta | Qué es | Ticket |
|---|---|---|
| `cuadros/S01/` a `cuadros/S08/` | Conjunto de evaluación: un JPEG por cuadro y `captura.jsonl` | P5-09 |
| `anotaciones.jsonl` | Cajas por cuadro, formato en [`config/anotaciones/`](../config/anotaciones/README.md) | P5-10 |
| `manifiesto.jsonl` | Una fila por cuadro, con SHA-256, estado esperado y zonas | P5-11 |
| `pruebas-b/` | S9 y S10 con sus anotaciones: solo para las pruebas de B, **fuera de la evaluación** | P5-03 |
| [`DOMINIO.md`](DOMINIO.md) | Escena, clases, regla obstáculo / transitable y lo que no se cubre | P5-03 |
| [`CARRO.md`](CARRO.md) | Medidas del carro armado y configuración de la cámara | P5-19 |
| `MAPA_CASOS.md` y `fixtures/` | Caso → secuencia → cuadros, y entradas fallidas de C8 y C9 (llegan con #77) | P5-12 |

Los videos crudos **no** se suben (`.gitignore`): la guía pide imágenes extraídas, y el video no las
sustituye. Tampoco se suben las tomas descartadas de `_fallidas/` ni las fotos de selección de
P5-04.

## Procedencia

- **Cámara:** ESP32-CAM del carro (OV2640, lente fijo), a 10 cm del piso y mirando al frente.
- **Formato:** 640×480, JPEG con calidad 10 del sensor. La configuración es la misma en todas las
  secuencias ([`CARRO.md`](CARRO.md)).
- **Captura:** `python -m captura` guarda los bytes JPEG del stream tal como llegan, sin
  recomprimir, con la hora real de recepción en `t_capture_ms`.
- **Quién y cuándo:** A2 (Andy), sin ayuda, el 2026-10-30; S6 se volvió a filmar el 2026-10-31 (ver
  #13).
- **Lugar:** S1 a S7 en un mismo espacio de una casa, con luz de día; S8 en otro cuarto de esa casa,
  con otro fondo y otra luz.

## Cómo se filmó

El carro se empuja a mano, sin motores: el control del proyecto es virtual y el firmware no tiene
paro automático. La cámara se alimenta por USB-C. El plan completo está en
[`DOMINIO.md`](DOMINIO.md).

| Secuencia | Escena | Caso | Cuadros | Huecos entre cuadros |
|---|---|---|---:|---|
| S1 | Vía libre | C1 | 12 | 203–359 ms |
| S2 | Taza al centro | C2 | 12 | 203–328 ms |
| S3 | Botella a la izquierda | C3 | 12 | 203–281 ms |
| S4 | Botella a la derecha | C4 | 12 | 203–313 ms |
| S5 | Botella, taza y botella en las tres zonas | C5 | 12 | 203–390 ms |
| S6 | La taza entra y sale del centro | C7 | 20 | 250–344 ms |
| S7 | Taza acercándose, cerca del umbral de confianza | C6 | 15 | 218–266 ms |
| S8 | Otro cuarto, con transitables | C1 | 12 | 203–281 ms |

Todos los huecos deben ser menores que `validez_orden_ms` (400 ms): una toma que no cumple se aparta
a `_fallidas/`. Ninguna excepción de hueco se ha aprobado.

**Diferencias con el plan:**

- **S6 lleva 20 cuadros y `--cada-ms 250`**, no unos 15 cada 200 ms, y en ella se ve la mano que
  mueve la taza. Los motivos están en #13.
- **S7 lleva 15 cuadros**, no de 10 a 12.

**Desde el 2026-10-31, ninguna toma nueva se filma sin el OK escrito del PM A en #13.**

## Criterio de anotación

Se anotó sin el detector. Cada línea de `anotaciones.jsonl` es un cuadro, con cajas `xyxy` en píxeles
del cuadro original. A2 dibujó las cajas a mano, salvo las 53 ajustadas que se explican abajo.

- **Qué se anota:** toda botella (`class_id` 39) o taza (41) visible, también las laterales, lejanas
  y parciales. No hay tamaño mínimo.
- **La caja:** ajustada a lo visible del objeto, con el asa y sin la mano. Si el objeto sale
  cortado, llega hasta el borde. Si está borroso por el movimiento, cubre todo el borrón.
- **Qué no se anota:** cualquier otra clase (el bote, los muebles, la mano) y los transitables.
- **Transitables:** menos de 2 cm de alto, como el borrador (0.9 cm), la tapa (1.2 cm) y el cable de
  S8. Se comprobó que el carro pasa por encima de estos dos sin atorarse, andando con sus motores
  solo para esa prueba (2026-10-31).
- **Cuadro despejado:** lleva `objetos: []` a propósito.
- **Estado esperado y zonas:** `conjunto manifiesto` los calcula a partir de las cajas, con las
  zonas y el `traslape_minimo` de `config/control/politica.yaml`. El estado es `obstaculo` si hay
  alguna caja, aunque el centro quede libre.

**Revisión visual:** `python -m conjunto hojas --salida <carpeta nueva>` dibuja las cajas sobre los
cuadros, una hoja por secuencia a resolución completa, y avisa si una caja se repite entre cuadros.

**Revisión cruzada:** Ale (A3) revisó los 107 cuadros el 2026-10-31, 47 de ellos con zoom (S5, S6 y
S7), en hojas a la mitad de resolución. No encontró cajas mal puestas ni objetos sin anotar, pero a esa
escala no se veía que algunas cajas eran copias.

**Cajas ajustadas antes de congelar:** en la revisión de #79, Ale vio que las 8 cajas de la taza en S6
tenían el mismo tamaño en todos los cuadros (134.4 × 94.4 px), y Andy, con Claude Code, encontró 45 más
en S4, S5 y S7 que se repetían de un cuadro a otro aunque la imagen se moviera. Claude Code midió esas 53
a ojo, sobre recortes ampliados y sin detector. Ale las revisó a resolución completa sobre `69f92c3`,
comparándolas con las anteriores y, en las tazas, con la segmentación del color. Los bordes quedan a
0–3 px, salvo el izquierdo de S7, que queda a 3–6 px por el lado en sombra y el borroso, como pide el
criterio. Las zonas ocupadas no cambiaron en ningún cuadro.

## Sin ajuste (D-06)

**No hubo partición de ajuste.** El detector es preentrenado y no se reentrenó. Su umbral y su NMS
vienen de P5-04, y las fotos de esa selección no forman parte de `datos/`. Todas las secuencias de
`cuadros/` son de evaluación (`split: evaluacion`), y las métricas se reportan sobre todas.

**Una excepción declarada:** el 2026-10-30 se corrió el detector, antes de congelar, sobre S1, una
toma fallida de S1 y la primera toma de S2, que luego se repitió. El registro completo está en #13.
S2 se repitió por movimiento brusco, pero esa decisión se tomó después de ver las confianzas. S3 a
S8 no pasaron por el detector antes de congelar.

## Verificar

```bash
git checkout datos-evaluacion-v1
python -m conjunto verificar --sha256 8a75e2718083411c4db5d3adf4cb247b302014510855dfe93e227e96273334ff
sha256sum datos/anotaciones.jsonl
```

`verificar` revisa los mínimos de E3, hashes, huecos y anotaciones, y termina con `OK con N
excepciones` si todo cumple. Las reglas están en `src/conjunto/verificacion.py`. Solo comprueba el hash
del manifiesto, que no guarda las coordenadas de las cajas: el de anotaciones se compara aparte, contra la
tabla de abajo.

## Conjunto congelado

| Dato | Valor |
|---|---|
| Etiqueta de Git | `datos-evaluacion-v1` (commit `9b8dc08`) |
| SHA-256 de `manifiesto.jsonl` | `8a75e2718083411c4db5d3adf4cb247b302014510855dfe93e227e96273334ff` |
| SHA-256 de `anotaciones.jsonl` | `7e842784a9240e0e4244252117de010fc9037287eaf7e7045bf716e8c4f4a051` |
| Cuadros / secuencias | 107 / 8 |
| Con obstáculo / despejados | 71 / 36 |

Este es el paso 1 del congelamiento (#13). El paso 2, la configuración del detector, se registra al
fusionarse #75. **Hasta entonces, nadie corre el detector sobre S1–S8.**
