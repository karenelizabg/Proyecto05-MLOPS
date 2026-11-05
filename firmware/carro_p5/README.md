# Firmware del carro (P5-20)

Firmware de la ESP32-CAM del carro para el modo en vivo. Conserva la cámara del kit, con los
cambios de [`datos/CARRO.md`](../../datos/CARRO.md), y agrega las órdenes por UDP del
[protocolo v1](../../docs/carro/protocolo.md), con paro automático.

| Archivo | Qué hace |
|---|---|
| `carro_p5.ino` | Arranque: motores en bajo, cámara, WiFi, servidor y órdenes |
| `ordenes.cpp` / `ordenes.h` | Protocolo v1: lee y valida cada orden, mueve los motores por PWM y frena solo |
| `app_httpd.cpp` | `/` y `/capture` en el puerto 80, `/stream` en el 81. **Sin** los `/go`, `/left`, etc. del kit, que no frenaban solos. |
| `config_carro.h` | Puerto, tope de vigencia, PWM (techo y mínimo), pines y correcciones de cableado |
| `secretos.h.ejemplo` | Plantilla de la red. La copia real, `secretos.h`, está en `.gitignore`. |

## Qué cambia respecto al firmware del kit

- **Los motores solo se mueven con órdenes UDP.** Cada orden vale como mucho 500 ms desde que
  llega. Si no llega otra, los motores se apagan solos. También frenan al perder el WiFi y con
  cualquier orden rechazada.
- **Velocidad por PWM** en los pines "adelante" del L298N, con techo y zona muerta en
  `config_carro.h`. **Nunca hay reversa:** los pines "atrás" (GPIO 2 y 15) se quedan en bajo.
- El Monitor Serie imprime una línea por **cambio** de orden (`orden AVANZAR pwm=118/118`), por
  rechazo y por paro automático. Ya no imprime `MJPG: ...` en cada cuadro del stream.

## Cargarlo

Va por USB (COM9), sin la pila y **con el cable azul (+5V) suelto**. USB y +5V del L298N nunca
al mismo tiempo.

1. Copia la plantilla y pon la red (2.4 GHz, WPA2-Personal):
   ```powershell
   Copy-Item firmware\carro_p5\secretos.h.ejemplo firmware\carro_p5\secretos.h
   # edita secretos.h: WIFI_SSID y WIFI_CLAVE
   ```
2. Compila y carga desde la raíz del repo. El puerto puede cambiar; revísalo con
   `arduino-cli board list`.
   ```powershell
   & "C:\Program Files\Arduino CLI\arduino-cli.exe" compile --upload -p COM9 --fqbn esp32:esp32:esp32wrover:PartitionScheme=huge_app firmware\carro_p5
   ```
3. Al terminar, **desconecta y vuelve a conectar el USB** sin presionar BOOT. La placa no tiene
   botón RST.
4. En el Monitor Serie (`arduino-cli monitor -p COM9 -c baudrate=115200`) deben salir
   `Ordenes UDP en el puerto 4210 ...` y `Camera Ready! Use 'http://<ip>'`.

## Probarlo (fase 2)

Conexión para las pruebas:

- **USB-C** a la laptop: alimenta la placa.
- **Pila** al L298N: alimenta los motores.
- **Solo el cable verde (GND)** entre el L298N y la placa. El azul (+5V) va suelto.

Prende la pila **después** de ver la IP, con el carro sobre una caja y las ruedas en el aire.

```powershell
python -m carro --ip <ip> --enviar orden AVANZAR --durante-ms 1500
python -m carro --ip <ip> --enviar orden GIRAR_IZQ --durante-ms 1500
python -m carro --ip <ip> --enviar prueba todas
```

| Comprobación | Esperado | Si no |
|---|---|---|
| `AVANZAR` | Las cuatro ruedas hacia adelante | Pon `INVERTIR_IZQ` o `INVERTIR_DER` en 1 para el lado que gire al revés |
| `GIRAR_IZQ` | El lado **izquierdo** más lento (arco a la izquierda) | Pon `INTERCAMBIAR_LADOS` en 1 |
| Ruedas sin moverse con `pwm` > 0 | — | Revisa la carga de la pila, los puentes ENA/ENB y el GND común. Si gira solo con el PWM alto, sube `MINIMO_PWM`. |
| `prueba todas` | 7 de 7 en `PASA` | Manda la salida y la bitácora (`--bitacora`) |
| Cortar el emisor (Ctrl+C) o apagar el WiFi | Las ruedas paran en ≤ 600 ms (video a 60 fps) | — |
| 10 minutos de órdenes y stream | Sin reinicios (`t_placa` no vuelve a 0) y sin video congelado | Alimenta la placa aparte (batería portátil por USB-C) |

Cada cambio en `config_carro.h` requiere volver a cargar el firmware. Los valores medidos van a
la tabla de parámetros de [`docs/carro/protocolo.md`](../../docs/carro/protocolo.md).
