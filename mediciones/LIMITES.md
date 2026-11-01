# Límites del sistema (P5-16, E7)

Qué acredita este proyecto y qué no, y cómo se contrastan los tiempos medidos con los plazos de B. Los números
salen de la corrida final de P5-15 (`python -m bench`) y de `python -m bench.limites`, que escribe
`contraste.md` junto a ella. Aquí no se copian a mano: se enlaza la corrida.

> **Estado:** la medición final espera al paso 2 del congelamiento (#13): fusionar P5-05 (#75) con
> `torch_threads: 2` y registrar su `config_sha256`. Hasta entonces nadie corre el detector sobre S01–S08.
> Las secciones marcadas *Pendiente* se completan con esa corrida.

## Qué acredita el control virtual

- Que el detector, **en CPU y en el equipo declarado (PEND-05)**, procesa un cuadro de 640×480 dentro de los
  plazos de B, con p50, p95 y máximo medidos sobre 100 ejecuciones después de 10 calentamientos.
- Que cada cuadro de las secuencias produce un evento del contrato v1 y que B responde con el comando que
  dicta su política, incluidos los casos de cuadro viejo, timeout del detector y ausencia de cuadros (C8, C9).
- Que todo lo anterior se reproduce desde los archivos del repositorio con los hashes registrados:
  `bench.limites` comprueba que los CSV de la corrida tengan el SHA-256 que registró `resumen.json`.

## Qué no acredita

- **Movimiento físico:** el control es virtual; los comandos se registran y nunca mueven el carro.
- **Frenado:** no hay distancia de frenado, tiempo de reacción mecánico ni velocidad máxima segura. No se
  declara ninguna distancia.
- **Un FPS universal:** los tiempos valen para el equipo de PEND-05, conectado a la corriente, con el runtime
  y los hilos registrados en `resumen.json`. En otra máquina, o en batería, cambian (ver *Lo que ya se vio*).
- **La cadena completa de la cámara:** el benchmark parte de la imagen en memoria. No mide la captura en la
  ESP32-CAM, la transmisión por WiFi ni la decodificación del JPEG, así que la edad real de un cuadro al llegar
  a B es mayor que `total_ms`.
- **Escenas fuera del dominio:** el detector solo se probó con los objetos, la escena y la luz de PEND-04.

## Contraste con los plazos

`python -m bench.limites mediciones/<run>/` compara la corrida con `config/control/plazos.yaml`:

| Medido | Plazo | Por qué importa |
|---|---|---|
| `inferencia_ms` | `detector_timeout_ms` (500) | Si una inferencia tarda más, A emite `detector_timeout` y B frena (C9). |
| `total_ms` | `max_frame_age_ms` (500) | El comando sale cuando el cuadro ya tiene al menos esa edad; si pasa el plazo, B lo rechaza (C8). |
| `total_ms` | periodo de entrada (200, PEND-09) | Si procesar tarda más que el periodo, los cuadros se acumulan y llegan cada vez más viejos. |
| intervalo entre comandos | `validez_orden_ms` (400) | Si entre dos comandos pasa más, el adaptador frena por su cuenta. |
| intervalo entre eventos | `watchdog_ms` (600) | Si entre dos eventos pasa más, B frena por falta de percepción. |

El intervalo es el mayor entre el periodo de entrada y `total_ms`. Cada fila lleva un veredicto: **cumple**
(hasta el máximo queda dentro), **cumple en p95** (el máximo lo pasa: algún cuadro se pierde o llega tarde) o
**no cumple** (el p95 lo pasa).

Las filas no son independientes:

- **La edad depende de la cola.** Si procesar tarda más que el periodo de entrada, cada cuadro espera a que
  termine el anterior, así que su edad pasa de `total_ms`. Por eso la fila de la edad nunca sale mejor que la
  del periodo: si el p95 pasa el periodo, la cola crece sin límite y la edad **no cumple** aunque `total_ms`
  esté lejos de 500 ms.
- **El intervalo no cambia con la cola.** Con cola, los eventos salen uno tras otro, cada `total_ms`, así que
  la validez de la orden y el watchdog se comparan igual.

**Para salir con `0` debe cumplir el máximo, no solo el p95.** `plazos.yaml` pide contrastar el p95, y la
tabla lo hace (con su margen), pero B decide cuadro por cuadro: un solo cuadro que pasa `max_frame_age_ms` o
`detector_timeout_ms` ya es un STOP. Un **cumple en p95** se reporta tal cual, con salida `1`, para que se vea
y se explique en vez de esconderlo en un percentil.

**Resultado:** *Pendiente* — enlazar `mediciones/<run>/contraste.md` de la corrida final.

## Declarado y reproducido

| | Qué es | Dónde está |
|---|---|---|
| **Declarado** | Plazos de B y ritmo de entrada (≈ 5 fps, provisional hasta que B cierre PEND-09). | `config/control/plazos.yaml` (su SHA-256 queda en `contraste.json`) |
| **Declarado** | Equipo de PEND-05. | [`README.md`](README.md#equipo-declarado-pend-05) |
| **Reproducido** | p50/p95/máximo por etapa, fallos aparte, hardware y energía de la corrida. | `mediciones/<run>/resumen.json`, `ejecuciones.csv`, `fallos.csv` |
| **Reproducido** | Veredicto de cada plazo. | `mediciones/<run>/contraste.md` y `contraste.json` |

`bench.limites` avisa (y no sale con `0`) si la corrida tiene advertencias, quedó incompleta, tuvo fallos
(aunque no entren en p50/p95), no midió la etapa de B, se contrasta con otro periodo que el de PEND-09, o si
`plazos.yaml` o los CSV cambiaron desde que se midió.

## Lo que ya se vio (antes de la medición final)

Prueba de compatibilidad de YOLO11n (checkpoint v8.3.0, Ultralytics 8.3.0, PyTorch 2.9.0 en CPU) en el equipo
de PEND-05, para P5-04. **No es la medición del entregable:** se hizo fuera del arnés, con una sola imagen de
ejemplo a 640×480, y no hay archivos en el repositorio que la reproduzcan.

| Condición | Mediana | p95 | Máximo |
|---|---|---|---|
| Conectada, 1 hilo | 142 ms | 179 ms | 210 ms |
| Conectada, 7 hilos (los que fija Ultralytics) | 87 ms | 113 ms | 162 ms |
| En batería | 352 ms | 708 ms | 2382 ms |

Lo que deja: en batería no se cumplen los plazos, así que la corrida final va conectada (el arnés lo registra y
lo advierte). El número de hilos cambia el resultado a casi la mitad, así que el detector de P5-05 debe fijarlo y
`resumen.json` registrarlo.

### Cuántos hilos (decisión del PM A, 2026-10-31)

Con 1 hilo, la evidencia de P5-05 en macOS dio p95 244 ms y máximo 314 ms, por encima del periodo de 200 ms.
Karen fijó la regla **antes de medir**: el menor número de hilos con p95 ≤ 150 ms y máximo ≤ 200 ms; si
ninguno cumple, 7. Se midió en el equipo de PEND-05, conectado, con el procedimiento de
`resultados/p5-05-benchmark.py` de #75 (`calentar()`, 10 calentamientos y 50 mediciones de
`detector_total_ms` sobre `docs/carro/objeto_taza_centro_cerca.jpg`), una configuración por proceso:

| Hilos | Mediana | p95 | Máximo | Regla |
|---|---|---|---|---|
| 1 | 141 ms | 158 ms | 210 ms | no cumple |
| **2** | **101 ms** | **138 ms** | **189 ms** | **cumple: se elige** |
| 4 | 97 ms | 129 ms | 168 ms | cumple |
| 7 | 83 ms | 161 ms | 218 ms | no cumple |

Se midió una sola vez y no se repitió para escoger. Dos cosas que la medición final tiene que confirmar:

- **El máximo con 2 hilos queda a 11 ms del límite.** Un cuadro lento basta para pasarlo.
- **Las colas varían entre corridas.** Con 7 hilos, la prueba de P5-04 dio p95 113 ms y máximo 162 ms, y esta
  dio 161 y 218 ms. Con más hilos compiten más con el sistema.

Los hilos no cambian las detecciones (7 contra 1 hilo: Δconf ≤ 1.3e-6), pero sí el `config_sha256`, por eso
se decidió antes del paso 2.

### Otros hallazgos, ya corregidos en P5-05 (#75)

- **El reloj de `infer`:** en el primer recorrido real (T16, `docs/recorrido-real.md`) los cuadros llegaron a
  B con unos 35 s de edad y todos terminaron en STOP por `cuadro_viejo`, porque la carga y el calentamiento
  del modelo entraban en el reloj del run. Con #75 el reloj empieza después de `calentar()`: el primer cuadro
  sale con unos 15 ms de edad.
- **Los hilos de `infer`:** `config/detector.json` pedía 1 hilo, pero Ultralytics lo cambiaba a 7 al preparar
  el predictor. Con #75, `DetectorJPEG` vuelve a fijar el de la configuración y falla si no queda.
  `bench.yolo` usa ese mismo detector, no tiene opción para cambiar los hilos y registra los que de verdad
  quedaron.
- **El `frame_id`:** `infer` numeraba los cuadros por posición (`f000001`) y el conjunto usa el nombre de la
  captura (`S01_f0001`), así que no se unía ningún cuadro con sus anotaciones. Con #75 usa el nombre del JPEG.

## Conjunto, umbrales y condiciones

- **Conjunto:** 8 secuencias (S01–S08), todas de evaluación (D-06), con 107 cuadros anotados en P5-10: 71 con
  obstáculo y 36 despejados. E3 pide al menos 60. Congelado en el tag `datos-evaluacion-v1` (P5-11, #13), con
  SHA-256 `8a75e271…` del manifiesto y `7e842784…` de `anotaciones.jsonl`. Es un conjunto chico: las métricas
  tienen la incertidumbre de una muestra así. S09 y S10 son solo para las pruebas de B y no cuentan.
- **Una excepción a D-06, declarada en #13:** antes de congelar se corrió el detector sobre S01, una toma
  fallida de S01 y la primera S02, que después se repitió.
- **Umbrales:** `conf` 0.25 e `iou` 0.70, propuestos en P5-04 (`modelo/configuracion.p5-04.propuesta.json`),
  fijados antes de correr sobre los cuadros. *Pendiente:* el `config_sha256` del paso 2 (con 2 hilos).
- **Objetos y escena (PEND-04):** botella (39) y taza (41), según P5-03; interior, piso plano, buena luz.
- **Iluminación:** solo luz de interior. No se probó con poca luz, contraluz ni exteriores.

## Lo que el equipo no pudo probar

- La cadena en vivo ESP32-CAM → detector → B con tiempos medidos de punta a punta.
- El carro moviéndose con los comandos de B.
- Otros equipos distintos al de PEND-05.
- *Pendiente:* lo que salga al filmar y al hacer la medición final.
