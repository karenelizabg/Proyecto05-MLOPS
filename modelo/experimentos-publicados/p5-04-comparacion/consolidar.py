"""Consolida P5-04 sin alterar los tres experimentos originales."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
MODELS = {
    "YOLO11n": ROOT / "p5-04-yolo11n" / "evidencia",
    "SSDLite320": ROOT / "p5-04-ssdlite320" / "evidencia",
    "YOLOX-Nano": ROOT / "p5-04-yolox-nano" / "evidencia",
}
GROUPS = ("botella", "mochila", "taza", "silla", "maleta")
CLASSES = {
    "botella": "bottle",
    "mochila": "backpack",
    "taza": "cup",
    "silla": "chair",
    "maleta": "suitcase",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def manifest_digest(rows: list[dict[str, str]]) -> str:
    content = "".join(
        row["archivo"] + row["sha256"] for row in sorted(rows, key=lambda item: item["archivo"])
    )
    return hashlib.sha256(content.encode()).hexdigest()


data = {}
for name, path in MODELS.items():
    required = (
        "configuracion.json",
        "manifiesto.csv",
        "por_imagen.csv",
        "detecciones.csv",
        "latencia_resumen.json",
        "revision_visual.csv",
        "revision_por_imagen.csv",
    )
    if any(not (path / item).is_file() for item in required):
        raise SystemExit(f"Evidencia incompleta: {name}")
    config = json.loads((path / "configuracion.json").read_text(encoding="utf-8"))
    latency = json.loads((path / "latencia_resumen.json").read_text(encoding="utf-8"))
    manifest = read_csv(path / "manifiesto.csv")
    images = read_csv(path / "por_imagen.csv")
    detections = read_csv(path / "detecciones.csv")
    review = read_csv(path / "revision_visual.csv")
    joined = read_csv(path / "revision_por_imagen.csv")
    keys = [{row["archivo"] for row in rows} for rows in (manifest, images, review, joined)]
    if (
        not all(len(rows) == 29 for rows in (manifest, images, review, joined))
        or not all(keys[0] == item for item in keys[1:])
        or len(keys[0]) != 29
    ):
        raise SystemExit(f"Inconsistencia de fotografías: {name}")
    if sum(int(row["detecciones"]) for row in images) != len(detections):
        raise SystemExit(f"Inconsistencia de detecciones: {name}")
    data[name] = {
        "config": config,
        "latency": latency,
        "manifest": manifest,
        "images": images,
        "detections": detections,
        "review": review,
    }

digests = {name: manifest_digest(item["manifest"]) for name, item in data.items()}
if len(set(digests.values())) != 1:
    raise SystemExit("Los tres manifiestos no tienen los mismos nombres y SHA-256")

association_rows = []
for group in GROUPS:
    expected = sum(row["archivo"].startswith(group + "_") for row in data["YOLO11n"]["manifest"])
    output = {"grupo": group, "clase_de_interes": CLASSES[group], "fotografias": expected}
    for name, item in data.items():
        selected = [row for row in item["review"] if row["archivo"].startswith(group + "_")]
        if len(selected) != expected:
            raise SystemExit(f"Revisión incompleta: {name}/{group}")
        if name == "YOLOX-Nano":
            count = sum(row["asociacion_clase_objetivo_valida"] == "1" for row in selected)
            invalid = sum(
                row["asociacion_clase_objetivo_geometria_invalida"] == "1" for row in selected
            )
            output["YOLOX-Nano_adicional_geometria_invalida"] = invalid
        else:
            count = sum(row["estado_visual"].startswith("coincide") for row in selected)
            # La revisión de silla_der en YOLO11n marca "parcial": chair cae
            # sobre la silla, aunque se omite una botella secundaria real.
            if name == "YOLO11n" and group == "silla":
                special = next(row for row in selected if row["archivo"] == "silla_der.jpg")
                assert (
                    special["estado_visual"] == "parcial"
                    and "chair sobre la silla" in special["observacion"]
                )
                count += 1
        output[name] = count
    association_rows.append(output)

for row in association_rows:
    # Contrasta con los resúmenes revisados de cada experimento.
    assert (
        row["YOLO11n"]
        == {"botella": 3, "mochila": 3, "taza": 3, "silla": 3, "maleta": 2}[row["grupo"]]
    )
    assert (
        row["SSDLite320"]
        == {"botella": 3, "mochila": 5, "taza": 3, "silla": 3, "maleta": 2}[row["grupo"]]
    )
    assert (
        row["YOLOX-Nano"]
        == {"botella": 3, "mochila": 2, "taza": 1, "silla": 1, "maleta": 1}[row["grupo"]]
    )

yolox_detections = data["YOLOX-Nano"]["detections"]
invalid = [row for row in yolox_detections if row["validacion"] != "ok"]
if len(invalid) != 3:
    raise SystemExit(f"Se esperaban tres cajas YOLOX fuera de límites; hay {len(invalid)}")
ratio = 416 / 640  # 0.65; letterbox alineado arriba a la izquierda.
clipping_rows = []
for row in invalid:
    box = [float(row[key]) for key in ("x1", "y1", "x2", "y2")]
    if not all(map(math.isfinite, box)):
        raise SystemExit("Caja con coordenada no finita")
    clipped = [
        min(640, max(0, box[0])),
        min(480, max(0, box[1])),
        min(640, max(0, box[2])),
        min(480, max(0, box[3])),
    ]
    clipping_rows.append(
        {
            "archivo": row["archivo"],
            "class_id": row["class_id"],
            "class_name": row["class_name"],
            "confidence": row["confidence"],
            "x1_original": box[0],
            "y1_original": box[1],
            "x2_original": box[2],
            "y2_original": box[3],
            "exceso_superior_px": -box[1],
            "y1_antes_de_dividir_por_ratio_0_65": box[1] * ratio,
            "x1_recortado_hipotetico": clipped[0],
            "y1_recortado_hipotetico": clipped[1],
            "x2_recortado_hipotetico": clipped[2],
            "y2_recortado_hipotetico": clipped[3],
            "caja_valida_tras_recorte": 0 <= clipped[0] < clipped[2] <= 640
            and 0 <= clipped[1] < clipped[3] <= 480,
        }
    )
if not all(row["caja_valida_tras_recorte"] for row in clipping_rows):
    raise SystemExit("El recorte hipotético no basta para validar todas las cajas")

summary = {
    "alcance": "Consolidación derivada; no altera experimentos originales; no benchmark P5-15",
    "fotografias": 29,
    "digest_nombres_y_sha256": next(iter(digests.values())),
    "modelos": {},
    "politica_clipping_hipotetica": {
        "momento": "después de decodificar, remapear y aplicar NMS; antes de validar o consumir",
        "regla": "x1,x2 a [0,640]; y1,y2 a [0,480]; descartar si x1>=x2 o y1>=y2",
        "detecciones_originales_yolox": len(yolox_detections),
        "detecciones_tras_recorte": len(yolox_detections),
        "cajas_originales_fuera_de_limites": 3,
        "cajas_validas_tras_recorte": 3,
        "asociaciones_backpack_validas_originales": 2,
        "asociaciones_backpack_validas_si_se_recorta": 3,
        "nota": "Escenario derivado; los CSV originales y el contrato v1 no se modifican",
    },
}
for name, item in data.items():
    config, latency = item["config"], item["latency"]
    summary["modelos"][name] = {
        "versiones": config["versiones"],
        "checkpoint_sha256": config["checkpoint_sha256"],
        "checkpoint_bytes": config["checkpoint_bytes"],
        "parametros": config["parametros"],
        "detecciones": len(item["detections"]),
        "fotos_sin_detecciones": sum(not row["clases_detectadas"] for row in item["images"]),
        "latencia_total_28_ms": latency["wall_ms"],
        "cajas_invalidas": len(latency["invalid_results"]),
    }

write_csv(HERE / "asociaciones_por_objeto.csv", association_rows)
write_csv(HERE / "cajas_yolox_analisis.csv", clipping_rows)
(HERE / "resumen_tecnico.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print("Consolidados tres experimentos y 29 fotografías idénticas; originales intactos.")
