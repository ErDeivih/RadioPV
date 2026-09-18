from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models, schemas
from ..config import MEDIA_ROOT
from ..security import get_current_user

router = APIRouter(prefix="/playlists", tags=["playlists"],
                   dependencies=[Depends(get_current_user)])

# Una portada de lista se pinta a 640x640 como mucho, asi que 4 MB sobra. El navegador ademas la
# reduce antes de subirla (ver `recortarCuadrada` en el frontend).
MAX_PORTADA_BYTES = 4 * 1024 * 1024

# Se valida por los PRIMEROS BYTES del fichero, no por lo que diga la peticion: el
# `content-type` lo elige quien sube el fichero, asi que no prueba nada.
_FIRMAS = (
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
)


def _extension(datos: bytes) -> str | None:
    for firma, ext in _FIRMAS:
        if datos.startswith(firma):
            return ext
    if datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        return "webp"
    return None


def _out(p: models.Playlist, n: int | None = None, db: Session | None = None) -> schemas.PlaylistOut:
    """Serializador unico: antes cada ruta repetia la construccion a mano y era facil que una se
    olvidara un campo (le paso a `user_id`, que dejo el menu de las listas sin opciones)."""
    if n is None:
        n = db.query(models.PlaylistTrack).filter_by(playlist_id=p.id).count()
    return schemas.PlaylistOut(id=p.id, name=p.name, description=p.description, type=p.type,
                               n_tracks=n, user_id=p.user_id, cover=p.cover)


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
        out.append(_out(p, db=db))
    return out


@router.get("/{playlist_id}", response_model=schemas.PlaylistOut)
def playlist_by_id(playlist_id: int, db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)):
    p = db.query(models.Playlist).filter_by(id=playlist_id).first()
    if not p or (p.user_id is not None and p.user_id != user.id):
        raise HTTPException(404, "Playlist no encontrada")
    return _out(p, db=db)


@router.get("", response_model=list[schemas.PlaylistOut])
def my_playlists(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return [_out(p, db=db) for p in db.query(models.Playlist)
            .filter(models.Playlist.user_id == user.id)]


@router.post("", response_model=schemas.PlaylistOut)
def create(data: schemas.PlaylistIn, db: Session = Depends(get_db),
           user: models.User = Depends(get_current_user)):
    p = models.Playlist(user_id=user.id, name=data.name, description=data.description, type=data.type)
    db.add(p)
    db.commit()
    db.refresh(p)
    return _out(p, n=0)


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
    _borrar_portada(p)
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
    return _out(p, db=db)


def _borrar_portada(p: models.Playlist) -> None:
    """Borra el fichero de la portada anterior. Si falla, no se interrumpe la peticion: como mucho
    queda un fichero suelto en `media/covers`."""
    if not p.cover_path:
        return
    try:
        from ..paths import resolve_media
        resolve_media("covers", p.cover_path).unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass


@router.put("/{playlist_id}/cover", response_model=schemas.PlaylistOut)
async def set_cover(playlist_id: int, file: UploadFile = File(...),
                    db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)):
    """Sube la portada de la lista (jpg, png o webp). Sustituye a la anterior."""
    p = _own_or_404(db, playlist_id, user)
    datos = await file.read()
    if not datos:
        raise HTTPException(400, "El fichero viene vacío")
    if len(datos) > MAX_PORTADA_BYTES:
        raise HTTPException(413, "La imagen es demasiado grande (máximo 4 MB)")
    ext = _extension(datos)
    if not ext:
        raise HTTPException(415, "Formato no admitido: usa JPG, PNG o WebP")

    destino_dir = MEDIA_ROOT / "covers"
    destino_dir.mkdir(parents=True, exist_ok=True)
    nombre = f"playlist-{p.id}-{uuid4().hex[:10]}.{ext}"
    (destino_dir / nombre).write_bytes(datos)

    _borrar_portada(p)
    p.cover_path = nombre
    p.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(p)
    return _out(p, db=db)


@router.delete("/{playlist_id}/cover", response_model=schemas.PlaylistOut)
def remove_cover(playlist_id: int, db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)):
    p = _own_or_404(db, playlist_id, user)
    _borrar_portada(p)
    p.cover_path = None
    db.commit()
    db.refresh(p)
    return _out(p, db=db)


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
