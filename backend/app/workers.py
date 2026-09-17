"""Trabajador en segundo plano. Arranque:  python -m app.workers (proceso separado, nunca uvicorn)."""
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler

from .database import SessionLocal, ensure_schema
from . import models
from .personalization import rebuild_similar

log = logging.getLogger("radiopv.worker")

_ROOT = None


def _root() -> str:
    global _ROOT
    if _ROOT is None:
        import os
        _ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return _ROOT


def _tarea(nombre, fn):
    """Envoltorio: sesión propia, errores capturados, nunca tumba el scheduler."""
    def wrapper():
        db = SessionLocal()
        try:
            n = fn(db)
            log.info("[%s] ok %s", nombre, n)
        except Exception:  # noqa: BLE001
            log.exception("[%s] FALLÓ", nombre)
        finally:
            db.close()
    return wrapper


def sync_catalogo(db) -> int:
    """Refresca el catálogo del backend desde radiov.db (migración no destructiva) + contadores.
    Idempotente. No borra señales de usuario. Propaga de verdad (no solo recuento): llama a
    migrate_sqlite para que las canciones nuevas del agente lleguen a la app sin pasos manuales."""
    from .maintenance import recount_artist_tracks
    try:
        import migrate_sqlite
        migrate_sqlite.migrate()
    except Exception:  # noqa: BLE001
        log.exception("[sync_catalogo] migración directa FALLÓ")
    recount_artist_tracks(db)
    return db.query(models.Track).count()


def rebuild_similar_job(db) -> int:
    """Top-40 vecinos por canción (reemplaza la tabla en una transacción)."""
    return rebuild_similar(db, top=40)


def _mix_frio(semilla, scored, n=25):
    """R4 · arranque en frío (<10 señales): popularidad (rank) + variedad forzada.
    Máx. 2 por artista, y procura ≥4 géneros y ≥3 eras. Determinista con la semilla por día."""
    from collections import Counter
    tracks = [t for t, _ in scored]
    tracks.sort(key=lambda t: (t.rank or 0), reverse=True)
    r = semilla.sample(tracks, min(len(tracks), n * 3))   # barajado estable por día
    sel = []
    por_artista = Counter()
    generos = set()
    eras = set()
    for t in r:
        if len(sel) >= n:
            break
        if por_artista[t.artist] >= 2:
            continue
        sel.append(t)
        por_artista[t.artist] += 1
        if t.genre:
            generos.add(t.genre)
        if t.era:
            eras.add(t.era)
    # rellenar si no se llegó a ≥4 géneros / ≥3 eras (sin restricción de artista)
    if len(generos) < 4 or len(eras) < 3:
        for t in tracks:
            if len(sel) >= n:
                break
            if t in sel:
                continue
            sel.append(t)
            if t.genre:
                generos.add(t.genre)
            if t.era:
                eras.add(t.era)
    return [t.id for t in sel]


