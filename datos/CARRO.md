# Carro y cámara (P5-19)

Medidas del carro armado y configuración de la cámara con la que se toman todas las fotos y
secuencias. De aquí salen PEND-06 y PEND-12 de `TICKETS.md`, y los usan `DOMINIO.md` (P5-03,
regla obstáculo / transitable) y la captura de secuencias (P5-09).

## Kit

| Dato | Valor |
|---|---|
| Kit | Kit Carrito ESP32-CAM 4WD (UNIT Electronics SKU AR4510, TSCINBUNY ZYC0024-EN), el que recomendó el profe |
| Placa | ESP32-CAM (AI Thinker) con convertidor USB-serie CH340 |
| Sensor | OV2640 |
| Motores | 4 motorreductores con puente H L298N |
| Dispositivo | Uno solo para todas las fotos y secuencias (decisión del PM A, 2026-10-26) |

## Medidas

Medidas con el carro armado, sobre piso plano.

| Medida | Valor | Cómo se midió |
|---|---|---|
| Diámetro de llanta | 6.4 cm | Regla, de lado a lado por el centro |
| Radio de llanta | 3.2 cm | Regla, del piso al centro de la llanta |
| Altura libre del chasis | 2 cm | Del piso a la parte más baja: los motores, que van debajo de la placa |
| Altura de la placa | 5.5 cm | Del piso a la placa de acrílico (solo referencia; los motores quedan más abajo) |
| Ancho total | 14.2 cm | De la cara exterior de una llanta a la de la otra |
| Largo total | 18.5 cm | Del frente a la parte de atrás |
| Altura de la cámara | 10 cm | Del piso al centro del lente |
| Ángulo de la cámara | 0° | Mira derecho al frente, sin inclinación |

**Regla obstáculo / transitable** (la define P5-03 en `DOMINIO.md`): es obstáculo lo que mide
más que el radio de la llanta o que la altura libre del chasis, lo que sea menor. Con estas
medidas el límite es la altura libre: **2 cm** (menor que el radio de 3.2 cm). Algo más bajo
(un borrador, una tapa, un cable) es transitable. Entre 2 y 3.2 cm la llanta podría subirse,
pero los motores pegarían: también es obstáculo.

Con la cámara a 10 cm y mirando al frente, el horizonte queda a media imagen y el piso ocupa la
mitad de abajo; un objeto pegado al frente del carro queda fuera de cuadro o cortado arriba.

## Cámara

| Dato | Valor |
|---|---|
| Resolución | 640×480 (VGA) |
| Formato | JPEG, calidad 10 del sensor (0 a 63; menor = mejor) |
| Tamaño típico por cuadro | 18 a 32 KB |
| Orientación | La cámara va montada de cabeza; el firmware la endereza en el sensor (`vflip` + `hmirror`), así que los cuadros ya salen derechos |
| Reloj de la cámara (XCLK) | 10 MHz |
| Búferes de cuadro | 2, en PSRAM |
| Foco | Fijo (el lente no gira) |
| Endpoints | `http://<ip>/capture` (un cuadro) y `http://<ip>:81/stream` (MJPEG) |

Tiempos por cuadro que reporta el firmware (`JPG: … ms`) en las pruebas del 2026-10-28: entre 75
y 616 ms, con la primera captura más lenta. **No es una medición de la secuencia:** el hueco
real entre cuadros (límite de 400 ms, `validez_orden_ms`) se mide en P5-09 y P5-11.

## Firmware

El programa base es `ESP32CAM_Car` del kit. **No está en el repo** porque tiene la red y la
contraseña del WiFi escritas. Cambios respecto al del kit:

| Cambio | Por qué |
|---|---|
| Arranca en VGA (`FRAMESIZE_VGA`), no en UXGA ni CIF | Es la resolución acordada para el detector. Con XCLK a 10 MHz el `set_framesize` posterior no se aplicaba y salía 1600×1200. |
| XCLK de 20 a 10 MHz | A 20 MHz el sensor respondía pero no entregaba cuadros (`Camera capture failed`). |
| `set_vflip(1)` y `set_hmirror(1)` | La cámara va montada de cabeza: equivale a girar la imagen 180°. |
| Endpoint `/capture` registrado | Para tomar cuadros sueltos con el script de captura. |
| Foto de prueba al arrancar y `ESP.restart()` si falla (máximo 3 veces seguidas) | Al conectar la corriente la cámara a veces arranca sin entregar cuadros; un reinicio con la placa ya alimentada lo arregla. |

Para cargarlo (Windows, `arduino-cli` 1.5.1, núcleo `esp32:esp32` 2.0.17):

```bash
arduino-cli compile --upload -p COM9 \
  --fqbn esp32:esp32:esp32wrover:PartitionScheme=huge_app ESP32CAM_Car
```

- El puerto puede cambiar (`arduino-cli board list`).
- Después de cargar, la placa se queda en modo de carga: hay que desconectar y volver a conectar
  el USB **sin** presionar BOOT.
- La red tiene que ser de 2.4 GHz y WPA2-Personal (sin portal de acceso). La IP la asigna el
  router: sale en el Monitor Serie a 115200 baudios, o se encuentra buscando el puerto 81 en la red.

## Alimentación

**No hay baterías** (PEND-13 sigue abierto): el kit no trae las 18650 ni el cargador y todavía no
se consiguen. Sin ellas los motores no se mueven, y la placa de la cámara se alimenta por USB-C:

- Desde la laptop (es el único cable que hay, y el mismo sirve para cargar el firmware).
- O desde un cargador de teléfono o una batería portátil con ese mismo cable: así la cámara
  transmite por WiFi sin estar atada a la laptop.

Los cables 5V/GND que van del L298N a la placa de la cámara están desconectados.

Solo con el USB de la laptop, la placa a veces se reinicia al arrancar (el Monitor Serie muestra
basura y `RTCWDT_RTC_RESET`) y la cámara falla; el firmware lo resuelve reiniciándose solo (ver
arriba). Un cargador de 5 V y 2 A o más debería evitarlo; no se ha probado.

## Fotos

En `docs/carro/`, reducidas a 1 MB o menos y sin datos EXIF:

| Archivo | Qué muestra |
|---|---|
| `frente_camara.jpg` | El carro de frente, con la ESP32-CAM montada |
| `lado.jpg` | Vista general de lado |
| `atras.jpg` | El carro por detrás, con el portabaterías |
| `video_transmitiendo.jpg` | El video de `:81/stream` en el navegador (2026-10-28) |
| `medida_llanta.jpg` | Escuadra pegada a la cara de la llanta, de borde a borde |
| `medida_altura_libre.jpg` | Escuadra vertical desde el piso (0 cm abajo) junto a un motor |
| `medida_camara.jpg` | Escuadra vertical junto al frente, **invertida**: el 0 queda arriba, a la altura del lente, y el 10 abajo, en el piso |

Se midió con una escuadra transparente. Los valores de la tabla de medidas son los que se
leyeron directo sobre la escuadra; en las fotos la escuadra queda un poco más cerca del teléfono
que el carro, así que leídas en la imagen pueden variar unos milímetros.
