# Anotaciones y métricas de detección

> **Formato v1, propuesto en P5-13** para que el script de métricas tenga qué leer. Lo confirma A2 en
> P5-10: si cambia, cambian este esquema, el ejemplo y `src/metricas/` en el mismo PR.

| Archivo | Qué es |
|---|---|
| [`anotaciones.v1.schema.json`](anotaciones.v1.schema.json) | Esquema de una línea (un cuadro). |
| [`ejemplos/anotaciones.jsonl`](ejemplos/anotaciones.jsonl) | La verdad de referencia de los cinco cuadros de `config/contrato/ejemplos/flujo.jsonl`. |

## Formato

Un JSONL con **una línea por cuadro del conjunto**, también los despejados:

```json
{"frame_id": "S02_f0003", "sequence_id": "S02", "image_width": 640, "image_height": 480,
 "objetos": [{"class_id": 1, "class_name": "mochila", "bbox": [195.0, 125.0, 450.0, 468.0]}]}
```

- `frame_id` y `sequence_id`: los mismos que emite el detector en el contrato.
- `image_width`, `image_height`: el cuadro original. Si no coinciden con las del evento, las métricas lo avisan:
  las cajas no estarían en el mismo sistema de coordenadas.
- `objetos[].bbox`: `[x1, y1, x2, y2]` en píxeles del cuadro original (D-04, igual que el contrato).
- `objetos[].class_id`: según `modelo/clases.json`. `class_name` es opcional.
- Un cuadro despejado lleva `"objetos": []` **a propósito**. Se pueden agregar campos (por ejemplo, el estado
  esperado para B); las métricas los ignoran.

## Métricas (`python -m metricas`)

```bash
uv run python -m metricas \
  --detecciones resultados/<run>/detecciones.jsonl \
  --anotaciones datos/anotaciones.jsonl \
  --salida resultados/metricas/ \
  --model-sha256 <hash de los pesos congelados> --config-sha256 <hash de la configuración congelada>
```

**Cómo cuenta**, por cuadro y por clase, a IoU ≥ 0.50: las predicciones se recorren de mayor a menor confianza
y cada una toma la caja real aún libre de su clase con mayor IoU. Cada caja real se usa una vez; un duplicado es
FP, un objeto sin pareja es FN y una clase equivocada deja 1 FP y 1 FN. `precisión = TP/(TP+FP)`,
`recall = TP/(TP+FN)`, `F1 = 2TP/(2TP+FP+FN)`; con denominador cero vale 0 y queda en `sin_soporte`.

**Nada se quita para mejorar el F1.** Se evalúan todos los cuadros anotados: uno sin evento, con `status=error`
o con `stale` sigue en el denominador (sus objetos son FN) y queda listado en `resumen.json`.

**Lo que escribe en `--salida`:**

| Archivo | Contenido |
|---|---|
| `por_cuadro.csv` | `frame_id`, `sequence_id`, `estado`, objetos reales y predichos, TP/FP/FN. Sumando sus columnas se recalcula el F1. |
| `detalle.csv` | Cada TP, FP y FN con su clase, confianza, IoU y cajas. |
| `resumen.json` | Micro (el que puntúa 1.4) y por clase con su soporte; criterio 1.4 (`floor(12 * F1) / 2`, con el tope de 3 si no se cumplen los mínimos de E3); procedencia; cobertura; SHA-256 de las entradas; advertencias. |

**Código de salida:** `0` todo en orden · `1` métricas calculadas pero con advertencias (hashes sin indicar o
distintos de los congelados, cuadros sin predicción válida, mínimos de E3, dimensiones distintas) · `2` una
entrada no se puede leer o no cumple su formato. La corrida que se entrega debe salir con `0`: predicciones
de los pesos y la configuración congelados, que cubren todos los cuadros de un conjunto que cumple E3.

El umbral de confianza y el NMS **no** se aplican aquí: vienen congelados en la configuración del detector
(D-06), y su hash es el `--config-sha256`.
