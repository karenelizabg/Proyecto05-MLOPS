"""Une la revisión visual manual a las detecciones de SSDLite320."""

import csv
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).parent / "evidencia"


def read(name):
    with (ROOT / name).open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def write(name, fields, rows):
    with (ROOT / name).open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


images = read("por_imagen.csv")
reviews = {row["archivo"]: row for row in read("revision_visual.csv")}
detections = defaultdict(list)
for row in read("detecciones.csv"):
    detections[row["archivo"]].append(row)
if len(images) != 29 or len(reviews) != 29 or {row["archivo"] for row in images} != set(reviews):
    raise SystemExit("Revisión visual incompleta o archivos diferentes")

combined = []
for item in images:
    name = item["archivo"]
    found = detections[name]
    if len(found) != int(item["detecciones"]):
        raise SystemExit(f"Conteo diferente en {name}")
    combined.append({
        "archivo": name,
        "grupo_nombre": item["grupo_nombre"],
        "objeto_visible": reviews[name]["objeto_visible"],
        "clases_confianzas": "; ".join(
            f"{row['class_name']}:{float(row['confidence']):.3f}" for row in found
        ),
        "detecciones": len(found),
        "estado_visual": reviews[name]["estado_visual"],
        "observacion": reviews[name]["observacion"],
    })
write("revision_por_imagen.csv", list(combined[0]), combined)

expected = {
    "botella": ("bottle",), "mochila": ("backpack",),
    "taza": ("cup",), "silla": ("chair",),
    "maleta": ("suitcase", "handbag"),
}
summary = []
for group in ("botella", "mochila", "taza", "silla", "maleta", "vacio", "varios"):
    subset = [row for row in combined if row["grupo_nombre"] == group]
    associated = sum(row["estado_visual"].startswith("coincide") for row in subset)
    summary.append({
        "grupo": group, "fotografias": len(subset),
        "clases_de_interes": ";".join(expected.get(group, ())),
        "asociaciones_visuales_clase_interes": associated if group in expected else "no aplica",
        "observacion": "Conteo exploratorio visual; no es métrica de recall ni verdad de referencia",
    })
write("resumen_por_objeto.csv", list(summary[0]), summary)
print(f"Revisión de {len(combined)} fotografías y {len(summary)} grupos")
