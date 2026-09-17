from enum import Enum
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import or_, func
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models, schemas

router = APIRouter(prefix="/tracks", tags=["tracks"])


class Energia(str, Enum):
    baja = "Baja"
    media = "Media"
    alta = "Alta"


@router.get("", response_model=list[schemas.TrackOut])
def list_tracks(
        response: Response,
        q: Optional[str] = None, genre: Optional[str] = None, language: Optional[str] = None,
        year: Optional[int] = None, era: Optional[str] = None, mood: Optional[str] = None,
        energy: Optional[Energia] = None, remix: Optional[bool] = None,
        explicit: Optional[bool] = None, artist: Optional[str] = None,
        album: Optional[str] = None,
        sort: str = Query("recientes", pattern="^(recientes|rank|year|aleatorio)$"),
        limit: int = Query(50, le=500), offset: int = 0,
        db: Session = Depends(get_db)):
    query = db.query(models.Track).filter(models.Track.status == "descargada")
    if q:
        like = f"%{q}%"
        query = query.filter(or_(models.Track.title.ilike(like), models.Track.artist.ilike(like),
                                 models.Track.album.ilike(like)))
    if genre:
        query = query.filter(models.Track.genre == genre)
    if language:
        query = query.filter(models.Track.language == language)
    if year:
        query = query.filter(models.Track.year == year)
    if era:
        query = query.filter(models.Track.era == era)
    if mood:
        query = query.filter(models.Track.tags.ilike(f"%{mood}%"))
    if remix is not None:
        query = query.filter(models.Track.is_remix.is_(True)) if remix else query.filter(models.Track.is_remix.is_(False))
    if explicit is not None:
        query = query.filter(models.Track.explicit.is_(explicit))
    if artist:
        query = query.filter(models.Track.artist == artist)
    if album:
        query = query.filter(models.Track.album == album)
    if energy:
        lo, hi = {"Baja": (0, 0.3), "Media": (0.3, 0.55), "Alta": (0.55, 1.01)}[energy.value]
        query = query.filter(models.Track.energy >= lo, models.Track.energy < hi)

    total = query.count()                                            # sin paginar
    if sort == "rank":
        query = query.order_by(models.Track.rank.desc())
    elif sort == "year":
        query = query.order_by(models.Track.year.desc())
    elif sort == "aleatorio":
        query = query.order_by(func.random())
    else:
        query = query.order_by(models.Track.id.desc())
    response.headers["X-Total-Count"] = str(total)
    return query.offset(offset).limit(limit).all()


@router.get("/{track_id}", response_model=schemas.TrackOut)
def get_track(track_id: int, db: Session = Depends(get_db)):
    t = db.query(models.Track).filter(models.Track.id == track_id,
                                      models.Track.status == "descargada").first()
    if not t:
        raise HTTPException(404, "Canción no encontrada")
    return t


@router.post("/{track_id}/report")
def report_track(track_id: int, db: Session = Depends(get_db)):
    """'Esta canción está mal': se marca para revisar (el worker la re-verificará)."""
    t = db.query(models.Track).filter(models.Track.id == track_id).first()
    if not t:
        raise HTTPException(404, "Canción no encontrada")
    t.status = "revisar"
    db.commit()
    return {"ok": True, "status": t.status}
