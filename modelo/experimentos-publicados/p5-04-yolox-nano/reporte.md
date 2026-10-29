# P5-04 · YOLOX-Nano en las 29 fotos ESP32-CAM

Se completaron **29 inferencias** sobre las mismas fotos originales de 640 ×
480 que en YOLO11n y SSDLite320. El checkpoint ONNX coincidió con SHA-256
`c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d`
y los 29 hashes coincidieron con el manifiesto de YOLO11n. Se utilizó únicamente
`CPUExecutionProvider`, con un hilo y batch 1. Hubo **48 detecciones** con
confianza ≥0.25; dos fotos no tuvieron detecciones. Todas las confianzas son
finitas y están en `[0,1]`; todas las coordenadas son finitas y cumplen
`x1<x2`, `y1<y2`. **Tres cajas tienen `y1<0`** y, por tanto, incumplen el límite
de la imagen. No se recortaron ni corrigieron. El script devolvió código 1 al
final como señal de esta validación, después de registrar las 29 fotos.

## Revisión visual por grupo

| Grupo | Fotos | Clase de interés sobre el objeto, con geometría válida | Observaciones |
|---|---:|---:|---|
| Botella | 4 | `bottle` en 3 | La lejana se omite. En derecha, `parking meter` y `bottle` coinciden sobre la botella; `chair` aparece sobre un bote en la foto lejana. |
| Mochila | 7 | `backpack` en 2 | `mochila_cerca` suma un `backpack` visual sobre la mochila, pero su caja tiene `y1=-0.98` y se excluye del conteo válido. Se confunde repetidamente con `suitcase`; las laterales aparecen como `person`. |
| Taza | 4 | `cup` en 1 | Solo la cercana se reconoce. Las otras omiten `cup` y detectan `chair` sobre un bote del fondo. |
| Silla | 6 | `chair` en 1 | La silla lejana se reconoce y hay una caja adicional sobre el bote. En otras vistas aparecen `airplane`, `tv`, `traffic light` o `skateboard` sobre la silla. La clase `chair` de `silla_centro_der` y `silla_lado` cae en el bote, no en la silla. |
| Estuche blando | 4 | `suitcase` en 1; `handbag` en 0 | Solo el estuche central cercano aparece como `suitcase`. A la derecha e izquierda se confunde con `chair`/`couch`; el lejano se omite. |
| Paso despejado | 2 | No aplica | `vacio_1` tiene `refrigerator` sobre puerta o mueble del fondo; `vacio_2` no tiene cajas. No se observa caja sobre el piso despejado. |
| Varios objetos | 2 | Parcial | En ambas se reconoce la mochila; en `varios_1` también la botella. `suitcase` se superpone a la mochila, `fire hydrant` recae sobre la botella de `varios_2` y las tazas se omiten; una está cortada. |

El conteo se hizo mirando la ubicación de cada caja en las fotos, sin dar por
buena la clase por coincidir con el nombre de archivo. No es recall ni precisión
formal: no existe una anotación de referencia completa. Las clases se mapearon
con índices COCO de YOLOX (`backpack=24`, `handbag=26`, `suitcase=28`,
`bottle=39`, `cup=41`, `chair=56`). El detalle por foto está en
`evidencia/revision_por_imagen.csv`, y las coordenadas y confianzas exactas en
`evidencia/detecciones.csv`.

Las cajas fuera de límites fueron: `mochila_cerca.jpg` `suitcase` con
`y1=-4.39`, la misma foto `backpack` con `y1=-0.98`, y `mochila_lado_2.jpg`
`person` con `y1=-0.04` píxeles. Su localización visual es comprensible, pero
la geometría no cumple la validación exigida. Un consumidor posterior tendría
que definir explícitamente cómo tratar esas cajas; este experimento las conserva.

## Latencia local

MacBook Air Apple M3, 8 núcleos, 16 GB, macOS arm64. Carga del modelo:
**44.04 ms**. Primera foto: 7.00 ms de lectura y preprocesamiento, 23.78 ms
de `session.run`, 0.94 ms de decodificación/filtro/NMS y **31.85 ms** total.
En las siguientes 28 fotos:

