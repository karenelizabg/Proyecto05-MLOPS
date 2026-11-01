# P5-05 · revisión independiente de A3 en Windows

**Estado:** A3 ejecutó tres JPEG en Windows 11 y solicitó cambios en el [PR #75](https://github.com/karenelizabg/Proyecto05-MLOPS/pull/75); todavía faltan una escena múltiple, una despejada y el dictamen sobre las omisiones. Su medición Windows previa (p95 aproximado de 153 ms) usó siete hilos intraop efectivos. La [evidencia macOS integrada](P5-05-ACEPTACION.md) usa el código local con un hilo efectivo, calentamiento sintético antes del reloj y Pillow de P5-09; las cifras no son directamente comparables hasta repetir la revisión en Windows con el mismo commit. Estas instrucciones se aplican al [issue #7](https://github.com/karenelizabg/Proyecto05-MLOPS/issues/7). Mantener Ultralytics 8.3.0, el checkpoint aprobado y la configuración actual. No cambiar umbrales durante esta revisión.

Heri añadió una [captura auténtica del CLI integrado](P5-05-COMANDO-INTEGRADO.png)
y [su JSONL validado](p5-05-comando-integrado.jsonl): un JPEG neutral,
`1 cuadros, 0 errores` y contrato v1 `OK (1 eventos)`. La
[captura anterior](P5-05-COMANDO.png) y [su JSONL](p5-05-captura-evidencia.jsonl)
permanecen como evidencia histórica. Esta ejecución macOS no sustituye la
selección independiente ni las mediciones Windows de A3.

## Bloqueos previos

1. La rama `p5-05-detector-infer` está publicada en el [PR #75](https://github.com/karenelizabg/Proyecto05-MLOPS/pull/75). Clonar esa rama y registrar el commit exacto antes de la revisión; no cambiar modelo, umbrales ni dependencias.
2. Los 29 JPEG de P5-04 están fuera del repositorio. Ale necesita recibir los bytes originales por un medio acordado o elegir sus propios cuatro JPEG. Para revisar específicamente varios_1 y varios_2 necesita esos dos archivos, con los SHA-256 indicados más abajo. Las anotaciones y los manifiestos no son entrada de inferencia. El CLI usa el nombre del JPEG sin extensión como `frame_id`: preparar copias con nombres neutros sin alterar los originales.
3. El checkpoint no está en el repositorio. P5-04 lo obtuvo de la [release oficial de Ultralytics v8.3.0](https://github.com/ultralytics/assets/releases/tag/v8.3.0); la release contiene el artefacto yolo11n.pt de 5 613 764 bytes. La URL de abajo es la del procedimiento ya usado. Si GitHub está inaccesible, obtener una copia del mismo archivo aprobado mediante un medio acordado y comprobar su hash; no usar otro modelo ni permitir una descarga automática de infer.

## Preparación en Windows PowerShell

Requisitos: Windows x86_64, Git, conexión **solo para obtener uv/dependencias/checkpoint**, espacio suficiente para el entorno PyTorch y cuatro JPEG. Python 3.12 está fijado en .python-version y pyproject.toml. El lockfile integrado fija Ultralytics 8.3.0, PyTorch 2.9.0, Torchvision 0.24.0, OpenCV 4.11.0.86, NumPy 1.26.4 y Pillow 12.3.0 de P5-09. Esta revisión debe esperar la publicación de los commits locales de P5-05; registrar el HEAD realmente instalado. Estas instrucciones son para PowerShell, no Git Bash. El comando de instalación de uv sigue la [documentación oficial de Astral](https://docs.astral.sh/uv/getting-started/installation/).

En un directorio nuevo:

~~~powershell
$Repo = Join-Path $HOME 'Proyecto05-MLOPS-P5-05'
git clone --branch p5-05-detector-infer --single-branch https://github.com/karenelizabg/Proyecto05-MLOPS.git $Repo
Set-Location $Repo
git rev-parse HEAD
git status --short

powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/0.13.6/install.ps1 | iex"
uv --version
uv python install 3.12
uv sync --locked
$Python = Join-Path (Get-Location).Path '.venv\Scripts\python.exe'
& $Python --version
~~~

Si uv ya está instalado, omitir únicamente el instalador y registrar uv --version. Si uv no aparece en el PATH inmediatamente después del instalador, abrir una nueva ventana PowerShell, volver con Set-Location $Repo y continuar desde uv --version. Si el lockfile no se instala, guardar el error y detener la revisión: no cambiar versiones ni editar uv.lock. Registrar el commit de HEAD para poder repetir la prueba.

### Checkpoint aprobado y hash

La descarga siguiente es **manual y previa a la inferencia**, desde la release oficial citada por P5-04. Se guarda fuera del clon. Si Ale recibe una copia aprobada, sustituye solo la línea Invoke-WebRequest por una copia a $Weights y ejecuta las mismas verificaciones.

~~~powershell
$WeightsDir = Join-Path $env:LOCALAPPDATA 'P5-05'
New-Item -ItemType Directory -Force -Path $WeightsDir | Out-Null
$Weights = Join-Path $WeightsDir 'yolo11n.pt'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri 'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt' -OutFile $Weights
$Expected = '0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1'
$Actual = (Get-FileHash -LiteralPath $Weights -Algorithm SHA256).Hash.ToLowerInvariant()
$Size = (Get-Item -LiteralPath $Weights).Length
if ($Actual -ne $Expected -or $Size -ne 5613764) { throw "Checkpoint incorrecto: SHA=$Actual; bytes=$Size" }
"Checkpoint verificado: SHA=$Actual; bytes=$Size"
~~~

No continuar si el hash no coincide. El CLI repetirá la verificación **antes** de deserializar. Una vez instaladas las dependencias y obtenido el checkpoint, la inferencia puede ejecutarse sin red.

## Selección ciega y ejecución de cuatro JPEG

Ale elige **independientemente** un JPEG con objeto central, uno lateral, uno con varios objetos y uno sin objetos. Registrar su elección y el SHA-256 de cada JPEG **antes de mirar las salidas macOS**. Puede usar las fotos recibidas de P5-04 o fotos propias. No introducir anotaciones, nombres de clase, manifiestos ni archivos CSV como entrada del comando. Evitar nombres con caracteres no ASCII hasta verificar que OpenCV los decodifique en su equipo.

Sustituir las cuatro rutas por archivos reales. Cada imagen se procesa como JPEG individual: t_capture_ms es el instante de recepción durante ese run, **no una fecha histórica inventada**. Los cuatro run_id distintos generan cuatro JSONL; el nombre de archivo determina solo `frame_id`, nunca las detecciones. Copiar cada JPEG a un nombre neutro `S01_f0001.jpg` a `S01_f0004.jpg` antes de inferir y comparar el SHA-256 de la copia.

~~~powershell
$Central  = 'C:\ruta\de\Ale\central.jpg'
$Lateral  = 'C:\ruta\de\Ale\lateral.jpg'
$Varios   = 'C:\ruta\de\Ale\varios.jpg'
$Vacio    = 'C:\ruta\de\Ale\despejado.jpg'
$ReviewDir = Join-Path $WeightsDir 'revision-a3'
New-Item -ItemType Directory -Force -Path $ReviewDir | Out-Null
Start-Transcript -Path (Join-Path $ReviewDir 'comandos-powershell.txt')
$Cases = @(
    @{ Name = 'central';  Path = $Central },
    @{ Name = 'lateral';  Path = $Lateral },
    @{ Name = 'varios';   Path = $Varios },
    @{ Name = 'despejado'; Path = $Vacio }
)
$FrameIndex = 1
foreach ($Case in $Cases) {
    if (-not (Test-Path -LiteralPath $Case.Path -PathType Leaf)) { throw "Falta JPEG: $($Case.Path)" }
    $InputHash = (Get-FileHash -LiteralPath $Case.Path -Algorithm SHA256).Hash.ToLowerInvariant()
    "Entrada $($Case.Name): $($Case.Path), SHA-256=$InputHash"
    $Neutral = Join-Path $ReviewDir ('S01_f{0:D4}.jpg' -f $FrameIndex)
    if (Test-Path -LiteralPath $Neutral) { throw "La copia neutral ya existe: $Neutral" }
    Copy-Item -LiteralPath $Case.Path -Destination $Neutral
    if ((Get-FileHash -LiteralPath $Neutral -Algorithm SHA256).Hash.ToLowerInvariant() -ne $InputHash) {
        throw "La copia neutral no coincide: $Neutral"
    }
    $Out = Join-Path $ReviewDir ($Case.Name + '.jsonl')
    $RunId = 'a3-' + $Case.Name
    & $Python -m infer --input $Neutral --config .\config\detector.json --weights $Weights --output $Out --run-id $RunId
    if ($LASTEXITCODE -ne 0) { throw "infer falló en $($Case.Name); revisar JSONL y stderr" }
    & $Python -m contrato $Out
    if ($LASTEXITCODE -ne 0) { throw "Contrato v1 inválido en $Out" }
    $Event = Get-Content -LiteralPath $Out -TotalCount 1 -Encoding UTF8 | ConvertFrom-Json
    $Event | Select-Object frame_id,status,image_width,image_height,model_sha256,config_sha256
    $Event.detections | Format-Table class_id,confidence,@{Name='bbox_xyxy';Expression={$_.bbox -join ', '}}
    if ($Case.Name -eq 'despejado' -and ($Event.status -ne 'ok' -or $Event.detections.Count -ne 0)) {
        throw 'El caso despejado no dio status=ok con detections=[]'
    }
    $FrameIndex++
}
Stop-Transcript
~~~

El chequeo de despejado es una **expectativa de la imagen elegida por Ale**: si el modelo marca un objeto real o un falso positivo, registrar el resultado y la imagen, no cambiar el detector para forzar una lista vacía. Si se quiere reproducir una secuencia, usar un directorio y un --capture-ms explícito por JPEG, en el orden lexicográfico; no usar los nombres para inventar tiempos de captura.

### Inspección visual de cajas

Leer cada JSONL y abrir el JPEG original. Las cajas son [x1,y1,x2,y2] en **píxeles de la imagen original**, con origen arriba a la izquierda. Confirmar 0 ≤ x1 < x2 ≤ image_width y 0 ≤ y1 < y2 ≤ image_height, y que la caja rodee visualmente el objeto de la clase indicada. Una lista vacía no debe dibujar caja.

El siguiente bloque **solo dibuja una copia de revisión**, nunca alimenta al detector. Después de definir $Cases y $ReviewDir arriba, ejecutarlo en PowerShell para crear PNG de inspección:

~~~powershell
$OverlayCode = @'
import cv2, json, sys
from pathlib import Path
image = cv2.imread(sys.argv[1], cv2.IMREAD_COLOR)
event = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8").splitlines()[0])
if image is None or (image.shape[1], image.shape[0]) != (event["image_width"], event["image_height"]):
    raise SystemExit("JPEG y dimensiones del evento no coinciden")
for detection in event["detections"]:
    x1, y1, x2, y2 = detection["bbox"]
    cv2.rectangle(image, (round(x1), round(y1)), (round(x2), round(y2)), (0, 255, 0), 2)
    cv2.putText(image, str(detection["class_id"]), (round(x1), max(12, round(y1))),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
if not cv2.imwrite(sys.argv[3], image):
    raise SystemExit("No se pudo escribir la copia de inspección")
'@
foreach ($Case in $Cases) {
    $Out = Join-Path $ReviewDir ($Case.Name + '.jsonl')
    $Overlay = Join-Path $ReviewDir ($Case.Name + '-cajas.png')
    $OverlayCode | & $Python - $Case.Path $Out $Overlay
    if ($LASTEXITCODE -ne 0) { throw "No se pudo crear $Overlay" }
}
~~~

La inspección puede complementarse con una captura de la terminal y de las imágenes superpuestas. Guardar el juicio visual por clase y por objeto; un JSONL válido no prueba que todas las detecciones sean correctas.

## Omisiones de varios_1 y varios_2

Tras la selección ciega, revisar también los **dos archivos exactos** de P5-04. Ale debe recibirlos fuera del repositorio y comprobar SHA-256:

| JPEG | SHA-256 esperado | macOS P5-05 |
|---|---|---|
| varios_1.jpg | fcd354f2ae91480f872f672ef19d17bc7a17f00bde47c4ae04dadb | bottle 39, confianza 0.2691411376, bbox [296.1824,107.0134,346.9567,274.1030]; taza visible omitida |
| varios_2.jpg | 12bf69b11bad6f4fbf70d7dae7655ae0cd4cea0e0c5e85ad7647806f935da6c6 | status=ok, detections=[]; botella y taza visibles omitidas |

Sustituir las rutas, comprobar los bytes y ejecutar **copias neutrales** como JPEG individuales, con nuevos run_id y archivos de salida. El SHA-256 completo de `varios_1` se comprobó contra el manifiesto histórico de P5-04:

~~~powershell
$Varios1 = 'C:\ruta\de\Ale\varios_1.jpg'
$Varios2 = 'C:\ruta\de\Ale\varios_2.jpg'
$Hash1 = (Get-FileHash -LiteralPath $Varios1 -Algorithm SHA256).Hash.ToLowerInvariant()
$Hash2 = (Get-FileHash -LiteralPath $Varios2 -Algorithm SHA256).Hash.ToLowerInvariant()
if ($Hash1 -ne 'fcd354f2ae91480f872f672ef19d17bc7a17f00bde47c4ae04dadb') { throw 'varios_1 no coincide' }
if ($Hash2 -ne '12bf69b11bad6f4fbf70d7dae7655ae0cd4cea0e0c5e85ad7647806f935da6c6') { throw 'varios_2 no coincide' }
$Neutral1 = Join-Path $ReviewDir 'S01_f0005.jpg'
$Neutral2 = Join-Path $ReviewDir 'S01_f0006.jpg'
if ((Test-Path -LiteralPath $Neutral1) -or (Test-Path -LiteralPath $Neutral2)) { throw 'Las copias neutrales ya existen' }
Copy-Item -LiteralPath $Varios1 -Destination $Neutral1
Copy-Item -LiteralPath $Varios2 -Destination $Neutral2
if ((Get-FileHash -LiteralPath $Neutral1 -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Hash1) { throw 'Copia de varios_1 alterada' }
if ((Get-FileHash -LiteralPath $Neutral2 -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Hash2) { throw 'Copia de varios_2 alterada' }
$Out1 = Join-Path $ReviewDir 'varios_1.jsonl'
$Out2 = Join-Path $ReviewDir 'varios_2.jsonl'
& $Python -m infer --input $Neutral1 --config .\config\detector.json --weights $Weights --output $Out1 --run-id a3-varios-1
if ($LASTEXITCODE -ne 0) { throw 'infer falló en varios_1' }
& $Python -m infer --input $Neutral2 --config .\config\detector.json --weights $Weights --output $Out2 --run-id a3-varios-2
if ($LASTEXITCODE -ne 0) { throw 'infer falló en varios_2' }
& $Python -m contrato $Out1 $Out2
if ($LASTEXITCODE -ne 0) { throw 'Contrato v1 inválido en varios_1 o varios_2' }
~~~

Registrar si Windows reproduce el mismo conteo, orden, clase, confianza y bbox; para diferencias numéricas anotar Δconfianza máximo y Δbbox máximo en píxeles. Comparar **solo las detecciones**, no los timestamps ni el run_id.

Un JPEG legible con status=ok, dimensiones correctas, hashes aprobados y una omisión repetida en ambos equipos apunta al comportamiento del detector con confianza 0.25/NMS 0.70. Un status=error, dimensiones erróneas, hash distinto, cajas fuera de límites o discrepancia Windows/macOS no explicada obliga a investigar el pipeline o entorno. No atribuir automáticamente toda omisión al modelo ni declararla aceptable sin la revisión de A3.

Ale debe concluir por escrito: **¿son aceptables estas omisiones para el alcance aprobado de P5-05?** Indicar fundamento, objetos visibles perdidos, impacto y si solicita una evaluación posterior de modelo/umbral. No cambiar el modelo ni la configuración en esta revisión: hacerlo alteraría config_sha256 y la evidencia de P5-04.

## Entorno y registro que entregará Ale

Ejecutar y conservar la salida junto con el transcript y los JSONL:

~~~powershell
Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,OSArchitecture,@{Name='RAM_GiB';Expression={[math]::Round($_.TotalVisibleMemorySize / 1MB, 2)}}
Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors
uv --version
& $Python -c 'import sys, importlib.metadata as m; print(sys.version); print({p:m.version(p) for p in ("ultralytics","torch","torchvision","opencv-python","numpy","pillow")})'
& $Python -c 'from infer.config import cargar_config_detector; print(cargar_config_detector().config_sha256)'
~~~

Si Ale mide rendimiento en esa laptop, guardar **10 calentamientos y al menos 30 inferencias medidas**; el [script](p5-05-benchmark.py) hace un calentamiento sintético mediante el predictor, 10 JPEG excluidos y 50 JPEG medidos, y registra por separado carga y preparación:

~~~powershell
& $Python .\resultados\p5-05-benchmark.py --weights $Weights --image $Central --output (Join-Path $ReviewDir 'latencia-windows.json')
& $Python .\resultados\p5-05-benchmark.py --weights $Weights --image $Central --output (Join-Path $ReviewDir 'latencia-windows-replica.json')
~~~

El benchmark exige un nombre de salida nuevo y rechaza un archivo o enlace
final existente; para repetirlo, usar otro nombre. Los directorios padres
enlazados pueden redirigir la salida y deben ser confiables. Registrar el
SHA-256 de la imagen antes y después de medir; si cambia, descartar esa serie.
Comprobar `torch_threads_configured`, `torch_threads_after_setup`,
`torch_threads_after_warmup` y `torch_threads_effective`: deben valer 1.
Comparar p50, p95 y máximo de ambas series con la evidencia macOS actual;
no usar el p95 Windows previo de 153 ms como medición de esta versión.

Entregar: (1) commit revisado, SO/CPU/RAM y versiones; (2) SHA-256 de pesos, config y cada JPEG; (3) cuatro JSONL y resultado de python -m contrato; (4) PNG con cajas y juicio visual, incluida la escena vacía; (5) resultados específicos de varios_1/varios_2 y conclusión de aceptabilidad; (6) diferencias numéricas frente a macOS, si son los mismos bytes; (7) transcript/captura del comando; (8) latencia Windows si se ejecutó. El registro puede añadirse a una copia de este archivo o en un documento nuevo, **sin modificar la evidencia macOS**.

**Plantilla de conclusión de A3 (sin completar):**

| Caso | SHA-256 JPEG | Estado / clases / confianzas / bbox | ¿Caja alineada visualmente? | Objetos visibles omitidos | Diferencia frente a macOS |
|---|---|---|---|---|---|
| Central | pendiente | pendiente | pendiente | pendiente | pendiente |
| Lateral | pendiente | pendiente | pendiente | pendiente | pendiente |
| Varios | pendiente | pendiente | pendiente | pendiente | pendiente |
| Despejado | pendiente | pendiente | pendiente | pendiente | pendiente |
| varios_1 | pendiente | pendiente | pendiente | pendiente | pendiente |
| varios_2 | pendiente | pendiente | pendiente | pendiente | pendiente |

**Dictamen sobre omisiones:** pendiente de A3. **Aceptación de P5-05:** pendiente de A3.
