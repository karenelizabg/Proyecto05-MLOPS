# Límites del sistema (P5-16, E7)

Qué acredita este proyecto y qué no, y cómo se contrastan los tiempos medidos con los plazos de B. Los números
salen de la corrida final de P5-15 (`python -m bench`) y de `python -m bench.limites`, que escribe
`contraste.md` junto a ella. Aquí no se copian a mano: se enlaza la corrida.

> **Estado:** la medición final espera al detector de P5-05. Las secciones marcadas *Pendiente* se completan
> con esa corrida.

## Qué acredita el control virtual

- Que el detector, **en CPU y en el equipo declarado (PEND-05)**, procesa un cuadro de 640×480 dentro de los
  plazos de B, con p50, p95 y máximo medidos sobre 100 ejecuciones después de 10 calentamientos.
- Que cada cuadro de las secuencias produce un evento del contrato v1 y que B responde con el comando que
  dicta su política, incluidos los casos de cuadro viejo, timeout del detector y ausencia de cuadros (C8, C9).
- Que todo lo anterior se reproduce desde los archivos del repositorio con los hashes registrados.

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

**Resultado:** *Pendiente* — enlazar `mediciones/<run>/contraste.md` de la corrida final.

## Declarado y reproducido

| | Qué es | Dónde está |
|---|---|---|
| **Declarado** | Plazos de B y ritmo de entrada (≈ 5 fps, provisional hasta que B cierre PEND-09). | `config/control/plazos.yaml` (su SHA-256 queda en `contraste.json`) |
| **Declarado** | Equipo de PEND-05. | [`README.md`](README.md#equipo-declarado-pend-05) |
| **Reproducido** | p50/p95/máximo por etapa, fallos aparte, hardware y energía de la corrida. | `mediciones/<run>/resumen.json`, `ejecuciones.csv`, `fallos.csv` |
| **Reproducido** | Veredicto de cada plazo. | `mediciones/<run>/contraste.md` y `contraste.json` |

`bench.limites` avisa (y no sale con `0`) si la corrida tiene advertencias, quedó incompleta, no midió la etapa
de B, o si `plazos.yaml` cambió desde que se midió.

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

## Conjunto, umbrales y condiciones

- **Conjunto:** *Pendiente* (P5-09 a P5-11). Es chico: 8 secuencias, del orden de 60 cuadros, todas de
  evaluación (D-06). Las métricas tienen la incertidumbre de una muestra así de chica.
- **Umbrales:** `conf` 0.25 e `iou` 0.70, propuestos en P5-04 (`modelo/configuracion.p5-04.propuesta.json`),
  fijados antes de correr sobre los cuadros. *Pendiente:* el hash de la configuración congelada de P5-05.
- **Objetos y escena (PEND-04):** interior, piso plano, buena luz. *Pendiente:* los objetos elegidos finalmente.
- **Iluminación:** solo luz de interior. No se probó con poca luz, contraluz ni exteriores.

## Lo que el equipo no pudo probar

- La cadena en vivo ESP32-CAM → detector → B con tiempos medidos de punta a punta.
- El carro moviéndose con los comandos de B.
- Otros equipos distintos al de PEND-05.
- *Pendiente:* lo que salga al filmar y al hacer la medición final.
