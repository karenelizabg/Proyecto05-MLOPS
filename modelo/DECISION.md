# P5-04 · Selección del detector

**Estado:** YOLO11n sigue seleccionado condicionalmente. Tras la revisión de
Andy con el umbral de la política B, ambas PM aprobaron que el dominio de
obstáculos quede en botella y taza. Pendientes la documentación completa de
AGPL-3.0 y la prueba de compatibilidad Windows. P5-04 no está cerrado.

## 1. Contexto

P5-04 debe seleccionar un detector ligero COCO que localice obstáculos en CPU
(D-01) y documentar candidatos, licencias y pruebas con fotografías de la
ESP32-CAM. Los objetos sugeridos antes en PEND-04 fueron lata, mochila, cajas
y tenis, pero solo mochila es una clase COCO directa. Karen (PM A) aprobó
**condicionalmente** YOLO11n y botella, taza y mochila tras revisar los
experimentos. Posteriormente, Andy revisó las detecciones con el umbral de
decisión de B (0.50) y Karen retiró la mochila del dominio de filmación.
PM B había aprobado `backpack=24`, `bottle=39`, `cup=41`, `conf=0.25`
e `iou=0.70`. Ahora confirmó expresamente, según lo comunicado por el usuario:
«OK de PM B: quitamos backpack y quedan bottle=39 y cup=41». Ambas PM
aprueban así la reducción de tres clases a dos. PM B aceptó
`modelo/clases.json` como lista de objetos con
`class_id` y `name`, o como diccionario ID → nombre. Se eligió la primera
estructura. Según la confirmación comunicada por el usuario, ambas son
compatibles con las pruebas de Hannah en PR #64; **no se ha confirmado que
ese PR esté integrado**.

La máquina declarada por Ale para P5-15 es una laptop con **Windows 11 Pro
64 bits (10.0.26200), Intel Core i5-1135G7, 8 GB RAM, Python 3.12.14, uv
y el `uv.lock` del repositorio**. La compatibilidad de YOLO11n en ella aún
no se ha probado.

La selección comunicada es: **YOLO11n principal**, **SSDLite320 MobileNetV3
de respaldo**. El dominio definitivo aprobado para la filmación contiene
solo `bottle=39` y `cup=41`; `backpack=24`, `chair=56` y `suitcase=28`
quedan descartados como clases activas. Se descarta también el estuche
blando/maleta. La confianza de salida del detector será **0.25** y NMS IoU
**0.70**. El Grupo B confirmó que necesita recibir detecciones menores que
**0.50** para probar C6; su política mantiene `umbral_confianza: 0.5`.
Esos son **dos umbrales distintos**: A emite desde 0.25 y B decide desde 0.50.
Una detección entre
0.25 y menos de 0.50 puede llegar a B y ser ignorada por confianza. No se
modificó `config/control/politica.yaml`.

Karen aclaró que la guía y la rúbrica no exigen un mínimo de clases distintas:
E3 exige 60 cuadros, al menos seis secuencias, al menos 20 cuadros con
obstáculo y al menos 20 despejados. El criterio original de P5-04 mencionaba
tres o cuatro objetos; la reducción a dos está aprobada por ambas PM, pero
este documento no declara satisfechos los demás criterios de aceptación.

## 2. Candidatos