def _generar_mixes_usuario(db, user, hoy=None) -> int:
    """R2+R3+R4+R5 · genera los mixes de UN usuario (daily_1/2/3, discover, on_repeat, radar,
    time_capsule). Devuelve cuántos creó. Lo usan rebuild_mixes (todos) y /mixes (un usuario
    recién registrado, para que no se quede sin mezclas hasta la próxima pasada programada)."""
    import random
    from collections import Counter
    from . import personalization as P
    if hoy is None:
        hoy = datetime.utcnow().date().isoformat()
    last30 = datetime.utcnow() - timedelta(days=30)
    semilla = random.Random(f"{user.id}-{hoy}")
    prof = P._profile(user, db)
    señal = P.señales(user.id, db)
    frio = len(señal) < 10
    allq = db.query(models.Track).filter(models.Track.status == "descargada").all()
    generos = prof.get("genres") or []
    played = {p.track_id for p in db.query(models.Play).filter_by(user_id=user.id)}
    n = 0

    def guarda(kind, track_ids, expl):
        nonlocal n
        if track_ids:
            db.add(models.Mix(user_id=user.id, kind=kind, seed=f"{user.id}-{hoy}",
                              tracks_json=str(track_ids), explicacion=expl))
            n += 1

    # daily_1/2/3 · anclados a grupos de géneros distintos
    for i in range(3):
        g = generos[i] if i < len(generos) else None
        pool = [t for t in allq if (g and t.genre == g)] or allq
        p = [(t, P._score(t, prof)) for t in pool]
        ids = _mix_frio(semilla, p) if frio else [t.id for t in P.seleccionar_diverso(p, 25)]
        guarda(f"daily_{i + 1}", ids, f"porque te gusta {g or tu_marca(prof)}")

    # discover · nunca escuchadas, de artistas fuera de tus preferidos
    preferidos = set(prof.get("artists") or [])
    pool = [t for t in allq if t.id not in played and t.artist not in preferidos]
    p = [(t, P._score(t, prof)) for t in pool]
    ids = _mix_frio(semilla, p) if frio or len(pool) > 25 else [t.id for t in P.seleccionar_diverso(p, 30)]
    guarda("discover", ids, "algo nuevo, lejos de tu zona de confort")

    # on_repeat · lo más escuchado en 30 días
    counts = Counter(p.track_id for p in db.query(models.Play).filter_by(user_id=user.id)
                     .filter(models.Play.played_at >= last30))
    guarda("on_repeat", [tid for tid, _ in counts.most_common(30)], "lo que más suenas")

    # time_capsule · tus géneros, pero de antes de 2010
    vie = ("1990s", "1980s", "1970s", "1960s")
    pool = [t for t in allq if t.genre in generos and (t.era in vie or (t.year or 0) < 2010)]
    if pool:
        p = [(t, P._score(t, prof)) for t in pool]
        guarda("time_capsule", [t.id for t in P.seleccionar_diverso(p, 25)], "tus géneros de antes de 2010")

    # radar · novedades recientes afines
    reciente = datetime.utcnow() - timedelta(days=60)
    pool = [t for t in allq if t.year and t.year >= reciente.year]
    if pool:
        p = [(t, P._score(t, prof)) for t in pool]
        guarda("radar", [t.id for t in P.seleccionar_diverso(p, 25)], "lo más reciente que te puede gustar")

    db.commit()
    return n


def rebuild_mixes(db) -> int:
    """R2+R3+R4+R5 · regenera los mixes de TODOS los usuarios (idempotente por día)."""
    hoy = datetime.utcnow().date().isoformat()
    usuarios = db.query(models.User).all()
    db.query(models.Mix).delete()                     # regenerar todos (idempotente)
    total = 0
    for user in usuarios:
        total += _generar_mixes_usuario(db, user, hoy)
    db.commit()
    return total


def tu_marca(prof) -> str:
    a = (prof.get("artists") or [None])[0]
    return a or "tu música"


def _normalizar(texto: str) -> str:
    """T1 · minúsculas, sin tildes, sin (feat. …)/[Remaster]/- Radio Edit/signos. Para emparejar."""
    import re
    import unicodedata
    s = unicodedata.normalize("NFD", texto or "").encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"\(feat\.[^)]*\)|\(with[^)]*\)|\[remaster[^\]]*\]|- radio edit", "", s, flags=re.I)
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def _emparejar_hits(db, hits):
    """T1+T2 · empareja cada hit con el catálogo (normalizado + difflib>0.87).
    Devuelve (emparejados [(track, pos)], faltantes [(artista, título)])."""
    import difflib
    catalog = db.query(models.Track).filter(models.Track.status == "descargada").all()
    por_clave = {}
    for t in catalog:
        por_clave.setdefault((_normalizar(t.artist), _normalizar(t.title)), t)
    emparejados = []
    faltantes = []
    pos = 1
    for h in hits:
        artist = h.get("artist", ""); title = h.get("title", "")
        t = por_clave.get((_normalizar(artist), _normalizar(title)))
        if t is None:
            # fallback por similitud del título
            best, best_r = None, 0.0
            for (a, ti), cand in por_clave.items():
                if a != _normalizar(artist):
                    continue
                r = difflib.SequenceMatcher(None, ti, _normalizar(title)).ratio()
                if r > best_r:
                    best, best_r = cand, r
            if best_r > 0.87:
                t = best
        if t:
            emparejados.append((t, pos)); pos += 1
        else:
            faltantes.append((artist, title))
    return emparejados, faltantes


