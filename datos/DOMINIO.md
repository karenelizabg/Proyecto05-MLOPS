# Dominio de obstáculos y plan de filmación (P5-03)

Qué ve el carro, qué cuenta como obstáculo, qué no cubre el sistema y cómo se filman las 10
secuencias: S1–S8 son la evaluación (E3) y S9–S10 son solo para las pruebas del grupo B. Las
medidas del carro y la configuración de la cámara están en [`CARRO.md`](CARRO.md); aquí solo se
resumen.

## Sin ajuste (D-06)

**No hay partición de ajuste.** El detector es preentrenado y no se reentrena; el umbral de
confianza y el NMS se fijan en la configuración del detector **antes** de correrlo sobre los
cuadros, y su hash queda en `config_sha256`. **S1–S8 son de evaluación** y las métricas se reportan
sobre todas ellas.

**S9 y S10 no son de evaluación** (decisión del PM A, 2026-10-30): la regla de la política ya se
probó con esas posiciones, así que no son independientes, y dejar S1–S8 igual mantiene comparables
los resultados. Se reportan aparte. Si A1 o el grupo B piden que cuenten, se incluyen mostrando el
resultado con y sin ellas.

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
- **Ya tenemos las baterías, pero no se usan:** el control es virtual y el firmware no tiene paro
  automático ni control de velocidad. El carro se **empuja a mano** con la cámara alimentada por
  USB-C, en todas las secuencias.

Lo que eso implica para los cuadros:

- El horizonte queda a media imagen y el piso ocupa la mitad de abajo.
- Un objeto pegado al frente del carro sale **cortado por arriba** o queda fuera de cuadro, y uno
  pegado a las llantas no se ve.
- El OV2640 comprime en JPEG y rinde peor con poca luz.

## Clases

**Definitivas** (PEND-04, DC-5), aprobadas por el PM A (Karen) y el PM B (Ale V) el 2026-10-28:

| Objeto | Clase COCO | `class_id` |
|---|---|---|
| Botella | `bottle` | 39 |
| Taza | `cup` | 41 |

Salen de la prueba de P5-04 ([`modelo/DECISION.md`](../modelo/DECISION.md)): YOLO11n sobre 29
fotos tomadas con la ESP32-CAM del carro. El detector emite desde confianza 0.25 y NMS IoU 0.70;
la política del grupo B decide desde **0.50**. Con ese umbral:

- **Botella:** se detecta a la izquierda (0.64) y a la derecha (0.82); al centro de cerca queda en
  0.29 (también sale como `vase`) y lejos no aparece.
- **Taza:** se detecta al centro de cerca (0.96) y a la derecha (0.61); a la izquierda queda en
  0.30 y lejos no aparece.

Se **descartaron** la mochila (YOLO11n la confunde con `suitcase` en 5 de 7 fotos y a la derecha
no la detecta como `backpack`), la silla (a la izquierda sale como `tv`) y la maleta, que era un
estuche blando. Los `class_id` están en `modelo/clases.json`.

> **Pendiente del grupo B:** la política (`clases_obstaculo` en `config/control/politica.yaml`)
> todavía tiene las clases provisionales `[0, 1]`, y el PR #64 de Hannah las cambia a
> `[24, 39, 41]`. Debe quedar en **`[39, 41]`**. Mientras no se cambie, una botella o una taza no
> cuentan como obstáculo para B: un cuadro de S5 con las tres detecciones da AVANZAR en vez de STOP.
> Este documento no cambia la política; lo ajusta Hannah.

**Toda botella o taza que aparezca en un cuadro se anota**, también las laterales, lejanas y
parciales (P5-10). Un objeto de otra clase (el bote, un mueble, una mochila) no se anota.

## Regla obstáculo / transitable

**Obstáculo** es lo que el carro no puede pasar por encima: lo que mide más que el radio de la
llanta (3.2 cm) o que la altura libre del chasis (2 cm, hasta los motores), lo que sea menor.

> **Límite: 2 cm.** **2 cm o más** es obstáculo: a esa altura el objeto ya toca los motores.
> **Menos de 2 cm** es **transitable**: no se anota, no está en las clases y **no debe provocar
> STOP** (si no, el carro "siempre se detiene").

Entre 2 y 3.2 cm la llanta podría subir, pero los motores pegarían: también es obstáculo.

### Objetos de prueba

| Objeto | Altura | Veredicto | ¿Se comprobó pasando el carro? |
|---|---|---|---|
| Mochila | 35 cm | Obstáculo, pero sin clase: no se filma | No hace falta |
| Botella | 25 cm (aprox.) | Obstáculo | No hace falta |
| Taza | 9 cm | Obstáculo | No hace falta |
| Cajita de un tag | 0.5 cm | Transitable | Sí, pasa |
| Cuaderno pequeño, acostado | 1 cm | Transitable | Sí, pasa |
| Cable | 0.5 mm | Transitable | Sí, pasa |
| Borrador, acostado | **pendiente** | Transitable si mide menos de 2 cm | **pendiente** |
| Tapa | **pendiente** | Transitable si mide menos de 2 cm | **pendiente** |

