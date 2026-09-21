from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models, schemas
from ..config import MEDIA_ROOT
from ..paths import media_filename
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


def _collage(db: Session, playlist_id: int, cuantas: int = 4) -> list[str]:
    """Hasta 4 carátulas de las primeras canciones de la lista, para el mosaico 2×2.

    POR QUÉ
    -------
    Las listas que genera la aplicación (Top pop, Fiesta, Tech house y guaracha…) no tienen portada
    propia, así que **todas salían con el mismo icono gris de relleno**: en la portada se veían seis
    tarjetas idénticas y parecía que faltaban las imágenes. Spotify resuelve esto con un mosaico de
    las carátulas de sus primeras canciones, y es lo que se compone aquí (la interfaz las pinta en
    cuadrícula).

    Se cogen las que TIENEN carátula y se respeta el orden de la lista: las 4 primeras con imagen
    son las que identifican la lista.
    """
    filas = (
        db.query(models.Track.cover_path)
        .join(models.PlaylistTrack, models.PlaylistTrack.track_id == models.Track.id)
        .filter(models.PlaylistTrack.playlist_id == playlist_id,
                models.Track.cover_path.isnot(None), models.Track.cover_path != "")
        .order_by(models.PlaylistTrack.position)
        .limit(cuantas)
        .all()
    )
    urls: list[str] = []
    for (ruta,) in filas:
        nombre = media_filename(ruta)
        if nombre:
            urls.append(f"/media/covers/{nombre}")
    return urls


def _out(p: models.Playlist, n: int | None = None, db: Session | None = None) -> schemas.PlaylistOut:
    """Serializador unico: antes cada ruta repetia la construccion a mano y era facil que una se
    olvidara un campo (le paso a `user_id`, que dejo el menu de las listas sin opciones)."""
    if n is None:
        n = db.query(models.PlaylistTrack).filter_by(playlist_id=p.id).count()
    # El mosaico sólo hace falta cuando la lista NO tiene portada propia: si la tiene (una lista de
    # usuario con foto), manda la suya.
    collage = [] if p.cover_path else (_collage(db, p.id) if db is not None else [])
    return schemas.PlaylistOut(id=p.id, name=p.name, description=p.description, type=p.type,
                               n_tracks=n, user_id=p.user_id, cover=p.cover,
                               public=bool(p.public), collage=collage)


def _visible_o_404(db: Session, playlist_id: int, user: models.User) -> models.Playlist:
    """Una lista se puede LEER si es tuya, si es del sistema (sin dueno) o si su dueno la ha
    hecho publica. Para editarla hay que ser el dueno (`_own_or_404`)."""
    p = db.query(models.Playlist).filter_by(id=playlist_id).first()
    if not p or (p.user_id is not None and p.user_id != user.id and not p.public):
        raise HTTPException(404, "Playlist no encontrada")
    return p


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
    return _out(_visible_o_404(db, playlist_id, user), db=db)


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
    # Red de seguridad: una lista recién creada NO puede tener canciones. Los ids de las listas se
    # reutilizan (SQLite asigna max+1 y `playlists.id` no es AUTOINCREMENT), así que si una lista
    # borrada dejó filas sueltas con este id, la nueva las heredaría y nacería con canciones que su
    # dueño no ha puesto. Aquí se barren antes de devolverla: si alguien vuelve a dejar basura por
    # otro camino, el daño no llega a la pantalla.
    db.query(models.PlaylistTrack).filter_by(playlist_id=p.id).delete()
    db.commit()
    return _out(p, n=0)


@router.get("/{playlist_id}/tracks", response_model=list[schemas.TrackOut])
def tracks_of(playlist_id: int, db: Session = Depends(get_db),
              user: models.User = Depends(get_current_user),
              explicit: Optional[bool] = Query(None)):
    p = _visible_o_404(db, playlist_id, user)
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
    if data.public is not None:
        p.public = bool(data.public)
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
