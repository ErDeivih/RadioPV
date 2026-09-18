from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models, schemas
from ..security import get_current_user

router = APIRouter(prefix="/playlists", tags=["playlists"],
                   dependencies=[Depends(get_current_user)])


@router.get("/system", response_model=list[schemas.PlaylistOut])
def system_playlists(db: Session = Depends(get_db)):
    """Listas que la aplicación genera PARA TODOS (Trending, Novedades, Top pop…).

    Se excluyen las que tienen dueño (`user_id` no nulo): son las personales ("Tus más
    escuchadas", "Descubrimientos de la semana"). Sin este filtro aparecían aquí con el nombre de
    otra persona, y al abrirlas daban 404 (la comprobación de propiedad las oculta), o sea una
    fila de listas rotas para todo el mundo.
    """
    out = []
    for p in db.query(models.Playlist).filter(models.Playlist.type == "system",
                                              models.Playlist.user_id.is_(None)):
        n = db.query(models.PlaylistTrack).filter_by(playlist_id=p.id).count()
        out.append(schemas.PlaylistOut(id=p.id, name=p.name, description=p.description,
                                       type=p.type, n_tracks=n, user_id=p.user_id))
    return out


@router.get("/{playlist_id}", response_model=schemas.PlaylistOut)
def playlist_by_id(playlist_id: int, db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)):
    p = db.query(models.Playlist).filter_by(id=playlist_id).first()
    if not p or (p.user_id is not None and p.user_id != user.id):
        raise HTTPException(404, "Playlist no encontrada")
    n = db.query(models.PlaylistTrack).filter_by(playlist_id=p.id).count()
    return schemas.PlaylistOut(id=p.id, name=p.name, description=p.description, type=p.type, n_tracks=n, user_id=p.user_id)


@router.get("", response_model=list[schemas.PlaylistOut])
def my_playlists(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    out = []
    for p in db.query(models.Playlist).filter(models.Playlist.user_id == user.id):
        n = db.query(models.PlaylistTrack).filter_by(playlist_id=p.id).count()
        d = schemas.PlaylistOut(id=p.id, name=p.name, description=p.description, type=p.type, n_tracks=n, user_id=p.user_id)
        out.append(d)
    return out


@router.post("", response_model=schemas.PlaylistOut)
def create(data: schemas.PlaylistIn, db: Session = Depends(get_db),
           user: models.User = Depends(get_current_user)):
    p = models.Playlist(user_id=user.id, name=data.name, description=data.description, type=data.type)
    db.add(p)
    db.commit()
    db.refresh(p)
    return schemas.PlaylistOut(id=p.id, name=p.name, description=p.description, type=p.type, n_tracks=0, user_id=p.user_id)


@router.get("/{playlist_id}/tracks", response_model=list[schemas.TrackOut])
def tracks_of(playlist_id: int, db: Session = Depends(get_db),
              user: models.User = Depends(get_current_user),
              explicit: Optional[bool] = Query(None)):
    p = db.query(models.Playlist).filter_by(id=playlist_id).first()
    if not p or (p.user_id is not None and p.user_id != user.id):
        raise HTTPException(404, "Playlist no encontrada")
    rows = (db.query(models.Track).join(models.PlaylistTrack, models.PlaylistTrack.track_id == models.Track.id)
            .filter(models.PlaylistTrack.playlist_id == playlist_id)
            .order_by(models.PlaylistTrack.position).all())
    if explicit is not None:
        rows = [r for r in rows if r.explicit == explicit]
    return rows


@router.post("/{playlist_id}/tracks/{track_id}")
def add_track(playlist_id: int, track_id: int, db: Session = Depends(get_db),
              user: models.User = Depends(get_current_user)):
    p = db.query(models.Playlist).filter_by(id=playlist_id, user_id=user.id).first()
    if not p:
        raise HTTPException(404, "Playlist no encontrada")
    exists = db.query(models.PlaylistTrack).filter_by(playlist_id=playlist_id, track_id=track_id).first()
    if exists:
        return {"ok": True}
    pos = db.query(models.PlaylistTrack).filter_by(playlist_id=playlist_id).count() + 1
    db.add(models.PlaylistTrack(playlist_id=playlist_id, track_id=track_id, position=pos))
    p.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


def _own_or_404(db, playlist_id, user):
    p = db.query(models.Playlist).filter_by(id=playlist_id, user_id=user.id).first()
    if not p:
        raise HTTPException(404, "Playlist no encontrada")
    return p


@router.delete("/{playlist_id}")
def delete_playlist(playlist_id: int, db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)):
    p = _own_or_404(db, playlist_id, user)
    db.query(models.PlaylistTrack).filter_by(playlist_id=playlist_id).delete()
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.delete("/{playlist_id}/tracks/{track_id}")
def remove_track(playlist_id: int, track_id: int, db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)):
    _own_or_404(db, playlist_id, user)
    db.query(models.PlaylistTrack).filter_by(playlist_id=playlist_id, track_id=track_id).delete()
    # recompactar position
    rows = db.query(models.PlaylistTrack).filter_by(playlist_id=playlist_id).order_by(
        models.PlaylistTrack.position).all()
    for i, r in enumerate(rows, 1):
        r.position = i
    db.commit()
    return {"ok": True}


@router.patch("/{playlist_id}", response_model=schemas.PlaylistOut)
def update_playlist(playlist_id: int, data: schemas.PlaylistPatch, db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)):
    p = _own_or_404(db, playlist_id, user)
    if data.name is not None:
        p.name = data.name
    if data.description is not None:
        p.description = data.description
    p.updated_at = datetime.utcnow()
    db.commit()
    n = db.query(models.PlaylistTrack).filter_by(playlist_id=playlist_id).count()
    return schemas.PlaylistOut(id=p.id, name=p.name, description=p.description, type=p.type, n_tracks=n, user_id=p.user_id)


@router.put("/{playlist_id}/order")
def reorder_playlist(playlist_id: int, order: list[int], db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)):
    """Cuerpo: [track_id, ...] en el nuevo orden. Reescribe `position`."""
    _own_or_404(db, playlist_id, user)
    for i, tid in enumerate(order, 1):
        r = db.query(models.PlaylistTrack).filter_by(playlist_id=playlist_id, track_id=tid).first()
        if r:
            r.position = i
    db.commit()
    return {"ok": True}
