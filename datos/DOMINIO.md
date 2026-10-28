# Dominio de obstáculos y plan de filmación (P5-03)

Qué ve el carro, qué cuenta como obstáculo, qué no cubre el sistema y cómo se filman las 8
secuencias de evaluación (E3). Las medidas del carro y la configuración de la cámara están en
[`CARRO.md`](CARRO.md); aquí solo se resumen.

## Sin ajuste (D-06)

**No hay partición de ajuste.** El detector es preentrenado y no se reentrena; el umbral de
confianza y el NMS se fijan en la configuración del detector **antes** de correrlo sobre los
cuadros, y su hash queda en `config_sha256`. Las **8 secuencias son de evaluación** y las métricas
se reportan sobre todas.

Las fotos que se usaron para escoger detector y objetos (P5-04, P5-19) **no** forman parte de
las secuencias ni se guardan en `datos/`.

## Escena

| Aspecto | Valor |
|---|---|
| Lugar | Interior: pasillo y cuarto de una casa |
| Piso | Duela laminada de madera, plana, sin desniveles |
| Luz | Luz de día por ventana, sin luz directa del sol sobre el piso |
| S8 | Otro cuarto de la misma casa, con otro fondo y otra luz |
| Fondo | Paredes claras, puertas y muebles de madera oscura, un bote de basura |
| Personas | Ninguna en cuadro. Si entra una mano para mover un objeto, sin rostros |

## Carro y cámara

Resumen de [`CARRO.md`](CARRO.md):

- Kit Carrito ESP32-CAM 4WD (el que recomendó el profe), sensor OV2640 con **lente fijo**.
- Cámara a **10 cm del piso, mirando al frente (0°)**. Cuadros de **640×480 en JPEG** (calidad 10),
  derechos desde el firmware. La configuración no cambia entre secuencias.
- **Sin baterías** (PEND-13): los motores no se mueven. El carro se **empuja a mano** con la
  cámara alimentada por USB-C.

Lo que eso implica para los cuadros:

- El horizonte queda a media imagen y el piso ocupa la mitad de abajo.
- Un objeto pegado al frente del carro sale **cortado por arriba** o queda fuera de cuadro, y uno
  pegado a las llantas no se ve.
- El OV2640 comprime en JPEG y rinde peor con poca luz.

## Clases

**Candidatas, sin aprobar todavía** (PEND-04, DC-5):

| Objeto | Clase COCO |
|---|---|
| Mochila | `backpack` |
| Botella | `bottle` |
| Taza | `cup` |
| Silla (de oficina) | `chair` |
| Maleta | `suitcase` |

A1 las prueba en P5-04 con 31 fotos tomadas con la ESP32-CAM del carro. Se eligen **3 o 4** con
la mejor detección, de modo que alguna pueda ir a un lado de la vía (C3, C4), y los PM A y B las
aprueban **antes de filmar**. Los `class_id` salen de `modelo/clases.json` (P5-04); la política
del grupo B (`clases_obstaculo`) usa un subconjunto de esas clases.

**Todo objeto de una clase elegida que aparezca en un cuadro se anota**, también los laterales,
lejanos y parciales (P5-10). Un objeto de otra clase (el bote, un mueble) no se anota.

## Regla obstáculo / transitable

**Obstáculo** es lo que el carro no puede pasar por encima: lo que mide más que el radio de la
llanta (3.2 cm) o que la altura libre del chasis (2 cm, hasta los motores), lo que sea menor.

> **Límite: 2 cm.** Más de 2 cm es obstáculo. Menos de 2 cm es **transitable**: no se anota, no
> está en las clases y **no debe provocar STOP** (si no, el carro "siempre se detiene").

Entre 2 y 3.2 cm la llanta podría subir, pero los motores pegarían: también es obstáculo.

### Objetos de prueba

| Objeto | Altura | Veredicto | ¿Se comprobó pasando el carro? |
|---|---|---|---|
| Mochila | 35 cm | Obstáculo | No hace falta |
| Botella | 25 cm (aprox.) | Obstáculo | No hace falta |
| Taza | 9 cm | Obstáculo | No hace falta |
| Cajita de un tag | 0.5 cm | Transitable | Sí, pasa |
| Cuaderno pequeño, acostado | 1 cm | Transitable | Sí, pasa |
| Cable | 0.5 mm | Transitable | Sí, pasa |

Se comprobó empujando el carro a mano (2026-10-28). Sin baterías las llantas giran duro, porque
arrastran la reducción de los motores; esa resistencia es del motor, no del objeto.

El cuaderno puede salir en el detector como `book`, una clase de COCO que no está entre las
elegidas: esa detección no cuenta como obstáculo para la política, y el detector debe filtrarla
antes de emitir (P5-05) para que no sume falsos positivos en las métricas.

