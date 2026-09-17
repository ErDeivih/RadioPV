def test_wrapped_y_requests(client):
    """W-06: /wrapped agrega la escucha; /requests encola una petición."""
    from app.database import SessionLocal
    from app import models
    r = client.post("/auth/register", json={"email": "wr@t.com", "password": "clave-larga-1"})
    token = r.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    # pedir una canción
    rq = client.post("/requests", json={"text": "Rosalía - DESPECHÁ"}, headers=h)
    assert rq.status_code == 200 and rq.json()["ok"] is True
    assert client.post("/requests", json={"text": ""}, headers=h).status_code == 400

    # /wrapped (aunque no haya plays, responde)
    w = client.get("/wrapped?period=week", headers=h)
    assert w.status_code == 200
    assert "top_artists" in w.json() and "minutes" in w.json()


def test_worker_tareas(client):
    """W-07 (sin scheduler): las tareas parametrizadas corren sin romper."""
    from app.database import SessionLocal
    from app import models
    from app import workers
    db = SessionLocal()
    # añadir un track descargado para que rebuild_similar y verificar tengan algo
    db.add(models.Track(title="WT", artist="WA", genre="pop", year=2020, bpm=120, energy=0.5,
                        status="descargada", source="test", file_path="E:/no_existe.mp3", rank=100))
    db.commit()

    n_sim = workers.rebuild_similar_job(db)
    n_mix = workers.rebuild_mixes(db)
    n_static = workers.rebuild_static_lists(db)
    n_ver = workers.verificar_ficheros(db)
    n_prune = workers.prune(db)
    db.close()

    assert isinstance(n_sim, int) and n_sim >= 0
    assert isinstance(n_mix, int) and n_mix >= 0
    assert n_static >= 0
    assert n_ver >= 0
    assert isinstance(n_prune, int)
