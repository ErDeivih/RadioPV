from datetime import datetime, timedelta
from collections import Counter
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models, schemas
from ..security import get_current_user

router = APIRouter(prefix="/library", tags=["library"])


@router.post("/{track_id}/play")
def record_play(track_id: int, data: schemas.PlayIn,
                db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    p = models.Play(user_id=user.id, track_id=track_id, source=data.source,
                    completed=data.completed, seconds_listened=data.seconds_listened,
                    context=data.context)
    db.add(p)
    db.commit()
    return {"ok": True}


@router.post("/{track_id}/like")
def like(track_id: int, data: schemas.LikeIn, db: Session = Depends(get_db),
         user: models.User = Depends(get_current_user)):
    r = db.query(models.Reaction).filter_by(user_id=user.id, track_id=track_id).first()
    if not r:
        r = models.Reaction(user_id=user.id, track_id=track_id, liked=1 if data.liked else 0,
                            skipped=0, updated_at=datetime.utcnow())
        db.add(r)
    else:
        r.liked = 1 if data.liked else 0
        r.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.post("/{track_id}/skip")
def skip(track_id: int, data: schemas.SkipIn, db: Session = Depends(get_db),
         user: models.User = Depends(get_current_user)):
    r = db.query(models.Reaction).filter_by(user_id=user.id, track_id=track_id).first()
    if not r:
        r = models.Reaction(user_id=user.id, track_id=track_id, liked=0, skipped=1 if data.skipped else 0,
                            updated_at=datetime.utcnow())
        db.add(r)
    else:
        r.skipped = 1 if data.skipped else 0
        r.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.get("/reactions", response_model=schemas.ReactionOut)
def my_reactions(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    liked = [r.track_id for r in db.query(models.Reaction).filter_by(user_id=user.id, liked=1)]
    skipped = [r.track_id for r in db.query(models.Reaction).filter_by(user_id=user.id, skipped=1)]
    return {"liked": liked, "skipped": skipped}


@router.get("/liked", response_model=list[schemas.TrackOut])
def my_liked(explicit: Optional[bool] = None, db: Session = Depends(get_db),
             user: models.User = Depends(get_current_user)):
    """Las canciones a las que diste 'me gusta' (join reactions+tracks en una sola petición)."""
    rows = (db.query(models.Track)
            .join(models.Reaction, models.Reaction.track_id == models.Track.id)
            .filter(models.Reaction.user_id == user.id, models.Reaction.liked == 1)
            .order_by(models.Track.id.desc()).all())
    if explicit is not None:
        rows = [r for r in rows if r.explicit == explicit]
    return rows


@router.get("/history", response_model=list[schemas.TrackOut])
def my_history(limit: int = 50, explicit: Optional[bool] = None, db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)):
    """Historial de reproducción (una vez por canción), de la más reciente a la más antigua."""
    sub = (db.query(models.Play.track_id, models.Play.played_at)
           .filter(models.Play.user_id == user.id)
           .order_by(models.Play.played_at.desc()).limit(limit).subquery())
    rows = (db.query(models.Track).join(sub, sub.c.track_id == models.Track.id)
            .order_by(sub.c.played_at.desc()).all())
    if explicit is not None:
        rows = [r for r in rows if r.explicit == explicit]
    return rows


@router.get("/top")
def my_top(type: str = Query("tracks", pattern="^(tracks|artists)$"),
           period: str = Query("all", pattern="^(week|all)$"), limit: int = Query(20, le=100),
           db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """"On Repeat": lo más escuchado del periodo, sale de plays (no de likes)."""
    since = None
    if period == "week":
        since = datetime.utcnow() - timedelta(days=7)
    q = db.query(models.Play).filter(models.Play.user_id == user.id)
    if since:
        q = q.filter(models.Play.played_at >= since)
    plays = q.all()
    tids = {p.track_id for p in plays}
    if not tids:
        return {"type": type, "items": []}
    tracks = {t.id: t for t in db.query(models.Track).filter(models.Track.id.in_(tids))}
    if type == "artists":
        c = Counter((tracks[p.track_id].artist) for p in plays if p.track_id in tracks)
        return {"type": type, "items": [{"name": a, "count": n} for a, n in c.most_common(limit)]}
    c = Counter((tracks[p.track_id].id) for p in plays if p.track_id in tracks)
    top_ids = [tid for tid, _ in c.most_common(limit)]
    top = {t.id: t for t in db.query(models.Track).filter(models.Track.id.in_(top_ids))}
    return {"type": type, "items": [schemas.TrackOut.model_validate(top[tid]) for tid in top_ids if tid in top]}
