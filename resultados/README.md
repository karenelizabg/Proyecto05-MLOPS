# resultados/

Salidas por cuadro (entregable **E6**): detecciones, decisiones, comandos y errores enlazados por `run_id`
y `frame_id`, más las métricas TP/FP/FN, precisión, recall y F1 recalculables con su script
(P5-13, P5-14, T14, T17). Se suben a Git: las cifras resumidas no bastan.

## Resultados por cuadro y trazabilidad (`python -m trazabilidad`, P5-14)

Une una corrida de `python -m control` con las anotaciones de P5-10, cuadro por cuadro, por `run_id` y
`frame_id`:

```bash
# 1. La corrida: los eventos del detector pasan por B (T14).
uv run python -m control --entrada <detector.jsonl> --config config/control/ --salida resultados/<run>/
# 2. Unirla con las anotaciones. Los hashes son los congelados del detector.
uv run python -m trazabilidad construir --corrida resultados/<run>/ --anotaciones datos/anotaciones.jsonl \
    --salida resultados/<run>/trazabilidad/ --model-sha256 <HASH> --config-sha256 <HASH>
# 3. Volver a sacar las cifras solo desde lo unido.
uv run python -m trazabilidad recalcular resultados/<run>/trazabilidad/
# 4. Un cuadro de punta a punta: del frame_id al comando.
uv run python -m trazabilidad cuadro resultados/<run>/trazabilidad/ <frame_id>
```

**`por_cuadro.jsonl`**: una línea por cuadro. Están todos los cuadros con evento y también los anotados que
el detector nunca emitió: siguen en el denominador de las métricas.

| Campo | Contenido |
|---|---|
| `run_id`, `frame_id`, `sequence_id` | La clave del cuadro. |
| `evento` | El evento del contrato v1 tal como lo emitió el detector: estado, `error` si lo hubo, detecciones, `model_sha256` y `config_sha256`. `null` si no hubo evento. |
| `anotacion` | La verdad de referencia del cuadro (formato de `config/anotaciones/`), o `null` si no está anotado. |
| `conteo` | TP/FP/FN del cuadro a IoU 0.50 (P5-13), o `null` si no está anotado. |
| `decision` | Qué decidió B: estados antes y después, acción, razón y quién decidió (política o supervisor). |
| `comando` | La orden que registró el adaptador: acción, velocidad, giro, `t_command_ms` y `valid_until_ms`. |
| `errores` | Lo que registró el supervisor para ese cuadro, con su `motivo` (p. ej. `cuadro_viejo`, `error_detector:<code>`). |
| `orden_evento`, `orden_anotacion` | Posición en los archivos de entrada, para recalcular en el mismo orden. |

**`ordenes_sin_cuadro.jsonl`**: las órdenes de B que no vienen de un cuadro (reloj, emergencia, rearme,
cierre).

**`resumen.json`**: las métricas de P5-13 (micro, por clase, criterio 1.4, procedencia, cobertura y mínimos
de E3), los conteos por secuencia (acciones, estados del detector y errores por motivo), la lista de errores
con su `frame_id`, los `model_sha256` y `config_sha256` vistos, la configuración de B con sus hashes
(`run.json`), el SHA-256 de cada entrada y de cada archivo escrito, y las advertencias. Nada se quita: un
cuadro sin decisión o sin comando es una advertencia.

**Recálculo:** `recalcular` lee solo `por_cuadro.jsonl` y `ordenes_sin_cuadro.jsonl` y vuelve a producir
las métricas, el TP/FP/FN de cada cuadro, los conteos y los hashes. Sale con `0` si da exactamente lo mismo
que `resumen.json` y con `1` si algo difiere o un archivo cambió desde que se escribió.

**El `frame_id` tiene que ser el mismo** en el detector y en las anotaciones. Si ninguno coincide,
`construir` no une nada y sale con `2`. `infer` (P5-05, #75) usa el nombre del JPEG sin extensión, que es el
`frame_id` del conjunto (`S01_f0001`), así que hay que pasarle los cuadros con su nombre original.

Salida de `construir`: `0` sin advertencias · `1` con advertencias (cuadros sin evento, errores del detector,
mínimos de E3, procedencia sin comprobar...) · `2` si no se puede leer o unir; no se escribe nada.
