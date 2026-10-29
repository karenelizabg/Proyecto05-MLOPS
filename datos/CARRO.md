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

### Verificación (P5-19, 2026-10-29)

Heri (A1) repitió dos medidas con regla sobre el mismo carro:

| Medida | Andy | Heri | Diferencia |
|---|---|---|---|
| Diámetro de llanta | 64 mm | 66 mm | 2 mm |
| Altura libre del chasis | 20 mm | 20 mm | 0 |

La altura libre, que es la que fija el límite, coincide. El diámetro difiere 2 mm (radio de 3.2 a
3.3 cm); no cambia el límite porque el radio queda por encima de la altura libre en los dos casos.

**Regla obstáculo / transitable** (la define P5-03 en `DOMINIO.md`): el límite es lo menor entre
el radio de la llanta y la altura libre del chasis. Con estas medidas es la altura libre:
**2 cm (20 mm)**, menor que el radio de 3.2 a 3.3 cm.

- **20 mm o más** es obstáculo: a esa altura el objeto ya toca los motores. Entre 2 y 3.2 cm
  la llanta podría subirse, pero los motores pegarían.
- **Menos de 20 mm** es transitable (un borrador, una tapa, un cable).

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

### Video desde otra computadora

El 2026-10-29 Heri (A1) abrió el video desde su MacBook Air con Safari, conectado a la misma red
que el carro, y comprobó que se movía en tiempo real (captura en `docs/carro/video_mac_safari.jpg`).
Con eso, dos personas del equipo vieron el video desde su propia computadora: Andy (Windows) y
Heri (macOS).

### Cuadros de prueba con objetos del dominio

Tres cuadros de la ESP32-CAM del carro, a 640×480, con objetos de las clases elegidas en P5-04
(`bottle` y `cup`). Son los mismos JPEG de las fotos de selección de P5-04, sin modificar: su
SHA-256 coincide con `modelo/experimentos-publicados/p5-04-yolo11n/evidencia/manifiesto.csv`.
Igual que las demás fotos de selección, **no** forman parte de las 8 secuencias de evaluación
(D-06).

| Archivo | Original en P5-04 | Objeto | SHA-256 |
|---|---|---|---|
| `objeto_botella_izq.jpg` | `botella_izq.jpg` | Botella a la izquierda | `b30d6f5b4e01c262527ca480ac32540bf065bdf2b0bec85ab4e8f409d224f7e1` |
| `objeto_botella_der.jpg` | `botella_der.jpg` | Botella a la derecha | `8e360d41326126ea58b781a071f583a9e8b7f5a841af0539e2c0ba19322a4e07` |
| `objeto_taza_centro_cerca.jpg` | `taza_centro_cerca.jpg` | Taza al centro, cerca | `670fec5473ceda61b5a6283711596d610d75577dfb1bc9d5ffc8de52c1e9cbcc` |

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
| `video_mac_safari.jpg` | El video abierto por Heri en Safari desde su MacBook Air (2026-10-29); las caras que salían en el video están pixeladas |
| `objeto_*.jpg` | Los tres cuadros de prueba con objetos (ver arriba); estos sí van sin reducir, tal como salieron de la cámara |
| `medida_llanta.jpg` | Escuadra pegada a la cara de la llanta, de borde a borde |
| `medida_altura_libre.jpg` | Escuadra vertical desde el piso (0 cm abajo) junto a un motor |
| `medida_camara.jpg` | Escuadra vertical junto al frente, **invertida**: el 0 queda arriba, a la altura del lente, y el 10 abajo, en el piso |

Se midió con una escuadra transparente. Los valores de la tabla de medidas son los que se
leyeron directo sobre la escuadra; en las fotos la escuadra queda un poco más cerca del teléfono
que el carro, así que leídas en la imagen pueden variar unos milímetros.