def _enqueue_missing(db, faltantes):
    """T2 · cada hit ausente se encola en `requests` para que el recolector lo baje."""
    n = 0
    for artist, title in faltantes:
        text = f"{artist} - {title}"
        existe = db.query(models.Request).filter_by(text=text, status="pendiente").first()
        if not existe:
            db.add(models.Request(user_id=None, text=text, status="pendiente"))
            n += 1
    db.commit()
    return n


def refresh_trends(db, _hits=None) -> int:
    """T1+T2 · listas de éxitos → playlist 'system' Trending + encolar lo que falta al catálogo."""
    if _hits is None:
        try:
            from radiov.charts import apple_top_songs
            _hits = apple_top_songs("es", limit=25)
        except Exception:  # noqa: BLE001
            _hits = []
    emparejados, faltantes = _emparejar_hits(db, _hits)
    pl = db.query(models.Playlist).filter_by(type="system", name="Trending").first()
    if not pl:
        pl = models.Playlist(user_id=None, name="Trending", type="system")
        db.add(pl)
        db.commit()
    db.query(models.PlaylistTrack).filter_by(playlist_id=pl.id).delete()
    for track, pos in emparejados:
        db.add(models.PlaylistTrack(playlist_id=pl.id, track_id=track.id, position=pos))
    db.commit()
    _enqueue_missing(db, faltantes)
    return len(emparejados)


def verificar_ficheros(db) -> int:
    """Comprueba que cada file_path existe. Si falta → status='perdida' (cola de re-descarga)."""
    from .paths import resolve_music
    n = 0
    for t in db.query(models.Track).filter(models.Track.status == "descargada").all():
        if not t.file_path:
            continue
        try:
            if not resolve_music(t.file_path).exists():
                t.status = "perdida"
                n += 1
        except Exception:  # noqa: BLE001
            t.status = "perdida"
            n += 1
    db.commit()
    return n


SYSTEM_LISTS = [
    ("Novedades", '{"sort":"year"}'),
    ("Los 2000", '{"eras":["00s"]}'),
    ("Fiesta", '{"tags":"fiesta"}'),
    ("Tranquilo", '{"energy":"baja","tags":"relax"}'),
    ("Para el gimnasio", '{"energy":"alta"}'),
    ("En español", '{"language":"es"}'),
    ("Clásicos", '{"eras":["90s","80s","70s","60s","vintage"]}'),
    ("Viral / Tendencia", '{"sort":"popularidad"}'),
]


def _seleccionar_por_regla(db, filtros: dict) -> list:
    """Aplica una regla de smart_playlist al catálogo (géneros/eras/energía/tags/idioma)."""
    q = db.query(models.Track).filter(models.Track.status == "descargada")
    if filtros.get("genres"):
        q = q.filter(models.Track.genre.in_(filtros["genres"]))
    if filtros.get("eras"):
        q = q.filter(models.Track.era.in_(filtros["eras"]))
    if filtros.get("language"):
        q = q.filter(models.Track.language == filtros["language"])
    if filtros.get("energy"):
        lo, hi = {"baja": (0, 0.3), "media": (0.3, 0.55), "alta": (0.55, 1.01)}[filtros["energy"]]
        q = q.filter(models.Track.energy >= lo, models.Track.energy < hi)
    if filtros.get("tags"):
        q = q.filter(models.Track.tags.ilike(f"%{filtros['tags']}%"))
    if filtros.get("sort") == "year":
        q = q.order_by(models.Track.year.desc())
    elif filtros.get("sort") == "popularidad":
        q = q.order_by(models.Track.popularidad.desc(), models.Track.rank.desc())
    else:
        q = q.order_by(models.Track.rank.desc())
    return q.limit(int(filtros.get("limit", 50))).all()


