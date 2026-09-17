"""T1+T2 · emparejado tolerante de tendencias + encolar lo que falta a `requests`."""
from app.database import SessionLocal
from app import models
from app.workers import _normalizar, _emparejar_hits, _enqueue_missing


def test_normalizar():
    assert _normalizar("Rosalía - DESPECHÁ (feat. X)") == "rosalia despecha"
    assert _normalizar("Artist - Song [Remaster]") == "artist song"
    assert _normalizar("Bad Bunny - Ojitos (with Y)" ) == "bad bunny ojitos"


def test_emparejar_tolerante_y_encolar(client):
    db = SessionLocal()
    t = models.Track(title="Despecha", artist="Rosalia", genre="flamenco", rank=10,
                     status="descargada", source="test_mix_t", file_path="E:/x.mp3")
    db.add(t); db.flush(); tid = t.id
    db.commit()

    hits = [
        {"artist": "Rosalía", "title": "DESPECHÁ (feat. X)"},   # -> empareja con el track
        {"artist": "Artista X", "title": "Canción Inexistente"},  # -> falta -> requests
    ]
    emparejados, faltantes = _emparejar_hits(db, hits)
    assert emparejados and emparejados[0][0].id == tid, "no emparejó la canción tolerante"
    assert len(faltantes) == 1, "debe quedar un faltante"

    n = _enqueue_missing(db, faltantes)
    assert n == 1
    assert db.query(models.Request).filter_by(text="Artista X - Canción Inexistente").first() is not None

    # limpieza para no contaminar el suite (BD compartida)
    db.query(models.Request).filter_by(text="Artista X - Canción Inexistente").delete()
    db.query(models.Track).filter(models.Track.source == "test_mix_t").delete()
    db.commit()
    db.close()
