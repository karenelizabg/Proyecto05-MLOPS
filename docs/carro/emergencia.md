# Emergencia y matriz de fallos (P5-22)

Qué hace el sistema ante cada fallo, cuánto tarda el carro en quedar detenido y qué hacer a
mano si algo sale mal con el carro real. El protocolo PC → carro está en
[`protocolo.md`](protocolo.md) y los plazos en
[`config/control/plazos.yaml`](../../config/control/plazos.yaml).

## Procedimiento de emergencia físico

**Antes de cada prueba con el carro en el piso:**

1. Ruedas en el aire para la primera orden del día. Comprobar que `STOP` las detiene.
2. Una persona solo para la emergencia, con la mano libre y cerca del carro. No es la misma que
   opera la PC.
3. La batería de motores va apagada al encender la placa, y se prende después de ver la IP en el
   Monitor Serie (`protocolo.md`, *Hardware*).
4. Velocidad baja: `TECHO` del PWM calibrado en la fase 2, no el máximo.

**Si el carro hace algo inesperado**, en este orden:

1. **Tecla `e`** en la terminal de `python -m vivo` (P5-21, `tecla_emergencia` de
   `config/vivo.yaml`). Llama a `Supervisor.emergencia()`: `STOP` inmediato y enclavado. `r`
   rearma y `q` sale.
2. Si no frena en menos de un segundo, o la PC no responde: **levantar el carro** del piso.
3. **Desconectar la batería de motores.** La placa y la cámara pueden seguir encendidas; los
   motores ya no.
4. Cerrar el lazo con Ctrl+C. Al salir manda `STOP` (fallo 8 de la matriz).

**Para volver a arrancar después de una emergencia:** el rearme es explícito (tecla `r`) y pide un cuadro
fresco de la cámara (fallo 7). Primero se rearma y después, con cuadros libres, el carro vuelve a
moverse. Antes de rearmar, revisar por qué se activó.

**Se prueba en la fase 2** con Andy y Angel: las ruedas en el aire primero y después en el piso,
con el tiempo de paro medido en video a 60 fps.

## Matriz de fallos

Las pruebas automáticas están en [`tests/test_matriz_fallos.py`](../../tests/test_matriz_fallos.py).
Corren el supervisor, la política y los plazos reales de `control` contra el carro simulado
(`python -m simulador`), con UDP real en localhost. Del lado de la PC usan un puente mínimo,
`simulador/puente.py`, que es el `AdaptadorVirtual` más el emisor de P5-20. Ese puente no es el
adaptador de P5-21. La política se carga como la usará el carro (`cargar_politica_vivo`, con el
`umbral_lateral` de `config/vivo.yaml`).

**Qué se mide:** el tiempo, con el reloj de la placa simulada, desde que empieza el fallo hasta
que el carro queda `DETENIDO`. El límite es `watchdog_ms`, 600 ms.

```bash
uv run python -m simulador.matriz                      # los 9, con la tabla
uv run python -m simulador.matriz 4 9 --salida m/      # algunos, y guarda matriz.json y bitácoras
```

| # | Fallo | Qué debe pasar | Cómo se provoca | Desde dónde se mide | Medido | Límite |
|---|---|---|---|---|---|---|
| 1 | Cámara cortada | STOP por watchdog o por orden vencida | Dejan de llegar cuadros | Último cuadro | 418 ms | 600 ms |
| 2 | Cuadro con más de 500 ms de edad | STOP al recibirlo (`cuadro_viejo` o `stale`) | Un `ok` de 600 ms de edad y un `stale` | Llegada del cuadro | 4 ms | 600 ms |
| 3 | Detector con excepción, timeout, imagen ilegible o salida inválida | STOP (`error_detector:<code>`) | Un evento `error` con cada uno de los 4 códigos del contrato | Llegada del error | 12 ms | 600 ms |
| 4 | El carro no responde | La PC anota y avisa (`avisos.jsonl`) y manda STOP; si el carro no oye, para solo | Dos variantes: el carro deja de recibir (`perdida=1`) y el carro oye pero no contesta (`mudo`), con la PC viendo vía libre | Inicio del fallo | 289 ms | 600 ms |
| 5 | Orden repetida o fuera de orden | La vieja no se aplica y frena (`SEQ_VIEJA`) | Duplicar y desordenar datagramas | Inicio del fallo | 173 ms | 600 ms |
| 6 | Comando fuera de rango o no finito | Se rechaza y hay STOP | Política que da velocidad 1.5, NaN o infinito, y una orden de 1.5 directo a la placa | Llegada del cuadro | 6 ms | 600 ms |
| 7 | Emergencia | STOP inmediato y enclavado hasta un rearme explícito con percepción fresca | `Supervisor.emergencia()`, cuadros libres, rearme con un cuadro viejo y luego con uno fresco | Emergencia | 1 ms | 600 ms |
| 8 | Cierre del programa o excepción | STOP antes de salir | Cierre normal y una excepción dentro del lazo | Cierre | 2 ms | 600 ms |
| 9 | WiFi cortado a mitad de una orden | El carro para solo | Se corta el WiFi del carro con un `AVANZAR` vigente | Corte | 4 ms | 600 ms |

