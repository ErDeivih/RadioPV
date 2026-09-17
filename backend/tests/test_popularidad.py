"""Popularidad: refrescar (visitas YouTube + histórico + score), tendencias y estadísticas."""
import os
import tempfile
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models
from app import popularidad as POP


def _db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    eng = create_engine("sqlite:///" + path.replace("\\", "/"))
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)(), eng


def _track(db, title="T", artist="A", ytid="yid", rank=500000, views=None):
    t = models.Track(title=title, artist=artist, status="descargada", youtube_id=ytid,
                     rank=rank, yt_views=views, genre="pop", era="10s", duration=200.0)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def test_score_mas_visitas_mas_popular():
    lo = POP._score(10000, 500000)
    hi = POP._score(50000000, 500000)
    assert lo < hi
    assert 0.0 <= lo <= hi <= 1.0


def test_refrescar_rellena_datos_e_historial(monkeypatch):
    db, _ = _db()
    a = _track(db, "A", "AA", "y1", rank=400000)
    b = _track(db, "B", "BB", "y2", rank=800000)

    fake = {"y1": (10000, 200), "y2": (50000, 400)}
    monkeypatch.setattr(POP, "yt_metrics", lambda yid: fake.get(yid, (0, 0)))

    n = POP.refrescar(db, limit=10)
    assert n == 2

    a2 = db.get(models.Track, a.id)
    b2 = db.get(models.Track, b.id)
    assert (a2.yt_views or 0) == 10000
    assert (b2.yt_views or 0) == 50000
    assert b2.popularidad > a2.popularidad             # más visitas → más score
    # histórico: youtube views + deezer rank por pista
    filas = db.query(models.PopularitySample).filter_by(track_id=a.id).all()
    assert any(s.metric == "views" and s.source == "youtube" for s in filas)
    assert any(s.metric == "rank" and s.source == "deezer" for s in filas)
    db.close()


def test_tendencias_detecta_subidas(monkeypatch):
    db, _ = _db()
    a = _track(db, "Sube", "S", "y1", rank=500000)
    b = _track(db, "Plana", "P", "y2", rank=500000)

    ahora = datetime.utcnow()
    # a: sube (1000 → 5000)    b: plena (5000 → 5000)
    for track, vieja, reciente in ((a, 1000, 5000), (b, 5000, 5000)):
        db.add(models.PopularitySample(track_id=track.id, source="youtube", metric="views",
                                       valor=vieja, sampled_at=ahora - timedelta(days=10)))
        db.add(models.PopularitySample(track_id=track.id, source="youtube", metric="views",
                                       valor=reciente, sampled_at=ahora - timedelta(days=1)))
    db.commit()

    # necesitamos yt_views para el fallback/salida
    a.yt_views, b.yt_views = 5000, 5000
    db.commit()

    t = POP.tendencias(db, dias=7)
    ids_suben = {x["track_id"] for x in t["subiendo"]}
    assert a.id in ids_suben
    assert b.id not in ids_suben                       # plena no se considera subida
    db.close()


def test_estadisticas_devuelve_agregados(monkeypatch):
    db, _ = _db()
    a = _track(db, "AA", "A", "y1", rank=500000, views=25000)
    b = _track(db, "BB", "B", "y2", rank=750000, views=80000)
    db.commit()

    fake = {"y1": (25000, 100), "y2": (80000, 200)}
    monkeypatch.setattr(POP, "yt_metrics", lambda yid: fake.get(yid, (0, 0)))
    POP.refrescar(db, limit=10)

    e = POP.estadisticas(db)
    assert {"top_views", "top_score", "por_genero", "total_popular"} <= set(e)
    assert e["top_views"][0]["id"] == b.id             # más visto primero
    assert e["total_popular"] >= 2
    db.close()


def test_recopilaciones_por_pico_de_epoca(monkeypatch):
    db, _ = _db()
    a = _track(db, "Vintage", "V1", "y1", rank=500000, views=10000)
    a.era = "00s"
    b = _track(db, "Moderna", "M1", "y2", rank=900000, views=900000)
    b.era = "20s"
    db.commit()

    fake = {"y1": (10000, 50), "y2": (900000, 999)}
    monkeypatch.setattr(POP, "yt_metrics", lambda yid: fake.get(yid, (0, 0)))
    POP.refrescar(db, limit=10)

    r = POP.recopilaciones(db, n=5)
    assert "por_era" in r and "por_genero" in r
    # la pista de mayor pico domina su época
    assert r["por_era"]["20s"][0]["id"] == b.id
    assert r["por_era"]["00s"][0]["id"] == a.id
    assert r["por_genero"]["pop"][0]["id"] == b.id      # 900k > 10k
    db.close()


def test_rebuild_recopilaciones_crea_playlists(monkeypatch):
    db, _ = _db()
    a = _track(db, "Vintage", "V1", "y1", rank=500000, views=10000)
    a.era, a.genre = "00s", "pop"
    b = _track(db, "Moderna", "M1", "y2", rank=900000, views=900000)
    b.era, b.genre = "20s", "pop"
    db.commit()

    fake = {"y1": (10000, 50), "y2": (900000, 999)}
    monkeypatch.setattr(POP, "yt_metrics", lambda yid: fake.get(yid, (0, 0)))
    POP.refrescar(db, limit=10)

    from app.workers import rebuild_recopilaciones
    n = rebuild_recopilaciones(db, n=5)
    assert n >= 2

    for nombre in ("Éxitos de los 00s", "Éxitos de los 20s", "Lo mejor del pop"):
        pl = db.query(models.Playlist).filter_by(type="system", name=nombre).first()
        assert pl is not None, f"no existe la playlist {nombre}"
        assert db.query(models.PlaylistTrack).filter_by(playlist_id=pl.id).count() >= 1
    db.close()
