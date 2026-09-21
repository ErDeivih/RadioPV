"""La carátula que se PUEDE saber hay que ponerla: si no, la canción se queda sin publicar.

EL FALLO REAL (21/09/2026)
--------------------------
Un vídeo de YouTube siempre tiene miniatura y su dirección es determinista
(`i.ytimg.com/vi/<id>/hqdefault.jpg`). Pero las canciones bajadas antes de que el recolector
guardara la miniatura se quedaron sin `cover_url`, y como la puerta de metadatos exige carátula,
**nueve canciones del servidor** llevaban desde entonces sin poder publicarse: en el disco, con su
audio, y sin aparecer nunca en la aplicación. Se veía así:

    id=2282   [agente] falta=year,cover_url   [yt -- sin-caratula]  Sandra - Quién te crees

Estas pruebas fijan que `caratulas_desde_youtube` las rellena (y que no toca lo que ya tiene carátula).
"""
import pytest


@pytest.fixture
def base(tmp_path, monkeypatch):
    from radiov import db as rdb
    from radiov import config as rcfg

    ruta = tmp_path / "radiov.db"
    monkeypatch.setattr(rcfg, "DB_PATH", ruta)
    monkeypatch.setattr(rdb, "DB_PATH", ruta)
    rdb.init_db()
    return rdb


def test_pone_la_caratula_del_video_a_lo_que_no_tiene_ninguna(base):
    from radiov.catalog import caratulas_desde_youtube

    rdb = base
    sin_caratula = rdb.add_track({"title": "Sin carátula", "artist": "A", "youtube_id": "VID123",
                                  "status": "incompleta", "file_path": "catalogada/x.mp3"})
    con_caratula = rdb.add_track({"title": "Con carátula", "artist": "B", "youtube_id": "VID456",
                                  "status": "incompleta", "file_path": "catalogada/y.mp3",
                                  "cover_url": "https://ejemplo/c.jpg"})
    con_fichero = rdb.add_track({"title": "Con fichero", "artist": "C", "youtube_id": "VID789",
                                 "status": "incompleta", "file_path": "catalogada/z.mp3",
                                 "cover_path": "covers/999.jpg"})
    sin_video = rdb.add_track({"title": "Sin vídeo", "artist": "D", "status": "incompleta",
                               "file_path": "catalogada/w.mp3"})

    assert caratulas_desde_youtube(limit=50) == 1

    con = rdb.get_conn()
    try:
        filas = {r["id"]: r["cover_url"] for r in con.execute(
            "SELECT id, cover_url FROM tracks")}
    finally:
        con.close()
    assert filas[sin_caratula] == "https://i.ytimg.com/vi/VID123/hqdefault.jpg"
    assert filas[con_caratula] == "https://ejemplo/c.jpg", "no se pisa una carátula que ya estaba"
    assert filas[con_fichero] is None, "si ya tiene el fichero de carátula, no se toca"
    assert filas[sin_video] is None, "sin id de vídeo no se puede inventar la dirección"


def test_lo_que_se_rellena_desbloquea_la_publicacion(base):
    """El objetivo de todo esto: que la canción deje de esperar y llegue a la aplicación."""
    from radiov import models as M
    from radiov.catalog import campos_que_faltan, caratulas_desde_youtube, republicar_completas

    rdb = base
    tid = rdb.add_track({"title": "Esperando carátula", "artist": "A", "youtube_id": "VID999",
                         "status": "incompleta", "file_path": "catalogada/x.mp3", "genre": "pop",
                         "language": "es", "bpm": 120.0, "energy": 0.5, "gain_db": -6.0,
                         "duration": 200.0})
    # Antes: sin carátula, no se publica.
    assert campos_que_faltan(dict(rdb.get_conn().execute(
        "SELECT * FROM tracks WHERE id=?", (tid,)).fetchone())) == ["cover_url"]

    caratulas_desde_youtube(limit=10)
    republicar_completas(limit=10)

    con = rdb.get_conn()
    try:
        estado = con.execute("SELECT status FROM tracks WHERE id=?", (tid,)).fetchone()[0]
    finally:
        con.close()
    assert estado == M.STATUS_DOWNLOADED, "con la carátula del vídeo tenía que publicarse"
