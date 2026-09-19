"""El borrado del catálogo tiene que decir la verdad sobre los ficheros.

Contexto (19/09/2026): el contenedor de la API montaba la música en **solo lectura**, así que
`unlink()` fallaba con EROFS, el error se tragaba con un `except OSError: pass` y el panel decía
«Borradas 412 canciones» mientras los 30 GB de audio seguían en el disco. Una herramienta de
limpieza que no libera espacio y asegura que sí es peor que no tenerla.

Estas pruebas sujetan que un fallo al borrar el fichero:
  · NO impide borrar la ficha (el catálogo no se queda con música que el usuario ha quitado), y
  · SÍ se cuenta y se cuenta, para que la interfaz pueda avisar.
"""
import pytest


@pytest.fixture
def radiov_temporal(tmp_path, monkeypatch):
    from radiov import db as rdb
    from radiov import config as rcfg

    ruta = tmp_path / "radiov.db"
    monkeypatch.setattr(rcfg, "DB_PATH", ruta)
    monkeypatch.setattr(rdb, "DB_PATH", ruta)
    rdb.init_db()
    return ruta


def _pista(rdb, titulo: str, file_path: str) -> int:
    return rdb.add_track({"title": titulo, "artist": "Pruebas", "status": "descargada",
                          "source": "prueba", "file_path": file_path})


def test_borra_la_ficha_y_cuenta_los_ficheros_que_no_pudo_borrar(radiov_temporal, monkeypatch):
    from radiov import blacklist, db as rdb

    tid = _pista(rdb, "Con fichero imposible", "catalogada/Pruebas/x.mp3")

    class FicheroQueNoSeDejaBorrar:
        def exists(self):
            return True

        def unlink(self):
            raise OSError(30, "Read-only file system")

    monkeypatch.setattr(blacklist, "resolve_music", lambda _fp: FicheroQueNoSeDejaBorrar())

    fallos: list = []
    borradas = blacklist.delete_tracks([tid], veto=False, fallos=fallos)

    assert borradas == 1, "la ficha se borra igual: el catálogo no debe quedarse con esa canción"
    assert len(fallos) == 1, "y el fallo al borrar el fichero tiene que quedar apuntado"
    assert "Read-only" in fallos[0]
    # Ficha fuera de la base
    con = rdb.get_conn()
    try:
        assert con.execute("SELECT COUNT(*) FROM tracks WHERE id=?", (tid,)).fetchone()[0] == 0
    finally:
        con.close()


def test_si_el_fichero_ya_no_esta_no_es_un_fallo(radiov_temporal, monkeypatch):
    """Que el fichero no exista es lo normal (ya se borró antes): eso no es un problema."""
    from radiov import blacklist, db as rdb

    tid = _pista(rdb, "Sin fichero", "catalogada/Pruebas/y.mp3")

    class NoExiste:
        def exists(self):
            return False

        def unlink(self):                       # no debería llamarse
            raise AssertionError("no se debe intentar borrar lo que no existe")

    monkeypatch.setattr(blacklist, "resolve_music", lambda _fp: NoExiste())
    fallos: list = []
    assert blacklist.delete_tracks([tid], veto=False, fallos=fallos) == 1
    assert fallos == []


def test_vetar_al_borrar_sigue_funcionando(radiov_temporal, monkeypatch):
    from radiov import blacklist, db as rdb

    tid = _pista(rdb, "Para vetar", "catalogada/Pruebas/z.mp3")
    monkeypatch.setattr(blacklist, "resolve_music", lambda _fp: type("F", (), {
        "exists": lambda self: True, "unlink": lambda self: None})())

    assert blacklist.delete_tracks([tid], veto=True) == 1
    con = rdb.get_conn()
    try:
        fila = con.execute("SELECT value FROM blacklist WHERE kind='song'").fetchone()
    finally:
        con.close()
    assert fila is not None and "Para vetar" in fila["value"]
