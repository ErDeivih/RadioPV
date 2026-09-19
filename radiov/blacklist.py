from __future__ import annotations

import datetime
from pathlib import Path

from . import db
from . import models as M
from .config import resolve_music


def _delete_file(file_path: str) -> bool:
    if not file_path:
        return False
    p = resolve_music(file_path)
    try:
        if p.exists():
            p.unlink()
            return True
    except OSError:
        pass
    return False


def block_song(track_id: int) -> bool:
    """Borra una canción de la biblioteca y la añade a la lista negra (dejará de descargarse)."""
    track = db.get_track_by_id(track_id)
    if not track:
        return False
    _delete_file(track.get("file_path"))
    db.delete_track(track_id)
    value = f"{track.get('title')}|{track.get('artist')}"
    added = db.add_blacklist(M.BLACKLIST_SONG, value, reason="borrada por el usuario")
    title = track.get("title")
    artist = track.get("artist")
    db.log_event(f"🗑️ {artist} - {title} borrada y añadida a la lista negra", "info")
    return added


def blacklist_song_only(track_id: int) -> bool:
    """Añade una canción a la lista negra SIN borrarla (se conserva en la biblioteca)."""
    track = db.get_track_by_id(track_id)
    if not track:
        return False
    db.add_blacklist(M.BLACKLIST_SONG, f"{track.get('title')}|{track.get('artist')}",
                     reason="vetada por el usuario (conserve)")
    db.log_event(f"🚫 Vetada (sin borrar): {track.get('artist')} - {track.get('title')}", "info")
    return True


def remove_track_no_veto(track_id: int) -> bool:
    """Borra la canción y su fichero SIN añadirla a la lista negra."""
    track = db.get_track_by_id(track_id)
    if not track:
        return False
    _delete_file(track.get("file_path"))
    db.delete_track(track_id)
    db.log_event(f"🗑️ {track.get('artist')} - {track.get('title')} borrada (sin vetar)", "info")
    return True


def block_artist(name: str) -> int:
    """Veta un artista completo: se añade a la lista negra y se eliminan sus canciones."""
    if not name or not name.strip():
        return 0
    db.add_blacklist(M.BLACKLIST_ARTIST, name.strip(), reason="vetado por el usuario")
    removed = db.purge_blacklisted_tracks()
    db.log_event(f"🚫 Artista vetado: {name} (se eliminaron {removed} canciones)", "info")
    return removed


def unblock(blacklist_id: int) -> None:
    db.remove_blacklist(blacklist_id)
    db.log_event("Elemento retirado de la lista negra", "info")


def list_blacklist(kind: str | None = None) -> list[dict]:
    return db.get_blacklist(kind)


def delete_tracks(track_ids, veto: bool = True, fallos: list | None = None) -> int:
    """Borra varias canciones en un solo paso (ficheros + filas + lista negra opcional).

    OJO CON LOS FICHEROS QUE NO SE PUEDEN BORRAR
    --------------------------------------------
    Aquí había `try: unlink() except OSError: pass`. El contenedor de la API montaba la música en
    **solo lectura**, así que el `unlink` fallaba con EROFS… y se tragaba el error. Resultado: el
    panel decía «Borradas 412 canciones», las fichas desaparecían del catálogo y **los ficheros
    seguían ocupando el disco**. Es decir, la herramienta de limpieza no limpiaba nada de verdad, y
    el mensaje decía que sí. Para colmo, `resolve_music` devuelve la ruta aunque no exista, así que
    «no existe» y «no tengo permiso» se veían igual.

    Ahora los fallos se recogen (si el que llama pasa una lista) y se apuntan como evento, para que
    se vea en el panel. La escritura se arregla en el montaje del contenedor (ver
    `docker-compose.yml`), pero el aviso se queda: un borrado a medias tiene que verse.
    """
    conn = db.get_conn()
    deleted = 0
    sin_borrar = 0
    try:
        for tid in track_ids:
            row = conn.execute("SELECT id, title, artist, file_path FROM tracks WHERE id=?", (tid,)).fetchone()
            if not row:
                continue
            fp = row["file_path"]
            if fp:
                try:
                    fichero = resolve_music(fp)
                    if fichero.exists():
                        fichero.unlink()
                except OSError as e:
                    # No se pudo borrar el audio (permisos, disco de solo lectura, fichero en uso).
                    # La fila se borra igual —el catálogo no debe quedarse con música que el usuario
                    # ha quitado— pero esto hay que decirlo, no esconderlo.
                    sin_borrar += 1
                    if fallos is not None:
                        fallos.append(f"{row['title']} ({str(e)[:40]})")
            if veto:
                conn.execute(
                    "INSERT OR IGNORE INTO blacklist(kind,value,reason,active,created_at) VALUES (?,?,?,1,?)",
                    (M.BLACKLIST_SONG, f"{row['title']}|{row['artist']}", "borrada por el usuario",
                     datetime.datetime.now().isoformat(timespec="seconds")))
            conn.execute("DELETE FROM tracks WHERE id=?", (tid,))
            deleted += 1
        conn.commit()
    finally:
        conn.close()
    db.log_event(f"🗑️ Borradas {deleted} canciones" + (" (y vetadas)" if veto else " (sin vetar)"), "info")
    if sin_borrar:
        db.log_event(f"⚠️ {sin_borrar} ficheros NO se pudieron borrar del disco "
                     f"(siguen ocupando sitio): {'; '.join((fallos or [])[:3])}", "warning")
    return deleted


def purge() -> int:
    removed = db.purge_blacklisted_tracks()
    db.log_event(f"Purgadas {removed} canciones de la lista negra", "info")
    return removed
