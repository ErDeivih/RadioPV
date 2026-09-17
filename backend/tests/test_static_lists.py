"""T4 · rebuild_static_lists genera contenido real (playlist_tracks) en las listas del sistema."""
from app.database import SessionLocal
from app import models
from app.workers import rebuild_static_lists, SYSTEM_LISTS


def test_listas_sistema_con_contenido(client):
    db = SessionLocal()
    # temas que caigan en varias listas (era 00s/90s/20s, energy alta, language es)
    for i, (gen, era, en, lang) in enumerate([("pop", "00s", 0.7, "es"),
                                              ("rock", "90s", 0.6, "es"),
                                              ("latin", "20s", 0.2, "es")]):
        db.add(models.Track(title=f"S{i}", artist=f"A{i}", genre=gen, era=era,
                            energy=en, language=lang, year=2000 + i, rank=1000 - i,
                            status="descargada", source="test_static", file_path="E:/x.mp3"))
    db.commit()

    rebuild_static_lists(db)

    con_contenido = 0
    for nombre, _ in SYSTEM_LISTS:
        pl = db.query(models.Playlist).filter_by(type="system", name=nombre).first()
        if pl and db.query(models.PlaylistTrack).filter_by(playlist_id=pl.id).count() > 0:
            con_contenido += 1
    assert con_contenido >= 3, f"solo {con_contenido} listas con contenido de {len(SYSTEM_LISTS)}"
    # "Los 2000" debe tener la pista de era 2000s
    pl2000 = db.query(models.Playlist).filter_by(type="system", name="Los 2000").first()
    assert db.query(models.PlaylistTrack).filter_by(playlist_id=pl2000.id).count() >= 1

    # limpieza
    db.query(models.Track).filter(models.Track.source == "test_static").delete()
    db.query(models.SmartPlaylist).filter(models.SmartPlaylist.user_id.is_(None)).delete()
    for nombre, _ in SYSTEM_LISTS:
        pl = db.query(models.Playlist).filter_by(type="system", name=nombre).first()
        if pl:
            db.query(models.PlaylistTrack).filter_by(playlist_id=pl.id).delete()
            db.delete(pl)
    db.commit()
    db.close()
