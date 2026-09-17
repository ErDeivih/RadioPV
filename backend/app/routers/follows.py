from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models
from ..security import get_current_user

router = APIRouter(prefix="/follows", tags=["follows"])


@router.post("/{name}")
def follow(name: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Sigue un artista. Idempotente."""
    exists = db.query(models.Follow).filter_by(user_id=user.id, artist_name=name).first()
    if not exists:
        db.add(models.Follow(user_id=user.id, artist_name=name))
        db.commit()
    return {"ok": True}


@router.delete("/{name}")
def unfollow(name: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Deja de seguir un artista. Idempotente."""
    db.query(models.Follow).filter_by(user_id=user.id, artist_name=name).delete()
    db.commit()
    return {"ok": True}


@router.get("", response_model=list[str])
def following(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Lista de artistas que sigues."""
    return [r.artist_name for r in db.query(models.Follow).filter_by(user_id=user.id).all()]
