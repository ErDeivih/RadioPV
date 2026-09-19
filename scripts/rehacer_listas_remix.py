"""Rehace AHORA las listas de mashups/remixes y sesiones de DJ, y dice cómo quedan.

Para qué: el worker las rehace cada 3 horas, así que después de subir música nueva (o de cambiar la
regla) puede tardar en verse. Esto las rehace al momento y enseña el resultado.

Uso (dentro del contenedor del API o del worker):
    docker exec radiopv-api python /app/scripts/rehacer_listas_remix.py
"""
import os
import sqlite3
import sys

sys.path.insert(0, "/app" if os.path.isdir("/app") else ".")

from app.database import SessionLocal  # noqa: E402
from app.workers import rebuild_remixes  # noqa: E402

DB = os.environ.get("RADIOPV_DATA_DIR", "/app/data") + "/backend.db"

db = SessionLocal()
try:
    total = rebuild_remixes(db)
    print(f"canciones colocadas en las listas: {total}")
finally:
    db.close()

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
print("\n=== cómo han quedado ===")
for p in con.execute(
        "SELECT id, name FROM playlists WHERE type='system' AND (name LIKE '%Mashup%'"
        " OR name LIKE '%Sesion%') ORDER BY name").fetchall():
    filas = con.execute(
        "SELECT t.title, t.artist, t.duration FROM playlist_tracks pt"
        " LEFT JOIN tracks t ON t.id=pt.track_id WHERE pt.playlist_id=?"
        " ORDER BY pt.position", (p["id"],)).fetchall()
    largas = sum(1 for f in filas if (f["duration"] or 0) > 900)
    print(f"\n   «{p['name']}»: {len(filas)} canciones · de más de 15 min: {largas}")
    for f in filas[:8]:
        mins = int((f["duration"] or 0) // 60)
        print(f"      {mins:>3} min  {f['artist']} - {f['title']}"[:105])
    if len(filas) > 8:
        print(f"      … y {len(filas) - 8} más")
con.close()
