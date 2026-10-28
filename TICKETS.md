# Tickets — Proyecto 5 · Mini Tesla · Grupo A (Percepción y datos)

> **Versión 2 — 2026-10-23.** Reemplaza el borrador anterior, que asumía un alcance MLOps/AWS que la guía
> oficial de P5 **no** pide. Este backlog sale de la guía
> (`~/Downloads/guia-pm-proyecto-5.html`, que no está en el repo) y cubre **solo al grupo A**:
> PM A + A1 (detector y runtime) + A2 (secuencias y anotaciones) + A3 (métricas y benchmark).
> Los tickets del grupo B (política, adaptador, casos C1–C10, integración) los lleva su PM.
>
> **Entrega: viernes 30 de octubre de 2026.** Quedan 7 días: el 29 se reserva para reproducir desde una copia
> limpia y el 30 para el cierre conjunto.
>
> **2026-10-26 — el carro está decidido:** es el kit que recomendó el profe (D-07). Se ajustaron PEND-06 y
> PEND-12, se agregó PEND-13 y el ticket P5-19 (armar el carro) y cambiaron P5-03, P5-04, P5-09, P5-12, el plan y
> los riesgos. Los PR de los tickets los revisan entre sí los tres devs (sección 3).
>
> **2026-10-26 — ya está la rúbrica detallada** (PEND-07 cerrado): `entregables-proyecto-5.md` y
> `prompt-evaluacion-proyecto-5.md`, en `~/Downloads`, que tampoco están en el repo. Cambiaron D-05 y D-06
> (sin ajuste: las 8 secuencias son evaluación), PEND-04 (objetos que el detector sí reconoce) y los tickets
> P5-03, P5-04, P5-05, P5-10, P5-11 y P5-13.

## Leyenda

| Marca | Significa |
|---|---|
| `[GUÍA]` | Lo pide literalmente la guía de P5. |
| `[SUGERENCIA]` | Propuesta mía para cumplir la guía; se puede cambiar. |
| `[PENDIENTE]` | Falta un dato; el ticket dice cuál (`PEND-NN`) y qué valor provisional se usó. |

**Tamaño** (por persona, provisional): `S` ≤ 2 h · `M` ≈ medio día · `L` ≈ un día.
**Prioridad:** `P0` si su ausencia rompe un entregable o activa la compuerta de 60 · `P1` suma puntos · `P2` deseable.
**Bloque:** los siete bloques del plan de la guía (sección 5). Las fechas son sugeridas y ajustables.

---

## 1. Qué pide la guía y qué le toca al grupo A

**Producto:** un detector que da **cajas, clase y confianza sobre cuadros completos**, una política temporal que
decide avanzar / girar / STOP y un adaptador virtual que registra velocidad y dirección **sin mover motores**.
Se evalúa desde archivos y código, **offline y en CPU**. No hay demo en vivo, ni AWS, ni GPU, ni API de pago,
ni portal nuevo, ni video.

**Una sola entrega y una sola nota (100 pts):** detector y localización 25 · decisiones de control 25 ·
respuesta a fallos y parada 20 · trazabilidad y medición 15 · reproducción y entrega 15.
**Compuerta de 60:** si no hay detector ejecutable, recorrido hasta el control virtual, o STOP efectivo ante
pérdida de percepción o emergencia, la nota se topa en 60.

**Entregables** (el grupo A lleva los marcados con ●; los demás son del B o compartidos):

| | Entregable | Lo que pide |
|---|---|---|
| ◐ | E1 · Repositorio y README | Ocho nombres, dos grupos, responsabilidades, versión; instalación fijada y comandos para inferir, reproducir, probar y medir. |
| ● | E2 · Detector ejecutable | Pesos, origen, **licencia**, SHA-256, clases, pre y posprocesamiento; cajas, clases y confianza. Se permite uno preentrenado. |
| ● | E3 · Secuencias etiquetadas | **60 cuadros distintos, ≥ 6 secuencias, ≥ 20 con obstáculo y ≥ 20 despejados.** IDs, tiempo relativo, cajas, estado esperado y separación de ajuste y evaluación (o la declaración de que no hubo ajuste, D-06). Imágenes extraídas: el video no sustituye. |
| ○ | E4 · Política y control virtual | (Grupo B.) |
| ○ | E5 · Diez casos C1–C10 | (Grupo B ejecuta; **A aporta las secuencias** de C1–C5 y C7, aclara scores para C6 y define los errores de C9.) |
| ● | E6 · Resultados y métricas | Detecciones, decisiones y comandos por cuadro; TP/FP/FN, precisión, recall y F1 a IoU 0.50 con **script de recálculo**. Las cifras resumidas no bastan. |
| ● | E7 · Benchmark y límites | 10 calentamientos + 100 ejecuciones válidas, tiempos por etapa, p50/p95, hardware/runtime, tamaño de pesos y límites. Registros individuales. |

**Lo que A entrega a B:** un detector inferible, datos etiquetados y detecciones con un **contrato estable**
(`run_id`, `sequence_id`, `frame_id`, `t_capture_ms`, dimensiones, `model_sha256`, `config_sha256`,
`status` ok/stale/error, `detections[]` con `class_id`/`confidence`/`bbox`, `bbox_format`).
Un cuadro sin objetos es `status=ok` con lista vacía; **un error o la falta de cuadros nunca equivale a vía libre.**

**Cuánto vale la calidad del detector.** El criterio 1.4 puntúa `floor(12 × F1) / 2`, hasta 6 puntos:

| F1 | 0.50 | 0.70 | 0.80 | 0.90 | 1.00 |
|---|---|---|---|---|---|
| Puntos (de 6) | 3 | 4 | 4.5 | 5 | 6 |

Pasar de F1 0.90 a 1.00 vale 1 punto de 100. **No conviene invertir días en mejorar el modelo**: un detector
preentrenado razonable y mucho cuidado en datos, trazabilidad, errores y reproducción rinde más.
**Topes de la rúbrica (PEND-07, cerrado):** el F1 es **micro**, a IoU 0.50 y con el umbral de confianza
**congelado**. Las predicciones deben cubrir todo el conjunto entregado y salir de los pesos verificados; si no se
puede acreditar de dónde salen, el crédito queda pendiente, y sin verdad de referencia o con fuga demostrada es 0.
Si no se cumplen los mínimos de E3 (60 cuadros, 6 secuencias, 20 con obstáculo y 20 despejados), 1.3 pierde puntos
y 1.4 se limita a 3 de 6.

**Fuera de alcance (la guía lo dice):** entrenar un modelo nuevo, GPU, API de pago, nuevo portal, AWS, video,
SLAM, simulación física. No hay que convertir el clasificador cat/dog de P3/P4 en detector, y su 85 % de
exactitud **no** es la métrica de esta entrega.

---

## 2. Pendientes de datos

Nada de esto frena el arranque: cada fila dice qué usé mientras tanto.