def rebuild_static_lists(db) -> int:
    """T4 · crea smart_playlists del sistema y genera su contenido real en playlist_tracks."""
    import json
    n = 0
    for nombre, filtro_s in SYSTEM_LISTS:
        sp = db.query(models.SmartPlaylist).filter_by(name=nombre).first()
        if not sp:
            sp = models.SmartPlaylist(user_id=None, name=nombre, filters=filtro_s)
            db.add(sp)
            n += 1
        elif (sp.filters or "") != filtro_s:
            sp.filters = filtro_s              # la regla de SYSTEM_LISTS manda (migra listas viejas)
        filtros = json.loads(sp.filters or "{}")
        tracks = _seleccionar_por_regla(db, filtros)
        # asegurar la playlist 'system' y rellenar sus pistas
        pl = db.query(models.Playlist).filter_by(type="system", name=nombre).first()
        if not pl:
            pl = models.Playlist(user_id=None, name=nombre, type="system")
            db.add(pl)
            db.commit()
        db.query(models.PlaylistTrack).filter_by(playlist_id=pl.id).delete()
        for i, t in enumerate(tracks, 1):
            db.add(models.PlaylistTrack(playlist_id=pl.id, track_id=t.id, position=i))
        n += len(tracks)
    db.commit()
    return n


def _tops_diversos(db, tracks, n=50):
    """TOP3 · top por rank con diversidad de artista (máx. 2 por artista)."""
    from collections import Counter
    tracks = sorted(tracks, key=lambda t: (t.rank or 0), reverse=True)
    sel = [] ; por_art = Counter()
    for t in tracks:
        if len(sel) >= n:
            break
        if por_art[t.artist] >= 2:
            continue
        sel.append(t) ; por_art[t.artist] += 1
    return [t.id for t in sel]


def rebuild_cut_tops(db) -> int:
    """TOP3 · una playlist 'system' por género (>30 canciones) y por década, ordenadas por rank
    y con diversidad de artista. Salen gratis del catálogo."""
    from sqlalchemy import func
    n = 0
    # por género
    counts = db.query(models.Track.genre, func.count()).filter(
        models.Track.status == "descargada", models.Track.genre.isnot(None)).group_by(models.Track.genre).all()
    for genre, cnt in counts:
        if cnt <= 30:
            continue
        tracks = db.query(models.Track).filter(models.Track.status == "descargada",
                                               models.Track.genre == genre).all()
        n += _swap_system_playlist(db, f"Top {genre}", _tops_diversos(db, tracks))
    # por década
    for dec in range(1960, 2030, 10):
        tracks = db.query(models.Track).filter(models.Track.status == "descargada",
                                               models.Track.year >= dec,
                                               models.Track.year < dec + 10).all()
        if tracks:
            n += _swap_system_playlist(db, f"Top {dec}s", _tops_diversos(db, tracks))
    return n


def rebuild_external_tops(db, sources=None) -> int:
    """TOP1 · tops externos (Apple/Los 40/Deezer/YouTube): emparejado tolerante + encolar lo que
    falta. `sources` es [(nombre, fn_hits)]; fn_hits() necesita red, por eso es inyectable."""
    if sources is None:
        try:
            from radiov.charts import apple_top_songs, los40_top
            sources = [
                ("Top España", lambda: apple_top_songs("es", limit=25)),
                ("Top Global", lambda: apple_top_songs("us", limit=25) + apple_top_songs("gb", limit=25)),
                ("Top Latino", lambda: apple_top_songs("mx", limit=25) + apple_top_songs("ar", limit=25)),
                ("Los 40 Principales", lambda: los40_top()),
            ]
        except Exception:  # noqa: BLE001
            sources = []
    n = 0
    for nombre, fn in sources:
        try:
            hits = fn()
        except Exception:  # noqa: BLE001
            continue
        emparejados, faltantes = _emparejar_hits(db, hits)
        n += _swap_system_playlist(db, nombre, [t.id for t, _ in emparejados])
        _enqueue_missing(db, faltantes)
    return n


def _swap_system_playlist(db, nombre: str, track_ids: list) -> int:
    """Crea/actualiza una playlist 'system' con esas pistas. Devuelve cuántas pistas hay."""
    pl = db.query(models.Playlist).filter_by(type="system", name=nombre).first()
    if not pl:
        pl = models.Playlist(user_id=None, name=nombre, type="system")
        db.add(pl)
        db.commit()
    db.query(models.PlaylistTrack).filter_by(playlist_id=pl.id).delete()
    for i, tid in enumerate(track_ids, 1):
        db.add(models.PlaylistTrack(playlist_id=pl.id, track_id=tid, position=i))
    db.commit()
    return len(track_ids)


