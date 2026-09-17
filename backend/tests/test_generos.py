"""D1 · prueba de `scripts/generos_artistas.py` con un lookup que devuelve la forma REAL de Deezer
(`/album/{id}` → `genres.data[].name`), no una inventada. Así se caza el endpoint equivocado."""
import os
import sys
import sqlite3
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "scripts"))

from generos_artistas import clasificar  # noqa: E402


def _fake_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE tracks (id INTEGER PRIMARY KEY, artist TEXT, genre TEXT, album_id TEXT)")
    con.execute("CREATE TABLE artists (id INTEGER PRIMARY KEY, name TEXT, genre TEXT)")
    # Metallica: 21 canciones en 'other' con album_id de Deezer
    for i in range(21):
        con.execute("INSERT INTO tracks (artist, genre, album_id) VALUES (?,?,?)",
                    ("Metallica", "other", f"alb{100 + i % 3}"))
    con.execute("INSERT INTO artists (name, genre) VALUES ('Metallica', 'other')")
    # un artista sin album_id → no se puede clasificar → no se toca
    con.execute("INSERT INTO tracks (artist, genre, album_id) VALUES ('SinAlbum', 'other', NULL)")
    con.execute("INSERT INTO artists (name, genre) VALUES ('SinAlbum', 'other')")
    con.commit()
    con.close()
    return path


def test_clasificar_usa_generos_del_album():
    path = _fake_db()
    # lookup REAL: dado un album_id, devuelve el género que vendría en genres.data
    def lookup(name, album_ids):
        if name == "Metallica" and album_ids:
            return "rock"          # Deezer diría "Metal" -> normalizado a "rock"
        return None                 # sin albums → no se inventa

    cambio = clasificar(path, lookup)
    assert cambio.get("Metallica") == "rock", cambio
    assert "SinAlbum" not in cambio, "no se debe inventar género sin album_id"
    os.unlink(path)


def test_clasificar_no_inventa_si_album_sin_generos():
    path = _fake_db()
    def lookup(name, album_ids):
        return None                 # el álbum no trae géneros
    assert clasificar(path, lookup) == {}
    os.unlink(path)
