def test_health(client):
    d = client.get("/health").json()
    assert d["status"] == "ok"
    # /health ampliado (DP-08): contadores de catálogo
    for k in ("tracks", "artists", "similar", "users"):
        assert k in d


def test_login_limite_de_intentos(client):  # DP-06
    r = client.post("/auth/register", json={"email": "lim@t.com", "password": "clave-larga-1"})
    assert r.status_code == 200
    # fallar el login 6 veces → el 6º debe dar 429 (límite de intentos)
    statuses = []
    for _ in range(6):
        s = client.post("/auth/login", data={"username": "lim@t.com", "password": "mala-123"}).status_code
        statuses.append(s)
    assert statuses[-1] == 429, statuses


def test_login_y_me(client, token):
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["email"] == "t@t.com"


def test_tracks_lista(client):
    assert client.get("/tracks?limit=5").status_code == 200


def test_artists_no_revienta(client):     # regresión de C2
    assert client.get("/artists?limit=5").status_code == 200


def test_energy_invalida_es_422(client):  # regresión de I8
    assert client.get("/tracks?energy=alta").status_code == 422


def test_like_con_body_json(client, token):   # regresión de C5
    h = {"Authorization": f"Bearer {token}"}
    assert client.post("/library/1/like", json={"liked": True}, headers=h).status_code in (200, 404)


