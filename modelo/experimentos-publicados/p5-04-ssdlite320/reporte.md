# P5-04 · Resultado exploratorio de SSDLite320

Se completaron **29 inferencias** sobre las mismas fotos ESP32-CAM de 640 × 480
usadas por YOLO11n. Hubo **72 cajas** con confianza ≥0.25; ninguna foto quedó
sin caja. Todas las confianzas son finitas y están en `[0,1]`. Todas las cajas
`xyxy` son finitas, están dentro de 640 × 480 y cumplen `x1<x2`, `y1<y2`.
Las clases se obtuvieron del catálogo COCO_V1 de Torchvision (por ejemplo,
`backpack=27`, `handbag=31`, `suitcase=33`, `bottle=44`, `cup=47`, `chair=62`).

## Revisión visual

| Grupo | Fotos | Clase de interés asociada visualmente | Hallazgos |
|---|---:|---:|---|
| Botella | 4 | `bottle` en 3 | Lejana omitida; cercana y derecha duplican `vase` sobre la botella. |
| Mochila | 7 | `backpack` en 5 | Centro cerca y derecha salen `suitcase`; algunas vistas mezclan `handbag` o `suitcase` con `backpack`. Un adorno de peluche recibe `dog`/`teddy bear`. |
| Taza | 4 | `cup` en 3 | Lejana omitida; el piso recibe `dining table` en las cuatro. |
| Silla | 6 | `chair` en 3 | La base cercana sale `airplane`; lateral sale `person` y `skateboard`. La derecha no sale como `chair` y se omite la botella real del borde. |
| Estuche blando | 4 | `suitcase` en 2; `handbag` en 0 | Centro lejos e izquierda se asocian al estuche; centro cerca y derecha son `chair`/`couch`. |
| Paso despejado | 2 | No aplica | Siete cajas sobre piso, puertas y muebles del fondo; no son obstáculos del dominio en la vía. |
| Varios objetos | 2 | Ninguna de `backpack`/`bottle`/`cup` | `suitcase` sobre mochila y, en `varios_1`, sobre la botella; taza omitida. |

Los conteos son juicios visuales de esta muestra, no recall ni precisión formal.
Se revisó la localización de cada clase sobre los objetos visibles; el prefijo
del archivo no se trató como verdad de referencia. Los casos completos están en
`evidencia/revision_por_imagen.csv`, y todas las cajas con confianza exacta en
`evidencia/detecciones.csv`. `varios_2` contiene una taza parcialmente cortada.

## Latencia local en CPU

MacBook Air Apple M3, 8 núcleos, 16 GB, PyTorch con un hilo, batch 1.
Carga de arquitectura y pesos: **145.80 ms**. Primera foto: **51.43 ms** dentro
de `model([tensor])` y **59.04 ms** total. En las otras 28:

| Medición | Mínimo | Mediana | p95 lineal | Máximo |
|---|---:|---:|---:|---:|
| Lectura, RGB, tensor (ms) | 0.78 | 0.84 | 0.92 | 0.93 |
| `model([tensor])` (ms) | 32.53 | 35.24 | 37.83 | 38.03 |
| Filtro y extracción (ms) | 0.26 | 0.26 | 0.28 | 0.38 |
| Total por foto (ms) | 33.62 | 36.40 | 38.93 | 39.13 |

El tiempo del modelo incluye resize interno a 320 × 320, red, NMS interno
IoU 0.55 y remapeo de cajas. No es equivalente al tiempo `inference_ms` de
Ultralytics. El total de YOLO11n en la corrida previa tuvo mediana 25.14 ms y
p95 26.00 ms en las otras 28 fotos; su NMS usó IoU 0.7 y entrada `imgsz=640`.
La comparación de tiempos es preliminar porque los runtimes y el trabajo
incluido en cada medición difieren. No es el benchmark de P5-15.

## Comparación preliminar y límites

SSDLite asoció `backpack` a 5 de 7 fotos individuales frente a 3 de 7 de
YOLO11n. Ambos asociaron `bottle` a 3 de 4, `cup` a 3 de 4, `chair` a 3 de 6 y
`suitcase` al estuche en 2 de 4. Los aciertos no son siempre las mismas fotos:
SSDLite reconoce `mochila_lado_2` y `maleta_izq`, mientras YOLO11n reconoce
`maleta_centro_cerca` y `silla_der`. SSDLite generó 72 cajas frente a 35 de
YOLO11n y añadió varias clases erróneas sobre piso, puertas y objetos del fondo;
las dos fotos de paso despejado tuvieron cero cajas con YOLO11n y siete con
SSDLite. No se ajustaron umbrales ni se entrenaron pesos.

La licencia del código Torchvision es BSD-3-Clause. La licencia o condiciones
independientes de los pesos COCO_V1 siguen pendientes de verificación; no se
debe inferir que son BSD-3-Clause. La exportación a ONNX tampoco fue probada.
Antes de elegir detector faltan la prueba de YOLOX-Nano, una revisión de las
condiciones de los pesos y la decisión conjunta de las PM sobre objetos.
