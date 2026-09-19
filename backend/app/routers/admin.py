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
    title: Optional[str] = None,
    tags: Optional[str] = None,
    era: Optional[str] = None,
    explicit: Optional[bool] = None,
    is_remix: Optional[bool] = None,
    has_file_path: Optional[bool] = None,
    rank_min: Optional[int] = None,
    rank_max: Optional[int] = None,
    duration_min: Optional[float] = None,
    duration_max: Optional[float] = None,
    bpm_min: Optional[float] = None,
    bpm_max: Optional[float] = None,
    energy_min: Optional[float] = None,
    energy_max: Optional[float] = None,
    match_score_min: Optional[float] = None,
    added_from: Optional[str] = None,
    added_to: Optional[str] = None,
    sort: Literal["artist", "title", "album", "year", "genre", "language", "added_at", "file_size"] = "artist",
    order: Literal["asc", "desc"] = "asc",
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: models.User = Depends(require_admin),
) -> dict:
    """Tabla de gestión.

    Acepta **el mismo juego de filtros que el borrado en masa** — se construye un
    `BulkFilter` con lo que llega y se usa la misma función `_where_bulk`. Así lo que
    ves en pantalla es **exactamente** lo que se borraría al pulsar el botón.
    """
    filtro = BulkFilter(
        q=q, artist=artist, album=album, genre=genre, language=language,
        status=status_, year_min=year_min, year_max=year_max,
        title=title, tags=tags, era=era, explicit=explicit, is_remix=is_remix,
        has_file_path=has_file_path,
        rank_min=rank_min, rank_max=rank_max,
        duration_min=duration_min, duration_max=duration_max,
        bpm_min=bpm_min, bpm_max=bpm_max,
        energy_min=energy_min, energy_max=energy_max,
        match_score_min=match_score_min,
        added_from=added_from, added_to=added_to,
    )
    try:
        clausula, args = _where_bulk(filtro)
    except HTTPException:
        clausula, args = "", []          # sin filtros: se listan todas

    # `sort` y `order` están restringidos por Literal: no hay inyección posible.
    total = _one(f"SELECT COUNT(*) n FROM tracks {clausula}", tuple(args)) or {"n": 0}
    filas = _rows(
        f"""SELECT id, title, artist, album, year, genre, language, bpm, energy,
                   duration, file_size, status, source, explicit, is_remix, era,
                   rank, match_score, added_at, file_path
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

    def _uno(estado: str) -> dict:
        """Cuántas canciones están en un estado concreto (por `status`)."""
        return _one("SELECT COUNT(*) n FROM tracks WHERE status = ?", (estado,)) or {"n": 0}

    return {
        "languages": facet("language"),
        "genres": facet("genre"),
        "artists": facet("artist", 2),     # artistas con al menos 2 pistas
        "years": _rows("SELECT year AS valor, COUNT(*) n FROM tracks "
                       "WHERE year IS NOT NULL GROUP BY year ORDER BY year"),
        "status": facet("status"),
        "sources": facet("source"),
        "eras": facet("era"),
        "duraciones": facet("duration"),   # valores exactos; sirve de referencia
        "booleanos": {
            "explicit": _one("SELECT COUNT(*) n FROM tracks WHERE explicit = 1") or {"n": 0},
            "remixes": _one("SELECT COUNT(*) n FROM tracks WHERE is_remix = 1") or {"n": 0},
            "huerfanas": _one("SELECT COUNT(*) n FROM tracks "
                              "WHERE file_path IS NULL OR file_path = ''") or {"n": 0},
            "total": _one("SELECT COUNT(*) n FROM tracks") or {"n": 0},
        },
        # Recuentos de los atajos de limpieza. Cada uno es EXACTAMENTE lo que selecciona su
        # atajo correspondiente en la pantalla (mismo WHERE), así el número que se ve antes de
        # pulsar es el número de canciones que se van a tocar.
        #
        # Ojo con `rank`: los `NULL` NO entran en los tramos de popularidad. `rank <= 39` con
        # `rank` nulo es NULL, y en SQL eso no es verdadero, así que una canción de la que no
        # sabemos la popularidad nunca se cuela en el atajo de «peor valoradas».
        "salud": {
            "sin_fichero": _one("SELECT COUNT(*) n FROM tracks "
                                "WHERE file_path IS NULL OR file_path = ''") or {"n": 0},
            "no_descargadas": _one("SELECT COUNT(*) n FROM tracks "
                                   "WHERE status IS NULL OR status <> 'descargada'") or {"n": 0},
            "perdidas": _uno("perdida"),
            "cuarentena": _uno("cuarentena"),
            "fallidas": _uno("fallida"),
            "incompletas": _uno("incompleta"),
            "pendientes": _uno("pendiente"),
            "rank_bajo_40": _one("SELECT COUNT(*) n FROM tracks "
                                 "WHERE rank IS NOT NULL AND rank <= 39") or {"n": 0},
            "rank_bajo_60": _one("SELECT COUNT(*) n FROM tracks "
                                 "WHERE rank IS NOT NULL AND rank <= 59") or {"n": 0},
            "cortas": _one("SELECT COUNT(*) n FROM tracks "
                           "WHERE duration IS NOT NULL AND duration < 60") or {"n": 0},
            # Este es EXACTAMENTE el atajo «sin idioma detectado», que filtra `language = 'other'`.
            # Contar además los NULL daría un número mayor que el de canciones que se tocan.
            "sin_idioma": _one("SELECT COUNT(*) n FROM tracks WHERE language = 'other'") or {"n": 0},
        },
    }


# --------------------------------------------------------------------------- borrado
_UNIR = 500          # cuántos ids caben en un `IN (...)` sin pasarse de largo


def _identidad_en_recolector(ids: list[int]) -> list[dict]:
    """Los datos que hacen falta para reconocer estas canciones en la OTRA base.

    Se leen ANTES de borrar en `radiov.db`, porque después ya no están. Se guardan los dos
    identificadores (`youtube_id`, `deezer_id`) y, como último recurso, artista y título.
    """
    if not ids:
        return []
    rdb, *_ = _radiov()
    salida: list[dict] = []
    con = rdb.get_conn()
    try:
        for i in range(0, len(ids), _UNIR):
            trozo = ids[i:i + _UNIR]
            q = ",".join("?" * len(trozo))
            salida += [dict(r) for r in con.execute(
                f"SELECT id, youtube_id, deezer_id, artist, title FROM tracks WHERE id IN ({q})",
                tuple(trozo)).fetchall()]
    finally:
        con.close()
    return salida


def _borrar_de_la_app(db: Session, identidades: list[dict]) -> int:
    """Quita de la base de la APLICACIÓN las canciones que se acaban de borrar del recolector.

    POR QUÉ HACE FALTA (fallo real, 19/09/2026)
    -------------------------------------------
    RadioPV guarda la música en **dos bases**: `radiov.db` (la biblioteca del recolector, que es la
    que gestiona este panel) y `backend.db` (la que sirve la aplicación: listas, portada,
    reproductor). El borrado tocaba la primera y el disco, y **no la segunda**. Resultado medido, con
    una canción de prueba en las dos bases:

        docker exec radiopv-api python /app/scripts/prueba_borrado_dos_bases.py --comprobar
        →  radiov.db: 0 fichas
           backend.db: 1 ficha   ← la canción SEGUÍA en la aplicación, sin fichero

    O sea: el panel decía «Borradas 1» y la canción seguía en la biblioteca del usuario, ahora rota
    (no suena, porque su fichero ya no está). Para una herramienta de limpieza es el peor fallo
    posible: el usuario borra 400 canciones, el contador sube y el disco y la aplicación no se
    enteran del todo. Ahora se borran las dos fichas.
    """
    if not identidades:
        return 0
    borradas = 0
    for ident in identidades:
        q = db.query(models.Track)
        if ident.get("youtube_id"):
            q = q.filter(models.Track.youtube_id == ident["youtube_id"])
        elif ident.get("deezer_id"):
            q = q.filter(models.Track.deezer_id == ident["deezer_id"])
        else:
            # Sin identificadores: por artista y título, que es como se sembró la ficha.
            q = q.filter(models.Track.artist == ident.get("artist"),
                         models.Track.title == ident.get("title"))
        borradas += q.delete(synchronize_session=False)
    if borradas:
        db.commit()
    return borradas


def _borrar_de_la_app_por_artista(db: Session, nombre: str) -> int:
    """Quita de la base de la aplicación todas las canciones de un artista.

    Mismo motivo que `_borrar_de_la_app`: vetar un artista borraba sus canciones del recolector y
    del disco, y en la aplicación se quedaban (rotas, sin fichero).
    """
    if not nombre:
        return 0
    n = (db.query(models.Track)
         .filter(models.Track.artist == nombre)
         .delete(synchronize_session=False))
    if n:
        db.commit()
    return n


def _borrar_de_la_app_la_lista_negra(db: Session) -> int:
    """Quita de la base de la aplicación todo lo que esté en la lista negra.

    `purge()` limpia el disco y `radiov.db` de lo vetado; esto limpia la otra mitad. Las entradas de
    canción se guardan como «titulo|artista» (ver `blacklist.block_song`), así que se separan por la
    primera barra vertical: el título puede llevarla, el artista no.
    """
    _, rbl, *_ = _radiov()
    borradas = 0
    for entrada in rbl.list_blacklist():
        tipo = (entrada.get("kind") or entrada.get("tipo") or "").lower()
        valor = entrada.get("value") or entrada.get("valor") or ""
        if tipo == "artist":
            borradas += _borrar_de_la_app_por_artista(db, valor)
        elif tipo == "song" and "|" in valor:
            titulo, artista = valor.split("|", 1)
            n = (db.query(models.Track)
                 .filter(models.Track.title == titulo, models.Track.artist == artista)
                 .delete(synchronize_session=False))
            borradas += n
    if borradas:
        db.commit()
    return borradas


@router.post("/tracks/delete", summary="Borrado masivo de canciones (ficheros + BD)")
def admin_delete_tracks(payload: DeleteRequest, db: Session = Depends(get_db),
                        admin: models.User = Depends(require_admin)) -> dict:
    """Borra las pistas indicadas del disco y de **las dos bases de datos**.

    Con `veto=True` (por defecto) además se añaden a la lista negra, de modo que el
    recolector **no volverá a descargarlas**.
    """
    _, rbl, *_ = _radiov()
    # `fallos` recoge los ficheros que no se han podido borrar del disco. Antes no se podía saber:
    # el borrado decía «Borradas N» aunque los ficheros siguieran ahí (el contenedor montaba la
    # música en solo lectura y el error se tragaba). Para una herramienta de limpieza, eso es lo
    # peor: crees que has liberado 30 GB y no has liberado ninguno.
    # Primero se apunta quiénes son (después de borrar ya no hay de dónde sacarlo).
    identidades = _identidad_en_recolector(payload.ids)
    no_borrados: list = []
    borradas = rbl.delete_tracks(payload.ids, veto=payload.veto, fallos=no_borrados)
    # Y ahora la otra mitad: la base de la aplicación, que es la que ve el usuario.
    de_la_app = _borrar_de_la_app(db, identidades)
    return {"borradas": borradas, "solicitadas": len(payload.ids), "vetadas": payload.veto,
            "borradas_de_la_app": de_la_app,
            "ficheros_no_borrados": len(no_borrados), "detalle_fallos": no_borrados[:5]}


@router.post("/tracks/blacklist", summary="Vetar canciones SIN borrarlas")
def admin_blacklist_tracks(payload: IdsRequest,
                           _: models.User = Depends(require_admin)) -> dict:
    _, rbl, *_ = _radiov()
    ok = sum(1 for tid in payload.ids if rbl.blacklist_song_only(tid))
    return {"vetadas": ok, "solicitadas": len(payload.ids)}


@router.post("/artists/veto", summary="Vetar un artista (y opcionalmente borrar sus canciones)")
def admin_veto_artist(payload: ArtistVetoRequest, db: Session = Depends(get_db),
                      _: models.User = Depends(require_admin)) -> dict:
    rdb, rbl, *_ = _radiov()
    if payload.delete_tracks:
        borradas = rbl.block_artist(payload.name)
        # Y de la base de la aplicación, que es la que ve el usuario.
        de_la_app = _borrar_de_la_app_por_artista(db, payload.name)
    else:
        # OJO con el desempaquetado: `_radiov()` devuelve (db, blacklist, config, ingest, models),
        # así que el primer valor es el módulo de base de datos. Antes esto era
        # `_, rdb, *_ = _radiov()`, con lo que `rdb` acababa siendo el módulo `blacklist`, que no
        # tiene `add_blacklist` (está en `db`): vetar un artista sin borrar sus canciones daba
        # un 500 seguro.
        rdb.add_blacklist("artist", payload.name, reason="vetado por el usuario")
        borradas = 0
        de_la_app = 0
    return {"artista": payload.name, "borradas": borradas, "borradas_de_la_app": de_la_app}


@router.post("/purge", summary="Borra del disco todo lo que esté en la lista negra")
def admin_purge(db: Session = Depends(get_db),
                _: models.User = Depends(require_admin)) -> dict:
    _, rbl, *_ = _radiov()
    purgadas = rbl.purge()
    de_la_app = _borrar_de_la_app_la_lista_negra(db)
    return {"purgadas": purgadas, "borradas_de_la_app": de_la_app}


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


# --------------------------------------------------------------- borrado en masa
class BulkFilter(BaseModel):
    """Filtros de una operación en masa. Al menos uno es obligatorio.

    Los campos en singular filtran por un valor exacto; los que son **listas** (`artists`,
    `albums`, `genres`, `languages`, `years`, `ids`) permiten operar sobre **muchos
    elementos elegidos a la vez** — que es como se limpia una biblioteca grande:
    filtrar por idioma, seleccionar 80 artistas y borrarlos de un golpe.
    """
    # --- valores únicos ---
    q: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    genre: Optional[str] = None
    language: Optional[str] = None
    status: Optional[str] = None
    source: Optional[str] = None
    year_min: Optional[int] = None
    year_max: Optional[int] = None

    # --- listas: selección múltiple ---
    ids: Optional[list[int]] = Field(None, description="IDs concretos de pista")
    artists: Optional[list[str]] = Field(None, description="Varios artistas a la vez")
    albums: Optional[list[str]] = Field(None, description="Varios álbumes a la vez")
    genres: Optional[list[str]] = Field(None, description="Varios géneros a la vez")
    languages: Optional[list[str]] = Field(None, description="Varios idiomas a la vez")
    years: Optional[list[int]] = Field(None, description="Varios años a la vez")

    # --- campos exactos adicionales ---
    title: Optional[str] = Field(None, description="Título exacto")
    tags: Optional[str] = Field(None, description="Busca dentro de las etiquetas")
    era: Optional[str] = Field(None, description="Época: pre2000, 2000s, 2010s…")

    # --- booleanos ---
    explicit: Optional[bool] = Field(None, description="Con o sin contenido explícito")
    is_remix: Optional[bool] = Field(None, description="Solo remixes, o todo lo contrario")
    has_file_path: Optional[bool] = Field(
        None, description="True: tiene fichero asignado · False: huérfana (sin file_path)"
    )

    # --- rangos numéricos ---
    rank_min: Optional[int] = Field(None, description="Popularidad Deezer mínima")
    rank_max: Optional[int] = None
    duration_min: Optional[float] = Field(None, description="Duración mínima, en segundos")
    duration_max: Optional[float] = None
    bpm_min: Optional[float] = None
    bpm_max: Optional[float] = None
    energy_min: Optional[float] = None
    energy_max: Optional[float] = None
    match_score_min: Optional[float] = Field(None, description="Calidad del emparejamiento")

    # --- fechas de alta ---
    added_from: Optional[str] = Field(None, description="Alta desde (AAAA-MM-DD)")
    added_to: Optional[str] = Field(None, description="Alta hasta (AAAA-MM-DD)")


class BulkRequest(BaseModel):
    filters: BulkFilter
    action: Literal["delete", "blacklist"] = "delete"
    veto: bool = Field(True, description="Añadir a la lista negra (no se volverán a descargar)")
    dry_run: bool = Field(False, description="Solo contar, sin tocar nada")
    limit: int = Field(0, ge=0, description="0 = sin límite")


def _marcas(n: int) -> str:
    """Devuelve '?,?,?' para un IN parametrizado de n elementos."""
    return ",".join("?" * n)


def _where_bulk(f: BulkFilter) -> tuple[str, list]:
    """Construye el WHERE del borrado en masa. Exige al menos un filtro."""
    donde: list[str] = []
    args: list = []

    if f.q:
        donde.append("(title LIKE ? OR artist LIKE ? OR album LIKE ?)")
        like = f"%{f.q}%"
        args += [like, like, like]
    if f.artist:
        donde.append("artist = ?"); args.append(f.artist)
    if f.album:
        donde.append("album = ?"); args.append(f.album)
    if f.genre:
        donde.append("genre = ?"); args.append(f.genre)
    if f.language:
        donde.append("language = ?"); args.append(f.language)
    if f.status:
        donde.append("status = ?"); args.append(f.status)
    if f.source:
        donde.append("source = ?"); args.append(f.source)
    if f.year_min is not None:
        donde.append("year >= ?"); args.append(f.year_min)
    if f.year_max is not None:
        donde.append("year <= ?"); args.append(f.year_max)

    # --- listas (selección múltiple) ---
    for columna, valores in (
        ("id", f.ids),
        ("artist", f.artists),
        ("album", f.albums),
        ("genre", f.genres),
        ("language", f.languages),
        ("year", f.years),
    ):
        if valores:
            donde.append(f"{columna} IN ({_marcas(len(valores))})")
            args += list(valores)

    # --- campos exactos adicionales ---
    if f.title:
        donde.append("title = ?"); args.append(f.title)
    if f.era:
        donde.append("era = ?"); args.append(f.era)
    if f.tags:
        donde.append("tags LIKE ?"); args.append(f"%{f.tags}%")

    # --- booleanos (la BD guarda 0/1) ---
    if f.explicit is not None:
        donde.append("explicit = ?"); args.append(1 if f.explicit else 0)
    if f.is_remix is not None:
        donde.append("is_remix = ?"); args.append(1 if f.is_remix else 0)
    if f.has_file_path is not None:
        if f.has_file_path:
            donde.append("file_path IS NOT NULL AND file_path <> ''")
        else:
            # Huérfanas: la fila existe pero no apunta a ningún fichero
            donde.append("(file_path IS NULL OR file_path = '')")

    # --- rangos numéricos ---
    for columna, minimo, maximo in (
        ("rank", f.rank_min, f.rank_max),
        ("duration", f.duration_min, f.duration_max),
        ("bpm", f.bpm_min, f.bpm_max),
        ("energy", f.energy_min, f.energy_max),
    ):
        if minimo is not None:
            donde.append(f"{columna} >= ?"); args.append(minimo)
        if maximo is not None:
            donde.append(f"{columna} <= ?"); args.append(maximo)

    if f.match_score_min is not None:
        donde.append("match_score >= ?"); args.append(f.match_score_min)

    # --- fechas de alta ---
    if f.added_from:
        donde.append("added_at >= ?"); args.append(f.added_from)
    if f.added_to:
        donde.append("added_at <= ?"); args.append(f.added_to + "T23:59:59")

    if not donde:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "El borrado en masa exige al menos un filtro, para que un clic accidental "
            "no pueda vaciar la biblioteca",
        )
    return "WHERE " + " AND ".join(donde), args


@router.get("/group", summary="Agrupar la biblioteca (por artista, álbum, género, idioma o año)")
def admin_group(
    by: Literal["artist", "album", "genre", "language", "year", "status", "source"] = "artist",
    q: Optional[str] = None,
    artist: Optional[str] = None,
    genre: Optional[str] = None,
    language: Optional[str] = None,
    status_: Optional[str] = Query(None, alias="status"),
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    min_tracks: int = Query(1, ge=1, description="Oculta grupos con menos pistas que esto"),
    sort: Literal["n", "size", "valor"] = "n",
    order: Literal["asc", "desc"] = "desc",
    limit: int = Query(300, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    _: models.User = Depends(require_admin),
) -> dict:
    """Devuelve la biblioteca **agrupada**, con el recuento de cada grupo.

    Es la vista con la que se limpia de verdad: en vez de 12.000 canciones sueltas,
    ves *"Inglés · 412 artistas · 3.180 canciones"* y puedes seleccionar 80 artistas
    de una vez. `by` está restringido por `Literal`, así que no hay inyección posible.
    """
    filtro = BulkFilter(
        q=q, artist=artist, genre=genre, language=language,
        status=status_, year_min=year_min, year_max=year_max,
    )
    # Sin filtros, agrupar es legítimo: se agrupa toda la biblioteca.
    try:
        clausula, args = _where_bulk(filtro)
    except HTTPException:
        clausula, args = "", []

    orden_col = {"n": "n", "size": "size", "valor": "valor"}[sort]
    total = _one(
        f"""SELECT COUNT(*) n FROM (
                SELECT 1 FROM tracks {clausula} GROUP BY {by} HAVING COUNT(*) >= ?
            )""",
        tuple(args) + (min_tracks,),
    ) or {"n": 0}

    filas = _rows(
        f"""SELECT {by} AS valor,
                   COUNT(*) AS n,
                   SUM(COALESCE(file_size, 0)) AS size,
                   GROUP_CONCAT(DISTINCT language) AS languages,
                   GROUP_CONCAT(DISTINCT genre) AS genres,
                   MIN(year) AS year_min,
                   MAX(year) AS year_max
            FROM tracks {clausula}
            GROUP BY {by}
            HAVING n >= ?
            ORDER BY {orden_col} {order.upper()}
            LIMIT ? OFFSET ?""",
        tuple(args) + (min_tracks, limit, offset),
    )
    return {"by": by, "total_grupos": total["n"], "limit": limit, "offset": offset, "items": filas}


@router.post("/tracks/bulk", summary="Borrar o vetar EN MASA por filtros")
def admin_bulk(payload: BulkRequest,
               _: models.User = Depends(require_admin)) -> dict:
    """Borra (o veta) todo lo que encaje con los filtros, sin mandar IDs.

    Es la operación pensada para limpiezas grandes: *todo lo que no sea español*,
    *todo el género X*, *todo de este artista*. Con `dry_run=true` solo cuenta.

    **Exige al menos un filtro** (ver `_where_bulk`).
    """
    _, rbl, *_ = _radiov()
    clausula, args = _where_bulk(payload.filters)

    limite = "" if payload.limit == 0 else f" LIMIT {int(payload.limit)}"
    ids = [r["id"] for r in _rows(f"SELECT id FROM tracks {clausula}{limite}", tuple(args))]

    if payload.dry_run:
        return {"afectadas": len(ids), "borradas": 0, "vetadas": 0, "dry_run": True}

    if payload.action == "blacklist":
        vetadas = sum(1 for tid in ids if rbl.blacklist_song_only(tid))
        return {"afectadas": len(ids), "borradas": 0, "vetadas": vetadas, "dry_run": False}

    borradas = rbl.delete_tracks(ids, veto=payload.veto)
    return {"afectadas": len(ids), "borradas": borradas,
            "vetadas": borradas if payload.veto else 0, "dry_run": False}


@router.post("/artists/bulk-veto", summary="Vetar en masa varios artistas")
def admin_bulk_veto_artists(payload: dict = Body(...),
                            _: models.User = Depends(require_admin)) -> dict:
    """Veta una lista de artistas y borra sus canciones.

    Cuerpo: `{"names": ["Artista A", "Artista B"], "dry_run": false}`
    """
    nombres = payload.get("names") or []
    dry = bool(payload.get("dry_run", False))
    if not nombres:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Falta la lista 'names'")

    _, rbl, *_ = _radiov()
    resultado = []
    total = 0
    for nombre in nombres:
        n = _one("SELECT COUNT(*) n FROM tracks WHERE artist = ?", (nombre,))
        cuantas = (n or {}).get("n", 0)
        total += cuantas
        resultado.append({"artista": nombre, "canciones": cuantas})
        if not dry:
            rbl.block_artist(nombre)
    return {"dry_run": dry, "total_canciones": total, "artistas": resultado}