| ID | Qué falta | Quién lo da | Bloquea | Valor provisional |
|---|---|---|---|---|
| PEND-01 | **Quién es A1, A2 y A3** (y su usuario de GitHub) y quién es el PM A. En P4 el equipo era Karen, Ale y Heri, pero P5 son 8 personas en dos grupos y no sé si repiten. | PM A | Asignación de todos los tickets | Roles A1/A2/A3 sin nombres. *Sugerencia:* quien llevó modelo, conversión y benchmark en P4 (Karen) encaja en A1 o A3. |
| PEND-02 | **PM B y su grupo:** contacto, rango de numeración de tickets y quién cierra el contrato. | PM A | P5-02, P5-08 | Numeración: grupo A usa `P5-01…49`, grupo B `P5-50…`. |
| PEND-03 | **Repositorio oficial único** para los dos grupos. El `origin` de este clon es `github.com/karenelizabg/Proyecto05-MLOPS`; confirmar que es el oficial, que B tiene acceso y si será **público o se entrega ZIP** (el evaluador debe acceder sin intervención del equipo; el repo de P4 era privado). | PM A + PM B | P5-01, P5-17 | Se usa el `origin` actual, privado, hasta decidir. |
| PEND-04 | **Dominio de obstáculos y clases** (qué objetos, qué escena, qué cámara). Lo deciden ambos PM. | PM A + PM B | P5-03, P5-04, P5-09 | El equipo A propuso primero **lata de refresco, mochila, cajas, tenis**, pero de esas solo "mochila" es clase COCO. El 2026-10-26 A2 propuso cambiar a objetos que el detector sí reconoce: **mochila, botella, taza, silla o maleta** (`backpack`, `bottle`, `cup`, `chair`, `suitcase`); interior, piso plano, buena luz. **Sujeto a la prueba de A1 en P5-04**, con fotos a 640×480 y JPEG: se eligen 3 o 4 de los de mejor detección y los PM A y B los aprueban (DC-5) **antes de filmar**; sin confirmar con B todavía. La rúbrica pide que los objetos laterales (C3, C4) estén anotados **y detectados**, así que un objeto que el detector no reconoce no sirve. La silla puede dar cajas inestables por las patas, y la taza debe ser más alta que el radio de la llanta (PEND-12) o es transitable. Si ninguno funciona, se cambia de detector (D-01). Lo más bajo que la llanta es *transitable* y queda fuera (ver P5-03). |
| PEND-05 | **Máquina de evaluación y benchmark:** SO, CPU, RAM. El benchmark debe medirse en el equipo declarado. | A3 | P5-15 | La laptop que use A3; si es la ASUS de P4 (i5-7300HQ, 8 GB, Windows 10), ya hay ficha de hardware en P4. |
| PEND-06 | **Cámara y quién filma.** El carro es el que recomendó el profe: **Kit Carrito ESP32-CAM 4WD** (UNIT Electronics SKU AR4510, TSCINBUNY ZYC0024-EN). Trae una placa ESP32-CAM con sensor OV2640, ranura SD, puente H L298, 4 motorreductores y 4 llantas de goma, y transmite video por WiFi a una página web. La ficha **no** dice la resolución de transmisión, si el foco es fijo o ajustable, el ángulo de visión ni a qué altura queda la cámara. El OV2640 comprime en JPEG y rinde peor con poca luz (confirmar en el módulo). Hay que anotar altura y ángulo de la cámara montada. | PM A | P5-03, P5-04, P5-09 | Filmar con la propia ESP32-CAM (misma óptica, resolución y compresión que vería el carro), a 640×480. Plan B si no transmite a tiempo: celular a baja altura, horizontal y reescalado a 640×480 (D-07). |
| PEND-07 | **Rúbrica detallada y prompt de evaluación** (la guía los enlaza como "Entregables detallados" y "Rúbrica y prompt de evaluación"; no están en el HTML). Incluye topes y detalles del criterio 1.4. | PM A | — (cerrado) | **Cerrado 2026-10-26:** Karen consiguió los dos documentos (`entregables-proyecto-5.md` y `prompt-evaluacion-proyecto-5.md`, en `~/Downloads`, no están en el repo). Cambiaron D-05, D-06, PEND-04, P5-03, P5-04, P5-05, P5-10, P5-11 y P5-13. |
| PEND-08 | **Formato de caja y de anotación** acordado con B (`xyxy` o `xywh`, píxeles del cuadro original, origen arriba-izquierda). | PM A + PM B | P5-02, P5-10 | `xyxy` en píxeles del cuadro original (ver D-04). |
| PEND-09 | **Ritmo de entrada** (fps de las secuencias) y plazos que B usará en el watchdog. A debe poder cumplirlos con su p95. | PM B | P5-05, P5-16 | Secuencias a ~5 fps (200 ms entre cuadros); ajustar cuando B declare plazos. |
| PEND-10 | **Fechas internas** de cada bloque (los campos "Fecha objetivo" de la guía están vacíos). | PM A + PM B | Plan de la sección 5 | Las fechas sugeridas de la sección 5. |
| PEND-11 | **Dónde viven los archivos grandes** (pesos, imágenes): dentro de Git o fuera con descarga automatizable + hash (la guía lo permite). | PM A + PM B | P5-07, P5-11 | Si pesan poco (< 50 MB) dentro de Git; si no, GitHub Release con SHA-256 y script de descarga. |
| PEND-12 | **Medidas del carro:** diámetro de llanta, altura libre del chasis, ancho, y altura y ángulo de la cámara. Con eso se fija la altura mínima de un obstáculo (un borrador, más bajo que la llanta, es transitable). **Pendiente:** la ficha del kit en UNIT Electronics (acrílico, caja de 275 × 170 × 50 mm, 795 g) no da el diámetro de llanta ni la altura libre. No hay dato hasta medir el carro armado. | Quien tenga el carro | P5-03, P5-09, P5-10, P5-19 | Sin valor: medirlo en P5-19 (10 minutos). Mientras tanto, objetos como un borrador, una tapa o un cable se tratan como transitables y no se fija ninguna altura mínima de obstáculo hasta tener la medida. |
| PEND-13 | **Baterías y quién arma el carro.** El kit **no incluye baterías** (18650, 6–7.4 V; ver cuántas en el instructivo) ni cargador. Armarlo y ponerlo a transmitir pide, según la ficha: el cable USB-C (viene en el kit), el IDE de Arduino con el soporte ESP32, el driver USB-serial CH340 y una red WiFi de **2.4 GHz**. **No es solo para Windows:** el IDE y el soporte ESP32 también existen para macOS; la ficha solo enlaza el driver de Windows, así que en Mac hay que comprobar si la placa aparece como puerto serial o instalar el driver CH340 de WCH. | PM A | P5-19 | Sin valor: decidir quién compra las baterías (los tres arman el carro en P5-19). Plan B: celular (D-07). |

### Decisiones abiertas (con default para no esperar)

| ID | Decisión | Default | Dueño |
|---|---|---|---|
| D-01 | Detector: cuál usar. | Un detector **COCO preentrenado y ligero**, evaluado en CPU. Candidatos a revisar: YOLOX (Apache-2.0), SSDlite con MobileNetV3 de torchvision (BSD-3 el código; revisar la licencia de los pesos). Los YOLO de Ultralytics son AGPL-3.0: se permiten, pero hay que **declarar la licencia**. Verificar licencias vigentes al elegir. | A1 (P5-04) |
| D-02 | Runtime: ONNX Runtime o PyTorch. | ONNX Runtime en CPU: instalación más liviana y el equipo ya lo usó en P4 (fijó `onnxruntime==1.30.0`, que exige Python ≥ 3.11). El NMS y el posprocesamiento hay que escribirlos y documentarlos. | A1 |
| D-03 | Herramienta de anotación. | La que el equipo pueda levantar en menos de una hora y exporte COCO (el portal de P1/P2 de `Proyecto04-MLOps` exporta COCO, pero exige Docker, MariaDB y MinIO). Luego un script convierte a manifiesto. | A2 |
| D-04 | Formato de caja. | `xyxy`, píxeles del cuadro **original** (deshacer cualquier redimensionado o *letterbox* antes de emitir). | A1 + B3 |
| D-05 | Tamaño del conjunto. | **8 secuencias, unos 80 a 90 cuadros**: 10 por secuencia y más en la de C7, que necesita varios cuadros libres, el bloqueo y varios libres otra vez. Mínimo exigido: 60 cuadros y 6 secuencias **en el conjunto de evaluación**, con ≥ 20 de obstáculo y ≥ 20 despejados; el objetivo es ≥ 30 y ≥ 30 para tener margen si algún cuadro se descarta por duplicado. | A2 |
| D-06 | Separación ajuste / evaluación. | **Sin ajuste** (propuesta de A2 del 2026-10-26, aceptada por el PM A). Los 60 cuadros mínimos son el conjunto de evaluación, así que con 3 secuencias de ajuste y 5 de evaluación (50 cuadros, 5 secuencias) no se llegaba al mínimo. Se usa un detector preentrenado con umbral de confianza y NMS fijados **antes** de correr sobre los cuadros (en `config/`, con su hash), y las 8 secuencias son evaluación. Las fotos que sirvan para escoger detector y objetos (P5-04, P5-19) quedan **fuera** de las 8 secuencias. Se declara por escrito en `datos/README.md`. Las métricas se reportan sobre todo el conjunto, que es la evaluación. Si luego se quisiera ajustar, hay que filmar secuencias aparte. | A2 + A3 |
| D-07 | Carro y cámara de captura. | **Decidido (lo recomendó el profe):** Kit Carrito ESP32-CAM 4WD (UNIT Electronics SKU AR4510, TSCINBUNY ZYC0024-EN). Se filma con su propia cámara (OV2640) a 640×480; si no transmite a tiempo, plan B con celular reescalado a 640×480 (PEND-06). | PM A |

