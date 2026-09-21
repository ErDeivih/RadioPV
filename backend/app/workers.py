"""Trabajador en segundo plano. Arranque:  python -m app.workers (proceso separado, nunca uvicorn)."""
import logging
import threading
from datetime import datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import func

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
    # Los recuentos de /facets cambian con el catálogo: se tira la caché para no servir los de
    # antes de la sincronización (si no, habría hasta 5 minutos de recuentos viejos).
    try:
        from .routers import facets
        facets.invalidar()
    except Exception:  # noqa: BLE001
        pass
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
    """Comprueba que cada file_path existe. Si falta → status='perdida' (se vuelve a descargar).

    OJO con el `except`: antes marcaba 'perdida' ante CUALQUIER excepción, así que un fallo
    transitorio (el disco ocupado, un permiso, el volumen montándose) sacaba de la aplicación
    canciones que estaban perfectamente. Ahora sólo se marca cuando la comprobación dice
    claramente que el fichero no está; si la comprobación falla, se deja como estaba y se anota.
    """
    from .paths import resolve_music
    n = dudosos = 0
    for t in db.query(models.Track).filter(models.Track.status == "descargada").all():
        if not t.file_path:
            continue
        try:
            existe = resolve_music(t.file_path).exists()
        except FileNotFoundError:
            existe = False                      # no hay fichero que buscar: sí es un problema
        except Exception:  # noqa: BLE001
            # No se sabe: no se toca la canción (mejor dejarla sonando que sacarla por un fallo
            # momentáneo del disco).
            dudosos += 1
            continue
        if not existe:
            t.status = "perdida"
            n += 1
    db.commit()
    if dudosos:
        log.warning("[verificar_ficheros] %s canciones no se pudieron comprobar (se dejan como estaban)", dudosos)
    if n:
        log.info("[verificar_ficheros] %s canciones marcadas como perdidas", n)
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


def _swap_system_playlist(db, nombre: str, track_ids: list, user_id=None) -> int:
    """Crea/actualiza una playlist 'system' con esas pistas. Devuelve cuántas pistas hay.

    `user_id` distingue las listas generadas PARA UNA PERSONA (sus más escuchadas, sus
    descubrimientos) de las que la aplicación genera para todos (Top pop, Fiesta, Novedades…).
    Antes las personales se guardaban sin dueño y con el id del usuario metido en el nombre
    («Top 12», «Subiendo 12») porque la búsqueda era sólo por nombre: el resultado era que
    **todo el mundo veía las listas de todo el mundo** con nombres que parecían un error.
    """
    pl = (db.query(models.Playlist)
          .filter_by(type="system", name=nombre, user_id=user_id).first())
    if not pl:
        pl = models.Playlist(user_id=user_id, name=nombre, type="system")
        db.add(pl)
        db.commit()
    db.query(models.PlaylistTrack).filter_by(playlist_id=pl.id).delete()
    for i, tid in enumerate(track_ids, 1):
        db.add(models.PlaylistTrack(playlist_id=pl.id, track_id=tid, position=i))
    db.commit()
    return len(track_ids)


