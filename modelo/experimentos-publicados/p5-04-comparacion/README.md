# P5-04 · Comparación consolidada para revisión

**Estado:** análisis derivado y recomendación preliminar; no hay detector ni
objetos aprobados. Este directorio no reemplaza ni modifica los tres
experimentos originales. Se utilizaron las mismas 29 fotos JPEG de 640 × 480
de la ESP32-CAM real, identificadas por el mismo nombre y SHA-256 en los tres
manifiestos. El digest de la lista ordenada `nombre+SHA-256` es
`f8e531e76ac5ae66bb776c0d561a910b53f4de64bffe341164b4248c5cd93c7f`.
Las fotos de selección no son las ocho secuencias de evaluación final.

Reproducir la consolidación desde la raíz del repositorio, sin inferir de
nuevo ni tocar la evidencia original:

```sh
python3 modelo/experimentos-publicados/p5-04-comparacion/consolidar.py
```

El script exige 29 filas por manifiesto, resultado y revisión visual; compara
los hashes entre los tres modelos y comprueba que el número de detecciones por
foto coincide con el CSV de cajas. Genera `resumen_tecnico.json`,
`asociaciones_por_objeto.csv` y `cajas_yolox_analisis.csv`. Los conteos de
asociación proceden de la revisión visual ya registrada; no se calculan solo
con el prefijo del nombre o con una clase predicha.

## Configuración y procedencia comprobadas

