def test_recommend_prioriza_flamenco(client):
    """W-01/W-02/W-04: con 2 likes de flamenco (de artistas distintos), las 5 primeras son flamenco."""
    from app.database import SessionLocal
    from app import models

    db = SessionLocal()
    for i in range(8):
        db.add(models.Track(title=f"Flam {i}", artist=f"ArtF{i}", genre="flamenco", year=2020,
                            bpm=100, energy=0.5, status="descargada", source="test", rank=600000))
    for i in range(5):
        db.add(models.Track(title=f"Pop {i}", artist=f"ArtP{i}", genre="pop", year=2020,
                            bpm=110, energy=0.6, status="descargada", source="test", rank=600000))
    db.commit()
    flam_ids = [r[0] for r in db.query(models.Track.id).filter(models.Track.genre == "flamenco").all()]
    db.close()
    liked = flam_ids[:2]

    r = client.post("/auth/register", json={"email": "rec@t.com", "password": "clave-larga-1",
                                            "display_name": "Rec"})
    token = r.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    for tid in liked:
        assert client.post(f"/library/{tid}/like", json={"liked": True}, headers=h).status_code == 200

    data = client.get("/recommend?n=5", headers=h).json()
    assert len(data) >= 2
    assert all(d["genre"] == "flamenco" for d in data[:5]), data[:5]


def test_recommend_sin_señales_prioriza_rank(client):
    """W-03: un usuario sin ninguna señal recibe canciones populares (rank alto), no arbitrarias."""
    from app.database import SessionLocal
    from app import models

    db = SessionLocal()
    for i in range(6):
        # 3 con rank bajo, 3 con rank alto (artistas distintos)
        for rk, pref in ((100, "low"), (900000, "high")):
            db.add(models.Track(title=f"{pref}{i}", artist=f"B{i}{pref}", genre="pop", year=2020,
                                bpm=110, energy=0.6, status="descargada", source="test", rank=rk))
    db.commit()
    db.close()

    r = client.post("/auth/register", json={"email": "cold@t.com", "password": "clave-larga-1"})
    token = r.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    data = client.get("/recommend?n=6", headers=h).json()
    # el primer grupo debe ser de los de rank alto (populares)
    assert data and data[0]["rank"] >= 800000, [d["rank"] for d in data]


def test_recommend_diversidad_max2_artista(client):
    """W-04: en las recomendaciones no hay más de 2 canciones del mismo artista."""
    from app.database import SessionLocal
    from app import models

    db = SessionLocal()
    # 6 canciones del mismo artista (rank alto) + otros artistas
    for i in range(6):
        db.add(models.Track(title=f"Same {i}", artist="SameArtist", genre="pop", year=2020,
                            bpm=110, energy=0.6, status="descargada", source="test", rank=900000))
    for i in range(6):
        db.add(models.Track(title=f"Oth {i}", artist=f"OtherArtist{i}", genre="pop", year=2020,
                            bpm=110, energy=0.6, status="descargada", source="test", rank=900000))
    db.commit()
    db.close()

    r = client.post("/auth/register", json={"email": "div@t.com", "password": "clave-larga-1"})
    token = r.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    data = client.get("/recommend?n=20", headers=h).json()
    from collections import Counter
    artists = Counter(d["artist"] for d in data)
    assert max(artists.values()) <= 2, dict(artists)


def test_radio_lee_similar(client):
    """W-05: /radio lee de la tabla `similar` (rebuild_similar), no calcula por petición."""
    from app.database import SessionLocal
    from app import models
    from app.personalization import rebuild_similar

    db = SessionLocal()
    a = models.Track(title="Base", artist="A", genre="pop", year=2020, bpm=120, energy=0.5,
                     status="descargada", source="test")
    b = models.Track(title="Near", artist="B", genre="pop", year=2020, bpm=122, energy=0.52,
                     status="descargada", source="test")
    c = models.Track(title="Far", artist="C", genre="metal", year=1990, bpm=60, energy=0.2,
                     status="descargada", source="test")
    db.add_all([a, b, c])
    db.commit()
    n = rebuild_similar(db, top=5)
    # ids frescos (evitar objetos detached tras commit)
    a_id = db.query(models.Track.id).filter(models.Track.title == "Base").scalar()
    b_id = db.query(models.Track.id).filter(models.Track.title == "Near").scalar()
    db.close()
    assert n > 0

    r = client.post("/auth/register", json={"email": "radio@t.com", "password": "clave-larga-1"})
    token = r.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    data = client.get(f"/recommend/radio?seed_track={a_id}&n=3", headers=h).json()
    # el vecino más parecido (pop, B) va antes que el metal (C)
    assert data and data[0]["id"] == b_id, [d["id"] for d in data]


def test_radio_fallback_calcula_al_vuelo(client):
    """W-08: si `similar` no tiene filas para ese seed, /radio calcula al vuelo (no devuelve [])."""
    from app.database import SessionLocal
    from app import models
    db = SessionLocal()
    db.add(models.Track(title="FB", artist="FA", genre="pop", year=2020, bpm=120, energy=0.5,
                        status="descargada", source="test"))
    db.add(models.Track(title="FBN", artist="FB", genre="pop", year=2020, bpm=122, energy=0.52,
                        status="descargada", source="test"))
    db.commit()
    # seed recién creado: rebuild_similar (corrido en otros tests) no lo incluye → fallback
    a_id = db.query(models.Track.id).filter(models.Track.title == "FB").scalar()
    db.close()

    r = client.post("/auth/register", json={"email": "fb@t.com", "password": "clave-larga-1"})
    token = r.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    data = client.get(f"/recommend/radio?seed_track={a_id}&n=3", headers=h).json()
    assert data, "el fallback debe calcular vecinos, no devolver lista vacía"