def rebuild_remixes(db) -> int:
    """Listas de mashups, remixes, sesiones de DJ y TECH HOUSE.

    POR QUÉ
    -------
    El usuario escucha mucho este tipo de música y **en la aplicación no había forma de
    encontrarla**: el catálogo la marcaba (`is_remix`) y el panel de administración podía
    filtrarla, pero para el oído no existía. Se generan tres listas:

      · «Mashups y remixes» — cruces de dos o más canciones y remixes sueltos.
      · «Sesiones de DJ»    — mezclas largas, para escuchar de un tirón.
      · «Tech house y guaracha» — las remezclas de tech house hechas por gente: es lo que pidió
        expresamente («me gustan los tech house remix y este tipo de canciones hechas por gente,
        por ejemplo Pomata… con bass, en español o inglés o mezcla, usando una o varias canciones
        originales»). Se reconoce por el género de la ficha (`techhouse`), que a su vez sale del
        título cuando no hay álbum de Deezer («Tech House Remix», «Guaracha», «Techengue»).

    El tipo lo decide `radiov.quality.clasificar` (el mismo que usa la puerta de calidad), así que
    la lista y el catálogo no pueden discrepar. Se ordena por popularidad: primero lo que más
    suena, que es lo que se quiere escuchar.
    """
    from radiov.catalog import guess_genre
    from radiov.quality import clasificar, parece_portugues

    filas = (db.query(models.Track.id, models.Track.title, models.Track.artist,
                      models.Track.duration, models.Track.rank, models.Track.language,
                      models.Track.genre)
             .filter(models.Track.status == "descargada")
             .all())
    remixes, sesiones, tech_house, club = [], [], [], []
    # Géneros que son «música de pista» (el terreno del perfil de electrónica que pidió el usuario):
    # la electrónica de baile del catálogo, sin las canciones de otros estilos.
    DE_PISTA = {"dance", "house", "electro", "techno", "techhouse"}
    for tid, title, artist, duration, rank, language, genre in filas:
        # Portugués fuera de las listas: la política del catálogo es español (España y Latinoamérica)
        # e inglés, con italiano y francés de siempre. Estas listas son las que el usuario pone a
        # sonar de un tirón, así que son justo donde no puede aparecer algo que no quiere oír.
        # (Las que ya están dentro y no se detecten aquí se limpian con el atajo «En portugués».)
        if language == "pt" or parece_portugues(title or "", artist or ""):
            continue
        # El tech house se mira por género Y por título: así entra también lo que se catalogó antes
        # de que existiera el género `techhouse` (el título lo dice igual de claro).
        if (genre or "") == "techhouse" or guess_genre(title or "", artist or "") == "techhouse":
            tech_house.append((rank or 0, tid))
        if (genre or "") in DE_PISTA:
            club.append((rank or 0, tid))
        tipo = clasificar(title or "", artist or "", duration)
        if tipo == "sesion":
            sesiones.append((rank or 0, tid))
        elif tipo in ("mashup", "remix"):
            remixes.append((rank or 0, tid))

    remixes.sort(reverse=True)
    sesiones.sort(reverse=True)
    tech_house.sort(reverse=True)
    club.sort(reverse=True)
    # SIN TOPE: la lista tiene que ser TODA la música de ese tipo, no una muestra. Antes cortaba en
    # 60 y 40, y con el catálogo creciendo eso significaba que las listas del tipo de música que el
    # usuario más escucha se quedaban cortas y no dejaban ver lo que había: pedía «la lista de este
    # tipo de canciones» y la lista era una selección de las 60 más populares. Se ordenan por
    # popularidad, así que lo mejor sigue saliendo primero.
    todas_remix = [tid for _, tid in remixes]
    todas_sesiones = [tid for _, tid in sesiones]
    todo_tech = [tid for _, tid in tech_house]
    todo_club = [tid for _, tid in club]
    n = _swap_system_playlist(db, "Mashups y remixes", todas_remix)
    n += _swap_system_playlist(db, "Sesiones de DJ", todas_sesiones)
    n += _swap_system_playlist(db, "Tech house y guaracha", todo_tech)
    # «Club y festival»: la electrónica de pista del catálogo (dance, house, electro, techno y tech
    # house). Nace del perfil de electrónica que pasó el usuario —dinámica de club y de festival,
    # con las sesiones y los clásicos de baile—, para que esa música tenga su sitio donde se ve.
    n += _swap_system_playlist(db, "Club y festival", todo_club)
    log.info("[remixes] %s mashups/remixes · %s sesiones · %s tech house · %s club y festival "
             "(listas completas)", len(todas_remix), len(todas_sesiones), len(todo_tech),
             len(todo_club))
    return n


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

    # 3) Listas personales: "Tus más escuchadas" y "Descubrimientos de la semana".
    #    Van con dueño (user_id) y con nombre de verdad, para que aparezcan en "Tus listas" y no
    #    las vea nadie más. Antes se llamaban «Top {uid}» y «Subiendo {uid}» y eran de todos.
    usuarios = {u[0] for u in db.query(models.Play.user_id).distinct()}
    for uid in usuarios:
        sub = db.query(models.Play).filter_by(user_id=uid)
        player = Counter(p.track_id for p in sub.filter(models.Play.played_at >= last30))
        n += _swap_system_playlist(db, "Tus más escuchadas",
                                   [tid for tid, _ in player.most_common(50)], user_id=uid)
        this_week = {p.track_id for p in sub.filter(models.Play.played_at >= week)}
        prev_week = {p.track_id for p in sub.filter(models.Play.played_at < week,
                                                    models.Play.played_at >= last30)}
        subiendo = [tid for tid in this_week if tid in player and tid not in prev_week][:50]
        if subiendo:
            n += _swap_system_playlist(db, "Descubrimientos de la semana", subiendo, user_id=uid)
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
    from radiov.config import DB_PATH

    # OJO: aquí había `sqlite3.connect(f"{root}\\data\\radiov.db")`, con barras invertidas de
    # Windows escritas a mano. En Linux eso NO es una ruta: SQLite creaba un fichero nuevo
    # con ese nombre tan raro, vacío, y al consultarlo saltaba "no such table: tracks". El
    # worker fallaba en cada pasada y el vigilante lo avisaba por ntfy cada vez.
    #
    # La ruta se saca ahora de la configuración de la app, que respeta RADIOPV_DATA_DIR, así
    # que funciona igual en Windows y en Linux.
    conn = sqlite3.connect(str(DB_PATH))
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
    Lenta (lee cada MP3); se programa aparte y corre con el recolector PAUSADO.

    Al terminar **publica las que ya estén completas** (`republicar_completas`). Van juntas a
    propósito: el análisis es justo lo que rellena el `gain_db` que les falta a las
    'incompleta', y publicarlas es lo que las hace visibles en la aplicación. Antes eran dos
    pasos separados y el segundo no lo llamaba nadie: el análisis se hacía y las canciones
    seguían ocultas igual.
    """
    import subprocess, sys, os
    root = _root()
    try:
        r = subprocess.run(
            [sys.executable, os.path.join(root, "scripts", "analisis_completo.py")],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=7200)
        log.info("[analisis_audio] %s", (r.stdout or "")[-200:])
    except Exception:  # noqa: BLE001
        log.exception("[analisis_audio] FALLÓ")
        return -1
    return republicar_completas()


def republicar_completas(db=None) -> int:
    """Publica (`descargada`) las 'incompleta' que ya tienen todos sus metadatos.

    Con `metadata_strict=True` toda descarga nueva nace 'incompleta' y sólo se publica cuando el
    análisis rellena lo que le faltaba. Esta función existía en `radiov/catalog.py`… y **no la
    llamaba nadie**: las canciones se quedaban 'incompleta' para siempre aunque ya estuvieran
    completas, y la aplicación (que sólo publica 'descargada') no las enseñaba nunca.
    """
    import sys
    root = _root()
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from radiov import catalog as CAT
        # Antes de republicar: la carátula del propio vídeo para lo que no tiene ninguna. Es
        # determinista y no gasta red, y sin ella la puerta de metadatos no deja publicar: había
        # canciones esperando desde hacía días sólo por eso.
        try:
            puestas = CAT.caratulas_desde_youtube(limit=200)
            if puestas:
                # Y al disco, que es lo que sirve la aplicación (`/media/covers/<fichero>`). El
                # límite se deja holgado: `fetch_media` no ordena, así que con el mínimo justo
                # podría coger otras y no éstas.
                CAT.fetch_media(limit=max(50, puestas))
        except Exception:  # noqa: BLE001
            log.exception("[republicar_completas] no se pudieron poner las carátulas del vídeo")
        return CAT.republicar_completas()
    except Exception:  # noqa: BLE001
        log.exception("[republicar_completas] FALLÓ")
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


def revisar_extremos_lote_job(db, limit: int = 40) -> int:
    """Repasa en un lote pequeño las intros y colas de las canciones que ya estaban en el catálogo.

    POR QUÉ EN LOTES Y POR QUÉ EN EL SERVIDOR
    -----------------------------------------
    Las canciones nuevas las mide el PC (que es donde se bajan y donde sobra máquina). Pero las
    ~6.000 que ya estaban tienen su audio aquí, en `/music`, y el servidor es un portátil de 4 GB que
    además sirve la aplicación: analizarlas todas de golpe son ~1,7 horas de CPU. Así que se hacen 40
    cada dos horas (menos de un minuto de trabajo cada vez) y el catálogo se va repasando solo.

    Devuelve cuántas se revisaron (para el registro).
    """
    from radiov import catalog as CAT

    revisadas, con_algo, cambiadas = CAT.revisar_extremos_lote(limit=limit, buscar_otra=0, log=log.info)
    if revisadas:
        log.info("[extremos] %s revisadas · %s con intro/cola · %s cambiadas por otra versión",
                 revisadas, con_algo, cambiadas)
    return revisadas


def _pasada_inicial(descargadora=None) -> None:
    """Al arrancar, corre una vez lo que regenera el catálogo y la personalización (para que
    'python -m app.workers' haga algo ya, no espere a las horas del cron).

    Se lanza en un hilo aparte y DESPUÉS de arrancar el planificador: antes se ejecutaba entera
    (con `rebuild_similar`, que son 205.600 filas) ANTES de `s.start()`, así que el planificador
    no existía durante minutos y, con el autodespliegue revisando cada 5 minutos, se repetía
    entera en cada reinicio del contenedor.
    """
    ensure_schema()      # columnas e índices que falten en bases antiguas
    # Si los mixes se regeneraron hace poco, es que ya se hizo: no se repite el trabajo pesado
    # en cada reinicio del contenedor (el autodespliegue lo revisa cada 5 minutos).
    try:
        db = SessionLocal()
        try:
            ultimo = db.query(func.max(models.Mix.created_at)).scalar()
        finally:
            db.close()
        if ultimo is not None:
            momento = ultimo if isinstance(ultimo, datetime) else datetime.fromisoformat(str(ultimo))
            if momento.tzinfo is not None:
                momento = momento.replace(tzinfo=None)
            if datetime.utcnow() - momento < timedelta(hours=6):
                log.info("[inicial] omitida: los mixes son de hace menos de 6 h")
                return
    except Exception:  # noqa: BLE001
        log.exception("[inicial] no se pudo comprobar la antigüedad de los mixes")

    for nombre, fn in (
        ("sync_catalogo", sync_catalogo),        # propaga géneros corregidos a backend.db
        # Antes que nada: publicar las que ya estén completas. Es barato (una consulta) y hace
        # visibles de golpe las canciones que llevaban meses descargadas pero ocultas.
        ("republicar_completas", republicar_completas),
        ("rebuild_remixes", rebuild_remixes),
        ("rebuild_similar", rebuild_similar_job),
        ("rebuild_static_lists", rebuild_static_lists),
        ("rebuild_home_tops", rebuild_home_tops),
        ("rebuild_cut_tops", rebuild_cut_tops),
        ("rebuild_recopilaciones", rebuild_recopilaciones),
        ("refresh_popularidad", lambda db: refresh_popularidad_pasar(db, 30)),  # primer lote
        ("rebuild_mixes", rebuild_mixes),
    ):
        db = None
        try:
            db = SessionLocal()
            n = fn(db)
            log.info("[inicial] %s → %s", nombre, n)
        except Exception:  # noqa: BLE001
            log.exception("[inicial] %s FALLÓ", nombre)
        finally:
            if db is not None:
                db.close()


# Margen para que una tarea programada que se retrase no se pierda. Ver `_programar`.
MARGEN_RETRASO_SEGUNDOS = 3600


def _programar(s, nombre: str, fn, **disparo) -> None:
    """Añade una tarea con las opciones que APScheduler NO pone por defecto.

    El valor por defecto de APScheduler 3 es `misfire_grace_time=1` segundo: si una tarea
    programada por `cron` se retrasa más de un segundo, la ejecución **se descarta sin avisar** y
    no se recupera hasta el día siguiente. En este servidor retrasarse es lo normal (4 GB de RAM,
    tareas que duran horas, el contenedor reiniciándose con cada despliegue), así que **todo el
    trabajo diario llevaba desde el 7 de septiembre sin hacerse**: mixes, listas del sistema y la
    tabla `similar` a medias. Las tareas de intervalo se salvaban porque su siguiente ejecución se
    recalcula sola; las de `cron` no. Y como cada tarea sólo escribía una línea «ok N» en la
    salida, nada lo decía.

    `max_instances=1` evita además que una tarea larga se solape consigo misma.
    """
    s.add_job(_tarea(nombre, fn), id=nombre, max_instances=1, coalesce=True,
              misfire_grace_time=MARGEN_RETRASO_SEGUNDOS, **disparo)


def main():
    logging.basicConfig(level=logging.INFO)
    s = BlockingScheduler(timezone="Europe/Madrid")
    _programar(s, "sync_catalogo", sync_catalogo, trigger="interval", minutes=30)
    _programar(s, "limpiar_catalogo", limpiar_catalogo, trigger="interval", hours=1)
    # El análisis dura mucho (lee cada MP3) y al final publica las que ya estén completas. Cada
    # media hora se publica lo que haya quedado listo, porque el análisis sólo corre cada 4 h y no
    # tiene sentido que una canción ya completa espere horas a que le toque el turno: son las que
    # rellena el revisor (carátula/metadatos), no el análisis.
    _programar(s, "analysis_audio", analisis_audio, trigger="interval", hours=4)
    _programar(s, "republicar", republicar_completas, trigger="interval", minutes=30)
    _programar(s, "rebuild_similar", rebuild_similar_job, trigger="cron", hour=4)
    _programar(s, "rebuild_mixes", rebuild_mixes, trigger="cron", hour=5)
    _programar(s, "refresh_trends", refresh_trends, trigger="interval", hours=8)
    _programar(s, "rebuild_static_lists", rebuild_static_lists, trigger="cron", hour=6)
    # Los mashups y las sesiones de DJ: la música que el usuario escucha de un tirón. Se
    # recalcula varias veces al día porque el recolector va añadiendo constantemente.
    _programar(s, "rebuild_remixes", rebuild_remixes, trigger="interval", hours=3)
    _programar(s, "rebuild_home_tops", rebuild_home_tops, trigger="cron", hour=6, minute=30)
    _programar(s, "rebuild_cut_tops", rebuild_cut_tops, trigger="cron", hour=6, minute=45)
    _programar(s, "rebuild_recopilaciones", rebuild_recopilaciones, trigger="cron", hour=7, minute=15)
    _programar(s, "refresh_popularidad", lambda db: refresh_popularidad_pasar(db, 40),
               trigger="interval", hours=6)
    # A diario, no semanal: mientras falte música en el disco, la aplicación ofrece canciones que
    # no pueden sonar. Antes era los domingos a las 3:00, y encima esa ejecución se perdía.
    _programar(s, "verificar_ficheros", verificar_ficheros, trigger="cron", hour=3)
    # Intros y colas del catálogo que ya estaba: 40 cada dos horas, en el servidor (aquí está el
    # audio de esas canciones). Las nuevas las mide el PC al bajarlas.
    _programar(s, "revisar_extremos", revisar_extremos_lote_job, trigger="interval", hours=2)
    _programar(s, "prune", prune, trigger="cron", hour=7)

    log.info("Worker RadioPV en marcha (%s tareas programadas)", len(s.get_jobs()))

    # La pasada inicial va en un HILO APARTE: antes se ejecutaba entera (con `rebuild_similar`,
    # 205.600 filas) antes de `s.start()`, así que durante minutos no había planificador y, con
    # el autodespliegue revisando cada 5 minutos, se repetía completa en cada reinicio.
    threading.Thread(target=_pasada_inicial, name="pasada-inicial", daemon=True).start()

    s.start()          # bloquea hasta que se pare el proceso


if __name__ == "__main__":
    main()
