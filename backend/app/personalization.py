"""Perfil de gustos y puntuación de canciones. Lo usan los endpoints y el worker."""
from collections import Counter
from datetime import datetime, timedelta
import math
from typing import Optional
from . import models


PESOS = {"like": 3.0, "play_completo": 1.0, "play_medio": -1.0,
         "skip_tardio": -2.0, "skip_inmediato": -3.0}
SEMIVIDA_DIAS = 90.0


def peso_recencia(cuando: datetime) -> float:
    """Los gustos recientes pesan más: w = exp(-dias/90)."""
    dias = max(0.0, (datetime.utcnow() - cuando).total_seconds() / 86400)
    return math.exp(-dias / SEMIVIDA_DIAS)


def señales(user_id: int, db) -> dict[int, float]:
    """track_id -> peso acumulado (likes/skips con recencia + plays con seconds_listened)."""
    acc: dict[int, float] = {}
    for r in db.query(models.Reaction).filter_by(user_id=user_id):
        w = peso_recencia(r.updated_at or datetime.utcnow())
        if r.liked:
            acc[r.track_id] = acc.get(r.track_id, 0) + PESOS["like"] * w
        if r.skipped:
            acc[r.track_id] = acc.get(r.track_id, 0) + PESOS["skip_tardio"] * w

    for p in db.query(models.Play).filter_by(user_id=user_id):
        w = peso_recencia(p.played_at or datetime.utcnow())
        seg, dur = (p.seconds_listened or 0), 0
        t = db.get(models.Track, p.track_id)
        dur = (t.duration or 0) if t else 0
        if p.completed or (dur and seg >= dur * 0.9):
            k = "play_completo"
        elif dur and seg < dur * 0.30:
            k = "skip_inmediato" if seg < 15 else "skip_tardio"
        else:
            k = "play_medio"
        acc[p.track_id] = acc.get(p.track_id, 0) + PESOS[k] * w
    return acc


def _profile(user: models.User, db) -> dict:
    """Perfil de gustos a partir de reacciones y plays con peso (recencia + señales implícitas)."""
    pesos = señales(user.id, db)
    positivos = [tid for tid, w in pesos.items() if w > 0]
    tracks = db.query(models.Track).filter(models.Track.id.in_(positivos)).all() if positivos else []
    genres, artists, eras = Counter(), Counter(), Counter()
    bpms, energies = [], []
    for t in tracks:
        if t.genre:
            genres[t.genre] += 1
        if t.artist:
            artists[t.artist] += 1
        if t.era:
            eras[t.era] += 1
        if t.bpm:
            bpms.append(t.bpm)
        if t.energy is not None:
            energies.append(t.energy)
    return {
        "genres": [g for g, _ in genres.most_common(6)],
        "artists": [a for a, _ in artists.most_common(12)],
        "eras": [e for e, _ in eras.most_common(6)],
        "bpm_mean": sum(bpms) / len(bpms) if bpms else None,
        "energy_mean": sum(energies) / len(energies) if energies else None,
        "n_señales": len(pesos),
    }


def _score(t: models.Track, prof: dict) -> float:
    s = 0.0
    if t.genre in prof["genres"]:
        s += 2.5
    if t.era in prof["eras"]:
        s += 1.5
    if t.artist in prof["artists"]:
        s += 1.5
    if prof.get("bpm_mean") and t.bpm:
        s += max(0.0, 1.0 - abs(t.bpm - prof["bpm_mean"]) / 100.0)
    if prof.get("energy_mean") is not None and t.energy is not None:
        s += max(0.0, 1.0 - abs(t.energy - prof["energy_mean"]) / 0.6)
    # prior de popularidad: manda cuando no hay señales, desaparece cuando las hay
    s += peso_frio(prof.get("n_señales", 0)) * 3.0 * min(1.0, (t.rank or 0) / 800_000)
    return s


def peso_frio(n_señales: int) -> float:
    """1.0 sin señales · ~0.5 con 10 · ~0.1 con 50."""
    return 1.0 / (1.0 + n_señales / 10.0)


