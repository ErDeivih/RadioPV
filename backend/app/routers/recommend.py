import random
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models, schemas
from ..security import get_current_user
from ..personalization import _profile, _score, _candidates, seleccionar_diverso, neighbors

router = APIRouter(prefix="/recommend", tags=["recommend"])


@router.get("", response_model=list[schemas.TrackOut])
def recommend(n: int = Query(20, le=100), mood: Optional[str] = None,
              explicit: Optional[bool] = None,
              db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    prof = _profile(user, db)
    cands = _candidates(db, user, mood)
    if explicit is not None:
        cands = [t for t in cands if t.explicit == explicit]
    scored = [(t, _score(t, prof)) for t in cands]
    return seleccionar_diverso(scored, n)


@router.get("/daily", response_model=list[schemas.TrackOut])
def daily(n: int = Query(20, le=100), explicit: Optional[bool] = None, db: Session = Depends(get_db),
          user: models.User = Depends(get_current_user)):
    recs = recommend(n // 2, explicit=explicit, db=db, user=user)
    ids = {t.id for t in recs}
    pool = [t for t in db.query(models.Track).filter(models.Track.status == "descargada").all() if t.id not in ids]
    if explicit is not None:
        pool = [t for t in pool if t.explicit == explicit]
    rest = random.sample(pool, min(len(pool), n - len(recs))) if pool else []
    return (recs + rest)[:n]


@router.get("/trending", response_model=list[schemas.TrackOut])
def trending(n: int = Query(30, le=100), explicit: Optional[bool] = None,
             db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Éxitos/trending: canciones descargadas por popularidad de Deezer (rank)."""
    q = db.query(models.Track).filter(models.Track.status == "descargada")
    if explicit is not None:
        q = q.filter(models.Track.explicit == explicit)
    return q.order_by(models.Track.rank.desc()).limit(n).all()


@router.get("/radio", response_model=list[schemas.TrackOut])
def radio(seed_track: int, n: int = Query(20, le=100), explicit: Optional[bool] = None,
          db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Vecinos por similitud: lee de la tabla `similar` (precomputada), no calcula por petición."""
    ids = [r[0] for r in db.query(models.Similar.track_b)
           .filter(models.Similar.track_a == seed_track)
           .order_by(models.Similar.score.desc()).limit(n)]
    if not ids:
        # fallback: si la tabla está vacía para este seed, calcular al vuelo y guardar
        ids = neighbors(db, seed_track, n)
    if not ids:
        return []
    tracks = db.query(models.Track).filter(models.Track.id.in_(ids),
                                           models.Track.status == "descargada").all()
    byid = {t.id: t for t in tracks}
    if explicit is not None:
        byid = {i: t for i, t in byid.items() if t.explicit == explicit}
    return [byid[i] for i in ids if i in byid]
