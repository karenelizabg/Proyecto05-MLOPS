# Configuración, pesos e inferencia JPEG · P5-05, pasos 1 a 3

`config/detector.json` describe la ruta de predicción verificada con YOLO11n
`yolo11n.pt` y Ultralytics 8.3.0. No ejecuta inferencia ni descarga pesos.
El SHA-256 esperado del checkpoint procede de P5-04; el cargador comprueba los
bytes del archivo antes de deserializarlo.

## Carga local de pesos (paso 2)

`infer.pesos.cargar_pesos(ruta, config)` exige una ruta local explícita a un
archivo regular `.pt`. Rechaza enlaces simbólicos, ausencias, lecturas fallidas
y un SHA-256 esperado malformado. Copia el archivo a un directorio temporal
privado mientras calcula el SHA-256 de **los mismos bloques**; solo construye
`YOLO` con esa copia cuando coincide con el hash esperado. Si el original
cambia después de leerlo, Ultralytics sigue recibiendo los bytes comprobados.
La copia se borra tras construir el modelo en memoria. Ultralytics recibe una
ruta absoluta local existente, su resolvedor de descargas se restringe a esa
copia durante la carga y la autoinstalación de paquetes se desactiva.

El cargador fija un hilo de Torch y comprueba detección, clases 39/41, stride
32, CPU, FP32 y modo de evaluación. Devuelve `model_sha256` calculado sobre
los pesos y el `config_sha256` independiente. No produce predicciones ni
eventos del contrato todavía. La carga de checkpoints `.pt` usa la
deserialización de PyTorch; por eso solo se permite el SHA-256 aprobado.

## Inferencia JPEG y validación previa (paso 3)

`infer.detector.DetectorJPEG` decodifica cada JPEG con `cv2.imread(...,
cv2.IMREAD_COLOR)` y pasa el arreglo BGR, no la ruta, al predictor. Extiende
`ultralytics.models.yolo.detect.predict.DetectionPredictor` sin alterar el
paquete instalado. El método `preprocess` heredado conserva el letterbox,
BGR→RGB, BCHW y `/255` de Ultralytics 8.3.0. El método `postprocess` extendido
valida la salida de la red **antes** de llamar a `super().postprocess`, que
conserva `ops.non_max_suppression` y `ops.scale_boxes` nativos.

Para este checkpoint `.pt` de detección COCO, el primer elemento de la salida
es un tensor CPU/FP32 de forma `(1, 84, N)`: cuatro canales `xywh` en píxeles
del tensor de entrada y 80 puntajes de clase en `[0,1]`. Todavía no hay un
`class_id` por caja: NMS lo obtiene al escoger el puntaje máximo. Se rechazan
forma o tipo incompatibles, NaN/Infinity, puntajes fuera de `[0,1]` y anchos
o altos no positivos. Se permiten centros y cajas fuera de la imagen porque
`scale_boxes` realiza el remapeo y recorte. El número de canales fija el
catálogo en 80 clases; un ID fuera de rango en el resultado final también se
rechaza. Después del NMS se comprueban finitud, confianza, clase y área de las
cajas originales, antes de filtrar clases COCO ajenas a botella/taza.

`ErrorSalidaInvalida.code == "invalid_output"` distingue una salida corrupta
de `detections == ()`. El predictor es una API interna de Ultralytics y su
firma, la forma cruda o las reglas del NMS podrían cambiar en otra versión;
el pin `8.3.0`, las comprobaciones de forma y las pruebas reales son la barrera
de compatibilidad.

## Comando `infer` y JSONL (paso 4)

Instalación reproducible con Python 3.12: `uv sync --locked`. Los pesos no se
instalan ni descargan; se indica un `.pt` local cuyo SHA-256 coincida con
`artifacts.expected_model_sha256`. El comando exige pesos, entrada, salida y
`run_id` explícitos:

```bash
uv run --locked python -m infer \
  --input docs/carro/objeto_taza_centro_cerca.jpg \
  --config config/detector.json \
  --weights /ruta/local/yolo11n.pt \
  --output resultados/ejemplo.jsonl \
  --run-id ejemplo-01
```

`--input` admite un JPEG o un directorio plano de `.jpg`/`.jpeg`; el directorio
se ordena por nombre **solo para establecer el orden de cuadros**, nunca para
predecir. No se leen anotaciones ni manifiestos. `--output` acepta un archivo
`.jsonl` o una carpeta; en este último caso crea `<run-id>.jsonl`. No se
sobrescribe una salida existente. `--config` tiene por defecto
`config/detector.json`; `--sequence-id` es obligatorio para directorios y vale
`independent` para un JPEG individual. Los IDs de cuadros son `f000001`,
`f000002`, etc., únicos dentro del run y ajenos al nombre del JPEG.

Para un directorio se exige **un `--capture-ms` por JPEG**, en el orden indicado
arriba. Son instantes finitos, no negativos y estrictamente crecientes, en ms
relativos al origen monotónico del run. El comando espera hasta cada instante
antes de procesar el cuadro; así el tiempo de emisión usa el mismo reloj y no
precede al de captura. Ejemplo para dos cuadros:

```bash
uv run --locked python -m infer --input /ruta/secuencia \
  --weights /ruta/local/yolo11n.pt --output resultados \
  --run-id secuencia-01 --sequence-id S01 --capture-ms 0 --capture-ms 200
```

En el modo independiente de un JPEG sin metadatos de captura, `t_capture_ms`
mide su **recepción por el comando durante ese run**. No representa la hora
original en que se tomó la fotografía. Si esa hora relativa es conocida, puede
indicarse un `--capture-ms`. `t_emit_ms` mide el instante monotónico tras la
inferencia, ambos relativos al mismo origen; el tiempo de carga inicial del
modelo queda fuera del run.

