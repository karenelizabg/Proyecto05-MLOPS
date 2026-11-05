# Protocolo de órdenes PC → carro, versión 1 (P5-20)

Cómo le manda órdenes la PC al carro y qué contesta la placa. Lo usan el firmware (P5-20), el
lazo en vivo (P5-21) y el carro simulado (P5-22).

**Estado: propuesto; queda congelado al fusionar el #102.** Después, cambiarlo requiere un PR revisado por los devs 1 y 2, que
suba la versión (`P5C2`/`P5R2`) y corrija en el mismo PR este documento y
[`src/carro/protocolo.py`](../../src/carro/protocolo.py). Ese archivo es el **modelo de
referencia** de las reglas (`Placa`), y el firmware las repite. Si alguno de los dos no
coincide con este documento, está mal.

## Transporte

| Dato | Valor |
|---|---|
| Medio | UDP sobre la misma red WiFi de 2.4 GHz del stream |
| Puerto de la placa | **4210**. El 80 (`/capture` y la página del kit) y el 81 (`/stream`) no cambian. |
| Respuesta | Al mismo IP y puerto de origen del datagrama |
| Codificación | ASCII. Una orden por datagrama, de 96 bytes o menos. Se tolera un `\n` al final. |
| Por qué UDP | Una orden perdida no se reenvía: la reemplaza la del periodo siguiente (ver [Frecuencia de envío](#frecuencia-de-envío)). TCP reintentaría órdenes ya vencidas y atrasaría las nuevas. |

## Orden (PC → placa)

```
P5C1,<sesion>,<seq>,<accion>,<velocidad>,<giro>,<vigencia_ms>
```

| Campo | Formato | Rango | Qué es |
|---|---|---|---|
| `sesion` | entero | 1 a 4294967295 | La elige el emisor al arrancar: **segundos desde 1970** (`int(time.time())`), y si no supera la sesión anterior del mismo proceso, la anterior + 1. Solo crece (regla 4). |
| `seq` | entero | 1 a 4294967295 | Número de secuencia. Crece de uno en uno dentro de la sesión. |
| `accion` | texto | `AVANZAR`, `GIRAR_IZQ`, `GIRAR_DER`, `STOP` | Las mismas del contrato de comando (`config/contrato/comando.v1.schema.json`) |
| `velocidad` | `d` o `d.ddd` (hasta 3 decimales) | 0 a 1 | Fracción del techo de PWM. Es `speed` del comando. |
| `giro` | `d` o `d.ddd` con signo opcional | −1 a 1 | **Negativo = izquierda.** Es `steering` del comando (la política usa ±0.5). |
| `vigencia_ms` | entero | 1 a 500 | Cuánto vale la orden desde que **llega** a la placa. El lazo manda 400 (`validez_orden_ms`). |

Ejemplo: `P5C1,3141592,17,GIRAR_IZQ,0.400,-0.500,400`

La vigencia se cuenta desde que la orden llega y no con el reloj de la PC, porque los relojes
no están sincronizados. El retraso de la red se suma al tiempo de paro total: ver
[Tiempos](#tiempos).

### Reglas

La placa revisa cada datagrama en este orden. **Cualquier rechazo frena los motores** y se
contesta con su motivo.

| # | Regla | Si no se cumple |
|---|---|---|
| 1 | Sigue el formato de arriba, con una acción conocida y como mucho 96 bytes | `MAL_FORMADA` |
| 2 | Todos los campos están en su rango | `FUERA_RANGO` |
| 3 | La acción coincide con los números: `STOP` lleva velocidad 0 y giro 0; `AVANZAR` velocidad > 0 y giro 0; `GIRAR_IZQ` velocidad > 0 y giro < 0; `GIRAR_DER` velocidad > 0 y giro > 0 | `INCONSISTENTE` |
| 4 | La sesión es la activa. Una sesión nueva **solo se acepta con un `STOP` y si es mayor que la activa**; entonces pasa a ser la activa. Al encender no hay sesión activa y cualquier `STOP` abre una. | `SESION` |
| 5 | `seq` es mayor que la última aceptada en la sesión (rechaza repetidas y fuera de orden) | `SEQ_VIEJA` |

Un datagrama rechazado no cambia la sesión ni la última `seq` aceptada.

Que una sesión nueva tenga que empezar con `STOP` sirve para dos cosas. Un emisor reiniciado
puede volver a empezar en `seq=1`. Y una orden de movimiento atrasada de un emisor anterior no
puede arrancar el carro. Por eso los emisores mandan un `STOP` antes de cualquier otra orden.

Que además tenga que ser **mayor** cierra el caso que encontró la revisión del #102: sin eso,
un `STOP` atrasado de la sesión 7 que llegara después de que la 8 tomó el control reabría la 7,
y el `AVANZAR` atrasado que venía detrás movía el carro. Con sesiones crecientes los dos se
rechazan con `SESION` (prueba `test_stop_atrasado_de_sesion_anterior_no_la_revive`).

- La sesión sale del reloj de la PC para que crezca también entre procesos y entre PCs. Las PCs
  del equipo sincronizan la hora por internet, así que la diferencia es de menos de un segundo.
  Si una PC tiene la hora muy atrasada, sus sesiones se rechazan con `SESION` hasta que la
  placa se reinicie: el carro queda quieto, que es el lado seguro.
- Dos emisores que arrancan en el mismo segundo comparten sesión. No es un riesgo, porque la
  `seq` sigue rigiendo: el segundo empieza en `seq=1`, la placa lo rechaza con `SEQ_VIEJA` y el
  carro se queda quieto. Basta con esperar un segundo y volver a arrancarlo.

## Respuesta (placa → PC)

La placa contesta **cada** datagrama, incluso los rechazados:

```
P5R1,<sesion>,<seq>,<motivo>,<estado>,<pwm_izq>,<pwm_der>,<t_placa_ms>
```

| Campo | Qué es |
|---|---|
| `sesion`, `seq` | Los de la orden que se contesta. Son `0,0` si no se pudieron leer (`MAL_FORMADA`). |
| `motivo` | `OK` o el motivo del rechazo (tabla de reglas), o `VENCIDA` en el aviso de paro automático |
| `estado` | `MOVIENDO` o `DETENIDO`, ya con la orden aplicada |
| `pwm_izq`, `pwm_der` | PWM aplicado a cada lado, de 0 a 255. En v1 nunca es negativo porque no hay reversa. |
| `t_placa_ms` | `millis()` de la placa. Sirve para ver reinicios (vuelve a empezar desde cero) y el ritmo de la placa. |

El emisor de prueba descarta (y anota en la bitácora como `ajena`) toda respuesta que no venga
de la IP y el puerto del carro, que no corresponda a una `(sesion, seq)` que mandó, o que sea
incoherente: PWM fuera de 0 a 255, `MOVIENDO` sin motores, `DETENIDO` con motores, o un
rechazo o `VENCIDA` que no esté en `DETENIDO`. Las únicas que acepta sin `(sesion, seq)`
propios son `0,0,MAL_FORMADA` y el `VENCIDA` de su sesión. El `rtt` solo se mide con
respuestas correlacionadas.

**Aviso de paro automático:** cuando una orden vence sin que llegue otra, la placa frena y
manda una sola vez `P5R1,<sesion>,<ultima_seq>,VENCIDA,DETENIDO,0,0,<t>` al último emisor
aceptado. Si el WiFi se cayó, el aviso no llega, pero el freno ocurre igual.

## Paro automático y movimiento

- **Paro automático:** sin una orden válida nueva, los motores se apagan al terminar la
  vigencia. El tope es 500 ms aunque la orden pida más, y queda por debajo del watchdog de
  600 ms del proyecto (`config/control/plazos.yaml`).
- También frena de inmediato al perder el WiFi (`WiFi.status() != WL_CONNECTED`), con un
  `STOP` y con cualquier rechazo de la tabla de reglas.
- La placa revisa los vencimientos cada 10 ms o menos, en una tarea aparte del servidor de
  video. Así el stream no atrasa los paros.
- **Giro diferencial**, sin reversa: con `giro < 0`, el lado izquierdo va a
  `velocidad × (1 + giro)` y el derecho a `velocidad`. Con `giro > 0` es al revés. Así, ±0.5
  hace un arco hacia ese lado y ±1 deja quieto el lado interior.
- **De fracción a PWM:** una fracción de 0 da PWM 0. Cualquier otra da
  `MINIMO + fracción × (TECHO − MINIMO)`, donde `MINIMO` es la zona muerta de los motores y
  `TECHO` es el máximo fijado en el firmware. El modelo de referencia es `a_pwm` en
  `src/carro/protocolo.py`.

## Frecuencia de envío

Quien maneja el carro tiene que mandar **al menos una orden por periodo `P`, con
`P ≤ vigencia / 2`**: con la vigencia de 400 ms, cada 200 ms o menos. Así una orden perdida no
deja vencer la anterior y el carro no tironea. Mandar más seguido no hace daño: cada orden
nueva solo renueva la vigencia.

| Quién | Periodo | |
|---|---|---|
| Emisor de prueba (`python -m carro`) | 100 ms (`paso_reloj_ms`) | Cumple con margen |
| Lazo en vivo de P5-21 | Una orden por cuadro nuevo, ~200 ms | Cumple justo: con un cuadro atrasado o una orden perdida, el carro frena. **Recomendación:** mandar en el tick de 100 ms del supervisor, repitiendo la última decisión mientras esté vigente. |

## Garantías ante datagramas retrasados o perdidos

UDP puede perder, repetir o desordenar datagramas. El protocolo v1 garantiza:

1. **Nada anterior a la última orden aceptada mueve el carro.** La `seq` crece y la placa
   rechaza con `SEQ_VIEJA` cualquier orden con `seq` menor o igual. Las sesiones anteriores se
   rechazan con `SESION` (regla 4).
2. **Ninguna orden mueve el carro más de `min(vigencia_ms, 500)` ms después de llegar**, aunque
   no llegue nada más.
3. **Requisito para el emisor y el lazo:** mientras el carro deba estar quieto, se sigue
   mandando `STOP` en cada periodo, no uno solo; al cerrar se mandan tres. Si se pierde un
   `STOP`, el siguiente lo reemplaza en un periodo, y una orden de movimiento atrasada que
   llegue después queda como `SEQ_VIEJA`. El emisor de prueba lo hace con `detener()` entre
   prueba y prueba y con los tres `STOP` de `cerrar()`.

**Límite declarado:** la vigencia se cuenta desde que la orden **llega**, porque la placa no
conoce el reloj de la PC. Una orden de movimiento atrasada que llegue **antes** que cualquier
`STOP` posterior todavía mueve el carro hasta `min(vigencia_ms, 500)` ms. En una red local los
retrasos son de milisegundos (rtt medido de 6 a 40 ms), así que en la práctica es la misma
orden que se esperaba. **Posible mejora para v2:** que la placa mida la edad con su propio
reloj (sincronizándolo con las respuestas) y rechace órdenes más viejas que un umbral.

## Hardware (del firmware del kit)

| Señal | GPIO | Nota |
|---|---|---|
| Izquierda adelante | 14 | |
| Izquierda atrás | 2 | Pin de arranque (*strapping*). En v1 se queda en bajo. |
| Derecha adelante | 13 | |
| Derecha atrás | 15 | Pin de arranque. En v1 se queda en bajo. |
| LED de flash | 4 | No se usa. Se queda en bajo. |

- El firmware está en [`firmware/carro_p5`](../../firmware/carro_p5/README.md). Los valores
  de esta sección están en su `config_carro.h`.
- El PWM va en los pines de adelante del L298N, con los puentes de ENA/ENB puestos. Usa LEDC a
  1 kHz y 8 bits en los **canales 8 y 10**, del grupo de baja velocidad. La cámara ocupa el
  canal 0 y el timer 0 del grupo de alta velocidad para XCLK, y **no se pueden tocar**.
- Todos los pines de motor se ponen en bajo en las primeras líneas de `setup()`, antes de la
  cámara y del WiFi. Entre el reinicio y `setup()` los pines quedan sin control unos
  milisegundos. Por eso **la batería de motores va apagada al encender la placa** y se prende
  después de ver la IP en el Monitor Serie.
- **Revisar en la fase 2:** en el firmware del kit, el botón "Left" pone la izquierda adelante
  y la derecha atrás, o sea que gira a la **derecha**. Puede ser una etiqueta equivocada o un
  cableado cruzado. El firmware nuevo trae `INVERTIR_IZQ`, `INVERTIR_DER` e
  `INTERCAMBIAR_LADOS` para corregirlo sin recablear. Con las ruedas en el aire se comprueba
  que `GIRAR_IZQ` frene el lado izquierdo.

## Parámetros

Valores por omisión. Los medidos se llenan en la fase 2 con las ruedas en el aire y luego en
el piso, y entran a este documento en el PR de esa prueba.

| Parámetro | Por omisión | Medido | Cómo se mide |
|---|---|---|---|
| `TECHO` (PWM máximo) | 160 | pendiente | El más bajo que mueve el carro en piso a una velocidad segura para el video |
| `MINIMO` (zona muerta) | 90 | pendiente | El PWM más bajo con el que giran las cuatro ruedas en el piso, desde parado |
| Tope de vigencia | 500 ms | — | Fijo en el firmware |
| Periodo de revisión del paro | 5 ms (`PERIODO_REVISION_MS`) | — | Fijo en el firmware |
| Tiempo de paro tras la última orden | ≤ 510 ms | pendiente | Video a 60 fps con `python -m carro --enviar prueba corte` |
| Tiempo de paro tras cortar el WiFi | ≤ 510 ms | pendiente | Video a 60 fps, apagando el router o el punto de acceso |

## Tiempos

Desde la última orden que llega, el peor caso es: vigencia (400 ms en el lazo) + revisión
(10 ms). Con el tope del firmware queda en 510 ms o menos, por debajo del criterio de 600 ms de
P5-20. Si el emisor muere, la última orden ya había llegado, así que también son ≤ 510 ms
desde ese momento. Este cálculo no incluye la inercia del carro: la distancia de frenado se
mide en P5-23.

## Emisor de prueba

`python -m carro` manda órdenes a mano, sin detector ni política. Sin `--enviar` es modo seco:
muestra los datagramas y no abre la red. Todos los comandos empiezan con `STOP` y terminan con
tres `STOP`, también con Ctrl+C. La IP va por `--ip` o por la variable `P5_CARRO_IP`, nunca en
el repo.

```bash
uv run python -m carro --ip <ip> stop
uv run python -m carro --ip <ip> orden AVANZAR --durante-ms 2000            # modo seco
uv run python -m carro --ip <ip> --enviar orden GIRAR_IZQ --durante-ms 1500 # mueve motores
uv run python -m carro --ip <ip> --enviar --bitacora b/pruebas.jsonl prueba todas
```

Cada respuesta se imprime con `seq`, motivo, estado, PWM por lado, ida y vuelta (`rtt`) y
`t_placa`. `--bitacora` guarda en JSONL cada datagrama enviado y recibido.

| Prueba | Qué manda (con el carro ya en `MOVIENDO`) | Pasa si |
|---|---|---|
| `corte` | Deja de mandar órdenes, sin `STOP` | Llega `VENCIDA` 600 ms o menos después de la última orden |
| `repetida` | La misma `seq` que la última aceptada | `SEQ_VIEJA` y `DETENIDO` |
| `vieja` | Una `seq` anterior | `SEQ_VIEJA` y `DETENIDO` |
| `mal_formada` | `P5C1,basura` | `MAL_FORMADA` y `DETENIDO` |
| `fuera_rango` | Velocidad 1.5 | `FUERA_RANGO` y `DETENIDO` |
| `inconsistente` | `AVANZAR` con giro 0.5 | `INCONSISTENTE` y `DETENIDO` |
| `sesion_ajena` | `AVANZAR` de otra sesión | `SESION` y `DETENIDO` |
| `sesion_vieja` | `STOP` atrasado de una sesión anterior | `SESION` y `DETENIDO` (no la reabre) |

El emisor mide lo que **contesta** la placa. Que las ruedas de verdad se detengan se comprueba
en video (aceptación de P5-20). Las pruebas automáticas de `tests/test_carro_emisor.py` corren
el emisor contra `Placa` en localhost, sin carro.