def rebuild_home_tops(db) -> int:
    """TOP2 · tops de la propia casa, hecho con los `plays` reales (testable, sin red)."""
    from collections import Counter
    n = 0
    last30 = datetime.utcnow() - timedelta(days=30)
    week = datetime.utcnow() - timedelta(days=7)

    # 1) Lo más escuchado de la casa (todos los usuarios, 30 días)
    agg = Counter(p.track_id for p in db.query(models.Play).filter(models.Play.played_at >= last30))
    n += _swap_system_playlist(db, "Lo más escuchado de la casa",
                               [tid for tid, _ in agg.most_common(50)])

    # 2) Rescatadas: nunca reproducidas (el fondo de armario). El backend no guarda la fecha de
    #    alta del catálogo, así que usamos "nunca suena" como criterio.
    played = {p.track_id for p in db.query(models.Play)}
    rescatadas = [tid for (tid,) in
                  db.query(models.Track.id).filter(models.Track.status == "descargada")
                  if tid not in played]
    n += _swap_system_playlist(db, "Rescatadas", rescatadas[:50])

    # 3) Top por usuario + Subiendo (crecimiento semanal) — por usuario con señales
    usuarios = {u[0] for u in db.query(models.Play.user_id).distinct()}
    for uid in usuarios:
        sub = db.query(models.Play).filter_by(user_id=uid)
        player = Counter(p.track_id for p in sub.filter(models.Play.played_at >= last30))
        n += _swap_system_playlist(db, f"Top {uid}", [tid for tid, _ in player.most_common(50)])
        this_week = {p.track_id for p in sub.filter(models.Play.played_at >= week)}
        prev_week = {p.track_id for p in sub.filter(models.Play.played_at < week,
                                                    models.Play.played_at >= last30)}
        subiendo = [tid for tid in this_week if tid in player and tid not in prev_week][:50]
        if subiendo:
            n += _swap_system_playlist(db, f"Subiendo {uid}", subiendo)
    return n


def prune(db) -> int:
    """Limpia de mixes/playlists lo que ya no aplica (nunca borra del catálogo)."""
    old = datetime.utcnow() - timedelta(days=30)
    n = db.query(models.Mix).filter(models.Mix.created_at < old).delete()
    db.commit()
    return n


def limpiar_catalogo(db=None) -> int:
    """T-25: puerta de calidad como tarea del worker. Marca 'cuarentena' en radiov.db (la fuente)
    las filas 'descargada' que no pasan quality.revisar(). No borra ficheros."""
    import sqlite3, sys
    root = _root()
    if root not in sys.path:
        sys.path.insert(0, root)
    from radiov import quality as Q
    conn = sqlite3.connect(f"{root}\\data\\radiov.db")
    conn.row_factory = sqlite3.Row
    n = 0
    for row in conn.execute("SELECT id,title,artist,duration,status FROM tracks WHERE status='descargada'"):
        rec = {"title": row["title"] or "", "artist": row["artist"] or "", "duration": row["duration"]}
        ok, _ = Q.revisar(rec)
        if not ok:
            conn.execute("UPDATE tracks SET status='cuarentena' WHERE id=?", (row["id"],))
            n += 1
    conn.commit()
    conn.close()
    return n


def analisis_audio(db=None) -> int:
    """T-24: pasada de análisis (rms + gain_db + percentil de energía) sobre radiov.db.
    Lenta (lee cada MP3); se programa aparte y corre con el recolector PAUSADO."""
    import subprocess, sys, os
    root = _root()
    try:
        r = subprocess.run(
            [sys.executable, os.path.join(root, "scripts", "analisis_completo.py")],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=7200)
        log.info("[analisis_audio] %s", (r.stdout or "")[-200:])
        return 0
    except Exception:  # noqa: BLE001
        log.exception("[analisis_audio] FALLÓ")
        return -1


def refresh_popularidad_pasar(db, limit: int = 40) -> int:
    """P · refresca visitas de YouTube + histórico de un lote de pistas relevantes."""
    from . import popularidad as POP
    return POP.refrescar(db, limit)


