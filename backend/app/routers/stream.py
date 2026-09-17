from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models
from ..paths import resolve_music
from ..security import verify_stream_token

router = APIRouter(tags=["stream"])


def servir_audio(tr: models.Track) -> FileResponse:
    """Resuelve el fichero y devuelve el FileResponse (con soporte Range de starlette).
    Lanza 404 si la canción no tiene fichero y 410 si el fichero ya no está en disco."""
    try:
        ruta = resolve_music(tr.file_path)
    except (FileNotFoundError, PermissionError):
        raise HTTPException(404, "Canción sin fichero asociado")
    if not ruta.exists():
        raise HTTPException(410, "El fichero ya no está en disco")
    return FileResponse(ruta, media_type="audio/mpeg",
                        headers={"Cache-Control": "private, max-age=3600",
                                 "Accept-Ranges": "bytes"})


@router.get("/stream/{track_id}")
def stream(track_id: int, t: str = Query(..., description="token de /auth/stream-token"),
           db: Session = Depends(get_db)):
    verify_stream_token(t)                                  # 401 si no vale
    tr = db.get(models.Track, track_id)
    if not tr or tr.status != "descargada":
        raise HTTPException(404, "Canción no disponible")
    return servir_audio(tr)