---

## 3. Equipo y reparto

`S`=1, `M`=2, `L`=3 puntos. Los nombres son `[PENDIENTE]` (PEND-01).

| Rol | Responsabilidad en la guía | Tickets | Carga |
|---|---|---|---|
| **A1** · detector y runtime | Carga de pesos, inferencia real, clases, cajas, CPU | P5-02, 04, 05, 06, 07, 08 y 19 (compartido) | 15 pts |
| **A2** · secuencias y anotaciones | Cuadros, verdad de referencia, IDs, separación por secuencia | P5-03, 09, 10, 11, 12, 17, 18 y 19 (compartido) | 15 pts |
| **A3** · métricas y benchmark | TP/FP/FN, F1, mediciones individuales, límites | P5-01, 13, 14, 15, 16 y 19 (compartido) | 14 pts |

**PM A** (no son tickets de dev): aceptar el contrato junto con el PM B, mantener el seguimiento diario,
**validar modelo, datos y mediciones** al cierre (guía, sección 10) y conseguir las respuestas de PEND-01 a PEND-13.

**Convenciones heredadas de P4:** un ticket = una rama = un PR; rama `p5-NN-descripcion`, commits
`P5-NN: qué cambia`, título del PR `P5-NN: descripción`; en el PR, qué probaste y **qué no pudiste probar**;
nunca secretos. El CI de P4 **rechaza ramas `p5-`** (`check-naming.sh` solo acepta `p2|p3|p4`): P5-01 lo arregla.

**Revisión cruzada.** Cada PR lo abre su responsable y lo aprueba el revisor asignado antes de fusionarse;
nadie aprueba su propio PR. El PM A no revisa los PR de los tickets: valida al cierre (guía, sección 10).
Cada ticket lleva su revisor en la línea `Revisa el PR`. P5-19 lo hacen los tres y se revisan entre sí.

| Tickets | Revisor |
|---|---|
| P5-01, P5-03, P5-09, P5-12, P5-15, P5-18 | A1 · Heri (`BeetlejuiceXD`) |
| P5-04, P5-06, P5-07, P5-13, P5-14, P5-16 | A2 · Andy (`Andy-752109`) |
| P5-02, P5-05, P5-08, P5-10, P5-11, P5-17 | A3 · Ale (`AleSarahi`) |

---

## 4. Orden de ejecución y dependencias

| Ticket | Depende de |
|---|---|
| P5-01 | PEND-03 |
| P5-02 | PEND-02, PEND-08 |
| P5-03 | PEND-04, PEND-06, PEND-12 |
| P5-04 | PEND-04 (y P5-19 para las fotos con la ESP32-CAM) |
| P5-05 | P5-02, P5-04 |
| P5-06 | P5-05 |
| P5-07 | P5-05 (y P5-04 para la licencia) |
| P5-08 | P5-05, P5-09 (primer lote) |
| P5-09 | P5-03, P5-19 |
| P5-10 | P5-09 |
| P5-11 | P5-10 |
| P5-12 | P5-03, P5-09 |
| P5-13 | P5-02 (para probar con datos sintéticos); datos reales con P5-11 |
| P5-14 | P5-02, P5-08 |
| P5-15 | P5-01; medición final con P5-05 |
| P5-16 | P5-15, declaración de plazos de B (PEND-09) |
| P5-17 | P5-07, P5-11, P5-13, P5-15 |
| P5-18 | P5-11 |
| P5-19 | PEND-13 |

---

## 5. Plan sugerido (los 7 bloques de la guía)

Hoy es viernes 23. Las fechas son mías (PEND-10). Dos adelantos respecto a lo mínimo: **filmar el fin de semana**
y **tener el primer recorrido completo el lunes**, no el miércoles.

| Bloque | Fechas | Qué pasa (grupo A) | Salida que se exige |
|---|---|---|---|
| **1** · Acordar dominio y contrato (ambos PM) | vie 23 – sáb 24 | P5-01, P5-02, P5-03, P5-04 | Contrato v1 con ejemplo válido, vacío y fallido, **aceptado por ambos PM antes de separar tareas**. |
| **2** · Primera entrega por grupo | sáb 24 – dom 25 | P5-05 (inferir una imagen real), P5-19 (armar el carro y verificar el video de la ESP32-CAM; PEND-13), P5-09 (empezar a filmar), P5-13 y P5-15 con datos sintéticos | Inferencia real en CPU; primer lote de 2–3 secuencias para que B pruebe. |
| **3** · Congelar datos | dom 25 – lun 26 | P5-09, P5-10, P5-11, P5-12 | **Datos de evaluación congelados** (hash). Los casos de B no se ajustan para aprobar. |
| **4** · Conectar detector real y control virtual | lun 26 – mar 27 | P5-08, P5-14, P5-06 | Primer cuadro real → detecciones → comando. C1–C5 y C7 con secuencias **reales**, no solo sintéticas. |
| **5** · Paradas y calidad de detección | mar 27 – mié 28 | P5-13 final sobre todo el conjunto, P5-06 cerrado | TP/FP/FN de todo el conjunto; B cierra C8–C10. |
| **6** · Medir y ejecutar desde copia limpia | mié 28 – jue 29 | P5-15 medición final, P5-16, P5-07 final, P5-17 | Benchmark, métricas y comandos documentados; p95 y máximo contrastados con el presupuesto. |
| **7** · Cierre | jue 29 (repro) – vie 30 (cierre) | P5-17, P5-18; PM A valida | Un solo paquete con E1–E7 y los ocho responsables identificados. |

---

## 6. Tickets

### Bloque 1 — Contrato, repo y decisiones de dominio

#### P5-01 · Repositorio, entorno fijado y CI mínimo
- **Responsable:** A3 · **Tamaño:** M · **Prioridad:** P0 · **Bloque:** 1 · **Marca:** `[GUÍA]` E1 + `[SUGERENCIA]`
- **Revisa el PR:** A1 · Heri (`BeetlejuiceXD`)
- **Depende de:** PEND-03
- **Por qué:** E1 pide instalación fijada y comandos para inferir, reproducir, probar y medir; el CI de P4 rechaza ramas `p5-`.
- **Alcance**
  - Esqueleto con la carpeta sugerida por la guía: `README.md`, `modelo/`, `config/`, `datos/`, `src/`, `casos/`, `resultados/`, `mediciones/` (dentro de `entrega-p5/` o en la raíz; se aceptan otros nombres).
  - Entorno fijado con lockfile (`uv`, como en P4) y versión de Python declarada; modo CPU y motores desconectados por defecto.
  - CI mínimo: lint (`ruff`) + `pytest`. **Copiar solo lo que haga falta de `Proyecto04-MLOps`** (`.github/scripts/check-naming.sh`, `pr-hygiene.yml`, `ci.yml` recortado, `CONTRIBUTING.md`) y agregar `p5` a los prefijos. **No importar** el monolito de P4 (portal, backend, terraform, DVC): no se evalúa.
  - `.gitignore` con `.env`, caches y datos pesados; ningún secreto.
