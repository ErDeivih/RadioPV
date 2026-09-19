"""Mira en detalle los envios que no cuadran: filas repetidas, rutas y ficheros.

Se ejecuta en el servidor con el manifiesto del PC. Para cada pista enviada dice:
  · cuantas filas hay con ese id de YouTube (puede haber mas de una: el single y el album),
  · cual de ellas tiene fichero y cual no,
  · y si el fichero existe de verdad en el disco.
"""
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, "/app")
from radiov.config import resolve_music  # noqa: E402

MANIFIESTO = sys.argv[1] if len(sys.argv) > 1 else "/tmp/transferencias_pc.txt"
DB = os.environ.get("RADIOPV_DATA_DIR", "/app/data") + "/radiov.db"

ids = []
for linea in Path(MANIFIESTO).read_text(encoding="utf-8", errors="replace").splitlines():
    if linea.startswith("#") or "|" not in linea:
        continue
    partes = linea.split("|")
    if len(partes) >= 3 and partes[2].strip():
        ids.append(partes[2].strip())

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

print(f"pistas enviadas por el PC: {len(ids)}\n")
sin_fichero = repetidas = 0
for yt in ids:
    filas = con.execute(
        "SELECT id, title, artist, status, file_path, youtube_id FROM tracks WHERE youtube_id=?",
        (yt,)).fetchall()
    if len(filas) != 1:
        repetidas += 1
        print(f"!! {len(filas)} filas con youtube_id={yt}")
    for r in filas:
        ruta = Path(resolve_music(r["file_path"])) if r["file_path"] else None
        existe = bool(ruta and ruta.exists())
        if not existe:
            sin_fichero += 1
            print(f"   SIN FICHERO  id={r['id']} [{r['status']}] {r['artist']} - {(r['title'] or '')[:40]}")
            print(f"                file_path={r['file_path']}")
            if ruta and ruta.parent.exists():
                print(f"                la carpeta SÍ existe; hay: {[p.name for p in ruta.parent.iterdir()][:4]}")
            elif ruta:
                print(f"                la carpeta NO existe: {ruta.parent}")

print(f"\nfilas sin fichero: {sin_fichero}")
print(f"ids con mas de una fila: {repetidas}")
con.close()
