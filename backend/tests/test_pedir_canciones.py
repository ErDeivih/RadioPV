"""La página de pedir canciones: buscar antes de pedir, y pedir LA versión elegida.

Antes era una caja de texto a ciegas: escribías «Artista - Título» y a esperar. Con eso pasaban tres
cosas malas:

  1. se pedía lo que YA estaba en la biblioteca (trabajo perdido para el recolector y una espera
     tonta para el usuario);
  2. de un mismo tema —original, remix, directo, veinte subidas— se bajaba «la que pareciera», que
     muchas veces no era la que se quería;
  3. si YouTube no contestaba, no había forma de saberlo.

Estas pruebas fijan que la búsqueda dice lo que hay en casa, que el vídeo elegido se guarda con la
petición (para que el recolector baje ESE), y que un fallo de YouTube no rompe la página.
"""
import pytest


@pytest.fixture
def usuario_con_catalogo(client):
    from app.database import SessionLocal
    from app import models

    db = SessionLocal()
    correo = "pedir@t.com"
    r = client.post("/auth/register", json={"email": correo, "password": "clave-larga-1"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]

    t = models.Track(title="Canción Que Ya Está", artist="Artista De Casa", status="descargada",
                     source="test_pedir", file_path="E:/y.mp3", rank=10, duration=200.0)
    db.add(t)
    db.commit()
    db.refresh(t)

    yield db, {"Authorization": f"Bearer {token}"}, t.id, correo

    db.query(models.Request).filter(models.Request.user_id.in_(
        [u.id for u in db.query(models.User).filter_by(email=correo)])).delete(
            synchronize_session=False)
    db.query(models.Track).filter(models.Track.source == "test_pedir").delete()
    db.query(models.User).filter(models.User.email == correo).delete(synchronize_session=False)
    db.commit()
    db.close()


def test_la_busqueda_ensena_lo_que_ya_esta_en_casa(client, usuario_con_catalogo, monkeypatch):
    """Sin resultados de YouTube, la página tiene que seguir diciendo que ya la tienes."""
    from radiov import youtube

    monkeypatch.setattr(youtube, "search_videos", lambda q, n=15: [])

    _, cab, tid, _ = usuario_con_catalogo
    r = client.get("/requests/buscar", params={"q": "Canción Que Ya"}, headers=cab)
    assert r.status_code == 200, r.text
    d = r.json()
    assert [t["id"] for t in d["en_biblioteca"]] == [tid]
    assert d["en_youtube"] == []


def test_la_busqueda_encuentra_escribiendo_sin_tildes(client, usuario_con_catalogo, monkeypatch):
    """La gente escribe «cancion», sin tilde. Buscar eso tiene que encontrar «Canción»."""
    from radiov import youtube

    monkeypatch.setattr(youtube, "search_videos", lambda q, n=15: [])

    _, cab, tid, _ = usuario_con_catalogo
    r = client.get("/requests/buscar", params={"q": "cancion que ya"}, headers=cab)
    assert r.status_code == 200, r.text
    assert [t["id"] for t in r.json()["en_biblioteca"]] == [tid]


def test_si_youtube_falla_la_pagina_sigue_sirviendo(client, usuario_con_catalogo, monkeypatch):
    """Un fallo de YouTube se cuenta (`aviso`), no se disfraza de «no existe esa canción»."""
    from radiov import youtube

    def revienta(*_a, **_k):
        raise RuntimeError("YouTube no contesta")

    monkeypatch.setattr(youtube, "search_videos", revienta)

    _, cab, _, _ = usuario_con_catalogo
    r = client.get("/requests/buscar", params={"q": "algo cualquiera"}, headers=cab)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["aviso"] and "YouTube" in d["aviso"]
    assert d["en_youtube"] == []


def test_la_busqueda_marca_lo_que_ya_esta_en_el_catalogo(client, usuario_con_catalogo, monkeypatch):
    """Un vídeo que ya está en el catálogo se marca: pedirlo otra vez no tiene sentido."""
    from radiov import youtube
    from app.database import SessionLocal
    from app import models

    db = SessionLocal()
    t = db.query(models.Track).filter_by(source="test_pedir").first()
    t.youtube_id = "VIDEOYAESTA"
    db.commit()
    db.close()

    monkeypatch.setattr(youtube, "search_videos", lambda q, n=15: [
        {"id": "VIDEOYAESTA", "title": "Una que ya está", "uploader": "Canal", "duration": 180},
        {"id": "VIDEONUEVO12", "title": "Una que no está", "uploader": "Canal", "duration": 240},
    ])

    _, cab, _, _ = usuario_con_catalogo
    r = client.get("/requests/buscar", params={"q": "cualquier cosa"}, headers=cab)
    assert r.status_code == 200, r.text
    por_id = {v["video_id"]: v for v in r.json()["en_youtube"]}
    assert por_id["VIDEOYAESTA"]["en_catalogo"] is True
    assert por_id["VIDEONUEVO12"]["en_catalogo"] is False


def test_la_peticion_guarda_el_video_elegido(client, usuario_con_catalogo):
    """Elegir versión tiene que servir para algo: el vídeo va guardado con la petición."""
    from app.database import SessionLocal
    from app import models

    _, cab, _, _ = usuario_con_catalogo
    r = client.post("/requests", json={"text": "Sesión de reggaetón viejo",
                                       "youtube_id": "ABCDEFGHIJK", "duration": 3600},
                    headers=cab)
    assert r.status_code == 200, r.text
    assert r.json()["youtube_id"] == "ABCDEFGHIJK"

    db = SessionLocal()
    try:
        fila = (db.query(models.Request)
                .filter_by(text="Sesión de reggaetón viejo", status="pendiente").first())
        assert fila is not None
        assert fila.youtube_id == "ABCDEFGHIJK"
        assert fila.duration == 3600
    finally:
        db.close()


def test_pedir_dos_veces_lo_mismo_no_duplica(client, usuario_con_catalogo):
    _, cab, _, _ = usuario_con_catalogo
    a = client.post("/requests", json={"text": "Otra canción pedida"}, headers=cab)
    b = client.post("/requests", json={"text": "Otra canción pedida"}, headers=cab)
    assert a.status_code == 200 and b.status_code == 200
    assert b.json().get("repetida") is True


def test_la_busqueda_necesita_dos_letras(client, usuario_con_catalogo):
    _, cab, _, _ = usuario_con_catalogo
    r = client.get("/requests/buscar", params={"q": "a"}, headers=cab)
    assert r.status_code == 422, r.text


def test_el_recolector_recibe_el_video_elegido(client, usuario_con_catalogo):
    """Lo que el PC necesita para bajar la versión correcta (va por el token de máquina)."""
    import os

    _, cab, _, _ = usuario_con_catalogo
    client.post("/requests", json={"text": "Un mashup concreto",
                                   "youtube_id": "MASHUPVIDEO", "duration": 200}, headers=cab)

    token = os.environ.get("RADIOPV_INGEST_TOKEN")
    if not token:
        pytest.skip("la ingesta está apagada en este entorno")
    r = client.get("/collector/peticiones", params={"limite": 50},
                   headers={"X-Ingest-Token": token})
    assert r.status_code == 200, r.text
    nuestra = [p for p in r.json()["peticiones"] if p["text"] == "Un mashup concreto"]
    assert nuestra and nuestra[0]["youtube_id"] == "MASHUPVIDEO"