Los transitables se comprueban empujando el carro por encima: si se atoran con los motores o las
llantas no los pasan, no son transitables.

## Lo que el sistema no cubre

- **Objetos sin clase en el detector.** COCO no tiene "caja", "cono" ni "borrador". Un obstáculo
  de una clase que no está en la lista no se detecta.
- **Desniveles, huecos y bordes** (escalones, alfombras gruesas, la orilla de una mesa).
- **Objetos transparentes o reflejantes.**
- **Poca luz y desenfoque por movimiento.**
- **Objetos fuera del campo de visión:** pegados al frente o a las llantas, o más altos que la
  imagen cuando están cerca.
- **Distancia y altura reales:** con una sola cámara no se miden; solo se infieren por la clase,
  el tamaño y la posición de la caja.
- **Lo que se vio en las fotos de selección** (P5-04, 2026-10-28):
  - Un objeto negro contra un fondo oscuro (la silla frente al mueble) casi se pierde.
  - Un objeto grande y muy saturado (la maleta roja de cerca) desajusta el balance de blancos y
    toda la imagen sale verdosa.
  - Muy de cerca solo se ve una parte del objeto (la base de la silla, la tela de la mochila).

## Plan de filmación

Las 8 secuencias, todas de evaluación. Los casos C8 y C9 (sin cuadros, cuadro viejo, errores del
detector) no salen de video: son entradas fallidas que arma P5-12. C10 (emergencia) es del grupo
B y puede usar cualquier secuencia.

| Seq | Escena | Objetos | Casos | Estado esperado |
|---|---|---|---|---|
| S1 | Vía despejada | Ninguno | C1 | Despejado en todos los cuadros |
| S2 | Obstáculo al centro | 1 objeto en el carril central | C2 | Obstáculo al centro |
| S3 | Obstáculo a la izquierda | 1 objeto en el tercio izquierdo | C3 | Obstáculo a la izquierda, centro libre |
| S4 | Obstáculo a la derecha | El mismo de S3, en el tercio derecho (espejo) | C4 | Obstáculo a la derecha, centro libre |
| S5 | Varios obstáculos | 3 objetos que ocupan izquierda, centro y derecha | C5 | Sin zona libre |
| S6 | Libre → bloqueo → libre | 1 objeto que entra al centro, sale un cuadro, vuelve y sale | C7 | Libre, bloqueo, libre (un cuadro), bloqueo, libre (≥ 5 cuadros) |
| S7 | Cerca del umbral de confianza | Objeto parcial, lejano o con poca luz | C6 | Lo que dé el detector; P5-12 marca qué cuadros quedan bajo y sobre el umbral |
| S8 | Otro cuarto, con transitables | La cajita, el cuaderno y el cable en la vía | C1, negativos | Despejado en todos los cuadros |

Cobertura: C1 (S1, S8), C2 (S2), C3 (S3), C4 (S4), C5 (S5), C6 (S7) y C7 (S6). Cada caso C1–C7
tiene al menos una secuencia.

### Cómo se filma

| Dato | Valor |
|---|---|
| Cuadros por secuencia | 10 a 12 (≈ 80 a 96 en total; el mínimo de E3 es 60) |
| Con obstáculo / despejados | S2–S6 casi todos con obstáculo, S1 y S8 despejados: ≈ 50 y ≈ 30 (mínimo 20 y 20) |
| Ritmo | ≈ 5 cuadros por segundo (uno cada 200 ms), el ritmo que supone el grupo B |
| Hueco máximo entre cuadros | **Menos de 400 ms** (`validez_orden_ms`); una secuencia con un hueco mayor se vuelve a filmar |
| Cómo se capturan | Script que lee el stream de la ESP32-CAM (`:81/stream`) y guarda los bytes JPEG como llegan, sin recomprimir, con la hora real de recepción (P5-09) |
| Movimiento | El carro se empuja a mano, despacio y en línea recta, hacia los objetos. Como las llantas giran duro sin baterías, se empuja parejo para que no avance a saltos (un salto desenfoca el cuadro) |
| Quién filma | A2 (Andy), que tiene el carro; **pendiente** quién ayuda a empujar y a mover los objetos |
| Cuándo | **pendiente** |

- Ningún nombre de archivo lleva la clase ni el caso (P5-09).
- Los cuadros casi iguales se revisan con su SHA-256: un duplicado exacto se descarta.
- La cámara, el lugar y la luz no cambian entre S1 y S7; solo S8 cambia de cuarto.

## Pendiente

- [ ] Clases aprobadas por los PM A y B tras P5-04 (PEND-04, DC-5); entonces se actualiza la tabla
      de clases y los objetos de cada secuencia.
- [ ] Quién ayuda a filmar y cuándo.
