# P5-05 · evidencia de aceptación CPU (actualizada 2026-11-01)

Rama `p5-05-detector-infer`, publicada en el [PR #75](https://github.com/karenelizabg/Proyecto05-MLOPS/pull/75). La evidencia de dos hilos se generó localmente después de `0bb2719`, sin commit ni push todavía. Se contrastó el [issue #7](https://github.com/karenelizabg/Proyecto05-MLOPS/issues/7) con el contrato A→B v1. Las copias neutrales `ensayo-NNNN.jpg` son las **29 capturas de selección** que P5-04 atribuye a la ESP32-CAM; no son las ocho secuencias oficiales congeladas bajo `datos-evaluacion-v1` ni una verdad de referencia anotada. Las fotos y los pesos permanecen fuera del repositorio. No se ejecutó el detector sobre S01–S08 ni se usó `datos/cuadros/` para esta decisión.

**Restricción del conjunto congelado:** está prohibido ejecutar el detector
sobre S01–S08 antes de completar el paso 2 del congelamiento y publicar el
segundo tag. El segundo tag y el registro del nuevo `config_sha256` corresponden
al procedimiento coordinado en el [issue #13](https://github.com/karenelizabg/Proyecto05-MLOPS/issues/13).
La elección de dos hilos se basó exclusivamente en las mediciones independientes
de Ale en Windows; ni S01–S08 ni las mediciones macOS fueron criterio de selección.

La [guía de revisión independiente para A3](P5-05-REVISION-A3.md) contiene comandos PowerShell. Ale aprobó formalmente el PR en el commit `621fbcc` tras revisar Windows y las omisiones. Sus mediciones posteriores de hilos fundamentan `torch_threads=2`; esta configuración nueva aún no forma parte de esa aprobación y debe revisarse después de publicarse.

## Entorno y artefactos

- MacBook Air `Mac15,12`, Apple M3 (8 núcleos: 4 rendimiento, 4 eficiencia), 16 GB RAM; macOS 27.0.1 arm64. Es una medición **macOS**, no Windows.
- Python 3.12.14; Ultralytics 8.3.0; torch 2.9.0; torchvision 0.24.0; OpenCV 4.11.0.86; NumPy 1.26.4; Pillow 12.3.0 tras integrar P5-09 desde `main`. CPU, FP32, batch 1. `DetectorJPEG` restablece **dos hilos intraop** de PyTorch después de `setup_model` y verifica `torch.get_num_threads()`; esto no controla todos los pools de OpenCV, BLAS o interop.
- Checkpoint local de 5 613 764 bytes: `model_sha256=0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`.
- Configuración efectiva actual: `config_sha256=6428a259f22939fe5055dc101cec4517612dad5fb573d5852187932f39954e08`. Solo cambió `torch_threads: 1 → 2`; el hash histórico de un hilo es `bd736aff92ac6ae39348272ec48763764edf16b30c6ba0d3847cf9bae0658fdf`.
- [Corrida A de dos hilos](p5-05-aceptacion-2h-a.jsonl), [corrida B de dos hilos](p5-05-aceptacion-2h-b.jsonl): 29 eventos cada una. [CLI individual de dos hilos](p5-05-comando-2h.jsonl): 1 evento. Son los JSONL vigentes. Las [corridas A](p5-05-aceptacion-a.jsonl) y [B](p5-05-aceptacion-b.jsonl) anteriores, [casos extra](p5-05-casos-extra.jsonl), [sin red](p5-05-sin-red.jsonl), [paso 4](p5-05-step4-real.jsonl) y [captura integrada anterior](p5-05-comando-integrado.jsonl) quedan como evidencia histórica de un hilo; sus hashes no deben confundirse con el actual.
- [Captura auténtica integrada](P5-05-COMANDO-INTEGRADO.png): muestra ambos comandos completos, `1 cuadros, 0 errores` y `OK (1 eventos)` sobre el JSONL histórico de un hilo. Heri la tomó en Terminal el 31 de octubre de 2026; la copia publicada conserva exactamente los bytes del PNG del Escritorio (SHA-256 `298513b774c519b4fc2b09325b082eb751dd38810284debb6087fad67c98f1bd`). No muestra rutas privadas ni credenciales. No existe todavía una captura de Terminal de dos hilos; el JSONL nuevo se generó con el mismo CLI y pasó el validador.
- [Captura auténtica de Terminal](P5-05-COMANDO.png): muestra la ejecución publicada anterior al cambio de `frame_id`, con [su JSONL original](p5-05-captura-evidencia.jsonl). Ambos se conservan como evidencia histórica, no como demostración del nuevo identificador; la imagen no muestra rutas privadas ni credenciales.
- [Tabla neutral por SHA-256](p5-05-fotos-neutrales.csv) y [script de copias](p5-05-preparar-fotos.py): 29 pares `neutral_name,sha256`, sin nombres originales ni fotografías en Git.
- [Latencia de dos hilos A](p5-05-latencia-2h-a.json), [réplica B](p5-05-latencia-2h-b.json) y [script reproducible](p5-05-benchmark.py): 50 muestras medidas por proceso. Las [series A](p5-05-latencia.json) y [B](p5-05-latencia-replica.json) de un hilo permanecen como evidencia histórica.

## Matriz de aceptación

| Criterio del issue #7 o del contrato | Prueba/evidencia | Resultado | Estado |
|---|---|---|---|
| JPEG real → caja, clase y confianza en CPU sin red | `botella_centro_cerca`, `botella_der`, `taza_centro_cerca`; ejecución con `socket.connect` bloqueado | Cajas visualmente alineadas; 39/41; salida sin red válida | **Cumplido en macOS** |
| Preprocesamiento BGR→RGB, letterbox y `/255` explícitos | `config/DETECTOR.md`, `src/infer/detector.py`, pruebas de tensor y proporciones | Tensor 640×480 → `1×3×480×640`; 1200×1600 → `1×3×640×480` | **Cumplido** |
| Confianza 0.25, NMS 0.70 por clase, clases `[39,41]`, cajas originales | Configuración y `tests/test_detector_jpeg.py` (NMS y `scale_boxes`) | Cajas finitas y dentro de límites en las 58 líneas nuevas | **Cumplido** |
| Pesos alterados → rechazo por SHA-256 | Copia temporal con último byte invertido; CLI terminó 2 | Hash obtenido `110fb84c…456529`; no se creó JSONL | **Cumplido** |
| Dos corridas idénticas o diferencias cuantificadas | Corridas A/B nuevas de 29 JPEG, mismo orden, pesos, configuración y entorno | 29/29 vectores idénticos; diferencias máximas 0, también frente a la corrida anterior de un hilo en este Mac | **Cumplido en este equipo** |
| JPEG central, lateral, varios y despejado; cajas originales | 29 fotos de P5-04 e inspección visual de imágenes seleccionadas | Centro/lateral correctos; ambos `vacio_*` dan `ok=[]`; en `varios_1` solo botella, en `varios_2` ninguna aunque hay objetos visibles | **Parcial: cobertura de varios objetos** |
| Revisión independiente de A3 | A3 instaló y ejecutó el PR en Windows; revisión formal en `621fbcc`; [guía](P5-05-REVISION-A3.md) | Ale aceptó las omisiones para P5-05 y aprobó el PR. La nueva configuración de dos hilos requiere revisión del commit futuro | **Parcial para la revisión nueva** |
| Copia renombrada conserva resultado; no se abren anotaciones/manifiesto | Dos copias con SHA `8e360d41…ae07` y nombres opuestos dieron la misma detección; prueba `test_infer_no_abre_anotaciones_ni_manifiesto` falla si se abre un archivo señuelo | Misma clase, confianza y bbox; señuelos ignorados | **Cumplido** |
| JSON estricto, sin `NaN` ni `Infinity` | `python -m contrato` en los tres JSONL nuevos | 59/59 eventos válidos en A, B y CLI individual de dos hilos; ninguna línea contiene esos literales | **Cumplido** |
| Un evento por cuadro; `ok=[]` y errores diferenciados | 29+29 eventos nuevos; caso corrupto y sus pruebas previas | 22 cuadros vacíos `ok=[]` en cada corrida nueva; la prueba de corrupto conserva `error/unreadable_image` | **Cumplido** |
| Evidencia JSONL en `resultados/` y captura del comando | [JSONL nuevo](p5-05-comando-2h.jsonl), [captura auténtica anterior](P5-05-COMANDO-INTEGRADO.png) y corridas A/B nuevas | Con dos hilos, `ensayo-0012` dio `1 cuadros, 0 errores` y `OK (1 eventos)`. La captura anterior documenta un hilo; falta captura nueva si se exige correspondencia visual con el hash actual | **Parcial para captura actual** |
| Rendimiento frente a B/PEND-05 | Selección de hilos por medición independiente Windows; dos series macOS nuevas; `config/control/plazos.yaml` | Windows con dos hilos: p95 138 y máximo 189 ms, según Ale. Mac: p95 40.72 y 46.86 ms. No es prueba extremo a extremo de B | **Pendiente para P5-06/P5-15/PEND-05** |

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
  --output /ruta/local/fuera-del-repo/salidas/p5-05-aceptacion-2h-a.jsonl \
  --run-id p5-05-aceptacion-2h-a --sequence-id ESP32-ensayo "${capture_args[@]}"
# Repetir con output p5-05-aceptacion-2h-b.jsonl y run-id p5-05-aceptacion-2h-b.
.venv/bin/python -m contrato /ruta/local/fuera-del-repo/salidas/p5-05-aceptacion-2h-a.jsonl
```

El calendario `0, 200, …, 5600 ms` es **un ritmo de reproducción suministrado para esta prueba**, no una medición de la captura histórica. En un JPEG individual sin tiempos originales, el CLI mide recepción durante el run. La salida de las dos corridas nuevas fue `29 cuadros, 0 errores` cada una y el validador imprimió `OK (29 eventos)` para ambas.

La [captura integrada histórica](P5-05-COMANDO-INTEGRADO.png) corresponde a una
ejecución real de Heri en Terminal **con un hilo**. Después de definir las
variables anteriores y ocultar sus rutas privadas de la pantalla, ejecutó:

```bash
.venv/bin/python -m infer --input "$P5_05_NEUTRALES/ensayo-0012.jpg" \
  --config config/detector.json --weights "$P5_05_YOLO11N_PT" \
  --output resultados/p5-05-comando-integrado.jsonl --run-id p5-05-comando-integrado
.venv/bin/python -m contrato resultados/p5-05-comando-integrado.jsonl
```

La captura muestra ambos comandos completos, `1 cuadros, 0 errores` y
`OK (1 eventos)`. [Su JSONL histórico](p5-05-comando-integrado.jsonl) pasó el
contrato v1 y contiene `frame_id=ensayo-0012`, `status=ok` y una detección.
Para dos hilos, repetir con `--output resultados/p5-05-comando-2h.jsonl` y
`--run-id p5-05-comando-2h`, usando un destino nuevo. El [JSONL nuevo](p5-05-comando-2h.jsonl)
fue generado realmente y validado (`1 cuadros, 0 errores`; `OK (1 eventos)`),
pero no tiene una captura de Terminal nueva. La captura más antigua permanece
como evidencia histórica de [su propio JSONL](p5-05-captura-evidencia.jsonl).

Para el conjunto adicional se copiaron dos veces los mismos bytes de `botella_der.jpg` como `S00_f0001.jpg` y `S00_f0002.jpg`, se copió `docs/carro/atras.jpg` como `S00_f0003.jpg` y se creó `S00_f0004.jpg` corrupto. Se añadieron `anotaciones.json` y `manifiesto.csv` señuelo en la prueba original; no son entrada del detector. La nueva ejecución usó `--capture-ms 0 --capture-ms 200 --capture-ms 400 --capture-ms 600`, devolvió código 1 por el cuadro corrupto y produjo **cuatro eventos válidos** con las mismas detecciones y estados anteriores. Las dos copias del mismo JPEG tienen SHA-256 idéntico y detecciones iguales, pero `frame_id` diferentes. La ejecución sin red usó una copia `S01_f0001.jpg` y la del paso 4 una copia `S02_f0001.jpg`. `error.message` conserva un texto estable sin ruta local y `error.code` conserva `unreadable_image`. El detalle original, incluida la ruta, queda en stderr local para diagnóstico y no forma parte del JSONL publicable.

La prueba de pesos alterados cambió **una copia temporal** (no el checkpoint original). `python -m infer` devolvió código 2 por discrepancia de SHA-256 y no creó salida. La ejecución sin red sustituyó `socket.connect`, `connect_ex` y `create_connection` por funciones que lanzan error; el CLI produjo una botella válida y el JSONL pasó el contrato.

## Reproducibilidad y latencia

Se compararon por `frame_id` los 29 arrays `detections` de las corridas nuevas de **dos hilos** A y B, excluyendo `run_id` y tiempos. Coinciden exactamente estado, conteo, orden, clase, confianza y cuatro coordenadas: `29/29` vectores idénticos, diferencia máxima de confianza `0` y de bbox `0 px`. Cada run contiene 7 detecciones y 22 cuadros sin detecciones. Frente a la corrida A histórica de **un hilo**, también coincidieron los `29/29` vectores exactamente en este Mac; esto es una observación de estas ejecuciones, no una garantía bit a bit entre plataformas. El primer `t_emit_ms` fue 38.23 ms en A y 37.13 ms en B; el calentamiento ocurrió antes del reloj. Los 59 eventos nuevos tienen `config_sha256=6428a259f22939fe5055dc101cec4517612dad5fb573d5852187932f39954e08` y el mismo `model_sha256` aprobado.

## Selección de hilos en Windows

Ale midió independientemente en Windows 11, i5-1135G7 y 8 GB RAM, con la laptop conectada. Para cada número de hilos usó un proceso independiente, calentamiento del predictor, diez inferencias JPEG excluidas y 50 medidas; verificó el número efectivo. Karen fijó **antes** la regla: elegir el menor número con p95 ≤ 150 ms y máximo ≤ 200 ms. Son resultados comunicados por Ale; los archivos de muestras Windows no se generaron en este Mac ni están en este repositorio.

| Hilos efectivos | p95 Windows, ms | Máximo Windows, ms | Regla |
|---:|---:|---:|---|
| 1 | 158 | 210 | No cumple |
| **2** | **138** | **189** | **Elegido: menor que cumple** |
| 4 | 129 | 168 | Cumple, pero usa más hilos |
| 7 | 161 | 218 | No cumple |

Dos hilos dejan **12 ms** de margen hasta el límite p95 y **11 ms** hasta el máximo. Es un margen observado en esa laptop conectada; la latencia puede variar entre procesos, carga del equipo y estados de energía. Una sola serie por configuración no caracteriza todas esas condiciones. No se ajustaron el modelo, umbral ni clases usando las secuencias oficiales congeladas.

## Benchmark macOS con dos hilos

El benchmark usó `ensayo-0012.jpg`, copia byte a byte de la taza central con SHA-256 `670fec5473ceda61b5a6283711596d610d75577dfb1bc9d5ffc8de52c1e9cbcc`: 640×480, tensor `1×3×480×640`. Se ejecutó dos veces en procesos independientes sobre macOS arm64, Python 3.12.14, Torch 2.9.0, Ultralytics 8.3.0 y OpenCV 4.11.0.86. En cada serie se cronometraron **por separado** la carga verificada de pesos, la construcción del detector, un calentamiento sintético mediante `predictor(...)` y diez inferencias JPEG de calentamiento. Después se midieron 50 inferencias JPEG. `detector_total_ms` comprende lectura JPEG, predictor y validación/posprocesamiento; no incluye carga ni calentamientos. `forward_ms` es `Results.speed["inference"]`. p95 usa interpolación lineal de NumPy. Ambos JSON conservan todas las muestras y registran **dos** hilos intraop configurados, tras `setup_model`, tras calentar y después de inferir; no miden los otros pools de hilos. Las mediciones de este Mac **no** determinaron la elección de dos hilos.

| Serie, ms | Media | p50 | p95 | Mínimo | Máximo |
|---|---:|---:|---:|---:|---:|
| Detector total A | 32.61 | 31.00 | 40.72 | 29.64 | 47.07 |
| Forward A | 30.66 | 29.07 | 37.92 | 27.89 | 45.07 |
| Detector total B | 37.49 | 35.00 | 46.86 | 30.69 | 48.70 |
| Forward B | 35.23 | 32.59 | 44.18 | 28.87 | 46.36 |

| Preparación excluida de las 50 medidas, ms | Serie A | Serie B |
|---|---:|---:|
| Carga y SHA-256 de pesos | 45.98 | 25.89 |
| Construcción y `setup_model` | 30.23 | 16.57 |
| Calentamiento sintético `480×640×3` | 666.29 | 574.15 |
| Diez JPEG de calentamiento | 316.89 | 351.10 |

Las nuevas series A/B difieren **6.13 ms en p95** (40.72 frente a 46.86 ms), aun con el mismo checkpoint y configuración. Las series históricas de un hilo dieron p95 de **244.04 y 121.53 ms** en este Mac, una diferencia considerable; quedan en sus JSON originales y no se mezclan con las nuevas. Los resultados macOS no se extrapolan a Windows. Reproducción desde un clon con los 29 JPEG autorizados y copiados fuera de Git:

```bash
.venv/bin/python resultados/p5-05-benchmark.py \
  --weights "$P5_05_YOLO11N_PT" \
  --image "$P5_05_NEUTRALES/ensayo-0012.jpg" \
  --output /ruta/salida/p5-05-latencia-2h-a.json
# Repetir en otro proceso con un destino nuevo: p5-05-latencia-2h-b.json.
```

El plazo inicial de B es `detector_timeout_ms=500` y `max_frame_age_ms=500` (`config/control/plazos.yaml`). El calentamiento del CLI ocurre **antes** del origen temporal del run y no emite eventos, pero estas series no demuestran por sí solas cumplimiento extremo a extremo de B. La captura histórica y el recorrido S09 de T16 preceden a esa corrección. P5-06 debe aplicar `stale`/timeout según la política; los resultados Windows comunicados no prueban por sí solos los plazos extremo a extremo de B.

## Pendientes para cierre

1. Ale aprobó formalmente el PR y consideró aceptables para P5-05 las omisiones repetidas de `varios_1`/`varios_2`. La configuración de dos hilos requiere una nueva revisión del cambio y del hash. Las escenas múltiples siguen revelando omisiones relevantes para métricas; cualquier ajuste de umbral/modelo requeriría una decisión separada.
2. P5-06 debe manejar `stale` y timeout. El calentamiento queda fuera del run, pero un cuadro realmente capturado antes del inicio o una reproducción retrasada aún puede llegar viejo; el contrato v1 valida la estructura, no demuestra seguridad temporal.
3. Los cuatro resultados de selección Windows proceden de Ale; faltan sus muestras brutas en el repositorio y una ejecución Windows con el nuevo `config_sha256` una vez publicado. La captura auténtica actual es histórica y no demuestra visualmente el hash de dos hilos. Las dos series de la tabla macOS son solo de Apple M3 y usan dos hilos intraop efectivos.
