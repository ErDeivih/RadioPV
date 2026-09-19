"""Borrar del panel tiene que borrar de LAS DOS bases: la del recolector y la de la aplicación.

FALLO REAL (19/09/2026)
-----------------------
RadioPV guarda la música en dos bases SQLite:

  · `radiov.db`  — la biblioteca del recolector; es la que gestiona el panel de administración.
  · `backend.db` — la que sirve la aplicación (listas, portada, reproductor): la que VE el usuario.

El botón de borrar tocaba la primera y el fichero del disco, y **no la segunda**. Comprobado con una
ficha de prueba creada en las dos bases:

    radiov.db:  0 fichas
    backend.db: 1 ficha      ← la canción seguía en la aplicación, y sin fichero (rota)

Es decir: el panel decía «Borradas 1», el disco se liberaba y la canción seguía en la biblioteca del
usuario, ahora sin poder sonar. Una herramienta de limpieza que deja fantasmas en lo que el usuario
ve es peor que no tenerla, y es justo lo que pidió arreglar («hay demasiadas canciones y tengo que
hacer limpieza lo más fácil posible»).

Estas pruebas montan las dos bases y comprueban que el borrado deja las dos limpias.
"""
import pytest


@pytest.fixture
def dos_bases(tmp_path, monkeypatch):
    """Una canción en la base del recolector y la MISMA en la de la aplicación."""
    from radiov import db as rdb
    from radiov import config as rcfg
    from app.database import SessionLocal
    from app import models

    ruta = tmp_path / "radiov.db"
    monkeypatch.setattr(rcfg, "DB_PATH", ruta)
    monkeypatch.setattr(rdb, "DB_PATH", ruta)
    rdb.init_db()

    fichero = tmp_path / "prueba.mp3"
    fichero.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 2048)
    monkeypatch.setattr("radiov.blacklist.resolve_music", lambda _fp: fichero)

    tid_rec = rdb.add_track({"title": "Canción De Dos Bases", "artist": "PruebaDos",
                             "status": "descargada", "source": "prueba",
                             "file_path": str(fichero), "youtube_id": "VIDEO123456"})

    db = SessionLocal()
    t = models.Track(title="Canción De Dos Bases", artist="PruebaDos", status="descargada",
                     source="test_dos_bases", file_path=str(fichero), rank=1,
                     youtube_id="VIDEO123456")
    db.add(t)
    db.commit()
    db.refresh(t)
    tid_app = t.id

    yield db, rdb, tid_rec, tid_app, fichero

    db.query(models.Track).filter(models.Track.source == "test_dos_bases").delete(
        synchronize_session=False)
    db.commit()
    db.close()


def test_borrar_del_panel_limpia_las_dos_bases(dos_bases):
    """El caso que fallaba: borrar por el panel dejaba la canción en la aplicación."""
    db, rdb, tid_rec, tid_app, fichero = dos_bases
    from app.routers.admin import _borrar_de_la_app, _identidad_en_recolector
    from app import models
    from radiov import blacklist

    # Lo que hace ahora el endpoint: apuntar quién es ANTES de borrar del recolector.
    identidades = _identidad_en_recolector([tid_rec])
    assert identidades and identidades[0]["youtube_id"] == "VIDEO123456"

    assert blacklist.delete_tracks([tid_rec], veto=False) == 1

    con = rdb.get_conn()
    try:
        assert con.execute("SELECT COUNT(*) FROM tracks WHERE id=?", (tid_rec,)).fetchone()[0] == 0
    finally:
        con.close()
    assert not fichero.exists(), "el fichero tiene que desaparecer del disco"

    # La otra mitad: la base de la aplicación.
    borradas = _borrar_de_la_app(db, identidades)
    assert borradas == 1, "la canción seguía en la base de la aplicación (queda rota y visible)"
    assert db.query(models.Track).filter_by(id=tid_app).count() == 0


def test_sin_identificadores_se_reconoce_por_artista_y_titulo(dos_bases):
    """Una ficha sin id de YouTube ni de Deezer también tiene que poder quitarse de la aplicación."""
    db, rdb, tid_rec, tid_app, _f = dos_bases
    from app.routers.admin import _borrar_de_la_app
    from app import models

    identidades = [{"id": tid_rec, "youtube_id": None, "deezer_id": None,
                    "artist": "PruebaDos", "title": "Canción De Dos Bases"}]
    assert _borrar_de_la_app(db, identidades) == 1
    assert db.query(models.Track).filter_by(id=tid_app).count() == 0


def test_vetar_un_artista_tambien_lo_quita_de_la_aplicacion(dos_bases):
    """Vetar un artista borra sus canciones: tienen que irse de las dos bases, no de una."""
    db, _rdb, _tr, tid_app, _f = dos_bases
    from app.routers.admin import _borrar_de_la_app_por_artista
    from app import models

    assert _borrar_de_la_app_por_artista(db, "PruebaDos") == 1
    assert db.query(models.Track).filter_by(id=tid_app).count() == 0


def test_la_respuesta_dice_cuantas_se_quitaron_de_la_aplicacion(dos_bases):
    """El panel tiene que poder enseñar que se limpiaron las dos bases, no sólo una."""
    import inspect

    import app.routers.admin as A

    fuente = inspect.getsource(A.admin_delete_tracks)
    assert "borradas_de_la_app" in fuente, "la respuesta no informa de la base de la aplicación"
    assert "_borrar_de_la_app(" in fuente