- **Criterios de aceptación**
  - [ ] `bash .github/scripts/check-naming.sh "p5-01-repo-base" "P5-01: repo base"` sale con 0; `p6-01-x` sigue fallando.
  - [ ] Clon limpio → instalar → `pytest` verde con un test de humo.
  - [ ] El grupo B puede clonar y crear su rama (PEND-03).
- **Pendientes:** PEND-03, PEND-02 (estructura compartida con B).

#### P5-02 · Contrato A → B v1 (esquema, ejemplos y validador)
- **Responsable:** A1 (con B3) · **Tamaño:** M · **Prioridad:** P0 · **Bloque:** 1 · **Marca:** `[GUÍA]`
- **Revisa el PR:** A3 · Ale (`AleSarahi`)
- **Depende de:** PEND-02, PEND-08
- **Por qué:** es la frontera entre los dos grupos; si cambia coordenadas, clases o tiempos sin versión, B produce comandos equivocados.
- **Alcance**
  - JSON Schema versionado (`v1`) para el evento de percepción: `run_id`, `sequence_id`, `frame_id`, `t_capture_ms` (tiempo relativo **monotónico**), `image_width/height`, `model_sha256`, `config_sha256`, `status` (`ok`/`stale`/`error`), `detections[]` (`class_id`, `confidence`, `bbox`) y `bbox_format` con su unidad.
  - **Tres ejemplos:** válido con detecciones, válido **vacío** (`ok` + lista vacía) y **fallido** (`error`, sin detecciones). Dejar claro que error o ausencia de cuadro ≠ vía libre.
  - Validador reutilizable (`jsonschema`; en P4 está el patrón en `edge/event_validator.py`) y pruebas.
  - Regla de cambios: toda modificación sube la versión y la aprueban ambos PM; B debe reconocer la versión antes de producir comandos.
- **Criterios de aceptación**
  - [ ] Los tres ejemplos validan o fallan como corresponde (pruebas).
  - [ ] **Ambos PM aceptan el mismo contrato** (comentario o aprobación del PR de B3 y del PM B).
  - [ ] Documentadas las unidades de `bbox` y `t_capture_ms` y el significado de `stale`.
- **Evidencia:** PR aprobado por A y B; ejemplos en `config/`.
- **Pendientes:** PEND-02, PEND-08.
- **Estado:** v1 en `main` (esquema, 4 ejemplos, flujo de ejemplo, [CONTRATO.md](config/contrato/CONTRATO.md)) con validador en `src/contrato/` y pruebas en `tests/test_contrato.py`. Aceptado por el PM A y revisado por el PM B (2026-10-26). Solo queda abierta DC-5 (clases, con P5-04) y el recorrido con el detector real (P5-08).

#### P5-03 · Dominio de obstáculos, clases y plan de filmación
- **Responsable:** A2 · **Tamaño:** S · **Prioridad:** P0 · **Bloque:** 1 · **Marca:** `[GUÍA]` + `[SUGERENCIA]`
- **Revisa el PR:** A1 · Heri (`BeetlejuiceXD`)
- **Depende de:** PEND-04, PEND-06
- **Por qué:** sin dominio acordado no se sabe qué filmar ni qué clases etiquetar; las secuencias deben cubrir los casos de B.
- **Alcance**
  - Documento `datos/DOMINIO.md`: escena, iluminación, clases reconocidas y **limitaciones declaradas (qué no cubre)**. Debe incluir:
    - **Regla de obstáculo vs. objeto transitable.** Obstáculo es lo que el carro no puede cruzar. Propuesta: altura mayor que el radio de la llanta (½ diámetro) o que la altura libre del chasis, lo que sea menor; **medirla** (PEND-12). Algo más bajo, como un borrador, una tapa o un cable, es *transitable*: no se etiqueta, no está en las clases relevantes y **no debe provocar STOP** (si no, el carro "siempre se detiene", que la guía no acepta).
    - **Tabla de objetos de prueba** con su altura medida y veredicto (obstáculo / transitable), de preferencia comprobado pasando el carro por encima.
    - **Lo que el sistema no cubre:** objetos sin clase en el detector (COCO no tiene "caja", "cono" ni "borrador"); desniveles, huecos y bordes; objetos transparentes o reflejantes; poca luz o desenfoque por movimiento; objetos fuera del campo de visión o pegados a las llantas; y distancia o altura reales, que una sola cámara no mide (solo se infieren por clase, tamaño y posición de la caja).
    - **Carro y cámara** (D-07): modelo del kit, resolución de captura, altura y ángulo de la cámara montada, tipo de foco (la ficha no lo dice) y lo que eso implica: una cámara baja deja fuera lo pegado a las llantas, y el OV2640 comprime en JPEG y rinde peor con poca luz. Los datos salen de `datos/CARRO.md` (P5-19).
  - **Matriz de secuencias × casos** (propuesta de 8 secuencias):

    | Seq | Escena | Casos que sirve |
    |---|---|---|
    | S1 | Vía despejada | C1 |
    | S2 | Obstáculo central | C2 |
    | S3 | Obstáculo izquierdo | C3 |
    | S4 | Obstáculo derecho (espejo de S3) | C4 |
    | S5 | Varios obstáculos | C5 (STOP si no hay zona libre) |
    | S6 | Libre → bloqueo → libre | C7 |
    | S7 | Objeto cerca del umbral de confianza (parcial, lejano, poca luz) | C6 |
    | S8 | Segundo despejado con otra escena/luz **y objetos bajos transitables en la vía (borrador, tapa, cable)**: esperado = despejado | C1, negativos |

  - Para cada secuencia: número de cuadros, ritmo y quién la filma.
- **Criterios de aceptación**
  - [ ] Cada caso C1–C7 tiene al menos una secuencia asignada.
  - [ ] El plan declara que no hay ajuste y que las 8 secuencias son evaluación (D-06) **antes** de filmar.
  - [ ] Los PM de A y B aprobaron las clases, y todas existen en el detector elegido.
  - [ ] La regla obstáculo/transitable usa las medidas reales del carro (PEND-12, que salen de P5-19) y la tabla tiene al menos 3 obstáculos y 3 objetos transitables con su altura.
  - [ ] `DOMINIO.md` declara el carro y la cámara (modelo, resolución, altura, ángulo) y sus límites.
- **Pendientes:** PEND-04, PEND-06, PEND-12.

#### P5-04 · Selección del detector
- **Responsable:** A1 · **Tamaño:** M · **Prioridad:** P0 · **Bloque:** 1–2 · **Marca:** `[GUÍA]` + `[SUGERENCIA]`
- **Revisa el PR:** A2 · Andy (`Andy-752109`)
- **Depende de:** PEND-04
- **Por qué:** la guía lista como bloqueo "solo hay un clasificador": un clasificador de recortes no localiza obstáculos.
- **Alcance**
  - Elegir 2–3 candidatos (D-01); revisar **licencia del código y de los pesos**, tamaño, formato (ONNX disponible o exportable), clases COCO que cubren el dominio.
  - Prueba rápida en **CPU** con varias imágenes con el objeto en distintas posiciones (izquierda, centro, derecha, cerca, lejos) y con una imagen sin objetos. Anotar latencia aproximada y falsos positivos evidentes.
  - **Probar con fotos reales de los objetos candidatos de PEND-04** (mochila, botella, taza, silla, maleta), **tomadas con la ESP32-CAM del kit** (misma óptica y compresión JPEG que verá el detector; si el carro aún no transmite, con celular reescalado a 640×480 y recomprimido a JPEG, y repetirlas cuando haya video del carro, P5-19): tabla objeto → ¿lo detecta? → con qué clase y confianza. Se eligen 3 o 4 objetos con la mejor detección, de modo que alguno pueda ir a un lado de la vía (C3, C4). Estas fotos son de **selección** y no entran a las 8 secuencias de evaluación (D-06).
  - Registrar la decisión y los descartados en `modelo/DECISION.md`.