Cada línea es un evento A→B v1 con los 14 campos obligatorios, `status=ok` y
`detections` (posiblemente `[]`), o `status=error`, `detections=[]` y
`error={code,message}`. `ErrorImagenJPEG` produce `unreadable_image`,
`ErrorSalidaInvalida` produce `invalid_output` y otras excepciones del detector
producen `detector_exception`. No se aplica todavía `stale` ni `detector_timeout`
de P5-06. El código de salida es 0 sin errores, 1 si hubo eventos de error y 2
para fallo de configuración, pesos o contrato. Cada evento se comprueba con
`validar_evento` y `validar_flujo`, se serializa con `allow_nan=False` y se
escribe como una línea completa. Se verifica con:

```bash
uv run --locked python -m contrato resultados/ejemplo.jsonl
```

Limitaciones: los tiempos de un directorio requieren datos suministrados por
el usuario; no se infieren del nombre del archivo. La inferencia reutiliza un
predictor CPU dentro del proceso. Una interrupción externa puede dejar un
archivo con los eventos completos ya emitidos; esta fase no implementa
transacciones del archivo entero ni la política temporal P5-06.

## Parámetros efectivos

El objeto `effective` completo participa en `config_sha256`:

| Sección | Campos | Uso real en Ultralytics 8.3.0 |
|---|---|---|
| `model` | `name`, `backend` | YOLO11n con checkpoint PyTorch `.pt`. |
| `runtime` | `ultralytics`, `torch`, `torchvision`, `opencv-python`, `numpy` | Versiones fijadas; Torchvision ejecuta NMS y OpenCV decodifica, redimensiona y rellena. |
| `execution` | `device`, `dtype`, `batch`, `torch_threads`, `augment` | CPU, FP32, batch 1, un hilo (`torch.set_num_threads(1)` antes de inferir) y sin aumentación. |
| `preprocess` | `decoder`, `input_channels`, `model_channels`, `layout`, `imgsz`, `letterbox`, `stride`, `scale_fill`, `scaleup`, `center`, `padding_value`, `interpolation`, `normalization_divisor` | `cv2.imread` entrega BGR; el predictor hace `LetterBox(auto=True)` por batch 1 y `.pt`, BGR→RGB, BCHW, FP32 y `/255`. |
| `postprocess` | `confidence`, `nms_iou`, `agnostic_nms`, `max_det`, `class_ids`, `bbox_format`, `bbox_unit`, `coordinates`, `clip_boxes` | Umbrales y NMS por clase; solo botella/taza; cajas `xyxy` en píxeles originales mediante `scale_boxes`, que recorta. |

La validación fija las propiedades internas que `predict` no expone como
parámetros cambiables: rectángulo mínimo, padding centrado de 114, stride 32,
interpolación lineal, orden de canales, normalización y remapeo de cajas. La
configuración **no incluye `rect`**: en Ultralytics 8.3.0 ese parámetro no
controla el preprocesamiento de `predict` para un `.pt` y batch 1. `imgsz=640`
es el objetivo máximo, no una promesa de tensor cuadrado. Un JPEG de 640×480
produce `BCHW=1×3×480×640` sin padding; una imagen de 1280×720 produce
`1×3×384×640` con 12 píxeles arriba y abajo. El tamaño se obtiene del contenido
de la imagen, no del nombre del archivo.

`ConfigDetector.predict_kwargs()` entrega las opciones que el futuro paso de inferencia pasará a
`YOLO.predict`: `device`, `half`, `batch`, `augment`, `imgsz`, `conf`, `iou`,
`agnostic_nms`, `max_det` y `classes`. El cargador actual llama antes a
`verificar_versiones_runtime`, fijará el hilo de Torch y comprobará que el
checkpoint cargado sea `.pt`, use FP32 y tenga stride 32. Los valores internos
de `LetterBox` dependen de la versión fijada; no se pretende sobreescribirlos.

## Cálculo de `config_sha256`

`validar_config_detector` rechaza claves desconocidas, tipos incompatibles,
valores no finitos y combinaciones ajenas al flujo aprobado. Normaliza los
umbrales a `float` y ordena `class_ids` porque su orden no afecta el filtro.
Después serializa **solo `effective`** con:

```python
json.dumps(
    effective, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
).encode("utf-8")
```

El SHA-256 se calcula sobre esos bytes exactos, sin salto de línea. Las rutas
locales, timestamps y hardware no entran en el hash. El objeto `artifacts`
contiene `weights_path` y `expected_model_sha256` para el paso 2, pero tampoco
entra: los bytes reales del checkpoint tendrán su propio `model_sha256` del
contrato A→B v1. Cambiar la ubicación del mismo checkpoint deja intacto
`config_sha256`.

Con los valores actuales, `config_sha256` es
`bd736aff92ac6ae39348272ec48763764edf16b30c6ba0d3847cf9bae0658fdf`.

## Reproducción y Windows

Las versiones directas coinciden con el ensayo P5-04: Ultralytics 8.3.0,
PyTorch 2.9.0, Torchvision 0.24.0, OpenCV 4.11.0.86 y NumPy 1.26.4, con
Python 3.12. `uv.lock` fija también las dependencias transitivas. En Linux,
`torch` sale como `2.9.0+cpu` y, en x86_64, `torchvision` como `0.24.0+cpu`
del índice CPU oficial de PyTorch. El sufijo local selecciona el artefacto
CPU sin cambiar la versión pública usada en P5-04. macOS arm64 y Windows
x86_64 usan sus ruedas de PyPI. No se han comprobado todavía instalación,
latencia ni igualdad numérica en la laptop Windows de Ale. Esa verificación
corresponde a PEND-05/P5-15; las posibles diferencias entre plataformas se
medirán con JPEG reales.
