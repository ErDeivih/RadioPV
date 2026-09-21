"""R1+R3+R4 · el mix diario personaliza, es estable por día y tiene buen arranque en frío."""
import json

from app.database import SessionLocal
from app import models
from app.workers import rebuild_mixes

SRC = "test_mix"           # fuente propia para poder limpiar estos tracks
EMPRESAS = {"mixA@t.com", "mixB@t.com", "estable@t.com", "frio@t.com", "senal@t.com"}


def _limpia(db):
    """Elimina lo que sembró este módulo para no contaminar el resto del suite (BD compartida)."""
    uids = [u.id for u in db.query(models.User).filter(models.User.email.in_(EMPRESAS))]
    db.query(models.Play).filter(models.Play.user_id.in_(uids)).delete()
    db.query(models.Reaction).filter(models.Reaction.user_id.in_(uids)).delete()
    db.query(models.Track).filter(models.Track.source == SRC).delete()
    db.query(models.Mix).filter(models.Mix.user_id.in_(uids)).delete()
    db.query(models.User).filter(models.User.email.in_(EMPRESAS)).delete()
    db.commit()


def _seed_tracks(db, generos_artistas: dict):
    """Crea 2 tracks por artista. Devuelve {artist: [id, id]}."""
    ids = {}
    n = 0
    for genre, artists in generos_artistas.items():
        for artist in artists:
            ids[artist] = []
            for j in range(2):
                n += 1
                t = models.Track(title=f"{artist}-{j}", artist=artist, genre=genre,
                                 era="2020s", rank=1000 - n, duration=200,
                                 status="descargada", source=SRC, file_path="E:/x.mp3")
                db.add(t)
                db.flush()          # asigna t.id antes de guardarlo
                ids[artist].append(t.id)
    db.commit()
    return ids


def test_rebuild_mixes_personaliza_dos_usuarios(client):
    """A con likes de flamenco, B con likes de reggaeton → intersección de mixes < 30 %."""
    db = SessionLocal()
    gen = {"flamenco": [f"RoF{i}" for i in range(12)],
           "reggaeton": [f"RG{i}" for i in range(12)]}
    ids = _seed_tracks(db, gen)   # {artist: [id,id]}
    db.commit()

    ua = models.User(email="mixA@t.com", hashed_password="x")
    ub = models.User(email="mixB@t.com", hashed_password="x")
    db.add_all([ua, ub])
    db.commit()
    db.refresh(ua); db.refresh(ub)

    def like(user_id, track_ids):
        for tid in track_ids:
            db.add(models.Reaction(user_id=user_id, track_id=tid, liked=1, skipped=0))

    # A -> 10 likes de flamenco ; B -> 10 likes de reggaeton (warm: >=10 señales)
    for genre, artists in gen.items():
        for artist in artists:
            if genre == "flamenco":
                like(ua.id, ids[artist])
            else:
                like(ub.id, ids[artist])
    db.commit()

    rebuild_mixes(db)

    mixa = db.query(models.Mix).filter_by(user_id=ua.id, kind="daily_1").first()
    mixb = db.query(models.Mix).filter_by(user_id=ub.id, kind="daily_1").first()
    assert mixa and mixb, "ambos usuarios deben tener mix"
    a = set(json.loads(mixa.tracks_json))
    b = set(json.loads(mixb.tracks_json))
    def genres(ids):
        return [t.genre for t in db.query(models.Track).filter(models.Track.id.in_(ids))]
    ga = genres(a); gb = genres(b)
    fa = sum(1 for x in ga if x == "flamenco"); ra = sum(1 for x in ga if x == "reggaeton")
    fb = sum(1 for x in gb if x == "flamenco"); rb = sum(1 for x in gb if x == "reggaeton")
    # A (liked flamenco) domina flamenco; B (liked reggaeton) domina reggaeton → personalización
    assert fa > ra, f"A no domina flamenco ({ga})"
    assert rb > fb, f"B no domina reggaeton ({gb})"
    # además, la intersección del catálogo sembrado es pequeña (< 30%)
    inter = len(a & b) / max(len(a), 1)
    assert inter < 0.30, f"intersección {inter:.0%} demasiado alta (A: {len(a)}, B: {len(b)})"
    _limpia(db)
    db.close()


def test_mix_estable_mismo_dia(client):
    """R3 · dos ejecuciones del mismo día dan el mismo mix (semilla user_id-fecha)."""
    db = SessionLocal()
    gen = {"pop": ["P1", "P2"], "rock": ["R1", "R2"], "rap": ["H1", "H2"], "latin": ["L1", "L2"]}
    _seed_tracks(db, gen)
    u = models.User(email="estable@t.com", hashed_password="x")
    db.add(u); db.commit(); db.refresh(u)
    rebuild_mixes(db)
    m1 = db.query(models.Mix).filter_by(user_id=u.id, kind="daily_1").first().tracks_json
    rebuild_mixes(db)
    m2 = db.query(models.Mix).filter_by(user_id=u.id, kind="daily_1").first().tracks_json
    assert m1 == m2, "el mix del día debe ser estable"
    _limpia(db)
    db.close()


