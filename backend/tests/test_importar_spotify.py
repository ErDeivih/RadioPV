"""Importar una lista de Spotify: el id del enlace, el emparejado y el endpoint.

Lo pidió el usuario: *«me gustaría una opción en donde pasara un playlist de spotify y se me creara
igual en mi aplicación»*.

Estas pruebas NO salen a Internet: la lectura de Spotify (`_leer_spotify`) se sustituye por un doble
con una lista conocida, y el emparejado se prueba contra un catálogo de prueba. Lo que se comprueba
es lo que puede romperse sin que nadie se entere: que el enlace se entienda, que las tildes y los
paréntesis no impidan encontrar una canción, que las que faltan se digan, y que se puedan pedir.
"""
from app import models
from app.database import SessionLocal
from app.routers import importar

SRC = "test_importar"


def test_el_id_sale_de_cualquier_forma_del_enlace():
    """La gente pega el enlace de la app, el de incrustar, el URI o el id a secas."""
    esperado = "37i9dQZEVXbNFJfN1Vw8d9"
    formas = [
        f"https://open.spotify.com/playlist/{esperado}",
        f"https://open.spotify.com/playlist/{esperado}?si=abc123&pt=xyz",
        f"https://open.spotify.com/embed/playlist/{esperado}",
        f"spotify:playlist:{esperado}",
        esperado,
    ]
    for forma in formas:
        assert importar.id_de_lista(forma) == esperado, forma


def test_un_enlace_que_no_es_de_una_lista_se_rechaza():
    from fastapi import HTTPException

    for malo in ("", "   ", "https://open.spotify.com/album/abc", "hola", "open.spotify.com"):
        try:
            importar.id_de_lista(malo)
        except HTTPException as e:
            assert e.status_code == 400, malo
        else:
            raise AssertionError(f"«{malo}» debería rechazarse")


def test_emparejar_aguanta_tildes_parentesis_y_el_artista_delante():
    catalogo = [
        (1, "De Lejitos (Remix)", "Jay Wheeler"),
        (2, "LA GRACIOSA", "Quevedo"),
        (3, "Canción con Tilde", "Rosalía"),
        (4, "Otra cosa", "Alguien"),
    ]
    canciones = [
        {"title": "De Lejitos - Remix", "artist": "Jay Wheeler, Omar Courtz"},   # paréntesis y guion
        {"title": "la graciosa", "artist": "Quevedo"},                          # mayúsculas
        {"title": "Cancion con Tilde", "artist": "Rosalia"},                    # tildes
        {"title": "Quevedo - LA GRACIOSA", "artist": "Quevedo"},                # artista delante
        {"title": "Una que no está", "artist": "Nadie"},                        # falta
    ]
    ids, faltan = importar.emparejar(canciones, catalogo)
    assert 1 in ids and 2 in ids and 3 in ids
    assert [f["title"] for f in faltan] == ["Una que no está"]
    # Sin repetidas dentro de la lista: «LA GRACIOSA» aparece dos veces y sólo entra una vez.
    assert ids.count(2) == 1


def test_endpoint_crea_la_lista_y_dice_lo_que_falta(client, monkeypatch):
    """El endpoint entero, con Spotify sustituido por un doble: lista creada, informe y peticiones."""
    db = SessionLocal()
    try:
        r = client.post("/auth/register", json={"email": "spotify@t.com", "password": "clave-larga-1"})
        assert r.status_code == 200, r.text
        tok = r.json()["access_token"]
        for i, (titulo, artista) in enumerate([("De Lejitos (Remix)", "Jay Wheeler"),
                                               ("LA GRACIOSA", "Quevedo")]):
            db.add(models.Track(title=titulo, artist=artista, status="descargada", source=SRC,
                                file_path=f"E:/s{i}.mp3", rank=100 - i, duration=200))
        db.commit()

        monkeypatch.setattr(importar, "_leer_spotify",
                            lambda _id: ("Top 50: España", [
                                {"title": "De Lejitos - Remix", "artist": "Jay Wheeler"},
                                {"title": "LA GRACIOSA", "artist": "Quevedo"},
                                {"title": "Inalcanzable", "artist": "Rosalía"},
                            ]))

        h = {"Authorization": f"Bearer {tok}"}
        r = client.post("/importar/spotify",
                        json={"url": "https://open.spotify.com/playlist/37i9dQZEVXbNFJfN1Vw8d9",
                              "pedir": True}, headers=h)
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["nombre"] == "Top 50: España"
        assert out["total"] == 3
        assert out["encontradas"] == 2, out
        assert [f["title"] for f in out["faltan"]] == ["Inalcanzable"]
        assert out["pedidas"] == 1, "la que falta debe pedirse al recolector"
        assert out["playlist"]["n_tracks"] == 2

        # Las canciones quedan EN ORDEN en la lista.
        ids = (db.query(models.PlaylistTrack.track_id)
               .filter_by(playlist_id=out["playlist"]["id"])
               .order_by(models.PlaylistTrack.position).all())
        titulos = [db.query(models.Track).get(tid).title for (tid,) in ids]
        assert titulos[0].startswith("De Lejitos"), titulos

        # Y la petición de la que falta existe, con «Artista - Título».
        u = db.query(models.User).filter_by(email="spotify@t.com").first()
        pedidas = db.query(models.Request).filter_by(user_id=u.id).all()
        assert [p.text for p in pedidas] == ["Rosalía - Inalcanzable"], [p.text for p in pedidas]

        # Importar DOS VECES la misma lista no crea una copia: rellena la misma.
        r2 = client.post("/importar/spotify",
                         json={"url": "https://open.spotify.com/playlist/37i9dQZEVXbNFjfN1Vw8d9"},
                         headers=h)
        assert r2.status_code == 200
        assert r2.json()["playlist"]["id"] == out["playlist"]["id"]
        assert db.query(models.Playlist).filter_by(user_id=u.id).count() == 1

        # limpieza
        db.query(models.PlaylistTrack).filter_by(playlist_id=out["playlist"]["id"]).delete()
        db.query(models.Playlist).filter_by(id=out["playlist"]["id"]).delete()
        db.query(models.Request).filter_by(user_id=u.id).delete()
        db.query(models.User).filter_by(id=u.id).delete()
        db.query(models.Track).filter(models.Track.source == SRC).delete()
        db.commit()
    finally:
        db.close()


def test_endpoint_dice_que_no_puede_leer_una_lista_privada(client, monkeypatch):
    """Sin canciones (lista privada) hay que decirlo, no crear una lista vacía en silencio."""
    db = SessionLocal()
    try:
        r = client.post("/auth/register", json={"email": "spotify2@t.com", "password": "clave-larga-1"})
        tok = r.json()["access_token"]
        monkeypatch.setattr(importar, "_leer_spotify", lambda _id: ("Una privada", []))
        h = {"Authorization": f"Bearer {tok}"}
        r = client.post("/importar/spotify",
                        json={"url": "https://open.spotify.com/playlist/37i9dQZEVXbNFJfN1Vw8d9"},
                        headers=h)
        assert r.status_code == 409, r.text
        u = db.query(models.User).filter_by(email="spotify2@t.com").first()
        assert db.query(models.Playlist).filter_by(user_id=u.id).count() == 0
        db.query(models.User).filter_by(id=u.id).delete()
        db.commit()
    finally:
        db.close()