- **Criterios de aceptación**
  - [ ] Decisión registrada con origen, versión, licencia y razón; incluye lo que se probó y lo que no.
  - [ ] El detector elegido localiza correctamente (a ojo) objetos laterales y centrales en CPU.
  - [ ] Cada objeto candidato tiene su resultado en la tabla; los que el detector no reconoce se reemplazan por otros o se cambia de detector **antes** de filmar (P5-09).
  - [ ] Quedan elegidos 3 o 4 objetos que el detector reconoce y los PM A y B los aprobaron antes de filmar (PEND-04).
  - [ ] La prueba incluye fotos de la ESP32-CAM, no solo del celular (o queda dicho que faltan).
  - [ ] Se sabe si el runtime elegido corre en la máquina de PEND-05.
- **Pendientes:** PEND-04, PEND-05.

### Bloque 2 — Primera entrega por grupo

#### P5-19 · Armar el carro y poner a transmitir la ESP32-CAM
- **Responsable:** A1 + A2 + A3 (los tres) · **Tamaño:** M · **Prioridad:** P0 · **Bloque:** 2 · **Marca:** `[SUGERENCIA]` (D-07)
- **Revisión:** los tres se revisan entre sí: cada medida y cada foto las comprueba alguien que no las tomó.
- **Depende de:** PEND-13 (baterías y cargador)
- **Por qué:** P5-09 (video con la óptica real) y P5-03 (regla obstáculo/transitable) necesitan el carro armado: el video de la ESP32-CAM y las medidas de llanta, chasis y cámara. Si no se logra a tiempo, el plan B es el celular (D-07).
- **Alcance** (según la ficha de UNIT Electronics; todavía no se probó)
  - Armar el kit con el instructivo (las baterías 18650 y el cargador no vienen incluidos).
  - Cargar el programa `ESP32CAM_Car` desde el IDE de Arduino: placa `ESP32 Wrover Module`, partición `Huge APP`, red WiFi de **2.4 GHz** y un puente entre GND y GPIO0 solo mientras se carga. Basta con que uno de los tres lo cargue.
  - **Windows o Mac:** el IDE y el soporte ESP32 existen para las dos; la ficha solo enlaza el driver CH340 de Windows, así que en Mac se comprueba si la placa aparece como puerto serial o se instala el driver CH340 de WCH.
  - Ver la IP en el Monitor Serie y abrir el video desde el navegador. La ESP32-CAM debe recibir 5 V estables; si baja, el video se corta.
  - Que los otros dos vean el video desde su propia computadora.
  - Medir y anotar en `datos/CARRO.md`: diámetro de llanta, altura libre del chasis, ancho, altura de la cámara sobre el piso, ángulo, y la resolución y calidad JPEG configuradas (PEND-12, PEND-06).
  - Guardar 3 cuadros de prueba con objetos del dominio tomados con la ESP32-CAM (los usa P5-04).
  - La contraseña del WiFi vive en el programa de la placa: **no subir ese archivo al repo** con la clave escrita. Fotos sin rostros ni pantallas con SSID o contraseña (repo público).
- **Criterios de aceptación**
  - [ ] **Fotos del carro armado** (vista general, cámara montada y las medidas con regla o cinta) en `docs/carro/`, reducidas (≤ 1 MB cada una).
  - [ ] Captura de pantalla del video transmitiendo desde la ESP32-CAM.
  - [ ] `datos/CARRO.md` con las medidas y la configuración de la cámara; PEND-06 y PEND-12 quedan resueltos.
  - [ ] Dos de los tres ven el video desde su propia computadora.
  - [ ] Otra persona del equipo comprobó las medidas (repitió al menos dos con regla o cinta).
- **Evidencia:** fotos en `docs/carro/`, `datos/CARRO.md` y la captura del video.
- **Pendientes:** PEND-06, PEND-12, PEND-13.

#### P5-05 · Detector ejecutable en CPU y comando `infer`
- **Responsable:** A1 · **Tamaño:** L · **Prioridad:** P0 · **Bloque:** 2 · **Marca:** `[GUÍA]` E2
- **Revisa el PR:** A3 · Ale (`AleSarahi`)
- **Depende de:** P5-02, P5-04
- **Por qué:** sin detector ejecutable la nota se topa en 60.
- **Alcance**
  - Carga de pesos **verificando SHA-256** antes de inferir; si no coincide, falla con mensaje claro.
  - Preprocesamiento documentado y **explícito en el orden de canales** (OpenCV entrega BGR: en `edge/preprocess.py` de P4 hay un `bgr_to_rgb` de ejemplo), redimensionado o *letterbox*, normalización.
  - Posprocesamiento: umbral de confianza, **NMS**, filtro de clases relevantes y **vuelta de las cajas a píxeles del cuadro original** (si no, izquierda/derecha salen mal en C3/C4).
  - Comando `infer` con entrada, configuración y carpeta de salida configurables que emite un evento del contrato v1 por cuadro (JSONL), con `model_sha256` y `config_sha256`.
  - **No usa etiquetas, nombres de archivo ni el manifiesto para predecir** (la guía lo comprueba): solo píxeles.
  - La salida es JSON estricto (`allow_nan=False`): una confianza o una caja no finita (NaN, infinito) o una clase fuera de rango no se emite como detección, sino como `status=error` con `invalid_output` (criterio 3.2; el tratamiento del error es de P5-06). El umbral de confianza y el NMS efectivos quedan en la configuración y en `config_sha256`, y un cuadro sin objetos sale como `ok` con lista vacía.
- **Criterios de aceptación**
  - [ ] Una imagen real → caja, clase y confianza correctas, en CPU, sin red.
  - [ ] Pruebas de unidad del posprocesamiento (NMS, conversión de coordenadas con una imagen de tamaño distinto al de entrada).
  - [ ] Pesos alterados → falla por hash.
  - [ ] Dos corridas con la misma entrada y configuración dan el mismo resultado (o la diferencia se documenta).
  - [ ] Con imágenes que elija otra persona (una con el objeto al centro, una lateral, una con varios objetos y una sin objetos) las cajas coinciden con los píxeles de entrada y la imagen vacía da `ok` con lista vacía.
  - [ ] Una copia de la imagen con otro nombre da la misma salida, y una prueba comprueba que `infer` no abre anotaciones ni el manifiesto.
  - [ ] Ninguna línea de la salida contiene `NaN` ni `Infinity`.
- **Evidencia:** salida JSONL de ejemplo en `resultados/` y captura del comando.
- **Pendientes:** PEND-05, PEND-09.

#### P5-09 · Captura de secuencias y extracción de cuadros únicos
- **Responsable:** A2 · **Tamaño:** L · **Prioridad:** P0 · **Bloque:** 2–3 · **Marca:** `[GUÍA]` E3
- **Revisa el PR:** A1 · Heri (`BeetlejuiceXD`)
- **Depende de:** P5-03, P5-19
- **Por qué:** E3 pide ≥ 6 secuencias y 60 cuadros distintos extraídos como imágenes; B necesita secuencias **reales** pronto (bloque 4).
- **Alcance**
  - **Requiere el carro armado y el video funcionando (P5-19).** Si no está listo a tiempo, pasar al plan B del celular a 640×480 (D-07) sin esperar al último día.
  - **Cómo se capturan los cuadros:** un script que lea el stream de la ESP32-CAM y guarde los bytes JPEG tal como llegan (sin recomprimir, para que el SHA-256 sea estable) con la marca de tiempo real de recepción. El WiFi da tiempos irregulares: **no suponer 200 ms fijos**; el contrato exige `t_capture_ms` estrictamente creciente. La URL del stream depende del programa `ESP32CAM_Car`: confirmarla en el instructivo.
  - Fijar y anotar la configuración de captura (resolución 640×480, calidad JPEG, orientación) y **no cambiarla entre secuencias**; la altura y el ángulo salen de `datos/CARRO.md`.
  - Filmar según el plan de P5-03 (**el fin de semana**) y extraer cuadros completos como imágenes (JPG/PNG), con IDs estables (`sequence_id`, `frame_id`) y **tiempo relativo** por cuadro.
  - **Primer lote de 2–3 secuencias el domingo 25** para que B pruebe con datos reales.
  - Evitar cuadros casi idénticos: la guía pide cuadros *únicos*; calcular SHA-256 de cada imagen y revisar duplicados.
  - Nombres de archivo neutros (sin la clase ni el caso), para que nada pueda "predecir con el nombre".
  - Si el repo será público y salen personas: usar compañeros que den su consentimiento y evitar rostros identificables.
