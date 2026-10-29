"""Une la salida de inferencia con la revisión visual manual de P5-04."""

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "evidencia"


def read(name):
    with (ROOT / name).open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def write(name, rows):
    with (ROOT / name).open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


images = read("por_imagen.csv")
review = read("revision_visual.csv")
assert len(images) == len(review) == 29
by_name = {row["archivo"]: row for row in review}
assert len(by_name) == 29 and set(by_name) == {row["archivo"] for row in images}
combined = []
for image in images:
    visual = by_name[image["archivo"]]
    combined.append({**image, **{k: v for k, v in visual.items() if k != "archivo"}})
write("revision_por_imagen.csv", combined)

interests = {
    "botella": "bottle",
    "mochila": "backpack",
    "taza": "cup",
    "silla": "chair",
    "maleta": "suitcase;handbag",
    "vacio": "",
    "varios": "",
}
summary = []
for group, classes in interests.items():
    rows = [row for row in combined if row["grupo_nombre"] == group]
    valid = sum(row["asociacion_clase_objetivo_valida"] == "1" for row in rows)
    invalid = sum(row["asociacion_clase_objetivo_geometria_invalida"] == "1" for row in rows)
    summary.append(
        {
            "grupo": group,
            "fotografias": len(rows),
            "clases_de_interes": classes,
            "asociaciones_visuales_clase_interes_geometria_valida": valid
            if classes
            else "no aplica",
            "asociaciones_visuales_geometria_invalida": invalid if classes else "no aplica",
            "observacion": (
                "Juicio visual exploratorio; no es una métrica formal de recall "
                "ni verdad de referencia"
            ),
        }
    )
assert sum(int(row["fotografias"]) for row in summary) == 29
write("resumen_por_objeto.csv", summary)
print("Revisión: 29 fotografías; resumen por siete grupos.")
