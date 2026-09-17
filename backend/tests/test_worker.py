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


# --- Programación de tareas y verificación de ficheros -----------------------------------------
#
# Contexto (17/09/2026): el servidor llevaba desde el 7 de septiembre SIN hacer el trabajo diario
# (mixes, listas del sistema, la tabla `similar` a medias) y nada lo decía. La causa: APScheduler
# usa por defecto `misfire_grace_time=1` SEGUNDO, así que una tarea de tipo `cron` que se retrase
# más de un segundo se descarta sin avisar y no vuelve hasta el día siguiente. Las de intervalo
# se salvaban porque su siguiente ejecución se recalcula sola.


def test_las_tareas_no_se_pierden_si_se_retrasan():
    from apscheduler.schedulers.background import BackgroundScheduler
    from app import workers as W

    s = BackgroundScheduler()
    try:
        W._programar(s, "prueba_cron", lambda db: 0, trigger="cron", hour=3)
        job = s.get_jobs()[0]
        assert job.id == "prueba_cron"
        # El valor por defecto (1 s) es exactamente lo que hacía perder el trabajo.
        assert job.misfire_grace_time > 1
        assert job.misfire_grace_time == W.MARGEN_RETRASO_SEGUNDOS
        assert job.max_instances == 1        # una tarea larga no se solapa consigo misma
        assert job.coalesce is True
    finally:
        pass                                 # el planificador nunca llegó a arrancar


def test_verificar_ficheros_no_saca_canciones_por_un_fallo_transitorio(client, monkeypatch):
    """Si la comprobación del fichero falla (disco ocupado, permiso…), la canción se deja como
    estaba: antes se marcaba 'perdida' ante CUALQUIER excepción y desaparecía de la aplicación."""
    from app.database import SessionLocal
    from app import models, paths, workers

    db = SessionLocal()
    db.add(models.Track(title="Transitorio", artist="TA", status="descargada", source="test",
                        file_path="catalogada/TA/x.mp3", rank=1))
    db.commit()

    def revienta(_fp):
        raise OSError("el disco no responde")

    monkeypatch.setattr(paths, "resolve_music", revienta)
    workers.verificar_ficheros(db)

    t = db.query(models.Track).filter_by(title="Transitorio").first()
    assert t.status == "descargada"          # sigue publicada
    db.delete(t)
    db.commit()
    db.close()


def test_verificar_ficheros_si_marca_cuando_de_verdad_no_esta(client, monkeypatch):
    from app.database import SessionLocal
    from app import models, paths, workers

    db = SessionLocal()
    db.add(models.Track(title="Ausente", artist="AA", status="descargada", source="test",
                        file_path="catalogada/AA/no.mp3", rank=1))
    db.commit()

    class Falso:
        def exists(self):
            return False

    monkeypatch.setattr(paths, "resolve_music", lambda _fp: Falso())
    workers.verificar_ficheros(db)

    t = db.query(models.Track).filter_by(title="Ausente").first()
    assert t.status == "perdida"
    db.delete(t)
    db.commit()
    db.close()