def test_stream_token_y_scope(client, token):  # T-12
    h = {"Authorization": f"Bearer {token}"}
    r = client.post("/auth/stream-token", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert "token" in body and "expires_in" in body
    # El token de streaming NO debe valer como sesión completa (get_current_user lo rechaza)
    st = body["token"]
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {st}"}).status_code == 401


def test_stream_range(client, token):  # T-13
    import os
    from app.database import SessionLocal
    from app import models
    music = os.environ["MUSIC_ROOT"]
    # Fichero bajo catalogada/ (ancla que _relativa reconoce)
    wav_dir = os.path.join(music, "catalogada", "Artista")
    os.makedirs(wav_dir, exist_ok=True)
    fp = os.path.join(wav_dir, "test_tema.mp3")
    with open(fp, "wb") as f:
        f.write(b"\xff\xfb\x90\x00" + b"\x00" * 8192)
    try:
        db = SessionLocal()
        tr = models.Track(title="Tema", artist="Artista", file_path=fp,
                          status="descargada", source="test")
        db.add(tr)
        db.commit()
        db.refresh(tr)
        tid = tr.id
        db.close()

        h = {"Authorization": f"Bearer {token}"}
        st = client.post("/auth/stream-token", headers=h).json()["token"]

        # seek: Range -> 206 + Content-Range
        r = client.get(f"/stream/{tid}?t={st}", headers={"Range": "bytes=0-1023"})
        assert r.status_code == 206, r.content
        assert r.headers.get("content-range", "").startswith("bytes 0-1023/")
        # sin rango -> 200
        assert client.get(f"/stream/{tid}?t={st}").status_code == 200
        # token malo -> 401
        assert client.get(f"/stream/{tid}?t=basura").status_code == 401
        # canción inexistente -> 404
        assert client.get("/stream/9999999?t=" + st).status_code == 404
    finally:
        if os.path.exists(fp):
            os.unlink(fp)


def test_media_covers_y_propiedad_cover(client):  # T-14
    import os
    from app.database import SessionLocal
    from app import models
    media = os.environ["MEDIA_ROOT"]
    cdir = os.path.join(media, "covers")
    os.makedirs(cdir, exist_ok=True)
    fp = os.path.join(cdir, "999.jpg")
    with open(fp, "wb") as f:
        f.write(b"\xff\xd8\xff" + b"\x00" * 64)  # bytes de JPEG mínimos
    try:
        # /media/covers/999.jpg se sirve por el StaticFiles montado
        r = client.get("/media/covers/999.jpg")
        assert r.status_code == 200, r.text
        assert r.content.startswith(b"\xff\xd8\xff")

        db = SessionLocal()
        tr = models.Track(title="T", artist="A", file_path="E:/x.mp3",
                          cover_path=os.path.join(cdir, "999.jpg"),
                          status="descargada", source="test")
        db.add(tr)
        db.commit()
        db.refresh(tr)
        tid = tr.id
        db.close()

        # TrackOut expone cover como URL de /media/covers
        data = client.get(f"/tracks/{tid}").json()
        assert data["cover"] == "/media/covers/999.jpg", data
    finally:
        if os.path.exists(fp):
            os.unlink(fp)


def test_tracks_filtros_y_total(client):  # T-15
    from app.database import SessionLocal
    from app import models
    db = SessionLocal()
    for nm, exp, rk in (("A", True, 50), ("B", False, 90)):
        tr = models.Track(title=f"Canción {nm}", artist="ArtistaX", genre="pop",
                          explicit=exp, rank=rk, feat="Invited", is_remix=False,
                          file_path="E:/x.mp3", status="descargada", source="test",
                          year=2020)
        db.add(tr)
    db.commit()
    db.close()

    # X-Total-Count + filtro explicit
    r = client.get("/tracks?explicit=true")
    assert r.status_code == 200
    assert "X-Total-Count" in r.headers
    body = r.json()
    assert all(t["explicit"] for t in body)

    # sort=rank → el de mayor rank (90) debe ir ANTES que el de 50 (entre los dos)
    rr = client.get("/tracks?sort=rank").json()
    idxB = next((i for i, t in enumerate(rr) if t["title"] == "Canción B"), None)
    idxA = next((i for i, t in enumerate(rr) if t["title"] == "Canción A"), None)
    assert idxB is not None and idxA is not None and idxB < idxA
    assert any("feat" in t for t in rr)  # campo feat expuesto

    # filtro por artista
    ar = client.get("/tracks?artist=ArtistaX").json()
    assert ar and all(t["artist"] == "ArtistaX" for t in ar)

    # sort inválido -> 422
    assert client.get("/tracks?sort=nope").status_code == 422


def test_tracks_busqueda(client):  # pantalla Search (FE-08): /tracks?q=
    from app.database import SessionLocal
    from app import models
    db = SessionLocal()
    db.add(models.Track(title="Baila Morena", artist="Victor", album="Verano",
                        status="descargada", source="test", file_path="E:/a.mp3", rank=1))
    db.add(models.Track(title="Noche", artist="Luna", album="Baila",
                        status="descargada", source="test", file_path="E:/b.mp3", rank=2))
    db.add(models.Track(title="Otro", artist="X", album="Y",
                        status="revisar", source="test", file_path="E:/c.mp3", rank=3))
    db.commit()
    db.close()

    # por título (parcial, case-insensitive)
    r = client.get("/tracks?q=mORENA")
    assert r.status_code == 200, r.content
    titles = [t["title"] for t in r.json()]
    assert "Baila Morena" in titles and "Noche" not in titles

    # por álbum
    assert any(t["title"] == "Noche" for t in client.get("/tracks?q=Baila").json())

    # solo descargadas: el de status 'revisar' no sale (TrackOut no expone status → por título)
    assert "Otro" not in [t["title"] for t in client.get("/tracks?q=").json()]

    # sin resultados -> 200 con lista vacía
    assert client.get("/tracks?q=zzz_no_existe").json() == []


def test_endpoints_t16(client, token):  # T-16
    from app.database import SessionLocal
    from app import models
    h = {"Authorization": f"Bearer {token}"}
    db = SessionLocal()
    t1 = models.Track(title="T1", artist="Art1", status="descargada", rank=10, source="test", file_path="E:/x.mp3")
    t2 = models.Track(title="T2", artist="Art1", status="descargada", rank=5, source="test", file_path="E:/y.mp3")
    t3 = models.Track(title="T3", artist="Art2", status="descargada", rank=3, source="test", file_path="E:/z.mp3")
    db.add_all([t1, t2, t3])
    db.add_all([models.Artist(name="Art1"), models.Artist(name="Art2")])
    db.commit()
    for t in (t1, t2, t3):
        db.refresh(t)
    db.close()

    # /library/liked (una petición, no N+1)
    client.post(f"/library/{t1.id}/like", json={"liked": True}, headers=h)
    liked = client.get("/library/liked", headers=h).json()
    assert any(x["id"] == t1.id for x in liked)

    # /artists/{name} y /top
    assert client.get("/artists/Art1").json()["name"] == "Art1"
    assert client.get("/artists/NoExiste").status_code == 404
    top = client.get("/artists/Art1/top").json()
    assert top and top[0]["rank"] == 10

    # ciclo de vida de playlist
    pid = client.post("/playlists", json={"name": "Mi"}, headers=h).json()["id"]
    for tid in (t1.id, t2.id, t3.id):
        client.post(f"/playlists/{pid}/tracks/{tid}", headers=h)
    client.put(f"/playlists/{pid}/order", json=[t3.id, t1.id, t2.id], headers=h)
    order = [x["id"] for x in client.get(f"/playlists/{pid}/tracks", headers=h).json()]
    assert order == [t3.id, t1.id, t2.id]
    client.patch(f"/playlists/{pid}", json={"name": "Mi2"}, headers=h)
    assert client.get("/playlists", headers=h).json()[0]["name"] == "Mi2"
    client.delete(f"/playlists/{pid}/tracks/{t2.id}", headers=h)
    client.delete(f"/playlists/{pid}", headers=h)
    assert client.get("/playlists", headers=h).json() == []

    # report
    # Este endpoint pone la pista en 'revisar' y todos los listados sólo sirven las 'descargada',
    # así que sin sesión cualquiera podía sacar canciones del catálogo. Antes este test lo llamaba
    # SIN cabeceras y esperaba un 200: estaba confirmando el agujero en vez de detectarlo.
    assert client.post(f"/tracks/{t1.id}/report").status_code == 401
    rp = client.post(f"/tracks/{t1.id}/report", headers=h)
    assert rp.status_code == 200 and rp.json()["status"] == "revisar"


def test_facets(client):  # T-23
    r = client.get("/facets")
    assert r.status_code == 200
    d = r.json()
    for k in ("genres", "eras", "languages", "years", "moods"):
        assert k in d and isinstance(d[k], list)
    # las entradas tienen value/count
    assert all("value" in e and "count" in e for e in d["genres"])


def test_w06_endpoints(client, token):  # W-06
    from app.database import SessionLocal
    from app import models
    h = {"Authorization": f"Bearer {token}"}
    db = SessionLocal()
    t = models.Track(title="W06", artist="WArtist", genre="pop", rank=999999, duration=200,
                     status="descargada", source="test", file_path="E:/x.mp3")
    db.add(t)
    db.commit()
    tid = db.query(models.Track.id).filter(models.Track.title == "W06").scalar()
    # playlist del sistema
    p = models.Playlist(user_id=None, name="Trending", type="system")
    db.add(p)
    db.commit()
    pid = db.query(models.Playlist.id).filter(models.Playlist.name == "Trending").scalar()
    db.add(models.PlaylistTrack(playlist_id=pid, track_id=tid, position=1))
    db.commit()
    db.close()

    # historial
    client.post(f"/library/{tid}/play", json={"source": "player", "completed": 1}, headers=h)
    hist = client.get("/library/history", headers=h).json()
    assert any(x["id"] == tid for x in hist)

    # trending
    tr = client.get("/recommend/trending?n=3", headers=h).json()
    assert any(x["id"] == tid for x in tr)

    # system
    sysp = [x["name"] for x in client.get("/playlists/system", headers=h).json()]
    assert "Trending" in sysp


def test_w09_follows_y_top(client, token):  # W-09
    from app.database import SessionLocal
    from app import models
    h = {"Authorization": f"Bearer {token}"}
    db = SessionLocal()
    t = models.Track(title="TopTrack", artist="TopArtist", genre="pop", duration=200,
                     status="descargada", source="test", file_path="E:/x.mp3")
    db.add(t)
    db.commit()
    tid = db.query(models.Track.id).filter(models.Track.title == "TopTrack").scalar()
    db.close()

    # follows
    assert client.post("/follows/TopArtist", headers=h).status_code == 200
    assert "TopArtist" in client.get("/follows", headers=h).json()
    assert client.delete("/follows/TopArtist", headers=h).status_code == 200
    assert "TopArtist" not in client.get("/follows", headers=h).json()

    # /library/top (sale de plays): registrar varios plays
    for _ in range(3):
        client.post(f"/library/{tid}/play", json={"source": "player", "completed": 1}, headers=h)
    top_tracks = client.get("/library/top?type=tracks", headers=h).json()
    assert top_tracks["items"] and any(x["id"] == tid for x in top_tracks["items"])
    top_art = client.get("/library/top?type=artists", headers=h).json()
    assert top_art["items"] and any(x["name"] == "TopArtist" for x in top_art["items"])


def test_artists_albums(client, token):  # página Artist (FE-08)
    from app.database import SessionLocal
    from app import models
    h = {"Authorization": f"Bearer {token}"}
    db = SessionLocal()
    db.add(models.ArtistAlbum(artist_name="ArtAl", artist_id="x", title="Disco1",
                              year=2020, cover_url="/media/covers/1"))
    db.add(models.ArtistAlbum(artist_name="ArtAl", artist_id="x", title="Disco2",
                              year=2015, cover_url="/media/covers/2"))
    db.commit()
    db.close()

    r = client.get("/artists/ArtAl/albums", headers=h)
    assert r.status_code == 200, r.content
    albums = r.json()
    assert [a["title"] for a in albums] == ["Disco1", "Disco2"]  # orden por year desc


def test_register_invite_code(client, monkeypatch):  # DP-06
    """Si INVITE_CODE está seteado, el registro lo exige; vacío = abierto (solo dev)."""
    from app import config
    monkeypatch.setattr(config, "INVITE_CODE", "secreto-ok")

    # sin código → 403
    assert client.post("/auth/register", json={"email": "inv1@t.com",
                                               "password": "clave-larga-1"}).status_code == 403
    # código erróneo → 403
    assert client.post("/auth/register", json={"email": "inv2@t.com", "password": "clave-larga-1",
                                               "invite_code": "mal"}).status_code == 403
    # correcto → 200 y token de acceso
    r = client.post("/auth/register", json={"email": "inv3@t.com", "password": "clave-larga-1",
                                            "invite_code": "secreto-ok"})
    assert r.status_code == 200, r.text
    assert "access_token" in r.json()


def test_patch_me_edita_perfil(client, token):  # D3
    h = {"Authorization": f"Bearer {token}"}
    r = client.patch("/auth/me", json={"display_name": "Nuevo Nombre"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["display_name"] == "Nuevo Nombre"
    # persiste en /auth/me
    assert client.get("/auth/me", headers=h).json()["display_name"] == "Nuevo Nombre"
    # nombre vacío no debe romper
    assert client.patch("/auth/me", json={"display_name": "  "}, headers=h).status_code == 200


def test_explicit_filter_en_listas(client, token):  # D2 (filtro en servidor, no en cliente)
    from app.database import SessionLocal
    from app import models
    h = {"Authorization": f"Bearer {token}"}
    db = SessionLocal()
    # tres canciones: dos limpias, una explícita; misma artista para /top
    for title, exp in (("Lim1", False), ("Lim2", False), ("Expl", True)):
        db.add(models.Track(title=title, artist="ExpArt", genre="reggaeton", explicit=exp,
                            status="descargada", source="test", file_path="E:/x.mp3",
                            rank=100, year=2020))
    db.commit()

    # me gusta de la explícita para probar /library/liked
    eid = db.query(models.Track.id).filter(models.Track.title == "Expl").scalar()
    lim1 = db.query(models.Track.id).filter(models.Track.title == "Lim1").scalar()
    client.post(f"/library/{eid}/like", json={"liked": True}, headers=h)
    client.post(f"/library/{lim1}/like", json={"liked": True}, headers=h)
    # playlist con la explícita + una limpia
    pid = client.post("/playlists", json={"name": "ExpTest"}, headers=h).json()["id"]
    for tid in (eid, lim1):
        client.post(f"/playlists/{pid}/tracks/{tid}", headers=h)
    db.close()

    # las listas con explicit=false no deben incluir "Expl"
    assert not any(t["title"] == "Expl" for t in client.get("/library/liked?explicit=false", headers=h).json())
    assert not any(t["title"] == "Expl" for t in client.get(f"/playlists/{pid}/tracks?explicit=false", headers=h).json())
    assert not any(t["title"] == "Expl" for t in client.get("/artists/ExpArt/top?explicit=false", headers=h).json())
    assert not any(t["title"] == "Expl" for t in client.get("/recommend/trending?explicit=false&n=50", headers=h).json())
    assert all(t["explicit"] is False for t in client.get("/tracks?explicit=false", headers=h).json())
    # /recommend con explicit=false: nunca devuelve una explícita
    recs = client.get("/recommend?explicit=false&n=20", headers=h).json()
    assert all(t["explicit"] is False for t in recs)


def test_recommend_daily(client, token):  # Home "Mix diario" (FE-08)
    from app.database import SessionLocal
    from app import models
    h = {"Authorization": f"Bearer {token}"}
    db = SessionLocal()
    for i, rank in enumerate((900000, 800000, 700000, 600000)):
        db.add(models.Track(title=f"D{i}", artist="DArt", rank=rank, duration=200,
                            status="descargada", source="test", file_path="E:/x.mp3"))
    db.commit()
    db.close()

    r = client.get("/recommend/daily?n=6", headers=h)
    assert r.status_code == 200, r.content
    items = r.json()
    assert len(items) <= 6 and items
    # todos vienen del conjunto descargada (el endpoint lo filtra); campos mínimos que pinta la fila
    assert all("id" in t and "title" in t and "artist" in t and "cover" in t for t in items)


def test_playlist_no_toca_otro_usuario(client):  # B3 · privacidad
    """Un usuario no puede leer ni modificar la playlist de otro → 404 (no 403), deja la ruta
    existente intacta (el `tracks_of` filtra por user_id)."""
    import os
    from app import models
    # user A crea una playlist
    client.post("/auth/register", json={"email": "plA@t.com", "password": "clave-larga-1"})
    ta = client.post("/auth/login", data={"username": "plA@t.com",
                                          "password": "clave-larga-1"}).json()["access_token"]
    pid = client.post("/playlists", json={"name": "DeA"}, headers={"Authorization": f"Bearer {ta}"}).json()["id"]

    # user B (otro) intenta leerla y modificarla
    client.post("/auth/register", json={"email": "plB@t.com", "password": "clave-larga-1"})
    tb = client.post("/auth/login", data={"username": "plB@t.com",
                                          "password": "clave-larga-1"}).json()["access_token"]
    hb = {"Authorization": f"Bearer {tb}"}
    assert client.get(f"/playlists/{pid}/tracks", headers=hb).status_code == 404
    assert client.patch(f"/playlists/{pid}", json={"name": "Robo"}, headers=hb).status_code == 404
    assert client.delete(f"/playlists/{pid}", headers=hb).status_code == 404
    # la ruta del propietario sigue OK
    assert client.get(f"/playlists/{pid}/tracks", headers={"Authorization": f"Bearer {ta}"}).status_code == 200