| Etapa, ms | Mínimo | Mediana | p95 lineal | Máximo |
|---|---:|---:|---:|---:|
| JPEG, letterbox, CHW | 0.81 | 0.89 | 1.10 | 1.12 |
| `session.run` | 19.29 | 19.76 | 21.09 | 21.37 |
| Decodificación, filtro, NMS | 0.65 | 0.76 | 0.87 | 1.50 |
| Total por foto | 20.87 | **21.56** | **23.17** | 23.26 |

El total incluye lectura JPEG, preprocesamiento, llamada ONNX Runtime y
posprocesamiento. Los tiempos son exploratorios de una sola corrida, sin los
calentamientos y repeticiones del benchmark P5-15.

## Comparación preliminar de los tres detectores

Asociaciones visuales en fotos individuales, con cajas geométricamente válidas:

| Grupo | YOLO11n | SSDLite320 | YOLOX-Nano |
|---|---:|---:|---:|
| Botella | 3/4 | 3/4 | 3/4 |
| Mochila | 3/7 | 5/7 | 2/7; una adicional con caja inválida |
| Taza | 3/4 | 3/4 | 1/4 |
| Silla | 3/6 | 3/6 | 1/6 |
| Estuche blando como `suitcase` | 2/4 | 2/4 | 1/4 |
| Estuche blando como `handbag` | 0/4 | 0/4 | 0/4 |

| Aspecto | YOLO11n | SSDLite320 | YOLOX-Nano |
|---|---|---|---|
| Escenas despejadas | Cero cajas en ambas | Siete cajas en ambas, principalmente piso/fondo | Una caja `refrigerator` en el fondo de una; ninguna en la otra |
| Varios objetos | Parcial: botella en una; mochila en otra | Ninguna asociación visual de `backpack`/`bottle`/`cup`; confusiones `suitcase` | Mochila en ambas y botella en una; confusiones `suitcase`/`fire hydrant`; taza omitida |
| Confusiones principales | `suitcase` sobre mochila; `couch`/`chair` sobre estuche | `suitcase`/`handbag` sobre mochila; `chair`/`couch` sobre estuche; cajas en piso/fondo | `suitcase` sobre mochila; `chair` sobre bote; `airplane`/`tv`/`traffic light` sobre silla |
| Mediana total de 28 fotos, ms | 25.14 | 36.40 | 21.56 |
| p95 total de 28 fotos, ms | 26.00 | 38.93 | 23.17 |
| Checkpoint, bytes | 5 613 764 | 14 069 355 | 3 659 407 |
| Licencias | Ultralytics declara AGPL-3.0 para código/modelos | Código BSD-3-Clause; condiciones de pesos por verificar | Código Apache-2.0; condiciones de pesos por verificar |

Los tres usan umbral de reporte 0.25, pero sus probabilidades no están
calibradas entre sí. YOLO11n usa Ultralytics con entrada 640 e IoU 0.7;
SSDLite320 usa PyTorch/Torchvision con resize interno 320 × 320 y NMS propio
IoU 0.55; YOLOX-Nano usa ONNX Runtime con entrada 416 y NMS NumPy por clase
IoU 0.45. Los tiempos totales ayudan a comparar esta ejecución local, pero
no garantizan el mismo desempeño en la computadora de evaluación ni son el
benchmark oficial.

## Límites y siguientes pasos

La procedencia ESP32-CAM de las fotos fue confirmada por el usuario; el CSV de
capturas no es anotación de verdad de referencia. Los objetos lejanos, sillas
desde cámara baja y estuche blando siguen siendo difíciles. La discrepancia
histórica del preprocesamiento ONNX se documenta en `README.md`; la ruta sin
normalización quedó fijada antes de esta corrida. Las condiciones independientes
de los pesos de YOLOX-Nano y SSDLite320 siguen pendientes de verificación.

Para cerrar P5-04 corresponde revisar conjuntamente las detecciones y las
tres cajas fuera de límites, aclarar licencias de pesos, confirmar escenario y
equipo de evaluación, y proponer tres o cuatro objetos para aprobación de
ambas PM. La decisión final del detector y `modelo/DECISION.md` deben esperar
esa revisión. No se cambió el contrato A → B v1 ni se implementó P5-05.
