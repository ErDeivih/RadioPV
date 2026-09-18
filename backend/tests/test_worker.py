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


# --- Republicar las 'incompleta' (18/09/2026) ---------------------------------------------------
#
# Con `metadata_strict`, cada descarga nueva nace 'incompleta' y sólo se publica cuando el análisis
# le rellena el `gain_db` que le falta. Dos bloqueos mutuos lo hacían imposible:
#   · `scripts/analisis_completo.py` buscaba sólo `status='descargada'`, o sea justo lo contrario
#     de las filas que necesitan el análisis;
#   · `republicar_completas` existía en `radiov/catalog.py` pero NO la llamaba nadie.
# Resultado: 279 canciones con su fichero ya descargado e invisibles para siempre en la aplicación.


def test_la_pasada_de_analisis_mira_tambien_las_incompletas():
    """Si el analizador ignora las 'incompleta', el `gain_db` que les falta no se rellena jamás."""
    import re
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent.parent
    fuente = (raiz / "scripts" / "analisis_completo.py").read_text(encoding="utf-8")
    # Nos quedamos con el SELECT de verdad, no con los comentarios que explican el fallo.
    codigo = "\n".join(l for l in fuente.splitlines() if not l.strip().startswith("#"))
    select = re.search(r"SELECT id, file_path, rms, gain_db FROM tracks(.+?)fetchall", codigo, re.S)
    assert select, "no se encontró la consulta de análisis"
    consulta = " ".join(select.group(1).split())
    assert "incompleta" in consulta, f"la consulta ignora las incompletas: {consulta}"
    assert "file_path != ''" in consulta, f"entrarían filas sin fichero real: {consulta}"


def test_el_worker_publica_las_incompletas_que_ya_estan_completas(client):
    """La función existe, pero lo que importa es que ALGUIEN la llame."""
    from radiov import catalog as CAT
    from radiov.config import DB_PATH
    from radiov import db as rdb
    import sqlite3

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    completo = dict(year=2001, genre="pop", language="es", bpm=120.0, energy=0.5,
                    gain_db=-3.0, duration=200.0, cover_url="http://x/c.jpg")
    columnas = ", ".join(completo)
    marcas = ", ".join("?" * len(completo))
    # 1: completa → se publica · 2: sin gain_db → se queda como está
    cur = conn.execute(
        f"INSERT INTO tracks(title, artist, status, {columnas}) VALUES (?,?,?,{marcas})",
        ["Completa YA", "PC", "incompleta", *completo.values()])
    id_completa = cur.lastrowid
    sin_gain = {k: v for k, v in completo.items() if k != "gain_db"}
    cur = conn.execute(
        f"INSERT INTO tracks(title, artist, status, {', '.join(sin_gain)}) "
        f"VALUES (?,?,?,{', '.join('?' * len(sin_gain))})",
        ["Aun sin gain", "PA", "incompleta", *sin_gain.values()])
    id_incompleta = cur.lastrowid
    conn.commit()
    conn.close()

    try:
        CAT.republicar_completas()
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        estados = {r["id"]: r["status"] for r in
                   conn.execute("SELECT id, status FROM tracks WHERE id IN (?,?)",
                                (id_completa, id_incompleta))}
        conn.close()
        assert estados[id_completa] == "descargada", "una completa se ha quedado oculta"
        assert estados[id_incompleta] == "incompleta", "se ha publicado sin gain_db"
    finally:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("DELETE FROM tracks WHERE id IN (?,?)", (id_completa, id_incompleta))
        conn.commit()
        conn.close()

    # Y que las tareas del worker la incluyan: el fallo original era que nadie la llamaba.
    from app import workers as W
    import inspect
    fuente = inspect.getsource(W)
    assert '"republicar"' in fuente or "republicar_completas" in fuente
    assert "republicar_completas" in inspect.getsource(W.analisis_audio), \
        "el análisis rellena el gain_db y debe publicar lo que quede completo"
