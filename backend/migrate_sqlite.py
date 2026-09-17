"""Migra el catálogo de la antigua SQLite (data/radiov.db) a la nueva base del backend.

Idempotente: evita duplicados (por deezer_id o artista+título).
Uso:
    python -m backend.migrate_sqlite          # con DATABASE_URL por defecto (SQLite)
    DATABASE_URL=postgresql://user:pass@host/radio python -m backend.migrate_sqlite
"""
import os
import sys
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import Base, engine, SessionLocal, ensure_schema  # noqa: E402
from app import models  # noqa: E402

SRC = os.environ.get("OLD_SQLITE", os.path.join(os.path.dirname(__file__), "..", "data", "radiov.db"))


def _track_exists(db, deezer_id, artist, title):
    q = db.query(models.Track)
    if deezer_id:
        q = q.filter(models.Track.deezer_id == deezer_id)
    else:
        q = q.filter(models.Track.artist == artist, models.Track.title == title)
    return q.first() is not None


def migrate() -> None:
    """Sincroniza el catálogo de radiov.db → BD del backend. NO destructivo, idempotente.

    - Empareja por deezer_id; si no hay, por (artista, título) en minúsculas.
    - Inserta lo nuevo, actualiza lo existente y marca 'retirada' lo que ya no está en origen.
    - NUNCA toca users / reactions / plays / playlists / playlist_tracks.
    - tracks.id NUNCA cambia.
    """
    from app.maintenance import recount_artist_tracks

    Base.metadata.create_all(bind=engine)
    ensure_schema()          # añade columnas nuevas (mixes.explicacion) a BD antiguas
    db = SessionLocal()
    con = sqlite3.connect(SRC)
    con.row_factory = sqlite3.Row

    # --- índices de lo que ya hay en destino ---
    por_deezer: dict[str, models.Track] = {}
    por_clave: dict[tuple[str, str], models.Track] = {}
    for t in db.query(models.Track).all():
        if t.deezer_id:
            por_deezer[str(t.deezer_id)] = t
        por_clave[((t.artist or "").lower(), (t.title or "").lower())] = t

    CAMPOS = ("title artist album release_date year genre language bpm energy gain_db valence tags era feat "
              "file_path cover_url cover_path artist_image_url artist_image_path album_id artist_id "
              "youtube_id duration rank source status").split()

    nuevos = actualizados = 0
    vistos: set[int] = set()

    for row in con.execute("SELECT * FROM tracks"):
        d = dict(row)
        did = str(d["deezer_id"]) if d.get("deezer_id") else None
        clave = ((d.get("artist") or "").lower(), (d.get("title") or "").lower())
        destino = por_deezer.get(did) if did else None
        if destino is None:
            destino = por_clave.get(clave)

        if destino is None:                                   # ---- alta ----
            destino = models.Track(deezer_id=did)
            db.add(destino)
            nuevos += 1
        else:
            actualizados += 1

        for c in CAMPOS:
            if c in d:
                setattr(destino, c, d[c])
        destino.is_remix = bool(d.get("is_remix"))
        destino.explicit = bool(d.get("explicit"))
        destino.status = d.get("status") or "descargada"
        if did:
            destino.deezer_id = did

        db.flush()                                            # asigna id sin cerrar la transacción
        vistos.add(destino.id)
        if did:
            por_deezer[did] = destino
        por_clave[clave] = destino

    db.commit()

    # --- lo que ya no está en origen se RETIRA, no se borra (conserva likes e historial) ---
    retiradas = 0
    for t in db.query(models.Track).filter(models.Track.status == "descargada").all():
        if t.id not in vistos:
            t.status = "retirada"
            retiradas += 1
    db.commit()

    # --- artistas (upsert por nombre) ---
    for row in con.execute("SELECT * FROM artists"):
        d = dict(row)
        a = db.query(models.Artist).filter_by(name=d["name"]).first()
        if a is None:
            a = models.Artist(name=d["name"])
            db.add(a)
        a.deezer_id = str(d["deezer_id"]) if d.get("deezer_id") else None
        a.image_url, a.image_path = d.get("image_url"), d.get("image_path")
        a.nb_fan, a.nb_album = d.get("nb_fan"), d.get("nb_album")
        a.genre, a.language = d.get("genre"), d.get("language")
    db.commit()

    # --- discografía (upsert por artista+album_id, si no por artista+título+año) ---
    existentes = {(x.artist_name, x.album_id or "", x.title or "", x.year or 0)
                  for x in db.query(models.ArtistAlbum).all()}
    for row in con.execute("SELECT * FROM artist_albums"):
        d = dict(row)
        k = (d["artist_name"], str(d["album_id"]) if d.get("album_id") else "",
             d.get("title") or "", d.get("year") or 0)
        if k in existentes:
            continue
        existentes.add(k)
        db.add(models.ArtistAlbum(artist_name=d["artist_name"], artist_id=d.get("artist_id"),
                                  album_id=str(d["album_id"]) if d.get("album_id") else None,
                                  title=d.get("title"), year=d.get("year"),
                                  cover_url=d.get("cover_url")))
    db.commit()

    recount_artist_tracks(db)
    con.close()
    print(f"[OK] nuevas={nuevos} actualizadas={actualizados} retiradas={retiradas} "
          f"| total={db.query(models.Track).count()}")
    db.close()


if __name__ == "__main__":
    migrate()
