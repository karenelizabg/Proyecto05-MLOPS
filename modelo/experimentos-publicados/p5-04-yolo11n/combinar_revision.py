"""Une la revision visual manual con los resultados crudos por nombre de archivo."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidencia"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def main() -> None:
    images = read_csv(EVIDENCE / "por_imagen.csv")
    detections = defaultdict(list)
    for row in read_csv(EVIDENCE / "detecciones.csv"):
        detections[row["archivo"]].append(row)
    visual = {row["archivo"]: row for row in read_csv(EVIDENCE / "revision_visual.csv")}
    if set(visual) != {row["archivo"] for row in images}:
        raise SystemExit("La revision visual no cubre exactamente las imagenes inferidas")

    fields = [
        "archivo",
        "grupo_nombre",
        "objeto_visible",
        "clases_confianzas",
        "detecciones",
        "estado_visual",
        "observacion",
    ]
    with (EVIDENCE / "revision_por_imagen.csv").open(
        "w", newline="", encoding="utf-8"
    ) as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        for row in images:
            filename = row["archivo"]
            review = visual[filename]
            writer.writerow(
                {
                    "archivo": filename,
                    "grupo_nombre": row["grupo_nombre"],
                    "objeto_visible": review["objeto_visible"],
                    "clases_confianzas": "; ".join(
                        f"{d['class_name']}:{float(d['confidence']):.3f}"
                        for d in detections[filename]
                    ),
                    "detecciones": row["detecciones"],
                    "estado_visual": review["estado_visual"],
                    "observacion": review["observacion"],
                }
            )


if __name__ == "__main__":
    main()
