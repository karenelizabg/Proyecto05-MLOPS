# Evidencia publicable de P5-04

Esta carpeta es una **copia de publicación** de los tres experimentos y la
comparación. Los archivos experimentales originales locales permanecen en
`modelo/experimentos/` sin modificar ni incluirse en el PR. En esta copia se
sustituyeron únicamente rutas personales de fotos, pesos y entornos en los
README y en `evidencia/configuracion.json`; cada configuración conserva en
`publicacion.configuracion_original_sha256` el hash del archivo original.
Los valores de los CSV de resultados, manifiestos y latencias, así como los
scripts y reportes, conservan su contenido; `.gitattributes` normaliza los
finales de línea de texto a LF al incorporarlos a Git. Se excluyó un caché
`.pyc` no necesario.

Los 29 JPEG originales de la ESP32-CAM **no** están incluidos. Se identifican
mediante nombre, tamaño, resolución y SHA-256 en cada `manifiesto.csv`.
Los checkpoints tampoco se incluyen; sus URL oficiales, tamaños y SHA-256
figuran en las configuraciones y README de cada modelo.

Para repetir inferencias, activar un entorno con las versiones indicadas en el
README del modelo y definir las rutas locales antes de ejecutar sus comandos:

```sh
export P5_04_FOTOS=/ruta/a/fotos
export P5_04_YOLO11N_PT=/ruta/a/yolo11n.pt
export P5_04_SSDLITE_PTH=/ruta/a/ssdlite320_mobilenet_v3_large_coco-a79551df.pth
export P5_04_YOLOX_ONNX=/ruta/a/yolox_nano.onnx
```

La comparación se regenera sin pesos ni fotos, desde la raíz del repositorio:

```sh
python3 modelo/experimentos-publicados/p5-04-comparacion/consolidar.py
```

Las rutas locales sanitizadas son metadatos de ejecución, no parámetros del
modelo. No se recalcularon ni editaron las detecciones originales. El
resultado YOLOX conserva tres cajas fuera de límites y las señala como tales.
