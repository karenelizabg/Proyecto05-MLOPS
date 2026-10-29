# P5-04 · YOLO11n en CPU · comparación técnica preliminar

## Alcance

Se procesaron las 29 fotografías JPEG de 640 × 480 que el usuario identifica como capturas
de la ESP32-CAM real. Son imágenes de **selección**; no pertenecen a las ocho secuencias de
evaluación final. La revisión es visual, sin cajas de verdad de referencia ni F1. Este ensayo
no elige detector ni objetos definitivos.

Checkpoint oficial `yolo11n.pt` de
[`ultralytics/assets` v8.3.0](https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt),
5 613 764 bytes, SHA-256
`0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`.
Entorno: Python 3.12.14; Ultralytics 8.3.0; torch 2.9.0; torchvision 0.24.0;
NumPy 1.26.4; OpenCV 4.11.0. Equipo local: MacBook Air Apple M3, 8 núcleos, 16 GB RAM,
macOS 27.0.1 arm64. PyTorch se limitó a un hilo. Parámetros: `device=cpu`, `imgsz=640`,
`conf=0.25`, `iou=0.7`, `batch=1`; sin MPS, entrenamiento ni ajustes de pesos.

## Resultado resumido

Hubo 35 cajas en 29 imágenes; seis imágenes no tuvieron detecciones. Todas las confianzas
fueron finitas y estuvieron entre 0 y 1. Todas las coordenadas `xyxy` fueron finitas,
estuvieron dentro de 640 × 480 y cumplieron `x1 < x2`, `y1 < y2`. Los `class_id`
observados coinciden con los nombres del mapa del checkpoint: `backpack=24`,
`suitcase=28`, `bottle=39`, `cup=41`, `chair=56`, entre otras clases espurias.

| Objeto en fotos individuales | Fotos | Clase esperada asociada visualmente | Hallazgo principal |
|---|---:|---:|---|
| Botella | 4 | 3 | La lejana se omitió; la cercana se marcó también como `vase` con mayor confianza. |
| Mochila | 7 | 3 | Cinco fotos reciben `suitcase`; la vista lateral segunda se omitió. Algunas cajas duplican el mismo objeto. |
| Taza | 4 | 3 | La lejana se omitió; en la izquierda aparece además `chair` sobre el bote del fondo. |
| Silla | 6 | 3 | Una cercana recibe dos `airplane`, la izquierda `tv` y una silla se omite. En `silla_der` se omite una botella real del borde. |
| Estuche blando | 4 | 2 como `suitcase`; 0 como `handbag` | Centro cerca/lejos sale `suitcase`; los laterales salen `couch` o `chair`. |
| Paso despejado | 2 | No aplica | Cero detecciones en ambas fotos; hay mobiliario de fondo. |
| Varios objetos | 2 | Parcial | `varios_1`: solo botella; `varios_2`: solo mochila. Taza y otros objetos quedan omitidos. |

Los conteos de la tercera columna son observaciones visuales de esta muestra, no recall ni
métrica formal. La tabla completa por fotografía, con clases y confidencias, está en
`evidencia/revision_por_imagen.csv`; las cajas sin redondear están en
`evidencia/detecciones.csv`. No se aceptó automáticamente una clase esperada: se revisó
que la caja cayera sobre el objeto visible. En `maleta_der`, por ejemplo, `chair` cae
sobre el estuche y es una **confusión**, no una silla detectada correctamente.

## Latencia local

Construcción de `YOLO(checkpoint)`: 22.37 ms. Primera imagen: 36.06 ms de inferencia
informada por Ultralytics y 162.06 ms alrededor de `predict` (incluye inicialización
adicional y lectura). Para las otras 28 imágenes, inferencia: mínimo 23.25, mediana
23.75, p95 lineal 24.49 y máximo 24.75 ms. Tiempo alrededor de `predict`: mínimo
24.62, mediana 25.14, p95 lineal 26.00 y máximo 26.19 ms. Tiempos individuales y de
pre/posprocesamiento: `evidencia/por_imagen.csv`.

Estas cifras pertenecen **solo al Mac Apple M3 local** y a esta corrida exploratoria.
No son el benchmark de P5-15 (10 calentamientos y 100 ejecuciones válidas), ni predicen
la latencia en la computadora de evaluación de PEND-05. `load_ms` mide la construcción
del objeto; la primera llamada muestra que parte del trabajo ocurre después.

## Limitaciones y siguiente paso

`registro.csv` es un historial de capturas y no identifica la cámara ni las cajas reales.
La procedencia ESP32-CAM se basa en la confirmación del usuario. Las fotos se mantienen
fuera del repositorio y se enlazan mediante nombre, tamaño y SHA-256 en el manifiesto.
El fondo contiene objetos que pueden generar falsos positivos. `varios_2` incluye una taza
parcialmente cortada. No se ajustó el umbral ni se calcularon métricas formales.

Comparar en las mismas 29 imágenes a SSDLite y YOLOX-Nano en experimentos separados,
normalizando salidas a nombres COCO y cajas originales sin asumir que sus confidencias
están calibradas igual. Después, proponer tres o cuatro objetos a las PM A y B. La licencia
AGPL-3.0 declarada por Ultralytics para código y modelos debe revisarse antes de cualquier
adopción en la entrega.
