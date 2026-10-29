# P5-04 · ensayo exploratorio de YOLO11n

Este ensayo usa las 29 fotos de selección indicadas por el usuario como capturas de la ESP32-CAM.
`registro.csv` no identifica la cámara ni constituye verdad de referencia anotada. Las fotos
permanecen en Downloads; esta carpeta solo contiene código y resultados derivados. Nada de aquí
produce eventos del contrato v1 ni sustituye el benchmark oficial de P5-15.

## Reproducción

Entorno usado: `entorno Python experimental con versiones indicadas`, Python 3.12.14, Ultralytics 8.3.0,
PyTorch 2.9.0, torchvision 0.24.0, NumPy 1.26.4 y OpenCV 4.11.0. El checkpoint es
`"$P5_04_YOLO11N_PT"`, descargado de la [release oficial
v8.3.0](https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt).
SHA-256 esperado: `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`.
Ultralytics declara AGPL-3.0 para código y modelos; revisar antes de adoptar el modelo.

Desde la raíz del repositorio:

```bash
YOLO_CONFIG_DIR=${TMPDIR:-/tmp}/p5-04-yolo11n-config \
MPLCONFIGDIR=${TMPDIR:-/tmp}/p5-04-matplotlib \
XDG_CACHE_HOME=${TMPDIR:-/tmp}/p5-04-cache \
python \
  modelo/experimentos-publicados/p5-04-yolo11n/ejecutar.py \
  --images "$P5_04_FOTOS" \
  --weights "$P5_04_YOLO11N_PT" \
  --output modelo/experimentos-publicados/p5-04-yolo11n/evidencia

python \
  modelo/experimentos-publicados/p5-04-yolo11n/combinar_revision.py
```

El script comprueba el hash del checkpoint, exige 29 imágenes legibles de 640 × 480,
calcula sus SHA-256 y usa `device=cpu`, `imgsz=640`, `conf=0.25`, `iou=0.7`, `batch=1`
y un hilo de PyTorch. No usa MPS. `revision_visual.csv` es juicio humano sobre las cajas;
`combinar_revision.py` lo une a las salidas crudas por nombre. Si cambian las fotos,
hay que revisar de nuevo las observaciones manuales, incluso si la unión por nombre pasa.

## Archivos

- `evidencia/configuracion.json`: procedencia, parámetros, versiones y hardware registrado.
- `evidencia/manifiesto.csv`: fotos actuales, tamaño y SHA-256.
- `evidencia/por_imagen.csv`: detecciones, clases y tiempos por fotografía.
- `evidencia/detecciones.csv`: cada clase, confianza y caja `xyxy` en píxeles originales.
- `evidencia/latencia_resumen.json`: carga, primera imagen y resumen de las otras 28.
- `evidencia/revision_visual.csv`: asociación visual manual y limitaciones.
- `evidencia/revision_por_imagen.csv`: tabla unida para consulta.
- `reporte.md`: interpretación de este ensayo.

Los tiempos `speed` provienen de Ultralytics y separan preprocesamiento, inferencia y
posprocesamiento. `wall_ms` se mide alrededor de `predict` y además incluye la lectura del
archivo y gastos de la llamada. La primera imagen se informa aparte por su inicialización.