def _rellenar_sistema(db, nombre: str, track_ids: list[int]) -> int:
    """Crea/actualiza una playlist del sistema con una lista explícita de track_ids."""
    pl = db.query(models.Playlist).filter_by(type="system", name=nombre).first()
    if not pl:
        pl = models.Playlist(user_id=None, name=nombre, type="system")
        db.add(pl)
        db.commit()
    db.query(models.PlaylistTrack).filter_by(playlist_id=pl.id).delete()
    for i, tid in enumerate(track_ids, 1):
        db.add(models.PlaylistTrack(playlist_id=pl.id, track_id=tid, position=i))
    db.commit()
    return len(track_ids)


def rebuild_recopilaciones(db, n: int = 20) -> int:
    """P · recopilaciones por PICO de popularidad: playlists del sistema "Éxitos de los {época}" y
    "Lo mejor del {género}" ordenadas por el máximo histórico de visitas (el 'momento' más popular)."""
    from . import popularidad as POP
    rec = POP.recopilaciones(db, n=n)
    total = 0
    for era, items in rec["por_era"].items():
        total += _rellenar_sistema(db, f"Éxitos de los {era}", [it["id"] for it in items])
    for genero, items in rec["por_genero"].items():
        total += _rellenar_sistema(db, f"Lo mejor del {genero}", [it["id"] for it in items])
    return total


def _pasada_inicial(descargadora=None) -> None:
    """Al arrancar, corre una vez lo que regenera el catálogo y la personalización (para que
    'python -m app.workers' haga algo ya, no espere a las horas del cron)."""
    ensure_schema()          # añade columnas nuevas (mixes.explicacion) a BD antiguas
    for nombre, fn in (
        ("sync_catalogo", sync_catalogo),        # propaga géneros corregidos a backend.db
        ("rebuild_similar", rebuild_similar_job),
        ("rebuild_static_lists", rebuild_static_lists),
        ("rebuild_home_tops", rebuild_home_tops),
        ("rebuild_cut_tops", rebuild_cut_tops),
        ("rebuild_recopilaciones", rebuild_recopilaciones),
        ("refresh_popularidad", lambda db: refresh_popularidad_pasar(db, 30)),  # primer lote
        ("rebuild_mixes", rebuild_mixes),
    ):
        try:
            db = SessionLocal()
            n = fn(db)
            log.info("[inicial] %s → %s", nombre, n)
        except Exception:  # noqa: BLE001
            log.exception("[inicial] %s FALLÓ", nombre)
        finally:
            db.close()


def main():
    logging.basicConfig(level=logging.INFO)
    s = BlockingScheduler(timezone="Europe/Madrid")
    s.add_job(_tarea("sync_catalogo", sync_catalogo), "interval", minutes=30)
    s.add_job(_tarea("limpiar_catalogo", limpiar_catalogo), "interval", hours=1)
    s.add_job(_tarea("analysis_audio", analisis_audio), "interval", hours=4)
    s.add_job(_tarea("rebuild_similar", rebuild_similar_job), "cron", hour=4)
    s.add_job(_tarea("rebuild_mixes", rebuild_mixes), "cron", hour=5)
    s.add_job(_tarea("refresh_trends", refresh_trends), "interval", hours=8)
    s.add_job(_tarea("rebuild_static_lists", rebuild_static_lists), "cron", hour=6)
    s.add_job(_tarea("rebuild_home_tops", rebuild_home_tops), "cron", hour=6, minute=30)
    s.add_job(_tarea("rebuild_cut_tops", rebuild_cut_tops), "cron", hour=6, minute=45)
    s.add_job(_tarea("rebuild_recopilaciones", rebuild_recopilaciones), "cron", hour=7, minute=15)
    s.add_job(_tarea("refresh_popularidad", lambda db: refresh_popularidad_pasar(db, 40)), "interval", hours=6)
    s.add_job(_tarea("verificar_ficheros", verificar_ficheros), "cron", day_of_week="sun", hour=3)
    s.add_job(_tarea("prune", prune), "cron", hour=7)
    log.info("Worker RadioPV en marcha")
    _pasada_inicial()          # regenera listas/mixes/tops y propaga géneros YA
    s.start()


if __name__ == "__main__":
    main()