| Detector | Versión y checkpoint | SHA-256 | Tamaño | Entrada y runtime | Filtro y NMS | Licencias |
|---|---|---|---:|---|---|---|
| YOLO11n | Ultralytics 8.3.0; [`yolo11n.pt` v8.3.0](https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt) | `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1` | 5 613 764 B | `imgsz=640`; PyTorch/Ultralytics CPU, un hilo | conf ≥0.25; NMS IoU 0.7 | Ultralytics declara AGPL-3.0 para código y modelos; requiere revisión de obligaciones antes de adopción. |
| SSDLite320 MobileNetV3-Large | torchvision 0.24.0, `COCO_V1`; [checkpoint oficial](https://download.pytorch.org/models/ssdlite320_mobilenet_v3_large_coco-a79551df.pth) | `a79551df90c79834bcd3bb3845ef9d966b5449a3a9b2833ae8404778ca5d65d2` | 14 069 355 B | resize interno 320 × 320; PyTorch/Torchvision CPU, un hilo | reporte ≥0.25; score interno 0.001, NMS interno IoU 0.55 | Código BSD-3-Clause; condiciones independientes de pesos COCO_V1 pendientes de verificar. |
| YOLOX-Nano | release 0.1.1rc0, commit `e1052df`; [`yolox_nano.onnx`](https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx) | `c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d` | 3 659 407 B | 416 × 416; ONNX Runtime 1.31.1, `CPUExecutionProvider`, un hilo | objeto × clase ≥0.25; NMS NumPy por clase IoU 0.45 | Código Apache-2.0; condiciones independientes de pesos pendientes de verificar. |

Todos usaron batch 1, Python 3.12.14, CPU de la MacBook Air M3, sin MPS,
entrenamiento ni ajuste de pesos. Las diferencias de preprocesamiento, NMS y
calibración de confianza impiden tratar los tres umbrales de 0.25 como
equivalentes. El método YOLOX no normaliza la imagen; su discrepancia histórica
con el ejemplo ONNX de la release se justifica en su README experimental.

## Reconocimiento visual exploratorio

Asociaciones de la clase de interés a una caja **sobre el objeto visible** en
fotos individuales, con geometría válida. Son juicios visuales registrados en
las revisiones, no precisión, recall ni verdad de referencia formal.

| Objeto | YOLO11n | SSDLite320 | YOLOX-Nano | Omisiones y confusiones relevantes |
|---|---:|---:|---:|---|
| Botella | 3/4 | 3/4 | 3/4 | La lejana se omite en los tres. YOLOX añade `parking meter` sobre una botella. |
| Mochila | 3/7 | 5/7 | 2/7* | YOLO11n y YOLOX confunden varias con `suitcase`; YOLOX llama `person` a vistas laterales. SSDLite reconoce más vistas, pero también mezcla clases. |
| Taza | 3/4 | 3/4 | 1/4 | La lejana se omite en los tres; YOLOX solo reconoce la cercana. |
| Silla | 3/6 | 3/6 | 1/6 | La cámara baja y las vistas parciales provocan omisiones/confusiones. En YOLOX, varios `chair` recaen sobre un bote del fondo, no sobre la silla. |
| Estuche blando como `suitcase` | 2/4 | 2/4 | 1/4 | Frecuentemente se clasifica como `chair` o `couch`. No hubo asociación como `handbag` en las fotos individuales. |

\* Otra mochila tiene un `backpack` sobre el objeto, pero la caja sale por el
borde superior y no se cuenta como geometría válida.

En las dos fotos de paso despejado, YOLO11n no produjo cajas; SSDLite320
produjo siete sobre piso o fondo; YOLOX-Nano produjo una sobre una puerta o
mueble del fondo. La vía despejada puede incluir objetos reales al fondo, así
que una caja allí no equivale automáticamente a un obstáculo delante del carro.
En las dos fotos con varios objetos, YOLO11n asoció una botella en una y una
mochila en otra; SSDLite320 no asoció `backpack`/`bottle`/`cup` a los objetos;
YOLOX-Nano asoció mochilas en ambas y una botella, pero omitió las tazas y
mezcló `suitcase` con `backpack`.

## Latencia y geometría

Tiempo total por foto en las 28 siguientes a la primera, en la misma Mac:

| Modelo | Mediana | p95 lineal | Cajas | Problemas geométricos |
|---|---:|---:|---:|---|
| YOLO11n | 25.14 ms | 26.00 ms | 35 | Ninguno registrado. |
| SSDLite320 | 36.40 ms | 38.93 ms | 72 | Ninguno registrado. |
| YOLOX-Nano | 21.56 ms | 23.17 ms | 48 | Tres cajas con `y1<0`. |

El total incluye trabajo distinto según el runtime. En YOLO11n se mide
alrededor de `predict`; en SSDLite320, `model([tensor])` incluye resize,
inferencia, NMS y remapeo; en YOLOX-Nano el NMS NumPy es un paso posterior a
`session.run`. Las resoluciones son 640, 320 y 416, respectivamente. Es una
comparación exploratoria local, no el benchmark P5-15 ni una medición en la
computadora pendiente de PEND-05.

## Las tres cajas YOLOX fuera del borde

| Foto | Clase | xyxy original, píxeles | Exceso superior | `y1` hipotética tras recorte |
|---|---|---|---:|---:|
| `mochila_cerca.jpg` | `suitcase` | `(195.286, -4.387, 550.900, 352.853)` | 4.387 px | 0 |
| `mochila_cerca.jpg` | `backpack` | `(200.016, -0.977, 547.260, 348.178)` | 0.977 px | 0 |
| `mochila_lado_2.jpg` | `person` | `(201.370, -0.044, 530.599, 372.265)` | 0.044 px | 0 |

La salida se decodifica a coordenadas del lienzo 416 × 416 y luego se divide
por la escala 0.65 para volver a 640 × 480. Como el letterbox está alineado
arriba a la izquierda, no hay offset superior. Antes de dividir por 0.65, las
`y1` ya eran aproximadamente −2.851, −0.635 y −0.029 píxeles del lienzo:
el remapeo **amplificó**, pero no creó, la salida del borde. El script YOLOX
no aplica recorte después del remapeo. Un recorte explícito de cada coordenada
a los límites y el rechazo de cajas degeneradas dejaría las tres válidas; no
cambiaría las **48 detecciones** porque se aplicaría tras el filtro y el NMS.
Sí cambiaría de 2/7 a 3/7 el conteo de asociación geométricamente válida de
`backpack` en fotos individuales. Esto es un **escenario hipotético de
posprocesamiento**, no una corrección de la evidencia ni una modificación del
contrato A → B v1. `cajas_yolox_analisis.csv` conserva ambos valores.

## Propuesta para revisión

YOLO11n merece consideración preliminar: reconoció botella y taza en 3/4,
mochila en 3/7 y silla en 3/6, no produjo cajas en las escenas despejadas y
tuvo menor latencia local que SSDLite320. Frente a YOLOX-Nano, fue más lento
pero reconoció más tazas y sillas y no produjo cajas fuera de límites. Su
principal condición pendiente es revisar si la licencia AGPL-3.0 es adecuada
para la entrega y cómo cumplir sus obligaciones. SSDLite320 reconoció más
mochilas, pero produjo más cajas de fondo/piso y tuvo mayor latencia. YOLOX fue
el más pequeño y rápido en esta Mac, pero omitió más objetos y requiere una
política explícita para sus cajas fuera del borde.

Se proponen **botella, taza y mochila** como objetos principales para discusión
con Karen y Ale V; **silla** como cuarto opcional sujeto a pruebas adicionales
desde la altura baja de la cámara. El estuche blando podría descartarse porque
solo se reconoció como `suitcase` en 1–2 de 4 fotos por modelo y se confunde
con muebles; `handbag` tampoco resultó útil. Esta propuesta cambia los objetos
sugeridos anteriormente en PEND-04 (lata, mochila, cajas, tenis), por lo que
requiere decisión expresa de ambas PM. Las omisiones son un riesgo para evitar
colisiones; las cajas de piso/fondo pueden provocar paradas innecesarias.
P5-04 no define aquí la respuesta de seguridad ni implementa P5-05.

Quedan pendientes la confirmación del dominio PEND-04, condiciones de pesos,
hardware de evaluación PEND-05, medidas/configuración de cámara P5-19 y
revisión de casos laterales, lejanos y superpuestos. `modelo/DECISION.md` es
un borrador sujeto a aprobación, no una decisión cerrada.