S8 usa el **borrador, la tapa y el cable**, los transitables que nombra la expectativa de C1
(`casos/C1/expectativa.yaml`), para que el plan y el caso coincidan. La cajita y el cuaderno
quedan como transitables comprobados, pero no se filman.

Se comprobó empujando el carro a mano (2026-10-28). Con los motores sin alimentar las llantas
giran duro, porque arrastran la reducción de los motores; esa resistencia es del motor, no del
objeto.

Un transitable puede salir en el detector con una clase de COCO que no está entre las elegidas
(el cuaderno como `book`): esa detección no cuenta como obstáculo para la política, y el detector
debe filtrarla antes de emitir (P5-05) para que no sume falsos positivos en las métricas.

Los transitables se comprueban empujando el carro por encima: si se atoran con los motores o las
llantas no los pasan, no son transitables.

## Lo que el sistema no cubre

- **Obstáculos que no son botella ni taza.** El sistema solo reconoce esas dos clases: una
  mochila, una silla, una caja o un cono en la vía no frenan al carro. COCO ni siquiera tiene
  "caja", "cono" ni "borrador".
- **Botellas y tazas lejanas.** En las fotos de selección ninguna de las dos se detectó lejos.
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

Son 10 secuencias: S1–S8 de evaluación y S9–S10 solo para las pruebas del grupo B. Los casos C8 y
C9 (sin cuadros, cuadro viejo, errores del detector) no salen de video: son entradas fallidas que
arma P5-12. C10 (emergencia) es del grupo B y puede usar cualquier secuencia.

| Seq | Escena | Objetos | Casos | Estado esperado |
|---|---|---|---|---|
| S1 | Vía despejada | Ninguno | C1 | Despejado en todos los cuadros |
| S2 | Obstáculo al centro | Taza en el carril central | C2 | Obstáculo al centro |
| S3 | Obstáculo a la izquierda | Botella en el tercio izquierdo | C3 | Obstáculo a la izquierda, centro libre |
| S4 | Obstáculo a la derecha | La misma botella, en el tercio derecho (espejo de S3) | C4 | Obstáculo a la derecha, centro libre |
| S5 | Varios obstáculos | Botella a la izquierda, taza al centro y **otra** botella a la derecha, bien separadas | C5 | Sin zona libre: las tres zonas ocupadas |
| S6 | Libre → bloqueo → libre | Taza que entra al centro, sale un cuadro, vuelve y sale (≈ 15 cuadros; ver abajo) | C7 | Libre, bloqueo, libre (un cuadro), bloqueo, libre (≥ 5 cuadros) |
| S7 | Cerca del umbral de confianza | Taza al centro: empieza lejos (baja o sin detección) y el carro se acerca hasta que pasa de 0.50 | C6 | Lo que dé el detector; P5-12 marca qué cuadros quedan bajo y sobre el umbral |
| S8 | Otro cuarto, con transitables | El borrador, la tapa y el cable en la vía (los de C1) | C1, negativos | Despejado en todos los cuadros |
| S9 | Solo pruebas de B: taza cargada a la izquierda | Taza tocando el centro, cargada hacia la izquierda | Ninguno de E3 | Obstáculo al centro; la política gira a la derecha |
| S10 | Solo pruebas de B: taza cargada a la derecha | Taza tocando el centro, cargada hacia la derecha (espejo de S9) | Ninguno de E3 | Obstáculo al centro; la política gira a la izquierda |

Cobertura: C1 (S1, S8), C2 (S2), C3 (S3), C4 (S4), C5 (S5), C6 (S7) y C7 (S6). Cada caso C1–C7
tiene al menos una secuencia de evaluación.

El reparto sigue lo que se detectó mejor en P5-04: la botella a los lados y la taza al centro.
S5 es el más arriesgado: en las fotos con varios objetos el detector solo encontró uno, y C5
necesita las **tres** detecciones de 0.50 o más en el mismo cuadro; si falta una, queda una zona
libre.

**S6 cuadro por cuadro** (C7). Con unos 15 cuadros a 5 por segundo, unos 3 segundos:

| Cuadros | Tramo de C7 | La taza |
|---|---|---|
| 1–3 | `libre` | Fuera del centro |
| 4–6 | `bloqueo` | Al centro |
| 7 | `un_cuadro_libre` | Fuera, **un solo cuadro** |
| 8–10 | `bloqueo_otra_vez` | Al centro otra vez |
| 11–15 | `libre_otra_vez` | Fuera; C7 pide al menos cinco cuadros libres al final |

Una persona mete y saca la taza mientras el carro avanza despacio. Los números son una guía: el
tramo de cada cuadro lo da su anotación (taza al centro o no), y P5-12 lo registra en
`MAPA_CASOS.md`. Si el hueco libre del medio sale de cero o de dos cuadros, la secuencia se vuelve
a filmar.

