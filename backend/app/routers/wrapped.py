from collections import Counter
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models, schemas
from ..security import get_current_user

router = APIRouter(tags=["wrapped"])


@router.get("/wrapped")
def wrapped(period: str = Query("week", pattern="^(week|year)$"), db: Session = Depends(get_db),
            user: models.User = Depends(get_current_user)):
    """Resumen de escucha del periodo (top artistas/géneros, minutos, redescubrimientos)."""
    since = datetime.utcnow() - (timedelta(days=7) if period == "week" else timedelta(days=365))
    plays = (db.query(models.Play).filter(models.Play.user_id == user.id,
                                          models.Play.played_at >= since).all())
    tids = {p.track_id for p in plays}
    tracks = {t.id: t for t in db.query(models.Track).filter(models.Track.id.in_(tids))} if tids else {}
    artists = Counter()
    genres = Counter()
    minutos = 0.0
    for p in plays:
        t = tracks.get(p.track_id)
        if not t:
            continue
        if t.artist:
            artists[t.artist] += 1
        if t.genre:
            genres[t.genre] += 1
        minutos += (p.seconds_listened or (t.duration or 0)) / 60.0
    top_tracks = [{"id": t.id, "title": t.title, "artist": t.artist, "plays": n}
                  for t, n in Counter(
                      (tracks[p.track_id], 1) for p in plays if p.track_id in tracks
                  ).items()]
    top_tracks = sorted(top_tracks, key=lambda x: -x["plays"])[:10]
    return {
        "period": period,
        "top_artists": [{"name": a, "count": c} for a, c in artists.most_common(10)],
        "top_genres": [{"name": g, "count": c} for g, c in genres.most_common(10)],
        "minutes": round(minutos, 1),
        "top_tracks": top_tracks,
    }


@router.post("/requests")
def create_request(data: dict, db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)):
    """Encola una canción pedida desde la app ("estado vacío" de una búsqueda)."""
    text = (data.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text es obligatorio")
    db.add(models.Request(user_id=user.id, text=text, status="pendiente"))
    db.commit()
    return {"ok": True, "text": text}


@router.get("/mixes", response_model=list[schemas.MixOut])
def my_mixes(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """U2 · los mixes del usuario (kind, explicacion, tracks_json) para la fila "Hecho para ti".
    Si el usuario aún no tiene mezclas (recién registrado), se generan en frío al momento."""
    mix = (db.query(models.Mix).filter_by(user_id=user.id)
           .order_by(models.Mix.created_at.desc()).all())
    if not mix:
        from ..workers import _generar_mixes_usuario
        _generar_mixes_usuario(db, user)
        mix = (db.query(models.Mix).filter_by(user_id=user.id)
               .order_by(models.Mix.created_at.desc()).all())
    return mix
