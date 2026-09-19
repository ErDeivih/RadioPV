"""Busca pistas publicadas cuyo fichero NO esta en el disco.

Es el fallo que hay que vigilar con el recolector en el PC: la ficha llega, el fichero no, y la
cancion aparece en la aplicacion pero no suena (el reproductor la salta con un aviso).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, "/app")
from radiov.config import resolve_music  # noqa: E402

import sqlite3  # noqa: E402

DB = os.environ.get("RADIOPV_DATA_DIR", "/app/data") + "/radiov.db"
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

filas = con.execute(
    "SELECT id, title, artist, file_path, duration, status, source FROM tracks "
    "WHERE status='descargada' AND file_path IS NOT NULL AND file_path != ''").fetchall()

sin_fichero = []
for r in filas:
    if not Path(resolve_music(r["file_path"])).exists():
        sin_fichero.append(r)

print(f"publicadas: {len(filas)}")
print(f"SIN FICHERO: {len(sin_fichero)}")
for r in sin_fichero[:20]:
    print(f"   {r['id']:>5} {int((r['duration'] or 0) // 60):>4} min  {r['artist']} - {(r['title'] or '')[:40]}")
    print(f"         {r['file_path']}")

# Se compara con las que SI estan, para ver si el patron es el mismo.
print("\nultimas 5 publicadas CON fichero (para comparar rutas):")
for r in filas[-5:]:
    print(f"   {r['id']:>5} {r['file_path']}")

con.close()
