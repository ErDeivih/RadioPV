"""republicar_completas(): pasa 'incompleta' → 'descargada' solo cuando la pista completa
todos los obligatorios de metadata_strict. Sin esto, las descargas nuevas se quedan
'incompleta' para siempre y la app (que solo sirve 'descargada') no las publica."""
import os
import tempfile
from pathlib import Path

import radiov.db as RDB
import radiov.catalog as C


def _temp_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(RDB, "DB_PATH", Path(path))
    RDB.init_db()
    return RDB.get_conn()


def _insert(con, tid, status, **kw):
    base = dict(title="T", artist="A", year=2020, genre="pop", language="en",
                youtube_id=f"v{tid}", bpm=100.0, energy=0.5, gain_db=-3.0, duration=200.0,
                cover_url="http://x/c.jpg")
    base.update(kw)
    con.execute(
        "INSERT INTO tracks (id, title, artist, status, year, genre, language, youtube_id, bpm, "
        "energy, gain_db, duration, cover_url) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (tid, base["title"], base["artist"], status, base["year"], base["genre"], base["language"],
         base["youtube_id"], base["bpm"], base["energy"], base["gain_db"], base["duration"],
         base["cover_url"]))


def test_republica_solo_las_completas(monkeypatch):
    """Se publica lo que tiene TODO lo que se puede medir o mirar; lo que falta, no.

    OJO con la carátula: faltar no bloquea sólo cuando no hay NINGUNA fuente de la que sacarla (ni
    vídeo ni ficha de tienda), que es el caso de las canciones recuperadas del disco. Por eso la
    fila 3 lleva `youtube_id` y la 6 no: la primera espera su carátula, la segunda se publica.
    """
    con = _temp_db(monkeypatch)
    _insert(con, 1, "incompleta")                       # completa → debe republicarse
    _insert(con, 2, "incompleta", gain_db=None)          # falta gain_db → no
    _insert(con, 3, "incompleta", cover_url=None)        # de un vídeo: su carátula se espera → no
    _insert(con, 4, "descargada")                        # ya descargada → no se toca
    _insert(con, 5, "incompleta", year=None)             # de un vídeo: el año no bloquea → sí
    _insert(con, 6, "incompleta", cover_url=None, youtube_id=None)   # sin fuente: sí
    con.commit()
    con.close()

    assert C.republicar_completas() == 3

    con = RDB.get_conn()
    assert con.execute("SELECT status FROM tracks WHERE id=1").fetchone()[0] == "descargada"
    assert con.execute("SELECT status FROM tracks WHERE id=2").fetchone()[0] == "incompleta"
    assert con.execute("SELECT status FROM tracks WHERE id=3").fetchone()[0] == "incompleta"
    assert con.execute("SELECT status FROM tracks WHERE id=4").fetchone()[0] == "descargada"
    assert con.execute("SELECT status FROM tracks WHERE id=5").fetchone()[0] == "descargada"
    assert con.execute("SELECT status FROM tracks WHERE id=6").fetchone()[0] == "descargada"
    con.close()


def test_modo_no_estricto_republica_todas(monkeypatch):
    con = _temp_db(monkeypatch)
    _insert(con, 1, "incompleta", gain_db=None)          # le falta gain_db
    con.commit()
    con.close()
    # apaga metadata_strict para forzar la república de todas las incompletas con fichero
    import radiov.config as CONFIG
    monkeypatch.setattr(C, "load_settings", lambda: {**CONFIG.load_settings(), "metadata_strict": False})

    assert C.republicar_completas() == 1
    con = RDB.get_conn()
    assert con.execute("SELECT status FROM tracks WHERE id=1").fetchone()[0] == "descargada"
    con.close()


def test_no_hay_incompletas_es_no_op(monkeypatch):
    con = _temp_db(monkeypatch)
    _insert(con, 1, "descargada")
    con.commit()
    con.close()
    assert C.republicar_completas() == 0
