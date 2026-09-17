from __future__ import annotations

import datetime
import random
import shutil
from pathlib import Path

from .config import load_settings, PLAYLIST_DIR
from . import db
from . import models as M
from . import activity as A
from .config import resolve_music


class PlaylistError(Exception):
    pass


def generate_playlist(
    activity_key: str,
    count: int,
    *,
    copy_files: bool = True,
    seed: Optional[int] = None,
    include_unclassified: bool = False,
    artists: Optional[list[str]] = None,
    genres: Optional[list[str]] = None,
    years: Optional[list[int]] = None,
    tags: Optional[list[str]] = None,
) -> dict:
    """Genera una subselección aleatoria de canciones para una actividad.

    Selecciona entre las pistas descargadas que encajan en el ritmo de la actividad,
    copia los ficheros a una carpeta y escribe un .m3u. Devuelve un resumen.
    """
    cfg = load_settings()
    if activity_key not in A.activities():
        raise PlaylistError(f"Actividad desconocida: {activity_key}")
    if count <= 0:
        raise PlaylistError("El número de canciones debe ser mayor que 0")
    max_size = int(cfg.get("max_playlist_size", 200))
    count = min(count, max_size)

    # Limpia de la biblioteca lo que esté en la lista negra, para no seleccionarlo.
    purge = db.purge_blacklisted_tracks()
    if purge:
        db.log_event(f"Se purgaron {purge} pistas marcadas en la lista negra", "info")

    conn = db.get_conn()
    try:
        rows = conn.execute("SELECT * FROM tracks WHERE status=? ORDER BY id", (M.STATUS_DOWNLOADED,)).fetchall()
    finally:
        conn.close()

    tracks = [dict(r) for r in rows]
    if not tracks:
        raise PlaylistError("No hay canciones en la biblioteca todavía.")

    strict = bool(artists or genres or years or tags)
    if artists:
        al = {a.lower() for a in artists}
        tracks = [t for t in tracks if t.get("artist", "").lower() in al]
    if genres:
        tracks = [t for t in tracks if t.get("genre") in genres]
    if years:
        tracks = [t for t in tracks if t.get("year") in years]
    if tags:
        tracks = [t for t in tracks if any(tg in (t.get("tags") or "") for tg in tags)]
    if strict and not tracks:
        raise PlaylistError("No hay canciones que cumplan los filtros elegidos.")

    primary = [t for t in tracks if A.in_bpm_range(t.get("bpm"), activity_key)]
    secondary = [t for t in tracks if t.get("bpm") is None and t.get("genre") in A.activity_genres(activity_key)]

    # Si no hay suficientes con BPM ajustado y se permite, se amplía con cualquier tema sin BPM.
    if include_unclassified:
        extra = [t for t in tracks if t not in primary and t not in secondary and not A.in_bpm_range(t.get("bpm"), activity_key)]
        secondary += extra

    pool = primary + secondary
    if len(pool) < count and not strict:
        # se rellena con el resto (mejor algún tema que ninguno), priorizando con BPM cercano
        db.log_event(f"Se necesitaban {count} temas y solo hay {len(pool)} para la actividad; se rellena.", "info")
        # ordenar restantes por cercanía al rango
        rest = [t for t in tracks if t not in pool]
        lo, hi = A.activity_bpm_range(activity_key)
        if lo is not None and hi is not None:
            mid = (lo + hi) / 2
            rest.sort(key=lambda t: abs((t.get("bpm") or mid) - mid))
        pool += rest

    pool = _dedup_by_ytid(pool)
    if seed is not None:
        rng = random.Random(seed)
    else:
        rng = random.Random()
    chosen = rng.sample(pool, min(count, len(pool)))

    if not copy_files:
        return {"tracks": chosen, "destination": None, "m3u": None, "count": len(chosen)}

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(cfg["playlist_dir"]) / f"{activity_key}_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    m3u_lines = ["#EXTM3U", f"# Actividad: {A.activity_label(activity_key)}",
                 f"# Generado: {stamp} · {len(chosen)} canciones"]

    copied = []
    for i, t in enumerate(chosen, 1):
        src = t.get("file_path")
        if not src:
            continue
        src = resolve_music(src)          # acepta ruta absoluta o relativa
        if not src.exists():
            continue
        ext = Path(src).suffix or ".mp3"
        safe = f"{t.get('artist')} - {t.get('title')}".replace(":", "-").replace("/", "-").replace("\\", "-")
        safe = "".join(c if (c.isalnum() or c in " -_") else "" for c in safe).strip()[:120] or f"tema_{i}"
        dest = out_dir / f"{i:03d}_{safe}{ext}"
        try:
            shutil.copyfile(src, dest)
            copied.append(dest)
            m3u_lines.append(f"#EXTINF:{int(t.get('duration') or 0)},{t.get('artist')} - {t.get('title')}")
            m3u_lines.append(dest.name)
        except OSError as e:
            db.log_event(f"No se pudo copiar {t.get('title')}: {e}", "warning")

    m3u_path = out_dir / "playlist.m3u"
    m3u_path.write_text("\n".join(m3u_lines), encoding="utf-8")

    return {
        "tracks": chosen,
        "destination": str(out_dir),
        "m3u": str(m3u_path),
        "count": len(chosen),
        "copied": len(copied),
    }


def _dedup_by_ytid(tracks: list[dict]) -> list[dict]:
    seen, out = set(), []
    for t in tracks:
        key = t.get("youtube_id") or (t.get("artist"), t.get("title"))
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out
