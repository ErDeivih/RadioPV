"""Comprueba que lo que manda el PC ha llegado bien: ficha en la base Y fichero en el disco.

Es la comprobación que importa de verdad en este reparto de trabajo: el PC puede decir «enviado»
y el servidor tener la ficha sin el fichero (o al revés), y entonces la canción aparecería en la
aplicación y no sonaría.
"""
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, "/app")
from radiov.config import BASE_MUSIC, resolve_music  # noqa: E402

DB = os.environ.get("RADIOPV_DATA_DIR", "/app/data") + "/radiov.db"
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

print(f"raiz de musica en el servidor: {BASE_MUSIC}")
print("\n=== ultimas pistas importadas (con youtube_id, por id descendente) ===")
filas = con.execute(
    "SELECT id, title, artist, status, file_path, source, duration, gain_db, cover_url, cover_path "
    "FROM tracks WHERE youtube_id IS NOT NULL ORDER BY id DESC LIMIT 8").fetchall()

sin_fichero = 0
for r in filas:
    ruta = resolve_music(r["file_path"]) if r["file_path"] else None
    existe = bool(ruta and Path(ruta).exists())
    if not existe:
        sin_fichero += 1
    print(f"  {r['id']:5d} [{r['status']:10s}] {'FICHERO OK ' if existe else 'SIN FICHERO'} "
          f"{r['artist']} - {(r['title'] or '')[:38]}")
    print(f"        file_path={r['file_path']}")
    print(f"        duration={r['duration']} gain_db={r['gain_db']} "
          f"cover_url={'si' if r['cover_url'] else 'no'} cover_path={r['cover_path']}")

print(f"\n  de las 8 ultimas, sin fichero: {sin_fichero}")

print("\n=== cuantas llevan caratula descargada ===")
n = con.execute("SELECT COUNT(*) FROM tracks WHERE cover_path IS NOT NULL AND cover_path != ''").fetchone()[0]
print(f"  {n} pistas con cover_path")

con.close()
