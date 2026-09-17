from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models, schemas

router = APIRouter(prefix="/artists", tags=["artists"])


@router.get("", response_model=list[schemas.ArtistOut])
def list_artists(q: str = Query(None), limit: int = Query(200, le=1000), offset: int = 0,
                 db: Session = Depends(get_db)):
    # NO recalcular aquí: lo hace maintenance.recount_artist_tracks() desde la migración/worker.
    query = db.query(models.Artist)
    if q:
        like = f"%{q}%"
        query = query.filter(models.Artist.name.ilike(like))
    return query.order_by(models.Artist.track_count.desc()).offset(offset).limit(limit).all()


@router.get("/{name}", response_model=schemas.ArtistOut)
def artist_by_name(name: str, db: Session = Depends(get_db)):
    a = db.query(models.Artist).filter(models.Artist.name == name).first()
    if not a:
        raise HTTPException(404, "Artista no encontrado")
    return a


@router.get("/{name}/top", response_model=list[schemas.TrackOut])
def artist_top(name: str, limit: int = Query(50, le=200), explicit: Optional[bool] = None,
               db: Session = Depends(get_db)):
    q = (db.query(models.Track)
         .filter(models.Track.artist == name, models.Track.status == "descargada"))
    if explicit is not None:
        q = q.filter(models.Track.explicit == explicit)
    return q.order_by(models.Track.rank.desc()).limit(limit).all()


@router.get("/{name}/albums", response_model=list[schemas.AlbumOut])
def artist_albums(name: str, db: Session = Depends(get_db)):
    return (db.query(models.ArtistAlbum).filter(models.ArtistAlbum.artist_name == name)
            .order_by(models.ArtistAlbum.year.desc()).all())