def test_mix_frio_diverso_y_por_artista():
    """R4 · _mix_frio (sin BD): ≥4 géneros, ≥3 eras, máx. 2 por artista."""
    import random
    from collections import Counter
    from app.workers import _mix_frio
    class T:
        pass
    def mk(i):
        o = T(); o.id = i; o.artist = f"Art{i}"
        o.genre = ("pop", "rock", "rap", "latin")[i % 4]
        o.era = ("2000s", "2010s", "2020s")[i % 3]
        o.rank = 1000 - i
        return o
    tracks = [mk(i) for i in range(12)]
    semilla = random.Random("1-2026-08-30")
    ids = _mix_frio(semilla, [(tr, 0) for tr in tracks])
    sel = [tr for tr in tracks if tr.id in ids]
    generos = {tr.genre for tr in sel}
    eras = {tr.era for tr in sel}
    por_art = Counter(tr.artist for tr in sel)
    assert len(generos) >= 4, f"faltan géneros: {generos}"
    assert len(eras) >= 3, f"faltan eras: {eras}"
    assert max(por_art.values()) <= 2, f"algún artista >2: {por_art}"


def test_r5_explicacion_y_kinds(client):
    """R2+R5 · un usuario con señales recibe los kinds con `explicacion`."""
    db = SessionLocal()
    for i in range(30):
        db.add(models.Track(title=f"X{i}", artist=f"XA{i % 6}", genre=("flamenco", "pop")[i % 2],
                            era=("2020s", "1990s")[i % 2], year=2000 + i, rank=1000 - i,
                            status="descargada", source=SRC, file_path="E:/x.mp3"))
    db.commit()
    u = models.User(email="senal@t.com", hashed_password="x")
    db.add(u); db.commit(); db.refresh(u)
    ids_src = [r[0] for r in db.query(models.Track.id).filter_by(source=SRC).order_by(models.Track.id.asc()).all()]
    for i in range(12):     # >=10 señales (warm)
        db.add(models.Reaction(user_id=u.id, track_id=ids_src[i % len(ids_src)], liked=1, skipped=0))
    # plays para on_repeat
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    for tid in ids_src[:3]:
        db.add(models.Play(user_id=u.id, track_id=tid, played_at=now))
    db.commit()

    rebuild_mixes(db)
    mixes = db.query(models.Mix).filter_by(user_id=u.id).all()
    kinds = {m.kind for m in mixes}
    assert len(kinds) >= 6, f"solo {len(kinds)} kinds: {kinds}"
    assert all(m.explicacion for m in mixes), "todas deben tener explicacion"
    _limpia(db)
    db.close()


def test_get_mixes_endpoint(client):
    """U2 · GET /mixes devuelve los mixes del usuario con explicacion, portada y recuento."""
    from app.database import SessionLocal
    db = SessionLocal()
    r = client.post("/auth/register", json={"email": "mixapi@t.com", "password": "clave-larga-1"})
    assert r.status_code == 200, r.text
    tok = r.json()["access_token"]
    for i in range(12):
        db.add(models.Track(title=f"M{i}", artist=f"MA{i % 4}", genre=("pop", "rock", "flamenco", "latin")[i % 4],
                            era="2020s", year=2000 + i, rank=1000 - i, status="descargada",
                            source=SRC, file_path="E:/x.mp3",
                            # carátula local: es la única que la interfaz puede pedir a la API
                            cover_path=f"E:/media/covers/mix{i}.jpg"))
    db.commit()
    rebuild_mixes(db)
    h = {"Authorization": f"Bearer {tok}"}
    ms = client.get("/mixes", headers=h).json()
    assert ms and "kind" in ms[0], ms
    assert all(m["explicacion"] for m in ms), "todos deben tener explicacion"
    # La tarjeta de «Hecho para ti» necesita las tres cosas: con qué URI suena, cuántas canciones
    # tiene y las carátulas del mosaico. Antes sólo llegaban `kind` y `explicacion`, así que la
    # tarjeta era un cuadro de texto gris sin imagen y sin forma de reproducir nada.
    for m in ms:
        assert m["uri"] == f"radiopv:mix:{m['kind']}", m
        assert m["n_tracks"] > 0, m
        assert len(m["collage"]) == 4, m
        assert all(c.startswith("/media/covers/") for c in m["collage"]), m
    # limpieza
    u = db.query(models.User).filter_by(email="mixapi@t.com").first()
    if u:
        db.query(models.Play).filter_by(user_id=u.id).delete()
        db.query(models.Reaction).filter_by(user_id=u.id).delete()
        db.query(models.Mix).filter_by(user_id=u.id).delete()
        db.query(models.User).filter_by(id=u.id).delete()
    db.query(models.Track).filter(models.Track.source == SRC).delete()
    db.commit(); db.close()