def seleccionar_diverso(scored, n, k_artista=0.6, k_genero=0.3):
    """Elige n canciones penalizando lo ya elegido (máx. 2 por artista) → el mix no es monótono.
    `scored`: lista de (track, score)."""
    from collections import Counter
    scored = sorted(scored, key=lambda pair: -pair[1])
    vistos_a, vistos_g, salida = Counter(), Counter(), []
    for t, _s in scored:
        if len(salida) >= n:
            break
        if vistos_a[t.artist] >= 2:
            continue
        salida.append(t)
        vistos_a[t.artist] += 1
        vistos_g[t.genre or ""] += 1
    return salida


# ---------- Vecinos por similitud (W-05) ----------
_GENEROS = ["pop", "reggaeton", "latin", "bachata", "rock", "merengue", "salsa",
            "cumbia", "corridos", "flamenco", "dance", "other"]
_ERAS = ["60s", "70s", "80s", "90s", "00s", "10s", "20s"]


def vector(t) -> list[float]:
    """Solo features que existen de verdad. Ampliar cuando T-21 añada valence."""
    return [(t.bpm or 120) / 200.0, (t.energy or 0.5)] + \
           [1.0 if t.genre == g else 0.0 for g in _GENEROS] + \
           [1.0 if (t.era or "") == e else 0.0 for e in _ERAS]


def rebuild_similar(db, top: int = 40) -> int:
    """Reconstruye la tabla `similar`: top-N vecinos por canción (coseno, numpy)."""
    import numpy as np
    tracks = db.query(models.Track).filter(models.Track.status == "descargada").all()
    ids = [t.id for t in tracks]
    if len(ids) < 2:
        return 0
    V = np.array([vector(t) for t in tracks], dtype=np.float32)
    norm = np.linalg.norm(V, axis=1, keepdims=True)
    norm[norm == 0] = 1.0
    cos = (V @ V.T) / (norm @ norm.T)
    # borrar la tabla y rellenar (una transacción)
    db.query(models.Similar).delete()
    n = 0
    for i, tid in enumerate(ids):
        sims = cos[i]
        # excluir la propia fila
        sims = sims.copy()
        sims[i] = -1
        best = np.argsort(sims)[::-1][:top]
        for j in best:
            if sims[j] <= 0:
                continue
            db.add(models.Similar(track_a=tid, track_b=ids[int(j)], score=float(sims[j])))
            n += 1
    db.commit()
    return n


def neighbors(db, seed_id, n: int = 20, top: int = 40) -> list[int]:
    """Fallback de /radio: calcula los vecinos del seed al vuelo (coseno), los guarda en `similar`
    y devuelve sus ids. Así la radio nunca devuelve [] en silencio aunque la tabla esté vacía."""
    import numpy as np
    seed = db.get(models.Track, seed_id)
    if not seed:
        return []
    tracks = db.query(models.Track).filter(models.Track.status == "descargada").all()
    if len(tracks) < 2:
        return []
    ids = [t.id for t in tracks]
    V = np.array([vector(t) for t in tracks], dtype=np.float32)
    norm = np.linalg.norm(V, axis=1, keepdims=True)
    norm[norm == 0] = 1.0
    cos = (V @ V.T) / (norm @ norm.T)
    i = ids.index(seed_id)
    sims = cos[i].copy()
    sims[i] = -1
    best = np.argsort(sims)[::-1][:max(n, top)]
    out: list[int] = []
    for j in best:
        if sims[j] <= 0:
            continue
        jid = ids[int(j)]
        if not db.query(models.Similar).filter_by(track_a=seed_id, track_b=jid).first():
            db.add(models.Similar(track_a=seed_id, track_b=jid, score=float(sims[j])))
        out.append(jid)
        if len(out) >= n:
            break
    db.commit()
    return out


def _candidates(db, user: models.User, mood: Optional[str] = None):
    query = db.query(models.Track).filter(models.Track.status == "descargada")
    if mood:
        query = query.filter(models.Track.tags.ilike(f"%{mood}%"))
    liked = {r.track_id for r in db.query(models.Reaction).filter_by(user_id=user.id, liked=1)}
    skipped = {r.track_id for r in db.query(models.Reaction).filter_by(user_id=user.id, skipped=1)}
    played = {p.track_id for p in db.query(models.Play).filter_by(user_id=user.id)}
    allq = query.all()
    cands = [t for t in allq if t.id not in liked and t.id not in skipped and t.id not in played]
    return cands or allq