| Detector | Implementación probada | Checkpoint oficial | Licencia y condición pendiente |
|---|---|---|---|
| YOLO11n · principal condicional | Ultralytics 8.3.0, PyTorch 2.9.0 | `yolo11n.pt`, v8.3.0; SHA-256 `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`; 5 613 764 B | Código AGPL-3.0; [Ultralytics declara](https://www.ultralytics.com/license) que sus modelos entrenados también se ofrecen bajo AGPL-3.0 por defecto o licencia Enterprise. Verificar avisos del checkpoint y obligaciones para esta entrega. |
| SSDLite320 MobileNetV3-Large · respaldo | torchvision 0.24.0, PyTorch 2.9.0, `COCO_V1` | `ssdlite320_mobilenet_v3_large_coco-a79551df.pth`; SHA-256 `a79551df90c79834bcd3bb3845ef9d966b5449a3a9b2833ae8404778ca5d65d2`; 14 069 355 B | Código BSD-3-Clause; condiciones independientes de los pesos sin verificar. |
| YOLOX-Nano · no seleccionado | ONNX release 0.1.1rc0, ONNX Runtime 1.31.1 | `yolox_nano.onnx`; SHA-256 `c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d`; 3 659 407 B | Código Apache-2.0; condiciones independientes de los pesos sin verificar. |

La procedencia, URLs y configuraciones se incluyen en las tres copias de
publicación `evidencia/configuracion.json` y en la [comparación consolidada](experimentos-publicados/p5-04-comparacion/README.md).
Las copias sustituyen solo rutas personales de ejecución por referencias
portables; los resultados experimentales originales permanecen intactos fuera
del conjunto que se publicará.

## 3. Metodología

Se procesaron las **mismas 29 fotografías JPEG de 640 × 480** de la ESP32-CAM
real del carrito. Los tres manifiestos coinciden en nombres y SHA-256. Incluyen
objetos a izquierda, centro, derecha, cerca y lejos, dos escenas con paso
despejado y dos con varios objetos. Son imágenes de **selección**, separadas de
las ocho secuencias de evaluación final (D-06). No hubo entrenamiento, ajuste
de pesos ni cambio de umbrales tras ver resultados.

Los tres experimentos corrieron en CPU de la MacBook Air M3, batch 1 y un hilo.
YOLO11n usó entrada 640, confianza 0.25 y NMS IoU 0.7; SSDLite320, entrada
interna 320, reporte ≥0.25 y NMS interno IoU 0.55; YOLOX-Nano, entrada 416,
confianza objeto × clase ≥0.25 y NMS por clase IoU 0.45. Se revisó visualmente
si cada caja caía sobre el objeto. Los nombres de archivo no se trataron como
etiquetas verificadas. Las probabilidades de los modelos no están calibradas
entre sí y los NMS difieren.

## 4. Resultados comprobados

Asociaciones visuales de clase de interés sobre objeto, en fotos individuales
y con geometría válida. Son conteos exploratorios sobre una **muestra pequeña
de 4 a 7 fotos por objeto**, no métricas formales:

| Objeto | YOLO11n | SSDLite320 | YOLOX-Nano |
|---|---:|---:|---:|
| Botella (`bottle`) | 3/4 | 3/4 | 3/4 |
| Mochila (`backpack`) | 3/7 | 5/7 | 2/7* |
| Taza (`cup`) | 3/4 | 3/4 | 1/4 |
| Silla (`chair`) | 3/6 | 3/6 | 1/6 |
| Estuche blando como `suitcase` | 2/4 | 2/4 | 1/4 |

\* Otra caja `backpack` de YOLOX-Nano cae visualmente sobre una mochila, pero
su `y1` negativa incumple los límites y se excluye. YOLOX tiene tres cajas
fuera del borde superior en total; los otros experimentos no registraron cajas
geométricamente inválidas. Un recorte posterior y explícito las haría válidas
sin cambiar las 48 detecciones YOLOX, pero elevaría su asociación válida de
`backpack` a 3/7. Es solo un análisis derivado; los CSV originales siguen sin
recortar y el contrato v1 no cambia.

YOLO11n no produjo cajas en las dos escenas de paso despejado. SSDLite320
produjo siete sobre piso o fondo; YOLOX-Nano, una sobre el fondo. En las dos
fotos con varios objetos, todos tuvieron reconocimiento parcial: YOLO11n
asoció una botella o una mochila según la foto; SSDLite320 no asoció
`backpack`, `bottle` ni `cup` a los objetos; YOLOX asoció mochila en ambas y
botella en una, pero omitió las tazas. Las confusiones frecuentes fueron
`suitcase` sobre mochila, `chair`/`couch` sobre estuche y, en YOLOX, `chair`
sobre un bote del fondo.

| Medición en esta Mac, 28 fotos tras la primera | YOLO11n | SSDLite320 | YOLOX-Nano |
|---|---:|---:|---:|
| Mediana total | 25.14 ms | 36.40 ms | 21.56 ms |
| p95 total | 26.00 ms | 38.93 ms | 23.17 ms |

Son tiempos totales exploratorios de una sola corrida. Los runtimes,
resoluciones y trabajo incluido en cada medición difieren; estas cifras no
constituyen el benchmark P5-15 ni predicen el rendimiento en la laptop de Ale. Los datos por
foto, las cajas y el desglose están en los tres experimentos originales.

### Revisión por posición de YOLO11n con el umbral de la política B

La [revisión de Andy en el PR #66](https://github.com/karenelizabg/Proyecto05-MLOPS/pull/66)
se contrastó con las confianzas de
[`detecciones.csv`](experimentos-publicados/p5-04-yolo11n/evidencia/detecciones.csv)
y las asociaciones de
[`revision_por_imagen.csv`](experimentos-publicados/p5-04-yolo11n/evidencia/revision_por_imagen.csv).
La tabla usa las fotos individuales de selección; «cerca» y «lejos» solo se
atribuyen cuando figuran en el nombre del archivo. Las cifras se redondean a
dos decimales. «Supera 0.50» se refiere a la **clase del obstáculo esperado**,
no a cualquier caja de otra clase. El detector sigue emitiendo desde
`conf=0.25`; la política B decide desde `umbral_confianza=0.50`.

| Objeto | Posición | Distancia documentada | Clase detectada (confianza) | Clase esperada ≥0.50 | Observación |
|---|---|---|---|---|---|
| Botella | Izquierda | — | `bottle` 0.64 | Sí | Asociación visual con la botella. |
| Botella | Centro | Cerca | `vase` 0.79; `bottle` 0.29 | No | `bottle` llega a B, pero queda bajo su umbral; también hay confusión con `vase`. |
| Botella | Derecha | — | `bottle` 0.82 | Sí | Asociación visual con la botella. |
| Botella | Centro | Lejos | Ninguna | No | Omitida a la distancia documentada. |
| Taza | Izquierda | — | `chair` 0.32; `cup` 0.30 | No | `cup` queda bajo el umbral; aparece una caja `chair`. |
| Taza | Centro | Cerca | `cup` 0.96 | Sí | Asociación visual con la taza. |
| Taza | Derecha | — | `cup` 0.61 | Sí | Asociación visual con la taza. |
| Taza | Centro | Lejos | Ninguna | No | Omitida a la distancia documentada. |
| Mochila | Izquierda | — | `suitcase` 0.70; `backpack` 0.52 | Sí | Ambas cajas se superponen sobre la mochila; confusión con `suitcase`. |
| Mochila | Centro | Cerca | `suitcase` 0.78, 0.77, 0.33 y 0.31; `person` 0.27 | No | Sin `backpack`; varias cajas `suitcase` fragmentan la mochila. |
| Mochila | Derecha | — | `suitcase` 0.64 | No | Sin `backpack`; no sirve para la posición derecha al umbral de B. |
| Mochila | Centro | Lejos | `suitcase` 0.57; `backpack` 0.40 | No | `backpack` queda bajo el umbral y se superpone con `suitcase`. |
| Mochila | Posición no documentada (`mochila_cerca.jpg`) | Cerca | `suitcase` 0.81 | No | Sin `backpack`. |
| Mochila | Vista lateral (`mochila_lado.jpg`) | — | `backpack` 0.58 | Sí | Asociación visual lateral; el nombre no fija izquierda/centro/derecha. |
| Mochila | Vista lateral (`mochila_lado_2.jpg`) | — | Ninguna | No | Omisión completa; el nombre no fija izquierda/centro/derecha. |

La clase `suitcase` aparece sobre la mochila en **5 de las 7 fotografías**
según el CSV publicado. El comentario de Andy dice 6/7; se conserva aquí el
conteo verificable de los resultados y queda señalada esa discrepancia. En
`varios_1` solo se reportó `bottle` 0.27 y en `varios_2`, `backpack` 0.51;
estas tomas no demuestran todavía el caso de dos obstáculos simultáneos.

## 5. Limitaciones

- No hay anotación completa de cajas de verdad de referencia ni cálculo formal
  de precisión/recall. Las fotos de selección son una muestra pequeña.
- Los objetos lejanos, sillas vistas desde cámara baja y objetos superpuestos
  presentan omisiones o confusiones. Una omisión puede dejar pasar un obstáculo;
  una caja sobre fondo o piso puede causar una parada innecesaria.
- La geometría de tres cajas YOLOX requiere una política de posprocesamiento si
  se considerara ese candidato. La política hipotética de clipping está
  documentada aparte y no se ha incorporado a producción.
- La licencia AGPL-3.0 del código de Ultralytics está identificada. Su
  [página oficial de licencia](https://www.ultralytics.com/license) afirma
  expresamente que los modelos entrenados están bajo AGPL-3.0 por defecto;
  también ofrece una licencia Enterprise. P5-07 debe comprobar los avisos del
  checkpoint v8.3.0 y documentar qué obligaciones de distribución,
  modificación y acceso al código aplican a la forma concreta de entrega,
  incluidos avisos y atribuciones. Esta decisión no resuelve ese alcance.
  Las condiciones de los pesos SSDLite320 y YOLOX-Nano siguen sin verificarse
  de forma independiente.
- Solo se probó CPU en la MacBook Air M3. La laptop Windows de Ale ya está
  identificada, pero falta probar allí YOLO11n para P5-15; las latencias
  locales no acreditan compatibilidad ni rendimiento en esa máquina.
- P5-19 debe confirmar con video del carro el comportamiento de botella y taza,
  junto con las medidas y la configuración de cámara. También debe comprobarse
  que la taza supera el radio de la llanta (PEND-12). Las omisiones observadas
  no se han resuelto.

## 6. Selección condicional y razón

**YOLO11n es el detector principal seleccionado condicionalmente por PM A.** Reconoció
botellas y tazas en 3/4, sillas en 3/6 y mochilas en 3/7; no generó cajas en
las dos escenas despejadas y fue más rápido que SSDLite320 en esta Mac. Frente
a YOLOX-Nano reconoció más tazas y sillas y no produjo cajas fuera de límites,
aunque YOLOX fue más pequeño y rápido. SSDLite320 reconoció más mochilas (5/7),
pero sus cajas sobre piso/fondo y mayor latencia son desventajas para este
escenario. La licencia AGPL-3.0 y las omisiones de YOLO11n son condiciones
materiales antes de cerrar la adopción.

**SSDLite320 queda como respaldo**; históricamente tuvo 5/7 asociaciones
visuales de mochila frente a 3/7 de YOLO11n. Sus cajas sobre piso y fondo y
su mayor latencia local obligan a repetir la revisión si se activa. YOLOX-Nano
no se selecciona: fue el más rápido y pequeño en esta Mac, pero reconoció
menos tazas, sillas y mochilas, y tres cajas excedieron el borde superior.

Tras la revisión de Andy, **Karen (PM A) y Ale V. (PM B) aprobaron retirar la
mochila**. Los obstáculos definitivos para filmar son **botella y taza**.
La mochila falla en la posición derecha con el umbral de B. La silla tampoco
resuelve el problema lateral: en `silla_izq.jpg` YOLO11n reportó `tv` 0.35,
y su asociación visual global fue 3/6. El estuche blando/maleta se descarta:
`suitcase` se asoció en solo 1–2 de 4 fotos según el modelo y hubo confusiones
con muebles; `handbag` no aportó detecciones útiles. No se define aquí la
respuesta de seguridad del sistema ni se implementa P5-05.

Para las secuencias planeadas, Karen asignó **botella a S3/S4** (izquierda y
derecha) y **taza al centro** donde corresponda. PM B aclaró que **S5/C5 debe
ocupar las tres zonas** para comprobar «sin zona libre → STOP»: **botella a la
izquierda, taza al centro y botella a la derecha**, bien separadas. Esta
distribución sustituye la propuesta anterior de dos objetos en S5. La revisión
sugiere comenzar a distancia media porque ni botella ni taza se detectaron
lejos en estas fotos. Andy hará tomas de prueba **antes de filmar**; las
secuencias finales permanecen separadas de
estas pruebas (D-06). Esta planificación no acredita todavía los criterios de
aceptación de S3, S4 o S5.

### Clases y configuración propuestas para coordinación

El checkpoint real de YOLO11n, con SHA-256 verificado, devuelve
`bottle=39` y `cup=41`. `modelo/clases.json` registra **solo esos dos IDs**
en la lista de objetos `class_id`/`name` aprobada por PM B. PM B confirmó que esta
estructura es compatible con las pruebas de Hannah en PR #64, según la
información comunicada por el usuario; no se presupone su integración. El
contrato v1 remite a este archivo y exige que las clases enviadas sean del
dominio. B conserva `[0,1]` como valores provisionales hasta coordinar T12;
esa actualización pertenece al Grupo B y no se hace en P5-04.

`modelo/configuracion.p5-04.propuesta.json` fija YOLO11n/Ultralytics 8.3.0,
SHA-256 del checkpoint, CPU, `imgsz=640`, `conf=0.25`, `iou=0.70`, batch 1 y
clases `[39,41]`. PM B aprobó ambos parámetros de inferencia. Incluye el
SHA-256 de `modelo/clases.json` para vincular el contenido de clases. Su
propio SHA-256 está en
`modelo/configuracion.p5-04.propuesta.sha256`, fuera del JSON, sin
autorreferencia. Es una **propuesta**, no la configuración congelada del run.
El responsable de ejecutar el detector deberá confirmar las rutas,
parámetros efectivos, clases y hash antes de procesar secuencias; cualquier
cambio exige un nuevo hash y registro. P5-09 congela la captura 640 × 480,
calidad JPEG y orientación antes de filmar; P5-19 aporta altura y ángulo de
la cámara montada. Esos parámetros de captura no están en este archivo.

## 7. Condiciones para cerrar la decisión

1. P5-05 consume las dos clases definitivas e implementa la inferencia y el
   filtro del dominio acordado, sin alterar el contrato A → B v1. Hannah
   actualiza la lista de clases relevantes del Grupo B; este ticket no modifica
   su política ni el PR #64.
2. P5-07 documenta origen, alcance y obligaciones de AGPL-3.0 para código y
   pesos YOLO11n, con avisos y forma de entrega; resuelve recuperación
   automatizable y verificación del checkpoint.
3. P5-09 congela la configuración efectiva antes de filmar, incluidos los
   parámetros de **captura** (resolución, calidad JPEG, orientación y cámara
   montada), y registra IDs y SHA-256 de cuadros. El responsable de inferencia
   verifica los parámetros del **detector** antes de procesar secuencias; si
   cambian, regenera el hash de configuración y documenta el cambio.
4. P5-15 prueba YOLO11n en la laptop Windows de Ale y registra compatibilidad
   y benchmark formal en esa máquina; PM B autorizó abrir el PR de P5-04
   antes de esta prueba.
5. Andy realiza tomas de prueba antes de filmar. P5-19 valida botella y taza
   con video real, distancia y las tres zonas ocupadas en S5, además de la
   altura de la taza respecto del radio de la llanta (PEND-12).
6. El Grupo B sustituye las clases provisionales por `[39,41]` mediante Hannah
   en T12 y verifica C6 con detecciones recibidas entre 0.25 y menos de 0.50.
   Esta decisión no modifica su política ni sus tests.

## 8. Aprobaciones y condiciones

| Persona | Decisión solicitada | Estado |
|---|---|---|
| Karen (PM A) | YOLO11n y, tras la revisión de Andy, solo botella/taza para filmar; mochila retirada | **Aprobado por PM A según su comentario en PR #66**. Aclaró que la rúbrica no exige mínimo de clases. Licencia y pruebas pendientes. |
| Ale V (PM B) | `bottle=39`, `cup=41`; `conf=0.25`, `iou=0.70`; estructura `class_id`/`name` | **Reducción a dos clases aprobada según lo comunicado por el usuario**: «OK de PM B: quitamos backpack y quedan bottle=39 y cup=41». B exige las tres zonas ocupadas en S5/C5 y mantiene su umbral 0.50. |

Esta tabla registra solo las aprobaciones comunicadas; no declara P5-04 cerrado.