def test_tracks_de_un_mix_en_su_orden(client):
    """Las canciones de un mix se sirven EN EL ORDEN del mix, y un `kind` inventado da 404.

    Esto es lo que hace que «Hecho para ti» suene de verdad: la tarjeta apuntaba a `/search`, que no
    busca nada, y no existía ninguna ruta que convirtiera los ids guardados en canciones."""
    from app.database import SessionLocal
    db = SessionLocal()
    r = client.post("/auth/register", json={"email": "mixapi@t.com", "password": "clave-larga-1"})
    assert r.status_code == 200, r.text
    tok = r.json()["access_token"]
    ids = []
    for i in range(12):
        t = models.Track(title=f"M{i}", artist=f"MA{i % 4}", genre=("pop", "rock", "flamenco", "latin")[i % 4],
                         era="2020s", year=2000 + i, rank=1000 - i, status="descargada",
                         source=SRC, file_path="E:/x.mp3", duration=200)
        db.add(t); db.flush(); ids.append(t.id)
    db.commit()
    u = db.query(models.User).filter_by(email="mixapi@t.com").first()
    # Un mix con orden deliberadamente AL REVÉS del que devolvería cualquier consulta por id.
    db.add(models.Mix(user_id=u.id, kind="radar", tracks_json=json.dumps(list(reversed(ids))),
                      explicacion="porque sí"))
    db.commit()
    h = {"Authorization": f"Bearer {tok}"}
    r = client.get("/mixes/radar/tracks", headers=h)
    assert r.status_code == 200, r.text
    assert [t["id"] for t in r.json()] == list(reversed(ids)), r.text
    assert client.get("/mixes/no-existe/tracks", headers=h).status_code == 404
    # Un tipo que no existe NO puede además crear mixes: eso fue lo que llenó la portada de
    # tarjetas repetidas (una consulta de prueba con un tipo inventado añadió otra tanda entera).
    assert db.query(models.Mix).filter_by(user_id=u.id).count() == 1
    # limpieza
    db.query(models.Play).filter_by(user_id=u.id).delete()
    db.query(models.Reaction).filter_by(user_id=u.id).delete()
    db.query(models.Mix).filter_by(user_id=u.id).delete()
    db.query(models.User).filter_by(id=u.id).delete()
    db.query(models.Track).filter(models.Track.source == SRC).delete()
    db.commit(); db.close()


def test_regenerar_los_mixes_no_deja_dos_tandas(client):
    """Regenerar los mixes del mismo usuario deja UN mix por tipo, y `/mixes` tampoco repite.

    La fila «Hecho para ti» llegó a pintar **diez** tarjetas en vez de cinco (cada mix dos veces)
    porque cada regeneración añadía otra tanda a la base y la API las devolvía todas."""
    from app.database import SessionLocal
    from app.workers import _generar_mixes_usuario

    db = SessionLocal()
    r = client.post("/auth/register", json={"email": "mixdup@t.com", "password": "clave-larga-1"})
    assert r.status_code == 200, r.text
    tok = r.json()["access_token"]
    for i in range(12):
        db.add(models.Track(title=f"D{i}", artist=f"DA{i % 4}", genre=("pop", "rock", "flamenco", "latin")[i % 4],
                            era="2020s", year=2000 + i, rank=1000 - i, status="descargada",
                            source=SRC, file_path="E:/x.mp3", duration=200))
    db.commit()
    u = db.query(models.User).filter_by(email="mixdup@t.com").first()

    _generar_mixes_usuario(db, u)
    _generar_mixes_usuario(db, u)                 # segunda pasada: la que duplicaba

    kinds = [m.kind for m in db.query(models.Mix).filter_by(user_id=u.id).all()]
    assert len(kinds) == len(set(kinds)), f"hay mixes repetidos: {sorted(kinds)}"

    h = {"Authorization": f"Bearer {tok}"}
    ms = client.get("/mixes", headers=h).json()
    assert len(ms) == len({m["kind"] for m in ms}), [m["kind"] for m in ms]

    # limpieza
    db.query(models.Play).filter_by(user_id=u.id).delete()
    db.query(models.Reaction).filter_by(user_id=u.id).delete()
    db.query(models.Mix).filter_by(user_id=u.id).delete()
    db.query(models.User).filter_by(id=u.id).delete()
    db.query(models.Track).filter(models.Track.source == SRC).delete()
    db.commit(); db.close()