- **Criterios de aceptación**
  - [ ] ≥ 6 secuencias (objetivo 8) y ≥ 60 cuadros (objetivo 80), todos completos y sin duplicados exactos.
  - [ ] ≥ 20 cuadros con obstáculo y ≥ 20 despejados (objetivo 30 y 30).
  - [ ] Primer lote entregado a B y confirmado que lo pueden leer.
  - [ ] La configuración de la cámara (resolución, calidad, altura, ángulo) está anotada y es la misma en todas las secuencias.
  - [ ] Cada cuadro tiene su marca de tiempo real de captura, no una calculada.
- **Pendientes:** PEND-06, PEND-12.

#### P5-13 · Script de métricas de detección (TP/FP/FN, P/R/F1 a IoU 0.50)
- **Responsable:** A3 · **Tamaño:** L · **Prioridad:** P0 · **Bloque:** 2–5 · **Marca:** `[GUÍA]` E6
- **Revisa el PR:** A2 · Andy (`Andy-752109`)
- **Depende de:** P5-02 (datos sintéticos primero); datos reales con P5-11
- **Por qué:** E6 exige un script de recálculo; las cifras resumidas no bastan.
- **Alcance**
  - **Emparejamiento uno a uno**, por cuadro y por clase: las predicciones se ordenan por confianza (de mayor a menor) y cada una se empareja con la caja real **aún libre de mayor IoU** de su clase, si IoU ≥ 0.50; cada caja real se usa una sola vez; duplicados son FP; objetos sin pareja son FN; una clase equivocada es FP para la predicción **y** FN para el objeto real. Las cajas se comparan en el mismo sistema de coordenadas (D-04).
  - `precisión = TP/(TP+FP)`, `recall = TP/(TP+FN)`, `F1 = 2TP/(2TP+FP+FN)`; con denominador cero se usa 0 y se marca **"sin soporte"**.
  - Resultados **micro** (el que puntúa 1.4) y **por clase con su soporte**; incluye **cuadros negativos** (sin objetos, donde cualquier detección es FP). AP es opcional y no sustituye esta fórmula.
  - Comando `metrics` con detecciones, anotaciones y carpeta de salida como parámetros; salida CSV/JSON con TP/FP/FN por cuadro, no solo el resumen.
  - Pruebas con casos armados a mano: caja perfecta, caja desplazada por debajo de 0.5, duplicado, clase equivocada (1 FP y 1 FN), cuadro negativo con falso positivo, conjunto sin objetos.
  - Sin ajuste (D-06), todo el conjunto es evaluación: se reporta **un solo juego de cifras sobre todos los cuadros**, con los negativos, los errores y los cuadros omitidos. Un cuadro sin predicción sigue en el denominador (sus objetos son FN) y sale listado; nada se quita para mejorar el F1.
  - Comprueba que el `model_sha256` y el `config_sha256` de las detecciones coinciden con los pesos y la configuración congelados, y que las predicciones cubren todos los cuadros del manifiesto. Si no, lo avisa: 1.4 solo se acredita con predicciones de procedencia comprobada.
- **Criterios de aceptación**
  - [ ] Las pruebas manuales dan exactamente los TP/FP/FN esperados.
  - [ ] Otra persona recalcula F1 desde los archivos y obtiene el mismo valor.
  - [ ] Se puede calcular el puntaje 1.4 (`floor(12×F1)/2`) a partir de la salida.
  - [ ] El umbral de confianza y el NMS estaban congelados antes de correr sobre los cuadros (D-06) y el reporte lo dice.
- **Pendientes:** ninguno (PEND-07 quedó cerrado el 2026-10-26).

#### P5-15 · Arnés de benchmark (10 calentamientos + 100 ejecuciones)
- **Responsable:** A3 · **Tamaño:** L · **Prioridad:** P0 · **Bloque:** 2 (arnés) y 6 (medición final) · **Marca:** `[GUÍA]` E7
- **Revisa el PR:** A1 · Heri (`BeetlejuiceXD`)
- **Depende de:** P5-01; medición final con P5-05
- **Por qué:** E7 pide registros individuales, calentamientos y fallos separados, tiempos por etapa y p50/p95.
- **Alcance**
  - Partir de `Proyecto04-MLOps/edge/benchmark.py`, que ya hace 10 calentamientos, ≥ 100 mediciones, p50/p95 y un CSV por ejecución con la marca `is_warmup`. **Hay que generalizarlo:** hoy exige exactamente 20 entradas y mediciones en múltiplos de 20, y mide un clasificador.
  - Medir **por etapa:** preprocesamiento, inferencia, política/adaptador (cuando B la tenga), total local. Guardar cada ejecución, **calentamientos y fallos aparte**, y el máximo observado.
  - Registrar hardware y runtime (SO, CPU, RAM, versiones, hilos), tamaño de pesos.
  - Comando `bench`. Las pausas de reproducción **no** cuentan como latencia de cómputo.
  - Medir con el equipo enchufado y en condiciones repetibles (una laptop puede bajar la frecuencia).
- **Criterios de aceptación**
  - [ ] Con un detector falso, el arnés produce 10 calentamientos + 100 válidas y rechaza una configuración distinta.
  - [ ] Una ejecución fallida queda registrada aparte y no entra en p50/p95.
  - [ ] Medición final con los pesos reales en la máquina declarada (PEND-05).
- **Pendientes:** PEND-05.

### Bloque 3 — Congelar datos

#### P5-10 · Anotación de cajas y estado esperado por cuadro
- **Responsable:** A2 · **Tamaño:** L · **Prioridad:** P0 · **Bloque:** 3 · **Marca:** `[GUÍA]` E3
- **Revisa el PR:** A3 · Ale (`AleSarahi`)
- **Depende de:** P5-09
- **Alcance**
  - Anotar cajas con clase en cada cuadro (herramienta de D-03) en el formato acordado (PEND-08) y registrar el **estado esperado** del cuadro (obstáculo/despejado y, útil para B, la zona: izquierda / centro / derecha).
  - Las etiquetas reales **se guardan aparte** de las detecciones.
  - **Revisión cruzada:** A3 revisa una muestra (≥ 20 %) y se corrigen discrepancias antes de congelar.
  - Se anotan **todos** los objetos de las clases elegidas, también los que quedan fuera de la zona de riesgo (laterales, lejanos, parciales): C3 y C4 necesitan el lado ocupado anotado, y un objeto sin anotar que el detector sí encuentra cuenta como falso positivo. Si se fija un tamaño mínimo, queda escrito y se aplica igual en todos los cuadros.
  - Criterio de anotación escrito (qué cuenta como obstáculo, objetos parciales, tamaño mínimo y **objetos transitables, que no se etiquetan**).
- **Criterios de aceptación**
  - [ ] Todos los cuadros anotados; los despejados tienen lista vacía **a propósito**, no por olvido.
  - [ ] Muestra revisada por otra persona con las discrepancias resueltas y anotadas.
  - [ ] Las cajas caen sobre los objetos al dibujarlas (script de revisión visual).
  - [ ] En los cuadros de C3 y C4 el objeto lateral está anotado, y en los cuadros con varios objetos están todos.
- **Pendientes:** PEND-08.