Medido el 2026-11-04 en la laptop de A3 (Windows 11, Intel i5-1135G7). Cuando un fallo tiene
varias variantes, se reporta la peor. Los números cambian unos milisegundos entre corridas; la
prueba solo exige que no pasen de 600 ms.

**Cómo leer los tiempos largos:**

- **Fallo 1 (418 ms):** el carro ya frenó solo cuando venció la orden (400 ms desde que llegó). El
  supervisor manda además su STOP de reloj (`orden_vencida`).
- **Fallo 4 (289 ms), dos variantes:**
  - *El carro no oye:* el STOP de la PC no le llega. Lo detiene su paro automático cuando vence la
    última orden aceptada, que ya llevaba unos 200 ms cuando empezó el fallo.
  - *El carro oye pero no contesta (`mudo`):* en 266 a 289 ms (8 corridas). El peor caso es un
    periodo del lazo más la espera: si el fallo empieza justo después de una respuesta, la
    siguiente orden sale a los 200 ms y el aviso llega 250 ms después, unos 450 ms. Sin el STOP de la PC, este caso **no
    paraba nunca**, porque el carro seguía obedeciendo los `AVANZAR` (lo encontró Angel en la
    revisión del #104). Por eso, después de 250 ms sin respuesta (más que un periodo de 200 ms,
    para que un solo paquete perdido no frene el carro), el puente avisa, manda STOP y
    cambia por STOP cada orden de movimiento hasta que el carro vuelva a contestar.
  - El aviso `VENCIDA` no cuenta como respuesta: el carro lo manda aunque no oiga nada.
  - El silencio se mide desde el envío real, con el reloj del puente. Con el `ahora_ms` del
    supervisor, el primer cuadro (~300 ms en procesarse) daba un aviso falso al arrancar.
  - **P5-21 tiene que hacer lo mismo** en su adaptador. Está acordado con Heri como propuesta, para
    integrarlo después del #105.
- **Fallo 5 (173 ms):** es lo que tarda en llegar el siguiente datagrama, a 5 fps.

**Lo que esta matriz no cubre:**

- La latencia real del WiFi, la inercia del carro y la distancia de frenado: se miden en P5-23.
- El firmware real. El simulador repite las reglas de `Placa`, el modelo de referencia, y el
  firmware se prueba aparte (P5-20).
- **Fallo 8, variante de excepción:** el `finally` que manda STOP lo escribe la propia matriz. El
  del lazo de P5-21 se prueba en sus pruebas, no aquí.
- **El ritmo del paro automático en Windows:** el simulador revisa los vencimientos cada 5 ms,
  pero `select` en Windows tiene una resolución de ~15 ms. En las mediciones de Angel, el paro
  llegó hasta 14.8 ms tarde, arriba de los 10 ms del firmware. El fallo 1 y el 4 quedan igual por
  debajo de 600 ms, pero los milisegundos exactos no son evidencia del carro real.
- **Fallo 9:** en el carro real, al perder la asociación con el punto de acceso la placa frena de
  inmediato (`protocolo.md`). Si la red sigue asociada pero no pasan paquetes, es el fallo 4: frena
  por vigencia, en 510 ms o menos.

## Notas de diseño

- **Una orden vieja frena el carro.** El protocolo v1 frena ante cualquier rechazo, también
  `SEQ_VIEJA`. Por eso un paquete que el WiFi duplique detiene el carro hasta la siguiente orden.
  Es seguro, pero puede verse como un tirón en el video.
- **No se rechazan órdenes "vencidas" al llegar.** El protocolo no manda la hora de la PC: la
  vigencia se cuenta desde que la orden llega a la placa. Una orden atrasada que sigue siendo la
  más nueva **se aplica** y dura toda su vigencia. La regla de `seq` solo descarta las que llegan
  después de una más nueva. Así, desde la última orden enviada, el paro queda acotado a retraso de
  la red + vigencia (400 ms, tope 500) + 10 ms.
- **Con `duplicar` y `desordenar` a la vez**, el simulador solo desordena.
