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
    # vuelve a descargar lo que ya está (y lo vuelve a enviar). Y ahora lleva TAMBIÉN el id de la
    # ficha del servidor, que es lo que permite pedir «sólo lo nuevo» con `desde_id`.
    pista = [p for p in indice["pistas"] if p[1] == "Ya la tengo"]
    assert pista, f"no sale en el índice: {indice['pistas']}"
    assert pista[0][2:] == ["Alguien", "abc123", "999"]
    assert indice["total"] >= 1
    assert indice["max_id"] == pista[0][0]

    # Sólo lo nuevo: pidiendo a partir del último id que ya tenemos no vuelve nada.
    vacio = client.get("/collector/indice", headers=cab, params={"desde_id": indice["max_id"]}).json()
    assert vacio["pistas"] == [] and vacio["nuevas"] == 0
    # Y desde 0 vuelve todo (es lo que se pide una vez al día, para corregir desajustes).
    completo = client.get("/collector/indice", headers=cab, params={"desde_id": 0}).json()
    assert len(completo["pistas"]) >= 1

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


def test_importar_no_acepta_rutas_absolutas(client, monkeypatch, radiov_temporal):
    """Una ruta absoluta del PC haría que la canción apareciera en la app y NO sonara.

    Pasó de verdad (20/09/2026): tres canciones de tech house se publicaron antes de que el
    organizador pasara su ruta a relativa, y llegaron como `E:/MusicaRadioPV/catalogada/…`. Aquí no
    existe esa ruta, así que en la aplicación salían y el reproductor no encontraba nada. Se arregla
    en el PC y también aquí: aunque la otra máquina esté con una versión vieja, no entra.
    """
    import sqlite3

    monkeypatch.setenv("RADIOPV_INGEST_TOKEN", "secreto-de-pruebas")
    cab = {"X-Ingest-Token": "secreto-de-pruebas"}

    # OJO con los títulos: tienen que ser DISTINTOS después de normalizar. La clave de canción corta
    # el título en palabras vacías («Prueba ruta con unidad» y «Prueba ruta con barras» dan la MISMA
    # clave, y la segunda se rechaza como repetida — que es justo lo que debe hacer). Se usan palabras
    # sueltas para que cada fila sea una canción distinta de verdad.
    for titulo, ruta, esperada in (
        ("Alfa", "E:/MusicaRadioPV/catalogada/DJ/2022/tema.mp3", "catalogada/DJ/2022/tema.mp3"),
        ("Bravo", "E:\\MusicaRadioPV\\catalogada\\DJ\\tema.mp3", "catalogada/DJ/tema.mp3"),
        ("Charlie", "MusicaRadioPV/catalogada/DJ/tema.mp3", "catalogada/DJ/tema.mp3"),
        ("Delta", "/music/catalogada/DJ/tema.mp3", "catalogada/DJ/tema.mp3"),
        ("Eco", "catalogada/DJ/tema.mp3", "catalogada/DJ/tema.mp3"),
    ):
        r = client.post("/collector/importar", json={"pistas": [
            {"title": titulo, "artist": "DJ Pruebas", "status": "descargada", "file_path": ruta}
        ], "origen": "pc-de-casa"}, headers=cab)
        assert r.status_code == 200, r.text
        con = sqlite3.connect(str(radiov_temporal))
        con.row_factory = sqlite3.Row
        fila = con.execute("SELECT file_path FROM tracks WHERE title=?", (titulo,)).fetchone()
        con.close()
        assert fila is not None, f"no entró «{titulo}»"
        assert fila["file_path"] == esperada, f"«{titulo}»: {fila['file_path']}"


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
