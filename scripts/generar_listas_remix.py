"""Genera las listas de mashups y sesiones de DJ a mano, sin esperar al worker.

El worker las recalcula cada 3 horas; esto es para verlas ya (y para comprobar que salen con
contenido después de cambiar la puerta de calidad).
"""
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/backend")

from app.database import SessionLocal  # noqa: E402
from app import models, workers  # noqa: E402

db = SessionLocal()
try:
    n = workers.rebuild_remixes(db)
    print(f"pistas colocadas: {n}")
    print()
    for nombre in ("Mashups y remixes", "Sesiones de DJ"):
        pl = db.query(models.Playlist).filter_by(name=nombre, type="system").first()
        if not pl:
            print(f"  {nombre}: NO EXISTE")
            continue
        filas = (db.query(models.Track.title, models.Track.artist, models.Track.duration)
                 .join(models.PlaylistTrack, models.PlaylistTrack.track_id == models.Track.id)
                 .filter(models.PlaylistTrack.playlist_id == pl.id)
                 .order_by(models.PlaylistTrack.position).all())
        print(f"  {nombre}: {len(filas)} canciones")
        for t, a, d in filas[:6]:
            print(f"     {int((d or 0) // 60):3d} min  {a} - {(t or '')[:52]}")
        print()
finally:
    db.close()
