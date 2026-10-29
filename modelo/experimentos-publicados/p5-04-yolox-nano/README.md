# P5-04 · YOLOX-Nano ONNX · reproducción

Experimento exploratorio sobre 29 JPEG originales de 640 × 480 de la ESP32-CAM.
Las imágenes permanecen en `"$P5_04_FOTOS"`; no se copiaron
al repositorio ni se usaron secuencias de evaluación final. El manifiesto fija
nombre, tamaño, resolución y SHA-256. Este experimento no implementa P5-05 ni
el benchmark P5-15.

## Procedencia y entorno

- Modelo: [`yolox_nano.onnx` de YOLOX 0.1.1rc0](https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx), 3 659 407 bytes, SHA-256 `c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d`.
- Código de referencia: [commit `e1052df`](https://github.com/Megvii-BaseDetection/YOLOX/tree/e1052df71842031413f6030723c3607b839c80ce). Código [Apache-2.0](https://github.com/Megvii-BaseDetection/YOLOX/blob/0.1.1rc0/LICENSE); las condiciones independientes de los pesos no se verificaron.
- Python 3.12.14, ONNX Runtime 1.31.1, NumPy 1.26.4 y OpenCV 4.11.0 en `entorno Python experimental con versiones indicadas`.
- MacBook Air Apple M3, macOS arm64. `CPUExecutionProvider` exclusivo, un hilo intra/inter, batch 1.

## Configuración fijada antes de la corrida

Entrada `images` float32 `[1,3,416,416]`; salida `output` float32 `[1,3549,85]`.
Redimensionar la imagen BGR 640 × 480 por 0.65 a 416 × 312 y completar hasta
416 × 416 con valor 114 abajo y a la derecha (contenido alineado arriba a la
izquierda). Convertir a CHW float32 **sin normalizar**. Decodificar con strides
8/16/32, dividir las coordenadas por 0.65, calcular confianza como objectness
× probabilidad de clase, filtrar `≥0.25` y aplicar NMS **por clase** con IoU
0.45. No se modificaron umbrales después de revisar las fotos.

Hay una discrepancia histórica: el [ejemplo ONNX del commit de la release](https://github.com/Megvii-BaseDetection/YOLOX/blob/e1052df71842031413f6030723c3607b839c80ce/demo/ONNXRuntime/onnx_inference.py)
normaliza como ImageNet, mientras las [notas de 0.1.1rc0](https://github.com/Megvii-BaseDetection/YOLOX/releases/tag/0.1.1rc0)
indican que los pesos nuevos ya no normalizan. La [documentación ONNX oficial
posterior](https://github.com/Megvii-BaseDetection/YOLOX/blob/main/demo/ONNXRuntime/README.md)
enlaza el mismo asset y usa la ruta sin normalización. Se validó antes con una
foto de taza y se mantuvo esta configuración para las 29 fotos. El NMS reproduce
el método por clase del [`demo_utils.py` de ese commit](https://github.com/Megvii-BaseDetection/YOLOX/blob/e1052df71842031413f6030723c3607b839c80ce/yolox/utils/demo_utils.py).

## Ejecutar

Con el checkpoint y las fotos en las rutas indicadas, desde la raíz del repositorio:

```sh
python modelo/experimentos-publicados/p5-04-yolox-nano/ejecutar.py \
  --images "$P5_04_FOTOS" \
  --weights "$P5_04_YOLOX_ONNX" \
  --yolo-manifest modelo/experimentos-publicados/p5-04-yolo11n/evidencia/manifiesto.csv \
  --output modelo/experimentos-publicados/p5-04-yolox-nano/evidencia
python3 modelo/experimentos-publicados/p5-04-yolox-nano/combinar_revision.py
```

`ejecutar.py` comprueba el hash del checkpoint y los 29 hashes de fotos antes
de inferir. En la corrida registrada terminó las **29 inferencias**, escribió
las salidas y devolvió código 1 al final por **tres cajas fuera de límites**.
Ese código es la barrera de validación, no una falla de ONNX Runtime. Las cajas
originales se conservan sin recorte en `detecciones.csv`, con `validacion`.
`combinar_revision.py` une el juicio visual manual y genera el resumen; la
revisión manual no se infiere de los nombres de archivo.

## Archivos de evidencia

| Archivo | Contenido |
|---|---|
| `configuracion.json` | Modelo, procedencia, versiones, hardware y parámetros. |
| `manifiesto.csv` | 29 nombres, tamaños, dimensiones y hashes. |
| `por_imagen.csv` | Clases, conteos y desglose de latencia por foto. |
| `detecciones.csv` | 48 detecciones, class ID COCO, confianza, xyxy sin recortar y validación. |
| `latencia_resumen.json` | Carga, primera imagen, estadísticas de las otras 28 y cajas inválidas. |
| `revision_visual.csv` | Asociación manual de caja y objeto, omisiones y confusiones. |
| `revision_por_imagen.csv` | Salida automática unida a la revisión manual. |
| `resumen_por_objeto.csv` | Conteo exploratorio de asociaciones visuales por grupo. |

Las confianzas de modelos distintos no están calibradas entre sí. Los conteos
visuales no son precisión ni recall formal porque no hay cajas de verdad de
referencia verificadas.
