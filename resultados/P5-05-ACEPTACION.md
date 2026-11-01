# P5-05 · evidencia de aceptación CPU (actualizada 2026-10-31)

Rama `p5-05-detector-infer`, publicada en el [PR #75](https://github.com/karenelizabg/Proyecto05-MLOPS/pull/75). Esta actualización se ejecutó sobre los commits **locales** `c9c49b9` y `f915763`, este último con `origin/main=4ed9d385` integrado; todavía no se publicaron en el PR. Se contrastó el [issue #7](https://github.com/karenelizabg/Proyecto05-MLOPS/issues/7) con el contrato A→B v1 y las ejecuciones de esta carpeta. Estas fotos son las **29 capturas de selección** que P5-04 atribuye a la ESP32-CAM; no son las ocho secuencias finales ni una verdad de referencia anotada. Las fotos y los pesos permanecen fuera del repositorio.

La [guía de revisión independiente para A3](P5-05-REVISION-A3.md) contiene comandos PowerShell, plantilla de registro y criterios para evaluar las omisiones. Ale ya comprobó tres JPEG y la instalación en Windows; faltan las escenas múltiples, la despejada y su dictamen sobre las omisiones. La aceptación de A3 sigue pendiente.

## Entorno y artefactos

- MacBook Air `Mac15,12`, Apple M3 (8 núcleos: 4 rendimiento, 4 eficiencia), 16 GB RAM; macOS 27.0.1 arm64. Es una medición **macOS**, no Windows.
- Python 3.12.14; Ultralytics 8.3.0; torch 2.9.0; torchvision 0.24.0; OpenCV 4.11.0.86; NumPy 1.26.4; Pillow 12.3.0 tras integrar P5-09 desde `main`. CPU, FP32, batch 1. `DetectorJPEG` restablece un hilo intraop de PyTorch después de `setup_model` y verifica `torch.get_num_threads()`; esto no controla todos los pools de OpenCV, BLAS o interop.
- Checkpoint local de 5 613 764 bytes: `model_sha256=0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`.
- Configuración efectiva: `config_sha256=bd736aff92ac6ae39348272ec48763764edf16b30c6ba0d3847cf9bae0658fdf`.
- [Corrida A](p5-05-aceptacion-a.jsonl), [corrida B](p5-05-aceptacion-b.jsonl): 29 eventos cada una. [Casos extra](p5-05-casos-extra.jsonl): 4 eventos. [Ejecución sin red](p5-05-sin-red.jsonl): 1 evento. [Ejemplo del paso 4](p5-05-step4-real.jsonl): 1 evento. [JSONL de la captura integrada](p5-05-comando-integrado.jsonl): 1 evento válido.
- [Captura auténtica integrada](P5-05-COMANDO-INTEGRADO.png): muestra ambos comandos completos, `1 cuadros, 0 errores` y `OK (1 eventos)` sobre el JSONL enlazado arriba. Heri la tomó en Terminal el 31 de octubre de 2026; la copia publicada conserva exactamente los bytes del PNG del Escritorio (SHA-256 `298513b774c519b4fc2b09325b082eb751dd38810284debb6087fad67c98f1bd`). No muestra rutas privadas ni credenciales.
- [Captura auténtica de Terminal](P5-05-COMANDO.png): muestra la ejecución publicada anterior al cambio de `frame_id`, con [su JSONL original](p5-05-captura-evidencia.jsonl). Ambos se conservan como evidencia histórica, no como demostración del nuevo identificador; la imagen no muestra rutas privadas ni credenciales.
- [Tabla neutral por SHA-256](p5-05-fotos-neutrales.csv) y [script de copias](p5-05-preparar-fotos.py): 29 pares `neutral_name,sha256`, sin nombres originales ni fotografías en Git.
- [Latencia integrada, 50 muestras](p5-05-latencia.json), [réplica integrada, 50 muestras](p5-05-latencia-replica.json) y [script reproducible](p5-05-benchmark.py). Los dos JSON se regeneraron con el lock integrado, sin sustituir una serie rápida por otra.

## Matriz de aceptación

| Criterio del issue #7 o del contrato | Prueba/evidencia | Resultado | Estado |
|---|---|---|---|
| JPEG real → caja, clase y confianza en CPU sin red | `botella_centro_cerca`, `botella_der`, `taza_centro_cerca`; ejecución con `socket.connect` bloqueado | Cajas visualmente alineadas; 39/41; salida sin red válida | **Cumplido en macOS** |
| Preprocesamiento BGR→RGB, letterbox y `/255` explícitos | `config/DETECTOR.md`, `src/infer/detector.py`, pruebas de tensor y proporciones | Tensor 640×480 → `1×3×480×640`; 1200×1600 → `1×3×640×480` | **Cumplido** |
| Confianza 0.25, NMS 0.70 por clase, clases `[39,41]`, cajas originales | Configuración y `tests/test_detector_jpeg.py` (NMS y `scale_boxes`) | Cajas finitas y dentro de límites en los 62 eventos | **Cumplido** |
| Pesos alterados → rechazo por SHA-256 | Copia temporal con último byte invertido; CLI terminó 2 | Hash obtenido `110fb84c…456529`; no se creó JSONL | **Cumplido** |
| Dos corridas idénticas o diferencias cuantificadas | Corridas A/B de 29 JPEG, mismo orden, pesos, configuración y entorno | 29/29 vectores de detecciones idénticos: conteo, orden, clase, confianza y bbox; diferencias máximas 0 | **Cumplido en este equipo** |
| JPEG central, lateral, varios y despejado; cajas originales | 29 fotos de P5-04 e inspección visual de imágenes seleccionadas | Centro/lateral correctos; ambos `vacio_*` dan `ok=[]`; en `varios_1` solo botella, en `varios_2` ninguna aunque hay objetos visibles | **Parcial: cobertura de varios objetos** |
| Cuatro imágenes escogidas por otra persona | A1 reutilizó las fotos de P5-04; [guía y plantilla para A3](P5-05-REVISION-A3.md) listas | Ale revisó tres JPEG en Windows; faltan escena múltiple, despejada y dictamen independiente | **Parcial** |
| Copia renombrada conserva resultado; no se abren anotaciones/manifiesto | Dos copias con SHA `8e360d41…ae07` y nombres opuestos dieron la misma detección; prueba `test_infer_no_abre_anotaciones_ni_manifiesto` falla si se abre un archivo señuelo | Misma clase, confianza y bbox; señuelos ignorados | **Cumplido** |
| JSON estricto, sin `NaN` ni `Infinity` | Parseo con `parse_constant` que falla, búsqueda textual y `python -m contrato` | 63/63 eventos válidos en A, B, casos extra y captura integrada; ninguna línea contiene esos literales | **Cumplido** |
| Un evento por cuadro; `ok=[]` y errores diferenciados | 29+29+4 eventos; JPEG corrupto | 22 cuadros vacíos `ok=[]` en cada corrida; corrupto `error/unreadable_image`; 4/4 en extra | **Cumplido** |
| Evidencia JSONL en `resultados/` y captura del comando | [JSONL integrado](p5-05-comando-integrado.jsonl) y [captura auténtica integrada](P5-05-COMANDO-INTEGRADO.png), junto a corridas A/B | `ensayo-0012` dio `1 cuadros, 0 errores`; el mismo JSONL pasó `OK (1 eventos)` y contiene `frame_id=ensayo-0012` | **Cumplido para evidencia del comando** |
| Rendimiento frente a B/PEND-05 | Calentamiento sintético, 10 JPEG excluidos y 50 medidas por serie, dos series integradas; `config/control/plazos.yaml` | p95 del detector 244.04 y 121.53 ms en este Mac; carga y calentamiento medidos por separado. Falta repetir Windows y el recorrido S09 con el código actual | **Pendiente para P5-06/P5-15/PEND-05** |

El issue no exige que cada objeto visible en una escena múltiple sea detectado, pero esa omisión es relevante para seguridad y no se cuenta como una detección acertada. No se calculó recall ni F1 porque no hay cajas de verdad de referencia para este conjunto.

## Imágenes y resultados observados

La inferencia recibió **solo los píxeles JPEG**. Los nombres originales siguientes sirven para ubicar la evidencia histórica, no se usaron en el nuevo run. Los 29 JPEG se copiaron sin alterar sus bytes a nombres neutros, ordenados por SHA-256; `frame_id` es el nombre neutro sin extensión. El orden de inferencia fue lexicográfico sobre `ensayo-0001.jpg` a `ensayo-0029.jpg`. Los nombres originales no entran en la [tabla publicada](p5-05-fotos-neutrales.csv).

| Caso (origen) | Resolución | Salida observada, corrida A |
|---|---:|---|
| `fotos/botella_centro_cerca.jpg` | 640×480 | bottle 0.2928, `[258.4,20.1,348.4,320.2]` |
| `fotos/botella_der.jpg` | 640×480 | bottle 0.8240, `[541.5,8.6,638.5,312.5]` |
| `fotos/taza_centro_cerca.jpg` | 640×480 | cup 0.9553, `[200.5,228.8,494.1,460.6]` |
| `fotos/taza_der.jpg` | 640×480 | cup 0.6064, `[519.5,218.1,623.4,287.6]` |
| `fotos/varios_1.jpg` | 640×480 | bottle 0.2691; taza visible omitida |
| `fotos/varios_2.jpg` | 640×480 | `ok=[]`; botella y taza visibles omitidas |
| `fotos/vacio_1.jpg`, `fotos/vacio_2.jpg` | 640×480 | `ok=[]` ambas |
| `docs/carro/atras.jpg` | 1200×1600 | `ok=[]`, tensor `1×3×640×480` |
| JPEG corrupto creado para la prueba | ilegible | `error/unreadable_image`, dimensiones `null` |

Para identificar el mismo conjunto en otra máquina, compare los SHA-256 del manifiesto **histórico** de P5-04; ese manifiesto no entra en la inferencia. Hashes de casos clave: `botella_centro_cerca=fd9995cacf67d53c979457d92e5e724ed6974b13d2f0b19f9299ccb70ff053bd`, `botella_der=8e360d41326126ea58b781a071f583a9e8b7f5a841af0539e2c0ba19322a4e07`, `taza_centro_cerca=670fec5473ceda61b5a6283711596d610d75577dfb1bc9d5ffc8de52c1e9cbcc`, `vacio_1=831bfbc5d8179e75c992c8ea5d3fe8ecf5c488715d72f4da0e570a5a9e18674c`, `varios_1=fcd354f2ae91480f872f672ef19d17bc7a17b47109bb17f00bde47c4ae04dadb`, `varios_2=12bf69b11bad6f4fbf70d7dae7655ae0cd4cea0e0c5e85ad7647806f935da6c6`. En las copias nuevas, `varios_1` corresponde a `ensayo-0026.jpg` y `varios_2` a `ensayo-0006.jpg` por SHA-256.

## Comandos y convención temporal

Ejecutar desde la raíz del repositorio tras `uv sync --locked`. En otra máquina, defina estas variables con **rutas locales propias**; los pesos y las 29 fotos no se descargan desde el comando:

```bash
export P5_05_YOLO11N_PT=/ruta/local/yolo11n.pt
export P5_04_FOTOS=/ruta/local/fotos
export P5_04_MANIFIESTO=/ruta/local/manifiesto-p5-04.csv
export P5_05_NEUTRALES=/ruta/local/fuera-del-repo/ensayo-p5-05
export P5_05_TABLA=/ruta/local/fuera-del-repo/tabla-nueva.csv
.venv/bin/python resultados/p5-05-preparar-fotos.py \
  --originales "$P5_04_FOTOS" --manifiesto "$P5_04_MANIFIESTO" \
  --copias "$P5_05_NEUTRALES" --tabla "$P5_05_TABLA"
diff -u resultados/p5-05-fotos-neutrales.csv "$P5_05_TABLA"
mkdir -p /ruta/local/fuera-del-repo/salidas
capture_args=()
for ((i=0; i<29; i++)); do capture_args+=(--capture-ms "$((i*200))"); done
.venv/bin/python -m infer --input "$P5_05_NEUTRALES" \
  --config config/detector.json --weights "$P5_05_YOLO11N_PT" \
  --output /ruta/local/fuera-del-repo/salidas/p5-05-aceptacion-a.jsonl \
  --run-id p5-05-aceptacion-a --sequence-id ESP32-ensayo "${capture_args[@]}"
# Repetir con output p5-05-aceptacion-b.jsonl y run-id p5-05-aceptacion-b.
.venv/bin/python -m contrato /ruta/local/fuera-del-repo/salidas/p5-05-aceptacion-a.jsonl
```

El calendario `0, 200, …, 5600 ms` es **un ritmo de reproducción suministrado para esta prueba**, no una medición de la captura histórica. En un JPEG individual sin tiempos originales, el CLI mide recepción durante el run. La salida de las dos corridas fue `29 cuadros, 0 errores` cada una y el validador imprimió `OK (29 eventos)` para ambas.

La [captura integrada](P5-05-COMANDO-INTEGRADO.png) corresponde a una ejecución
real de Heri en Terminal. Después de definir las variables anteriores y
ocultar sus rutas privadas de la pantalla, ejecutó estos comandos con un
**destino nuevo**:

```bash
.venv/bin/python -m infer --input "$P5_05_NEUTRALES/ensayo-0012.jpg" \
  --config config/detector.json --weights "$P5_05_YOLO11N_PT" \
  --output resultados/p5-05-comando-integrado.jsonl --run-id p5-05-comando-integrado
.venv/bin/python -m contrato resultados/p5-05-comando-integrado.jsonl
```

La captura muestra ambos comandos completos, `1 cuadros, 0 errores` y
`OK (1 eventos)`. [Su JSONL](p5-05-comando-integrado.jsonl) pasó el contrato
v1 y contiene `run_id=p5-05-comando-integrado`, `frame_id=ensayo-0012`,
`status=ok`, una detección y los hashes aprobados. La captura anterior
permanece como evidencia histórica de [su propio JSONL](p5-05-captura-evidencia.jsonl).

Para el conjunto adicional se copiaron dos veces los mismos bytes de `botella_der.jpg` como `S00_f0001.jpg` y `S00_f0002.jpg`, se copió `docs/carro/atras.jpg` como `S00_f0003.jpg` y se creó `S00_f0004.jpg` corrupto. Se añadieron `anotaciones.json` y `manifiesto.csv` señuelo en la prueba original; no son entrada del detector. La nueva ejecución usó `--capture-ms 0 --capture-ms 200 --capture-ms 400 --capture-ms 600`, devolvió código 1 por el cuadro corrupto y produjo **cuatro eventos válidos** con las mismas detecciones y estados anteriores. Las dos copias del mismo JPEG tienen SHA-256 idéntico y detecciones iguales, pero `frame_id` diferentes. La ejecución sin red usó una copia `S01_f0001.jpg` y la del paso 4 una copia `S02_f0001.jpg`. `error.message` conserva un texto estable sin ruta local y `error.code` conserva `unreadable_image`. El detalle original, incluida la ruta, queda en stderr local para diagnóstico y no forma parte del JSONL publicable.

La prueba de pesos alterados cambió **una copia temporal** (no el checkpoint original). `python -m infer` devolvió código 2 por discrepancia de SHA-256 y no creó salida. La ejecución sin red sustituyó `socket.connect`, `connect_ex` y `create_connection` por funciones que lanzan error; el CLI produjo una botella válida y el JSONL pasó el contrato.

## Reproducibilidad y latencia

Se compararon por `frame_id` los 29 arrays `detections` de las nuevas corridas A y B, excluyendo `run_id` y tiempos. Coinciden exactamente clase, confianza, cuatro coordenadas, número, orden y estado: `29/29` vectores idénticos, diferencia máxima de confianza `0` y de bbox `0 px`. Cada run contiene 7 detecciones y 22 cuadros sin detecciones. Frente a la evidencia neutral anterior al calentamiento y a la restauración de hilos, se conservaron `29/29` estados, conteos, clases y orden; diferencia máxima de confianza `8.344650268554688e-7` y de bbox `6.103515625e-5 px`. Por ello se documenta equivalencia numérica dentro de esas tolerancias observadas, no identidad bit a bit con la versión anterior. La edad del primer cuadro fue 111.15 ms en A y 114.12 ms en B, en esta reproducción macOS. Los hashes son constantes en los 62 eventos de A, B y casos extra.

El benchmark integrado usó `ensayo-0012.jpg`, copia byte a byte de la taza central con SHA-256 `670fec5473ceda61b5a6283711596d610d75577dfb1bc9d5ffc8de52c1e9cbcc`: 640×480, tensor `1×3×480×640`. Se ejecutó dos veces en procesos independientes sobre macOS arm64, Python 3.12.14, Torch 2.9.0, Ultralytics 8.3.0 y OpenCV 4.11.0.86. En cada serie se cronometraron **por separado** la carga verificada de pesos, la construcción del detector, un calentamiento sintético mediante `predictor(...)` y diez inferencias JPEG de calentamiento. Después se midieron 50 inferencias JPEG. `detector_total_ms` comprende lectura JPEG, predictor y validación/posprocesamiento; no incluye carga ni calentamientos. `forward_ms` es `Results.speed["inference"]`. p95 usa interpolación lineal de NumPy. Los JSON conservan todas las muestras y registran un hilo intraop configurado, uno tras `setup_model`, uno tras calentar y uno después de inferir; no miden los otros pools de hilos.

| Serie, ms | Media | p50 | p95 | Mínimo | Máximo |
|---|---:|---:|---:|---:|---:|
| Detector total A | 117.92 | 99.29 | 244.04 | 67.95 | 313.94 |
| Forward A | 111.49 | 93.50 | 236.78 | 64.18 | 294.94 |
| Detector total B | 103.82 | 106.51 | 121.53 | 83.44 | 135.13 |
| Forward B | 97.73 | 100.16 | 114.55 | 78.46 | 127.44 |

| Preparación excluida de las 50 medidas, ms | Serie A | Serie B |
|---|---:|---:|
| Carga y SHA-256 de pesos | 44.04 | 60.79 |
| Construcción y `setup_model` | 31.70 | 48.44 |
| Calentamiento sintético `480×640×3` | 667.10 | 1435.43 |
| Diez JPEG de calentamiento | 571.95 | 909.07 |

Antes de la corrección de hilos, las dos series históricas de este Mac dieron p95 de **29.62 y 49.95 ms**; ya no describen el código actual. Una comprobación temporal intermedia dio 167.31 ms. La variación actual entre A y B es considerable; no se eligió solo la serie rápida ni se extrapola a Windows. Reproducción desde un clon con los 29 JPEG autorizados y copiados fuera de Git:

```bash
.venv/bin/python resultados/p5-05-benchmark.py \
  --weights "$P5_05_YOLO11N_PT" \
  --image "$P5_05_NEUTRALES/ensayo-0012.jpg" \
  --output /ruta/salida/latencia-nueva-a.json
# Repetir en otro proceso con un destino nuevo: latencia-nueva-b.json.
```

El plazo inicial de B es `detector_timeout_ms=500` y `max_frame_age_ms=500` (`config/control/plazos.yaml`). El calentamiento del CLI ocurre **antes** del origen temporal del run y no emite eventos, pero estas series no demuestran por sí solas cumplimiento extremo a extremo de B. La captura histórica y el recorrido S09 de T16 preceden a esa corrección. Es necesario repetir S09 y medir Windows con el código actual. P5-06 debe aplicar `stale`/timeout según la política; no se afirma cumplimiento de plazos de B en Windows.

## Pendientes para cierre

1. A3 revisó tres JPEG en Windows. Debe completar la escena múltiple, la despejada y el juicio sobre `varios_1`/`varios_2`; las escenas múltiples actuales revelan omisiones de botella/taza. Cualquier ajuste de umbral/modelo requiere una decisión separada porque cambia configuración, hash y evidencia aprobada de P5-04.
2. P5-06 debe manejar `stale` y timeout. El calentamiento queda fuera del run, pero un cuadro realmente capturado antes del inicio o una reproducción retrasada aún puede llegar viejo; el contrato v1 valida la estructura, no demuestra seguridad temporal.
3. Ale ejecutó instalación e inferencia real en Windows 11 y observó un p95 aproximado de 153 ms con siete hilos efectivos, antes de esta corrección. La latencia vigente debe medirse de nuevo. Las dos series de la tabla superior son solo de macOS Apple M3 y usan un hilo intraop efectivo.
