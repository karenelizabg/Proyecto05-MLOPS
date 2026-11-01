"""Prepara copias neutrales de las 29 fotos P5-04 fuera del repositorio."""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import shutil
import tempfile
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[1]
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _sha256(ruta: Path) -> str:
    digest = hashlib.sha256()
    # S8707: lectura local de originales o copias; ambos hashes se contrastan con el manifiesto.
    with ruta.open("rb") as archivo:  # NOSONAR
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


def preparar_fotos(
    originales: Path, manifiesto: Path, copias: Path, tabla: Path
) -> list[tuple[str, str]]:
    """Valida el manifiesto histórico y publica copias ordenadas por SHA-256."""
    originales, copias, tabla = Path(originales), Path(copias), Path(tabla)
    if copias.resolve().is_relative_to(RAIZ_REPO):
        raise ValueError("las fotografías copiadas deben quedar fuera del repositorio")
    if copias.exists() or copias.is_symlink() or tabla.exists() or tabla.is_symlink():
        raise FileExistsError("la carpeta de copias y la tabla deben ser destinos nuevos")
    if not originales.is_dir():
        raise ValueError("falta la carpeta de 29 JPEG originales")

    # S8707: manifiesto local del operador; se validan sus 29 filas, nombres y hashes.
    with Path(manifiesto).open(encoding="utf-8-sig", newline="") as archivo:  # NOSONAR
        filas = list(csv.DictReader(archivo))
    if len(filas) != 29 or any(not {"archivo", "sha256", "bytes"} <= fila.keys() for fila in filas):
        raise ValueError("el manifiesto P5-04 debe contener 29 filas con archivo, sha256 y bytes")
    nombres = [fila["archivo"] for fila in filas]
    if len(set(nombres)) != 29 or any(Path(nombre).name != nombre for nombre in nombres):
        raise ValueError("el manifiesto contiene nombres repetidos o rutas")
    archivos = [p for p in originales.iterdir() if p.suffix.lower() in {".jpg", ".jpeg"}]
    if len(archivos) != 29 or {p.name for p in archivos} != set(nombres):
        raise ValueError("la carpeta no coincide exactamente con los 29 JPEG del manifiesto")

    por_hash: list[tuple[str, Path]] = []
    for fila in filas:
        ruta = originales / fila["archivo"]
        esperado = fila["sha256"]
        if ruta.is_symlink() or not ruta.is_file():
            raise ValueError("cada original debe ser un JPEG regular")
        if SHA256.fullmatch(esperado) is None or _sha256(ruta) != esperado:
            raise ValueError("un JPEG original no coincide con su SHA-256 de P5-04")
        if ruta.stat().st_size != int(fila["bytes"]):
            raise ValueError("un JPEG original no coincide con su tamaño de P5-04")
        por_hash.append((esperado, ruta))
    por_hash.sort(key=lambda par: par[0])
    if len({sha for sha, _ in por_hash}) != 29:
        raise ValueError("hay SHA-256 duplicados: se requiere conservar cada cuadro por separado")

    correspondencias = [
        (f"ensayo-{indice:04d}.jpg", sha) for indice, (sha, _) in enumerate(por_hash, start=1)
    ]
    with tempfile.TemporaryDirectory(prefix="p5-05-neutrales-", dir=copias.parent) as temporal:
        preparadas = Path(temporal)
        for (nombre, sha), (_, origen) in zip(correspondencias, por_hash, strict=True):
            destino = preparadas / nombre
            shutil.copyfile(origen, destino)
            if _sha256(destino) != sha:
                raise ValueError("una copia neutral no conserva los bytes originales")
        # S8707: copias verificadas; destino nuevo fuera del repositorio en un padre confiable.
        preparadas.rename(copias)  # NOSONAR

    # S8707: tabla local nueva; el modo exclusivo impide reemplazar un archivo o enlace final.
    with tabla.open("x", encoding="utf-8", newline="\n") as archivo:  # NOSONAR
        archivo.write("neutral_name,sha256\n")
        for nombre, sha in correspondencias:
            archivo.write(f"{nombre},{sha}\n")
    return correspondencias


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--originales", required=True, type=Path)
    parser.add_argument("--manifiesto", required=True, type=Path)
    parser.add_argument("--copias", required=True, type=Path)
    parser.add_argument("--tabla", required=True, type=Path)
    args = parser.parse_args()
    correspondencias = preparar_fotos(args.originales, args.manifiesto, args.copias, args.tabla)
    print(f"{len(correspondencias)} copias neutrales verificadas en {args.copias}")
    print(f"tabla de correspondencias: {args.tabla}")


if __name__ == "__main__":
    main()
