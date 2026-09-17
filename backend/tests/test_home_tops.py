"""TOP2 · los tops de la casa se nutren de los plays reales."""
from datetime import datetime, timedelta

from app.database import SessionLocal
from app import models
from app.workers import rebuild_home_tops


def test_home_tops_con_plays(client):
    db = SessionLocal()
    # tracks: uno escuchado mucho (reciente), otro viejo sin reproducir (rescatable)
    t_mucho = models.Track(title="Mucho", artist="A", genre="pop", status="descargada",
                           source="test_top", file_path="E:/x.mp3")
    t_old = models.Track(title="Viejo", artist="B", genre="rock", status="descargada",
                         source="test_top", file_path="E:/x.mp3")
    db.add_all([t_mucho, t_old]); db.flush()
    u = models.User(email="top@t.com", hashed_password="x")
    db.add(u); db.commit(); db.refresh(u); db.refresh(t_mucho); db.refresh(t_old)
    # 3 plays recientes de t_mucho
    now = datetime.utcnow()
    for _ in range(3):
        db.add(models.Play(user_id=u.id, track_id=t_mucho.id, played_at=now))
    db.commit()

    rebuild_home_tops(db)

    casa = db.query(models.Playlist).filter_by(type="system", name="Lo más escuchado de la casa").first()
    assert casa and db.query(models.PlaylistTrack).filter_by(playlist_id=casa.id).count() >= 1
    top_u = db.query(models.Playlist).filter_by(type="system", name=f"Top {u.id}").first()
    assert top_u and db.query(models.PlaylistTrack).filter_by(playlist_id=top_u.id).count() >= 1
    rescat = db.query(models.Playlist).filter_by(type="system", name="Rescatadas").first()
    assert rescat and db.query(models.PlaylistTrack).filter_by(playlist_id=rescat.id).count() >= 1

    # limpieza (BD compartida)
    db.query(models.Play).filter_by(user_id=u.id).delete()
    db.query(models.Track).filter(models.Track.source == "test_top").delete()
    for nombre in ("Lo más escuchado de la casa", "Rescatadas", f"Top {u.id}"):
        pl = db.query(models.Playlist).filter_by(type="system", name=nombre).first()
        if pl:
            db.query(models.PlaylistTrack).filter_by(playlist_id=pl.id).delete()
            db.delete(pl)
    db.query(models.User).filter(models.User.email == "top@t.com").delete()
    db.commit(); db.close()
