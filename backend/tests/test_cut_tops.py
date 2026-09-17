"""TOP3 · tops por género (>30 canciones) y por década, con diversidad de artista."""
from app.database import SessionLocal
from app import models
from app.workers import rebuild_cut_tops


def test_cut_tops_por_genero(client):
    db = SessionLocal()
    for i in range(31):
        db.add(models.Track(title=f"P{i}", artist=f"Art{i % 5}", genre="pop", year=2000 + i,
                            rank=1000 - i, status="descargada", source="test_cut", file_path="E:/x.mp3"))
    db.commit()
    rebuild_cut_tops(db)
    pl = db.query(models.Playlist).filter_by(type="system", name="Top pop").first()
    assert pl and db.query(models.PlaylistTrack).filter_by(playlist_id=pl.id).count() >= 1
    # diversidad: como son 5 artistas, el top tiene <= 2 por artista -> no puede haber >2 del mismo
    from collections import Counter
    ids = [r.track_id for r in db.query(models.PlaylistTrack).filter_by(playlist_id=pl.id)]
    por_art = Counter(a for (a,) in db.query(models.Track.artist).filter(models.Track.id.in_(ids)))
    assert max(por_art.values()) <= 2, por_art
    # limpieza
    db.query(models.PlaylistTrack).filter_by(playlist_id=pl.id).delete(); db.delete(pl)
    db.query(models.Track).filter(models.Track.source == "test_cut").delete()
    db.commit(); db.close()
