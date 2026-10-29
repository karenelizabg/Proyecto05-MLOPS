# mediciones/

Benchmark y límites (entregable **E7**): 10 calentamientos + 100 ejecuciones válidas con un registro por
ejecución, tiempos por etapa, p50/p95/máximo, hardware y runtime, y el reporte de límites (P5-15, P5-16).

## Equipo declarado (PEND-05)

El benchmark del entregable se mide en **la laptop de A3 (Ale)**, conectada a la corriente. Lo da A3 según
PEND-05; P5-04 comprueba que el detector elegido corre aquí.

| Dato | Valor |
|---|---|
| SO | Windows 11 Pro (10.0.26200), 64 bits |
| CPU | Intel Core i5-1135G7 @ 2.40 GHz (4 núcleos, 8 hilos) |
| RAM | 8 GB |
| Python | 3.12.14 (el de `.python-version`, con `uv`) |
| GPU | No se usa: todo en CPU |

`resumen.json` vuelve a registrar en cada corrida el SO, el CPU, la RAM, si estaba conectada a la corriente y las
versiones, así que se puede comprobar que se midió aquí.

## Comando (`python -m bench`)

```bash
uv run python -m bench \
  --entradas datos/cuadros/ \
  --salida mediciones/<run>/ \
  --equipo "laptop de A3" \
  --detector <módulo del detector> \
  --model-sha256 <hash de los pesos congelados> --config-sha256 <hash de la configuración congelada>
```

- `--entradas`: imágenes o carpetas (de una carpeta se toman `.jpg`, `.jpeg` y `.png` en orden de nombre). Se
  recorren en ciclo hasta juntar las ejecuciones.
- `--detector falso` (el valor por omisión) usa el detector de prueba del arnés. El detector real (P5-05) se
  conecta con un módulo que expone `crear(**opciones)` y devuelve un objeto como el `Detector` de
  [`src/bench/detector.py`](../src/bench/detector.py). `--opcion clave=valor` se pasa a `crear`.
- `--mediciones` (100 por omisión, no menos) y `--max-fallos` (10). `--sin-politica` mide solo el detector.

**Qué se mide** en cada ejecución, con `time.perf_counter_ns`: `preprocesamiento_ms`, `inferencia_ms`,
`posprocesamiento_ms`, `politica_ms` (el Supervisor de B con la política y el AdaptadorVirtual reales, con la
configuración de `config/control/`) y `total_ms`, la suma de las etapas. **No se mide** leer y decodificar la
imagen, cargar el modelo ni las pausas de reproducción: un cuadro sale en cuanto termina el anterior.

**Qué escribe** (la carpeta debe estar vacía, para no mezclar corridas):

| Archivo | Contenido |
|---|---|
| `ejecuciones.csv` | Una fila por ejecución válida: `intento`, `fase` (`calentamiento` o `medicion`), entrada, cada etapa en ms, número de detecciones y la acción que decidió B. |
| `fallos.csv` | Las ejecuciones que fallaron, **aparte**: etapa, tipo de error y mensaje. No cuentan ni entran en p50/p95; el arnés sigue hasta juntar las 10 + 100 válidas. |
| `resumen.json` | Por etapa: p50, p95, máximo, mínimo y media de las 100 mediciones (sin calentamientos). Hardware, energía, runtime e hilos, pesos (ruta, bytes, SHA-256), procedencia, protocolo, SHA-256 de cada entrada y de los CSV, y advertencias. |

**Procedencia:** si el `model_sha256` o el `config_sha256` del detector no son los congelados, o los pesos no
tienen el SHA-256 que dice el detector, **no se mide** (salida 2). Sin `--model-sha256` o `--config-sha256` se mide
pero queda como advertencia.

**Código de salida:** `0` completo y sin advertencias · `1` se midió pero hay advertencias (detector falso, hashes
sin indicar, equipo sin declarar, en batería, sin política) o quedó incompleto porque los fallos pasaron de
`--max-fallos` · `2` no se mide así (configuración distinta, entradas o argumentos inválidos; no se escribe nada).
La medición del entregable debe salir con `0`.

El percentil es lineal (posición `(n - 1) * q`, interpolando entre vecinos), igual que en P4. P5-16 contrasta el p95
y el máximo con los plazos de `config/control/plazos.yaml`.
