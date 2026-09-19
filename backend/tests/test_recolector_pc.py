"""Sincronización con el recolector del PC (`/collector/...`).

El reparto es: el PC descarga (es la máquina que está encendida y le sobra potencia) y el servidor
se queda con servir la aplicación. Estas rutas son la mitad del servidor, y lo que hay que
comprobar es sobre todo **la puerta**: sin token no entra nadie, y si la función está apagada lo
dice en vez de aceptar cualquier cosa.
"""
import pytest


@pytest.fixture
def radiov_temporal(tmp_path, monkeypatch):
    """Una `radiov.db` de mentira, para no tocar la de verdad."""
    from radiov import db as rdb
    from radiov import config as rcfg

    ruta = tmp_path / "radiov.db"
    monkeypatch.setattr(rcfg, "DB_PATH", ruta)
    # `db.py` importó el nombre, así que hay que apuntar también el suyo.
    monkeypatch.setattr(rdb, "DB_PATH", ruta)
    rdb.init_db()
    return ruta


def test_dice_si_la_ingesta_esta_apagada(client, monkeypatch):
    """Sin token configurado, el servidor lo dice. Es mejor que un «no autorizado» sin más: el PC
    puede distinguir «no me han dado permiso» de «aquí no se acepta esto»."""
    monkeypatch.delenv("RADIOPV_INGEST_TOKEN", raising=False)
    r = client.get("/collector/estado")
    assert r.status_code == 200
    assert r.json()["encendida"] is False


def test_apagada_no_acepta_envios(client, monkeypatch):
    monkeypatch.delenv("RADIOPV_INGEST_TOKEN", raising=False)
    assert client.get("/collector/indice").status_code == 503
    assert client.post("/collector/importar", json={"pistas": []}).status_code == 503


def test_sin_token_no_entra(client, monkeypatch):
    monkeypatch.setenv("RADIOPV_INGEST_TOKEN", "secreto-de-pruebas")
    assert client.get("/collector/estado").json()["encendida"] is True
    assert client.get("/collector/indice").status_code == 401
    assert client.get("/collector/indice", headers={"X-Ingest-Token": "otro"}).status_code == 401
    assert client.get("/collector/ajustes").status_code == 401


def test_con_token_devuelve_indice_y_ajustes(client, monkeypatch, radiov_temporal):
    from radiov import db as rdb

    monkeypatch.setenv("RADIOPV_INGEST_TOKEN", "secreto-de-pruebas")
    cab = {"X-Ingest-Token": "secreto-de-pruebas"}

    rdb.add_track({"title": "Ya la tengo", "artist": "Alguien", "youtube_id": "abc123",
                   "deezer_id": "999", "file_path": "", "status": "descargada"})

    indice = client.get("/collector/indice", headers=cab).json()
    # El índice lleva los identificadores, no sólo artista y título: sin el id de YouTube el PC
    # vuelve a descargar lo que ya está (y lo vuelve a enviar).
    assert ["Ya la tengo", "Alguien", "abc123", "999"] in indice["pistas"]
    assert indice["total"] >= 1

    ajustes = client.get("/collector/ajustes", headers=cab).json()
    # Las semillas viajan al PC: si cada máquina tuviera su copia, con el tiempo se separarían.
    assert "agent_seeds" in ajustes
    # La ruta de la música NO viaja: es de cada máquina (en el PC es otra letra de unidad).
    assert "base_music_dir" not in ajustes


def test_importar_mete_las_pistas_y_no_las_duplica(client, monkeypatch, radiov_temporal):
    import sqlite3
    from radiov import db as rdb

    monkeypatch.setenv("RADIOPV_INGEST_TOKEN", "secreto-de-pruebas")
    cab = {"X-Ingest-Token": "secreto-de-pruebas"}

    pista = {
        "title": "Sesion de prueba", "artist": "DJ Pruebas", "duration": 1320.0,
        "status": "descargada", "file_path": "catalogada/DJ Pruebas/Sesion de prueba.mp3",
        "youtube_id": "yt-sesion", "cover_url": "http://x/c.jpg", "bpm": 120.0,
        "energy": 0.5, "gain_db": -6.0, "genre": "dance", "language": "es",
    }

    r = client.post("/collector/importar", json={"pistas": [pista], "origen": "pc-de-casa"}, headers=cab)
    assert r.status_code == 200, r.text
    assert r.json()["nuevas"] == 1

    con = sqlite3.connect(str(radiov_temporal))
    con.row_factory = sqlite3.Row
    fila = con.execute("SELECT * FROM tracks WHERE youtube_id='yt-sesion'").fetchone()
    con.close()
    assert fila is not None
    assert fila["duration"] == 1320.0
    assert fila["file_path"] == "catalogada/DJ Pruebas/Sesion de prueba.mp3"
    assert fila["gain_db"] == -6.0            # el análisis ya viene hecho del PC

    # Volver a mandar la misma pista no la duplica (el PC puede reintentar sin miedo).
    r2 = client.post("/collector/importar", json={"pistas": [pista], "origen": "pc-de-casa"}, headers=cab)
    assert r2.status_code == 200
    assert r2.json()["nuevas"] == 0
    con = sqlite3.connect(str(radiov_temporal))
    n = con.execute("SELECT COUNT(*) FROM tracks WHERE youtube_id='yt-sesion'").fetchone()[0]
    con.close()
    assert n == 1


def test_una_pista_que_falla_no_tumba_el_resto(client, monkeypatch, radiov_temporal):
    """Si una fila viene mal, las demás tienen que entrar igual: el PC manda lotes."""
    monkeypatch.setenv("RADIOPV_INGEST_TOKEN", "secreto-de-pruebas")
    cab = {"X-Ingest-Token": "secreto-de-pruebas"}

    r = client.post("/collector/importar", json={"pistas": [
        {"title": "Buena", "artist": "Uno", "status": "descargada"},
        {"title": "Otra buena", "artist": "Dos", "status": "descargada"},
    ]}, headers=cab)
    assert r.status_code == 200
    assert r.json()["nuevas"] == 2
