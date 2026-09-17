"""Administración de la biblioteca de RadioPV.

Expone por HTTP la gestión que ya existía en el recolector (`radiov/blacklist.py`) para
poder hacerlo **todo desde la web de RadioPV**: borrado masivo de canciones, listas
negras de canciones y artistas, purga de lo vetado y el interruptor de ingesta.

Todos los endpoints exigen un usuario con `is_admin = True`.

La biblioteca vive en `radiov.db` (SQLite, gestionada por el paquete `radiov`), que es
una base distinta de la que usa el resto de la API. Por eso este router habla con
`radiov.db` mediante las funciones del propio paquete, y no por SQLAlchemy.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..security import get_current_user

router = APIRouter(prefix="/admin", tags=["admin"])


# --------------------------------------------------------------------------- utils
def _radiov():
    """Importa el recolector. Lanza 503 explicativo si no está disponible."""
    try:
        from radiov import blacklist as rbl          # noqa: PLC0415
        from radiov import config as rconfig         # noqa: PLC0415
        from radiov import db as rdb                 # noqa: PLC0415
        from radiov import ingest_control as ric     # noqa: PLC0415
        from radiov import models as rmodels         # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"El recolector (radiov) no está disponible en la imagen: {exc}",
        )
    return rdb, rbl, rconfig, ric, rmodels


def require_admin(user: models.User = Depends(get_current_user)) -> models.User:
    """Dependencia: solo administradores."""
    if not getattr(user, "is_admin", False):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Se requieren permisos de administrador")
    return user


def _rows(sql: str, params: tuple = ()) -> list[dict]:
    rdb, *_ = _radiov()
    conn = rdb.get_conn()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _one(sql: str, params: tuple = ()) -> Optional[dict]:
    filas = _rows(sql, params)
    return filas[0] if filas else None


# --------------------------------------------------------------------------- modelos
class DeleteRequest(BaseModel):
    ids: list[int] = Field(..., min_length=1, description="IDs de las pistas a borrar")
    veto: bool = Field(True, description="Añadirlas también a la lista negra (no se volverán a descargar)")


class IdsRequest(BaseModel):
    ids: list[int] = Field(..., min_length=1)


class BlacklistRequest(BaseModel):
    kind: Literal["artist", "song"]
    value: str = Field(..., min_length=1, description="Artista, o 'titulo|artista' para canciones")
    reason: str = ""


class ArtistVetoRequest(BaseModel):
    name: str = Field(..., min_length=1)
    delete_tracks: bool = Field(True, description="Borrar además sus canciones de la biblioteca")


class IngestRequest(BaseModel):
    enabled: bool


# --------------------------------------------------------------------------- estado
@router.get("/status", summary="Resumen del catálogo y del sistema")
def admin_status(_: models.User = Depends(require_admin)) -> dict:
    rdb, _, rconfig, ric, rmodels = _radiov()

    total = _one("SELECT COUNT(*) n FROM tracks") or {"n": 0}
    por_estado = _rows("SELECT status, COUNT(*) n FROM tracks GROUP BY status ORDER BY n DESC")
    tamano = _one("SELECT SUM(file_size) bytes FROM tracks") or {"bytes": 0}
    vetados = _one("SELECT COUNT(*) n FROM blacklist WHERE active=1") or {"n": 0}

    # Espacio en disco de la carpeta de música (best-effort).
    disco = None
    try:
        import shutil
        uso = shutil.disk_usage(str(rconfig.BASE_MUSIC))
        disco = {"total_gb": round(uso.total / 1024**3, 1),
                 "libre_gb": round(uso.free / 1024**3, 1),
                 "usado_pct": round(uso.used / uso.total * 100, 1)}
    except OSError:
        pass

    return {
        "tracks_total": total["n"],
        "tracks_por_estado": por_estado,
        "biblioteca_gb": round((tamano["bytes"] or 0) / 1024**3, 2),
        "vetados": vetados["n"],
        "disco": disco,
        "rutas": {
            "base_music": str(rconfig.BASE_MUSIC),
            "catalog_dir": str(rconfig.CATALOG_DIR),
            "download_dir": str(rconfig.RAW_DIR),
        },
        "ingesta": ric.status(),
    }


@router.get("/events", summary="Últimos eventos del recolector")
def admin_events(limit: int = Query(100, ge=1, le=1000),
                 _: models.User = Depends(require_admin)) -> list[dict]:
    return _rows("SELECT id, ts, level, message FROM events ORDER BY id DESC LIMIT ?", (limit,))


# --------------------------------------------------------------------------- listado
@router.get("/tracks", summary="Listado paginado y filtrable para la tabla de gestión")
def admin_tracks(
    q: Optional[str] = Query(None, description="Busca en título, artista o álbum"),
    artist: Optional[str] = None,
    album: Optional[str] = None,
    genre: Optional[str] = None,
    language: Optional[str] = None,
    status_: Optional[str] = Query(None, alias="status"),
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    sort: Literal["artist", "title", "album", "year", "genre", "language", "added_at", "file_size"] = "artist",
    order: Literal["asc", "desc"] = "asc",
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: models.User = Depends(require_admin),
) -> dict:
    donde: list[str] = []
    args: list = []

    if q:
        donde.append("(title LIKE ? OR artist LIKE ? OR album LIKE ?)")
        like = f"%{q}%"
        args += [like, like, like]
    if artist:
        donde.append("artist = ?"); args.append(artist)
    if album:
        donde.append("album = ?"); args.append(album)
    if genre:
        donde.append("genre = ?"); args.append(genre)
    if language:
        donde.append("language = ?"); args.append(language)
    if status_:
        donde.append("status = ?"); args.append(status_)
    if year_min is not None:
        donde.append("year >= ?"); args.append(year_min)
    if year_max is not None:
        donde.append("year <= ?"); args.append(year_max)

    clausula = ("WHERE " + " AND ".join(donde)) if donde else ""
    # `sort` y `order` están restringidos por Literal: no hay inyección posible.
    total = _one(f"SELECT COUNT(*) n FROM tracks {clausula}", tuple(args)) or {"n": 0}
    filas = _rows(
        f"""SELECT id, title, artist, album, year, genre, language, bpm, energy,
                   duration, file_size, status, source, added_at, file_path
            FROM tracks {clausula}
            ORDER BY {sort} {order.upper()}, title ASC
            LIMIT ? OFFSET ?""",
        tuple(args) + (limit, offset),
    )
    return {"total": total["n"], "limit": limit, "offset": offset, "items": filas}


@router.get("/facets", summary="Valores disponibles para los filtros, con recuento")
def admin_facets(_: models.User = Depends(require_admin)) -> dict:
    def facet(col: str, minimo: int = 1) -> list[dict]:
        return _rows(
            f"""SELECT {col} AS valor, COUNT(*) AS n FROM tracks
                WHERE {col} IS NOT NULL AND {col} <> ''
                GROUP BY {col} HAVING n >= ? ORDER BY n DESC""",
            (minimo,),
        )

    return {
        "languages": facet("language"),
        "genres": facet("genre"),
        "artists": facet("artist", 2),     # artistas con al menos 2 pistas
        "years": _rows("SELECT year AS valor, COUNT(*) n FROM tracks "
                       "WHERE year IS NOT NULL GROUP BY year ORDER BY year"),
        "status": facet("status"),
        "sources": facet("source"),
    }


# --------------------------------------------------------------------------- borrado
@router.post("/tracks/delete", summary="Borrado masivo de canciones (ficheros + BD)")
def admin_delete_tracks(payload: DeleteRequest,
                        admin: models.User = Depends(require_admin)) -> dict:
    """Borra las pistas indicadas del disco y de la base de datos.

    Con `veto=True` (por defecto) además se añaden a la lista negra, de modo que el
    recolector **no volverá a descargarlas**.
    """
    _, rbl, *_ = _radiov()
    borradas = rbl.delete_tracks(payload.ids, veto=payload.veto)
    return {"borradas": borradas, "solicitadas": len(payload.ids), "vetadas": payload.veto}


@router.post("/tracks/blacklist", summary="Vetar canciones SIN borrarlas")
def admin_blacklist_tracks(payload: IdsRequest,
                           _: models.User = Depends(require_admin)) -> dict:
    _, rbl, *_ = _radiov()
    ok = sum(1 for tid in payload.ids if rbl.blacklist_song_only(tid))
    return {"vetadas": ok, "solicitadas": len(payload.ids)}


@router.post("/artists/veto", summary="Vetar un artista (y opcionalmente borrar sus canciones)")
def admin_veto_artist(payload: ArtistVetoRequest,
                      _: models.User = Depends(require_admin)) -> dict:
    _, rbl, *_ = _radiov()
    if payload.delete_tracks:
        borradas = rbl.block_artist(payload.name)
    else:
        rbl.list_blacklist  # noqa: B018  (documenta que el módulo ya está cargado)
        _, rdb, *_ = _radiov()  # noqa: F841
        rdb.add_blacklist("artist", payload.name, reason="vetado por el usuario")
        borradas = 0
    return {"artista": payload.name, "borradas": borradas}


@router.post("/purge", summary="Borra del disco todo lo que esté en la lista negra")
def admin_purge(_: models.User = Depends(require_admin)) -> dict:
    _, rbl, *_ = _radiov()
    return {"purgadas": rbl.purge()}


# --------------------------------------------------------------------------- lista negra
@router.get("/blacklist", summary="Lista negra (canciones y artistas)")
def admin_get_blacklist(kind: Optional[Literal["artist", "song"]] = None,
                        _: models.User = Depends(require_admin)) -> list[dict]:
    _, rbl, *_ = _radiov()
    return rbl.list_blacklist(kind)


@router.post("/blacklist", summary="Añadir una entrada a la lista negra")
def admin_add_blacklist(payload: BlacklistRequest,
                        _: models.User = Depends(require_admin)) -> dict:
    _, _, _, _, rmodels = _radiov()
    rdb, *_ = _radiov()
    anadido = rdb.add_blacklist(payload.kind, payload.value,
                                reason=payload.reason or "añadido desde la web")
    return {"anadido": bool(anadido), "kind": payload.kind, "value": payload.value}


@router.delete("/blacklist/{entry_id}", summary="Retirar una entrada de la lista negra")
def admin_remove_blacklist(entry_id: int,
                           _: models.User = Depends(require_admin)) -> dict:
    _, rbl, *_ = _radiov()
    rbl.unblock(entry_id)
    return {"retirada": entry_id}


# --------------------------------------------------------------------------- ingesta
@router.get("/ingest", summary="Estado del interruptor de ingesta")
def admin_get_ingest(_: models.User = Depends(require_admin)) -> dict:
    _, _, _, ric, _ = _radiov()
    return ric.status()


@router.put("/ingest", summary="Activar o desactivar la ingesta")
def admin_set_ingest(payload: IngestRequest,
                     admin: models.User = Depends(require_admin)) -> dict:
    _, _, _, ric, _ = _radiov()
    ric.set_enabled(payload.enabled, by=getattr(admin, "username", None) or str(admin.id))
    return ric.status()
