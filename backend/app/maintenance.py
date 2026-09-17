"""Tareas de mantenimiento del catálogo. Las llama la migración y el worker, NUNCA un endpoint."""
from sqlalchemy import text
from sqlalchemy.orm import Session


def recount_artist_tracks(db: Session) -> int:
    """Recalcula artists.track_count. Devuelve el nº de artistas actualizados."""
    res = db.execute(text(
        "UPDATE artists SET track_count = ("
        "  SELECT COUNT(*) FROM tracks t"
        "  WHERE lower(t.artist) = lower(artists.name) AND t.status = 'descargada')"
    ))
    db.commit()
    return res.rowcount or 0