**S9 y S10** (pedidas por el grupo B). S3 y S4 no sirven para probar el giro: el centro queda libre
y la política avanza recto. Aquí la taza ocupa el centro y su caja queda cargada hacia un lado. Con
la imagen de 640 px, el centro de la caja debe caer en **x ≈ 240–290** en S9 y en **x ≈ 350–400** en
S10, sin acercarse a x = 320, donde la política rompe el empate hacia la izquierda. La taza se queda
en su posición toda la toma. **S9 es la más arriesgada:** en P5-04 la taza a la izquierda quedó en
0.30, debajo del umbral de 0.50.

La caja de la taza debe medir **menos de 350 px de ancho**. Si es muy ancha, también ocupa los dos
lados y la política da STOP en lugar de girar: con la política de `main`, desde 398 px con el centro
en x = 290 o x = 350, y desde 354 px en x = 305. S10 se filmó con el centro en **x = 337–347**
según el detector, debajo de los 350 del plan; ahí sigue dando GIRAR_IZQ con cajas de menos de
360 px. Cada una lleva **12 cuadros**.

S9 y S10 se anotan con el mismo criterio que las demás, pero sus anotaciones van en
**`datos/pruebas-b/anotaciones.jsonl`**, no en `datos/anotaciones.jsonl`: `conjunto manifiesto`
falla si hay una anotación sin cuadro capturado. Sus cuadros se guardan **fuera de
`datos/cuadros/`**, porque el manifiesto y el benchmark toman todo lo que hay ahí:

```bash
python -m captura --url http://<ip>:81/stream --secuencia S09 --salida datos/pruebas-b
python -m captura --url http://<ip>:81/stream --secuencia S10 --salida datos/pruebas-b
```

Los intentos fallidos quedan en `datos/pruebas-b/_fallidas/` y no se suben.

### Tomas de prueba

Antes de filmar se hacen **tomas de prueba aparte**, con la misma cámara y el mismo lugar, para
comprobar que botella y taza se detectan con 0.50 o más en la posición y la distancia de cada
secuencia, en S5 las tres a la vez y en S9 y S10 la taza en la posición de cada una. Para S7 (C6)
se comprueba además que, acercando la taza, sale **al menos un cuadro con `cup` entre 0.25 y
0.50** (el detector la emite, la política la ignora) y otro con **0.50 o más**; si no, se cambia la
distancia o la luz de S7, sin tocar los umbrales congelados. Estas tomas son de selección como las de P5-04: **no**
entran a `datos/` ni a las métricas (D-06). Si una posición no se detecta, se ajusta la distancia
o la separación y se vuelve a probar antes de filmar.

### Cómo se filma

| Dato | Valor |
|---|---|
| Cuadros por secuencia | 10 a 12, y unos 15 en S6 (S1–S8: ≈ 85 a 100 en total; el mínimo de E3 es 60). S9 y S10 no cuentan para ese mínimo |
| Con obstáculo / despejados | S2–S6 casi todos con obstáculo, S1 y S8 despejados: ≈ 50 y ≈ 30 (mínimo 20 y 20) |
| Ritmo | ≈ 5 cuadros por segundo (uno cada 200 ms), el ritmo que supone el grupo B |
| Hueco máximo entre cuadros | **Menos de 400 ms** (`validez_orden_ms`); una secuencia con un hueco mayor se vuelve a filmar |
| Cómo se capturan | Script que lee el stream de la ESP32-CAM (`:81/stream`) y guarda los bytes JPEG como llegan, sin recomprimir, con la hora real de recepción (P5-09) |
| Distancia | Las secuencias empiezan a distancia media, no lejos: ni botella ni taza se detectaron lejos (salvo S7, que lo usa a propósito) |
| Movimiento | El carro se empuja a mano, despacio y en línea recta, hacia los objetos. Como las llantas giran duro con los motores sin alimentar, se empuja parejo para que no avance a saltos (un salto desenfoca el cuadro) |
| Quién filma | A2 (Andy), que tiene el carro; **pendiente** quién ayuda a empujar y a mover los objetos |
| Cuándo | **pendiente** |

- Ningún nombre de archivo lleva la clase ni el caso (P5-09).
- Los cuadros casi iguales se revisan con su SHA-256: un duplicado exacto se descarta.
- La cámara, el lugar y la luz no cambian entre S1 y S7, ni en S9 y S10; solo S8 cambia de cuarto.

## Pendiente

- [x] Clases aprobadas por los PM A y B tras P5-04 (PEND-04, DC-5): botella y taza.
- [ ] Conseguir una segunda botella para S5.
- [ ] Medir el borrador y la tapa de S8 y comprobarlos con el carro.
- [ ] Grupo B: `clases_obstaculo: [39, 41]` en la política (PR #64 de Hannah).
- [ ] Tomas de prueba de cada posición, de S5, de S9 y de S10 antes de filmar.
- [ ] Quién ayuda a filmar y cuándo.