#### P5-11 · Manifiesto, verificación del conjunto y congelamiento
- **Responsable:** A2 · **Tamaño:** M · **Prioridad:** P0 · **Bloque:** 3 · **Marca:** `[GUÍA]` E3
- **Revisa el PR:** A3 · Ale (`AleSarahi`)
- **Depende de:** P5-10
- **Alcance**
  - Manifiesto (CSV/JSON): `frame_id`, `sequence_id`, `t_relativo_ms`, ruta, SHA-256, `split` (`evaluacion` en todos: D-06 declara que no hubo ajuste), estado esperado y procedencia.
  - Script `verify_dataset`: ≥ 60 cuadros **únicos**, ≥ 6 secuencias, ≥ 20 con obstáculo, ≥ 20 despejados (los mínimos se cumplen con el conjunto de evaluación por sí solo), hashes coinciden, anotaciones válidas. Sale con código ≠ 0 si algo falla.
  - **Hueco máximo entre cuadros:** ningún par de cuadros consecutivos de una secuencia puede estar separado por más de `validez_orden_ms` (400 ms, se lee de `config/control/plazos.yaml` en vez de fijarlo a mano). Una orden vale 400 ms; si el siguiente cuadro llega después, el corredor de B frena con STOP (T05, #25) en una secuencia que debía avanzar (C1). A los 600 ms (`watchdog_ms`) entra además el watchdog. Si el script de captura (P5-09) deja un hueco mayor, se regraba la secuencia; una armada a propósito con huecos se marca así en el manifiesto.
  - **Congelar:** registrar el hash del manifiesto y etiquetar el commit, con el umbral de confianza y el NMS ya escritos en `config/` (D-06); a partir de ahí, cambios solo con visto bueno de ambos PM.
- **Criterios de aceptación**
  - [ ] `verify_dataset` pasa y falla cuando se rompe una regla (probar quitando un cuadro, repitiendo una imagen, abriendo un hueco de más de 400 ms entre dos cuadros y marcando una secuencia con otro `split`).
  - [ ] Hash del manifiesto y de la configuración de evaluación documentados.
  - [ ] Congelado **antes** de ver los resultados del detector sobre evaluación.
- **Evidencia:** salida de `verify_dataset`; etiqueta del repo con el congelamiento.

#### P5-12 · Entradas para casos temporales y de fallo
- **Responsable:** A2 (con A1) · **Tamaño:** S · **Prioridad:** P1 · **Bloque:** 3–4 · **Marca:** `[GUÍA]` (A aporta secuencias, aclara scores y define errores)
- **Revisa el PR:** A1 · Heri (`BeetlejuiceXD`)
- **Depende de:** P5-03, P5-09
- **Alcance**
  - Tabla `datos/MAPA_CASOS.md`: caso → secuencia(s) → cuadros → qué se espera de la percepción.
  - **C6:** documentar qué cuadros quedan bajo y sobre el umbral de confianza y con qué score los produce el detector elegido.
  - **C8/C9:** fixtures de entrada fallida: imagen ilegible o vacía, archivo corrupto (si el stream de la ESP32-CAM entrega un JPEG truncado real, conservarlo), cuadro con dimensiones distintas, y la lista de errores que A1 define (excepción, tiempo agotado, salida inválida).
- **Criterios de aceptación**
  - [ ] Cada caso C1–C7 apunta a cuadros **reales**.
  - [ ] Las fixtures de error disparan `status=error` en `infer` (con P5-06).
  - [ ] B3 confirmó que el mapa le sirve para armar C1–C9.

### Bloque 4 — Recorrido integrado

#### P5-08 · Primer recorrido: cuadro real → detector → comando de B
- **Responsable:** A1 (con B3) · **Tamaño:** M · **Prioridad:** P0 · **Bloque:** 4 (**objetivo lunes 26**) · **Marca:** `[GUÍA]`
- **Revisa el PR:** A3 · Ale (`AleSarahi`)
- **Depende de:** P5-05, P5-09 (primer lote)
- **Por qué:** la guía lo señala como riesgo "Integración al final": si cada grupo muestra su parte pero no hay recorrido único, se pierde la compuerta de 60.
- **Alcance**
  - A1 y B3 conectan el contrato con **pesos reales**; los dos PM siguen **un cuadro** desde la imagen hasta el registro del adaptador virtual.
  - Un ejemplo compartido reproduce el mismo resultado en las dos máquinas; si no coinciden coordenadas, clases o tiempos, se corrige con el contrato versionado.
  - Repetir con una secuencia completa de cada tipo (central, izquierda, derecha, despejada).
- **Criterios de aceptación**
  - [ ] Un cuadro real queda trazado: `frame_id` → detecciones → estado → decisión → comando.
  - [ ] La secuencia izquierda y la derecha producen comandos opuestos (confirma orientación de coordenadas).
  - [ ] Los dos PM presenciaron o verificaron el recorrido.

#### P5-14 · Resultados por cuadro y trazabilidad completa
- **Responsable:** A3 (con B3) · **Tamaño:** M · **Prioridad:** P0 · **Bloque:** 4–5 · **Marca:** `[GUÍA]` E6
- **Revisa el PR:** A2 · Andy (`Andy-752109`)
- **Depende de:** P5-02, P5-08
- **Alcance**
  - Formato único por cuadro (JSONL/CSV, documentado) que une: `run_id`, `frame_id`, detecciones, estado, decisión, comando, `model_sha256`, `config_sha256` y errores.
  - Script de recálculo que, desde esos archivos, vuelve a producir las métricas de P5-13 y los conteos por caso, sin depender de cifras pegadas a mano.
  - Los errores y vencimientos aparecen con su ID; nada se oculta.
- **Criterios de aceptación**
  - [ ] Dado un `frame_id`, se llega a su comando en un paso.
  - [ ] Cambiar el modelo o la configuración cambia los hashes registrados.
  - [ ] El recálculo desde cero da las mismas cifras que el reporte.

#### P5-06 · Estados de percepción y manejo de errores del detector
- **Responsable:** A1 · **Tamaño:** M · **Prioridad:** P0 · **Bloque:** 2–5 · **Marca:** `[GUÍA]` (C9, C8)
- **Revisa el PR:** A2 · Andy (`Andy-752109`)
- **Depende de:** P5-05
- **Por qué:** C9 exige que una excepción, un tiempo agotado, una salida inválida o una imagen ilegible dejen **error registrado y STOP**; la parada ante pérdida de percepción es parte de la compuerta de 60.
- **Alcance**
  - Cualquier fallo del detector produce un evento `status=error` (nunca una lista vacía con `ok`).
  - Entrada vieja o sin cuadro nuevo se marca `stale` cuando A publica el estado de la entrada (C8, el watchdog es de B).
  - Tiempo límite de inferencia configurable; salida inválida (NaN, clase fuera de rango, caja fuera de imagen) rechazada y registrada.
  - Pruebas que fuercen cada error con las fixtures de P5-12.
- **Criterios de aceptación**
  - [ ] Cada tipo de fallo da `error` con causa legible y el proceso no se cae.
  - [ ] Un cuadro vacío legítimo sigue siendo `ok` (pruebas lado a lado).
  - [ ] B2/B3 reciben `error` y `stale` y confirman que producen STOP.

### Bloques 5–7 — Calidad, medición y cierre

#### P5-07 · Paquete del detector: origen, licencia, hash y descarga automatizable
- **Responsable:** A1 · **Tamaño:** M · **Prioridad:** P0 · **Bloque:** 3–6 · **Marca:** `[GUÍA]` E2
- **Revisa el PR:** A2 · Andy (`Andy-752109`)
- **Depende de:** P5-05 (y P5-04 para la licencia)
- **Alcance**
  - `modelo/README.md`: origen (URL y versión), **licencia del código y de los pesos**, clases (`class_id` → nombre), resolución, preprocesamiento y posprocesamiento, SHA-256 y tamaño.
  - Pesos en Git o descarga automatizable con verificación de hash (PEND-11), probada desde una carpeta vacía.
  - Entorno fijado con lockfile; versiones de runtime documentadas (D-02).
- **Criterios de aceptación**
  - [ ] Desde una copia limpia, un solo comando recupera los pesos y verifica el hash.
  - [ ] Origen y licencia documentados y el hash coincide con el de `config/`.
  - [ ] La documentación basta para que otra persona identifique el modelo sin preguntar.
- **Pendientes:** PEND-11.

#### P5-16 · Reporte de límites y contraste con plazos
- **Responsable:** A3 (con B2) · **Tamaño:** M · **Prioridad:** P1 · **Bloque:** 6 · **Marca:** `[GUÍA]` E7
- **Revisa el PR:** A2 · Andy (`Andy-752109`)
- **Depende de:** P5-15, plazos de B (PEND-09)
- **Alcance**
  - Contrastar **p95 y peor tiempo** con los plazos declarados por B y con el watchdog.
  - Explicar los límites: qué acredita el control virtual (percepción y comandos sobre secuencias) y qué **no** (frenado mecánico, distancia, movimiento físico). Sin FPS universal ni distancias inventadas.
  - Declarar el conjunto chico, los umbrales, las condiciones de iluminación y lo que el equipo no pudo probar.
- **Criterios de aceptación**
  - [ ] Tabla p50/p95/máximo por etapa frente al presupuesto, con veredicto y razón.
  - [ ] Los límites están escritos y no contradicen las afirmaciones del README.
  - [ ] Lo declarado y lo reproducido se distinguen.
- **Pendientes:** PEND-09.

#### P5-17 · Ensayo de reproducción de la parte A desde una copia limpia
- **Responsable:** A2 · **Tamaño:** M · **Prioridad:** P0 · **Bloque:** 6–7 (**jueves 29**) · **Marca:** `[GUÍA]` (recorrido de aceptación)
- **Revisa el PR:** A3 · Ale (`AleSarahi`)
- **Depende de:** P5-07, P5-11, P5-13, P5-15
- **Alcance**
  - En una copia limpia, **con CPU y sin red tras el setup**, seguir solo el README: recuperar pesos y datos, calcular hashes, cargar el detector, inferir imágenes elegidas por quien verifica, generar resultados nuevos, recalcular métricas y revisar el benchmark.
  - Abrir todos los archivos del paquete y anotar enlaces rotos o rutas absolutas.
  - Registrar qué máquina, qué sistema y quién lo ejecutó; marcar cada paso observado / no observado.
  - La reproducción conjunta final la hace B3 con el equipo B; este ensayo la prepara.
- **Criterios de aceptación**
  - [ ] Todo corre sin pedir ayuda al equipo, sin secretos y sin tokens.
  - [ ] Los fallos del ensayo quedan corregidos o declarados.
  - [ ] Modelo identificable, clases y transformaciones, datos completos y congelados, métricas y benchmark auditables desde el README (esa validación final es del PM A; ver sección 3).
- **Pendientes:** PEND-03, PEND-11.

#### P5-18 · Documentación de la parte A (README y datos)
- **Responsable:** A2 · **Tamaño:** S · **Prioridad:** P1 · **Bloque:** 7 · **Marca:** `[GUÍA]` E1
- **Revisa el PR:** A1 · Heri (`BeetlejuiceXD`)
- **Depende de:** P5-11
- **Alcance**
  - Sección del README del grupo A: responsables y traspasos (con los **ocho nombres** y los dos PM cuando B aporte los suyos), comandos `infer`, `metrics`, `bench`, `verify_dataset`, versión de entrega.
  - `datos/README.md`: procedencia, cómo se filmó, criterio de anotación, la declaración de que no hubo ajuste (D-06) y hashes.
  - Sin secretos; rutas relativas y configurables.
- **Criterios de aceptación**
  - [ ] Cada comando del README se probó en P5-17.
  - [ ] Los responsables de A1, A2, A3 y PM A aparecen con nombre.

---

## 7. Cobertura de la guía

| Entregable / criterio | Tickets del grupo A |
|---|---|
| E1 · repo y README | P5-01, P5-18 (con B) |
| E2 · detector | P5-04, P5-05, P5-06, P5-07 |
| E3 · secuencias etiquetadas | P5-03, P5-19, P5-09, P5-10, P5-11 |
| E5 · aporte de A a los casos | P5-12, P5-06, P5-08 |
| E6 · métricas y trazabilidad | P5-13, P5-14 |
| E7 · benchmark y límites | P5-15, P5-16 |
| Recorrido de aceptación y cierre | P5-17, P5-08 |
| Contrato A→B | P5-02 |

Con **E4** (política, adaptador) y **E5** (ejecutar C1–C10) cubiertos por el grupo B, el paquete completo cubre E1–E7.

---

## 8. Riesgos

| Riesgo | Efecto | Mitigación |
|---|---|---|
| Solo hay un clasificador, no un detector. | Sin cajas no hay recorrido: compuerta de 60. | P5-04 en el bloque 1; no reciclar el modelo de P3/P4. |
| Datos incompletos: faltan negativas, cajas laterales o cuadros únicos. | E3 incumplido; C3/C4 sin material. | Matriz de P5-03; `verify_dataset` (P5-11); D-05 con margen. |
| Contrato cambiante o coordenadas incompatibles. | B decide mal; izquierda y derecha invertidas. | Versión del contrato, ejemplo compartido (P5-02, P5-08), D-04. |
| Ajustar el umbral o NMS mirando los cuadros de evaluación. | Métricas infladas. | Sin ajuste (D-06): congelar antes (P5-11) y reportar un solo conjunto. |
| BGR/RGB o *letterbox* mal deshecho. | Detecciones corridas, F1 bajo sin causa clara. | Pruebas de P5-05 con imagen de tamaño distinto. |
| Integración al final. | Cada grupo muestra su parte y no hay recorrido único. | Primer recorrido el lunes 26 (P5-08). |
| Licencia del detector (p. ej. AGPL) sin declarar. | E2 incumplido o incómodo de entregar. | D-01: declarar origen y licencia en P5-07. |
| Evaluador no puede instalar o recuperar los pesos. | Reproducción fallida. | Lockfile, descarga con hash, probar en copia limpia (P5-17); repo público o ZIP (PEND-03). |
| Rostros en repo público. | Privacidad. | Consentimiento y cuadros sin rostros identificables (P5-09). |
| Objetos bajos (borrador, cable) tratados como obstáculo, o un obstáculo real ignorado, sin una regla escrita. | STOP innecesarios (no avanza), o choque no detectado; etiquetas inconsistentes y F1 ruidoso. | Regla con medidas reales (P5-03, PEND-12), cuadros transitables en S8 y el mismo criterio en anotación (P5-10) y en la lista de clases relevantes de B1. |
| El carro no se arma o la ESP32-CAM no transmite a tiempo (driver CH340, WiFi de 2.4 GHz, 5 V inestables, baterías que el kit no trae). | Sin cuadros con la óptica del carro; se atrasa P5-09 y todo lo que cuelga de los datos. | Plan B del celular a 640×480 (D-07). `[SUGERENCIA]` Decidir hoy quién compra las baterías y quién arma el carro (PEND-13), y pasar al celular si el martes 27 no hay video. |
| Poco tiempo (7 días). | Se empuja todo al final. | Filmar el fin de semana; plan por bloques de la sección 5. |

---

## 9. Plantilla para tickets nuevos

```markdown
#### P5-NN · Título corto
- **Responsable:** A1/A2/A3 · **Tamaño:** S/M/L · **Prioridad:** P0/P1/P2 · **Bloque:** N · **Marca:** [GUÍA]/[SUGERENCIA]/[PENDIENTE]
- **Depende de:** …
- **Por qué:** …
- **Alcance**
  - …
- **Criterios de aceptación**
  - [ ] …
- **Evidencia:** …
- **Pendientes:** PEND-NN / D-NN
```
