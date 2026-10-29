# P5-04 · SSDLite320 MobileNetV3-Large en CPU

Ensayo exploratorio sobre las mismas 29 fotos de selección ESP32-CAM de YOLO11n. Las
fotografías originales permanecen en Downloads; el manifiesto registra sus SHA-256.
No son las ocho secuencias de evaluación final, ni existe verdad de referencia con
cajas anotadas. Nada de este ensayo implementa el contrato A → B v1 o P5-05.

## Reproducción

Entorno: `entorno Python experimental con versiones indicadas` (Python 3.12.14, torch 2.9.0,
torchvision 0.24.0, NumPy 1.26.4, OpenCV 4.11.0). Equipo: MacBook Air M3,
8 núcleos, 16 GB. El archivo de pesos COCO_V1 se obtuvo del [servidor oficial
de PyTorch](https://download.pytorch.org/models/ssdlite320_mobilenet_v3_large_coco-a79551df.pth).
Tamaño: 14 069 355 bytes. SHA-256:
`a79551df90c79834bcd3bb3845ef9d966b5449a3a9b2833ae8404778ca5d65d2`.

Desde la raíz del repositorio:

```bash
python \
  modelo/experimentos-publicados/p5-04-ssdlite320/ejecutar.py \
  --images "$P5_04_FOTOS" \
  --weights "$P5_04_SSDLITE_PTH" \
  --yolo-manifest modelo/experimentos-publicados/p5-04-yolo11n/evidencia/manifiesto.csv \
  --output modelo/experimentos-publicados/p5-04-ssdlite320/evidencia

python \
  modelo/experimentos-publicados/p5-04-ssdlite320/combinar_revision.py
```

El script comprueba SHA-256 de pesos y de las 29 fotos antes de inferir. Construye
`ssdlite320_mobilenet_v3_large(weights=None, weights_backbone=None)`, carga el
`state_dict` local con `strict=True`, usa `model.eval()` y `torch.inference_mode()`.
No hay descargas automáticas. El dispositivo es CPU y PyTorch usa un hilo. El lote
es 1. Las fotos se decodifican en RGB `[0,1]`; el modelo las redimensiona
internamente a 320 × 320, normaliza con media/desviación `[0.5,0.5,0.5]` y
devuelve cajas `xyxy` remapeadas a la resolución 640 × 480 original.

SSDLite aplica su propio NMS por clase con IoU 0.55, `score_thresh=0.001`,
`topk_candidates=300` y máximo 300 detecciones. Después de su NMS, este ensayo
reporta solo confianza ≥0.25. YOLO11n se ejecutó con IoU 0.7, `imgsz=640` y su
propio preprocesamiento/NMS: estos ajustes no son idénticos. Los `class_id` de
Torchvision corresponden a su lista COCO de 91 entradas con huecos `N/A`; no
coinciden numéricamente con los de Ultralytics.

## Mediciones y evidencia

- `evidencia/configuracion.json`: procedencia, configuración, versiones y hardware.
- `evidencia/manifiesto.csv`: 29 fotos, tamaños y SHA-256.
- `evidencia/por_imagen.csv`: tiempos y conteos por foto.
- `evidencia/detecciones.csv`: clases, confianza y cajas originales por detección.
- `evidencia/latencia_resumen.json`: carga, primera foto y distribución de las otras 28.
- `evidencia/revision_visual.csv`: juicio visual manual y sus limitaciones.
- `evidencia/revision_por_imagen.csv`: unión de clases, confianza y juicio visual.
- `evidencia/resumen_por_objeto.csv`: conteo exploratorio por grupo.
- `reporte.md`: interpretación y comparación preliminar.

`preprocess_ms` mide lectura JPEG, RGB y tensor; `inference_ms` mide todo el
`model([tensor])`, que **incluye** resize interno, red, NMS y remapeo de cajas;
`postprocess_ms` mide el filtro ≥0.25 y extracción de resultados; `wall_ms`
cubre todo. No es posible comparar `inference_ms` directamente con el campo
homónimo de Ultralytics, que excluye parte de ese trabajo. La primera foto se
informa por separado. No es el benchmark oficial de P5-15.

La [licencia del código Torchvision](https://github.com/pytorch/vision/blob/main/LICENSE)
es BSD-3-Clause. La [documentación oficial sobre pesos preentrenados](https://docs.pytorch.org/vision/master/models.html)
advierte que pueden existir condiciones de los datos de entrenamiento; no se
encontró licencia independiente explícita en los metadatos de COCO_V1. Verificar
las condiciones de los pesos antes de adoptarlos. La exportación a ONNX sería
una prueba separada; no se realizó ni se garantiza para estas versiones.
