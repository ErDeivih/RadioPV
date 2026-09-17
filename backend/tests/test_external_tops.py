"""TOP1 · tops externos con fuentes inyectadas (sin red): empareja y encola lo que falta."""
from app.database import SessionLocal
from app import models
from app.workers import rebuild_external_tops


def test_external_tops_con_fuente_falsa(client):
    db = SessionLocal()
    t = models.Track(title="Despecha", artist="Rosalia", genre="flamenco", rank=10,
                     status="descargada", source="test_ext", file_path="E:/x.mp3")
    db.add(t); db.flush(); tid = t.id
    db.commit()

    fuentes = [
        ("Top España", lambda: [{"artist": "Rosalía", "title": "DESPECHÁ"},
                                {"artist": "Falta", "title": "No Existe"}]),
    ]
    n = rebuild_external_tops(db, fuentes)
    assert n >= 1
    pl = db.query(models.Playlist).filter_by(type="system", name="Top España").first()
    assert pl and db.query(models.PlaylistTrack).filter_by(playlist_id=pl.id).count() >= 1
    # la que falta quedó en requests
    assert db.query(models.Request).filter_by(text="Falta - No Existe").first() is not None

    # limpieza
    db.query(models.Request).filter_by(text="Falta - No Existe").delete()
    db.query(models.PlaylistTrack).filter_by(playlist_id=pl.id).delete(); db.delete(pl)
    db.query(models.Track).filter(models.Track.source == "test_ext").delete()
    db.commit(); db.close()
