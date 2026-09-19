from __future__ import annotations

import os
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Optional

import yt_dlp

from .config import load_settings
from . import db
from . import models as M

# Una única descarga a la vez para no saturar YouTube ni arriesgar bloqueos.
download_lock = threading.Lock()

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


class DownloadError(Exception):
    pass


def _ydl_opts(outdir: Path) -> dict:
    cfg = load_settings()
    return {
        "format": "bestaudio/best",
        "outtmpl": str(outdir / "%(id)s.%(ext)s"),
        "download_archive": None,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": cfg.get("audio_format", "mp3"),
            "preferredquality": cfg.get("audio_quality", "0"),
        }],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "noprogress": True,
        "restrictfilenames": True,
        "ignoreerrors": False,
        "socket_timeout": 20,
        "retries": 2,
        "http_headers": {"User-Agent": UA, "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"},
    }


def _clean_title(t: str) -> str:
    t = re.sub(r"\s*\((?:official|official\s*audio|official\s*video|lyric[s]?|audio|video|letra)\)\s*$", "", t, flags=re.I)
    t = re.sub(r"\s*\[(?:official|lyric[s]?|audio|video|letra)\]", "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _search_candidates(query: str, n: int = 8) -> list[dict]:
    """Busca en YouTube y devuelve candidatos planos (sin descargar)."""
    outdir = Path(load_settings()["download_dir"])
    opts = _ydl_opts(outdir)
    opts["skip_download"] = True
    opts["ignoreerrors"] = True   # saltar vídeos caídos/no disponibles
    opts["extract_flat"] = "in_playlist"
    with download_lock:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{n}:{query}", download=False)
    entries = info.get("entries") or []
    cands = []
    for e in entries:
        if not e:
            continue
        duration = e.get("duration")
        # La artista a veces viene en 'artist'/'creator'/'channel'
        artist = (e.get("artist") or e.get("creator") or e.get("uploader") or e.get("channel") or "").strip()
        cands.append({
            "id": e.get("id"),
            "url": e.get("webpage_url") or f"https://www.youtube.com/watch?v={e.get('id')}",
            "title": e.get("title") or "",
            "clean_title": _clean_title(e.get("title") or ""),
            "artist": artist,
            "duration": float(duration) if duration else 0.0,
            "channel": e.get("channel") or "",
        })
    return cands


# Caché de búsquedas: buscar en YouTube lanza `yt-dlp`, que es un proceso de Python entero. La
# página de pedir canciones busca MIENTRAS se escribe, así que sin esto cada consulta (y cada
# repetición de la misma, al volver a la pantalla) arrancaba un proceso en un servidor de 4 GB. Y
# además YouTube limita si se le pregunta demasiado seguido.
#
# Se guarda poco tiempo a propósito: los resultados de una búsqueda no cambian de un minuto a otro,
# pero tampoco queremos enseñar siempre lo mismo.
_TTL_BUSQUEDA = 600.0        # 10 minutos
_MAX_BUSQUEDAS = 200         # tope de entradas (memoria: en este servidor va justa)
_CACHE: dict[tuple[str, int], tuple[float, list[dict]]] = {}
_CACHE_LOCK = threading.Lock()


def _cache_limpia() -> None:
    """Quita lo caducado y, si sigue habiendo demasiado, lo más viejo."""
    ahora = time.time()
    for k in [k for k, (t, _) in _CACHE.items() if ahora - t > _TTL_BUSQUEDA]:
        _CACHE.pop(k, None)
    if len(_CACHE) > _MAX_BUSQUEDAS:
        for k, _ in sorted(_CACHE.items(), key=lambda kv: kv[1][0])[:len(_CACHE) - _MAX_BUSQUEDAS]:
            _CACHE.pop(k, None)


def search_videos(query: str, n: int = 15, usar_cache: bool = True) -> list[dict]:
    """Busca vídeos en YouTube y devuelve los candidatos (sin descargar).

    Hace falta para el contenido que **no existe en las tiendas de música**: mashups, remixes
    caseros y sesiones de DJ. Eso se publica en YouTube y sólo en YouTube, así que buscar en
    Deezer (que es lo que hacía el recolector) no encontraba nada.

    Con `usar_cache=False` se pregunta a YouTube aunque haya resultado guardado: el recolector lo
    usa cuando quiere variedad (baraja los resultados y busca cosas nuevas).
    """
    clave = (query.strip().lower(), int(n))
    if usar_cache:
        with _CACHE_LOCK:
            guardado = _CACHE.get(clave)
            if guardado and time.time() - guardado[0] <= _TTL_BUSQUEDA:
                # Copia: quien llame puede barajar o recortar sin estropear lo guardado.
                return [dict(c) for c in guardado[1]]
    resultados = _search_candidates(query, n)
    if usar_cache and resultados:
        with _CACHE_LOCK:
            _CACHE[clave] = (time.time(), [dict(c) for c in resultados])
            _cache_limpia()
    return resultados


def download_video(video_id: str, artist: str = "", title: str = "") -> Optional[dict]:
    """Descarga un vídeo concreto de YouTube y devuelve la ficha del fichero.

    Es la mitad que faltaba para las búsquedas de YouTube: `_search_candidates` dice QUÉ hay y
    `search_and_download` sabe bajar «la mejor coincidencia para esta canción», pero aquí ya se
    sabe exactamente qué vídeo se quiere.
    """
    cfg = load_settings()
    outdir = Path(cfg["download_dir"])
    outdir.mkdir(parents=True, exist_ok=True)
    try:
        return _download_by_id(video_id, outdir, artist=artist, title=title)
    except Exception as e:  # noqa: BLE001
        db.log_event(f"⚠️ No se pudo descargar el vídeo {video_id}: {str(e)[:120]}", "warning")
        return None


def _best_candidate(cands: list[dict], artist: str, title: str,
                    expected_duration: Optional[float]) -> Optional[dict]:
    def score(c):
        s = 0.0
        # coincidencia de título (palabras de la canción presentes en el título del vídeo)
        title_words = set(re.findall(r"[a-z0-9áéíóúüñ]+", title.lower()))
        clean = set(re.findall(r"[a-z0-9áéíóúüñ]+", c["clean_title"].lower()))
        if title_words:
            s += len(title_words & clean) / len(title_words)
        # artista en el canal/título
        artist_l = artist.lower()
        where = (c["channel"] + " " + c["title"]).lower()
        if artist and artist_l in where:
            s += 0.25
        elif artist and artist_l.split()[0] in where and len(artist_l.split()) <= 2:
            s += 0.1
        # duración
        if expected_duration and c["duration"]:
            diff = abs(c["duration"] - expected_duration) / max(expected_duration, 1)
            s += max(0.0, 1.0 - diff)
        return s

    if not cands:
        return None
    ranked = sorted(cands, key=score, reverse=True)
    for c in ranked[:4]:
        # validar duración si la conocemos
        if expected_duration and c["duration"]:
            tol = float(load_settings().get("duration_tolerance", 0.20))
            diff = abs(c["duration"] - expected_duration) / max(expected_duration, 1)
            if diff <= tol * 1.6:
                return c
        elif not expected_duration:
            return c
    # devolver el mejor aunque no encaje del todo (mejor que nada)
    return ranked[0]


def _safe_name(s) -> str:
    """Sanitiza un nombre para usarlo como nombre de archivo en Windows."""
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", str(s or "")).strip().rstrip(".")
    return s[:120].strip() or "descarga"


def _download_by_id(video_id: str, outdir: Path, artist: str = "", title: str = "") -> dict:
    cfg = load_settings()
    ext = cfg.get("audio_format", "mp3")

    # Descargamos en una carpeta temporal para no dejar ficheros intermedios (webm/m4a/…)
    staging = outdir / "_tmp"
    staging.mkdir(parents=True, exist_ok=True)
    opts = _ydl_opts(staging)
    try:
        with download_lock:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
        cand = _locate(staging, video_id, ext)
        if not cand or not cand.exists():
            raise DownloadError("No se generó fichero de audio")
        # nombre amigable en la carpeta visible "en bruto"
        friendly = _safe_name(f"{artist} - {title}".strip(" -")) + f".{ext}"
        dest = outdir / friendly
        i = 2
        while dest.exists():
            dest = outdir / f"{_safe_name(f'{artist} - {title}')} ({i}).{ext}"
            i += 1
        os.replace(cand, dest)  # mover de la temporal a descargas con nombre correcto
        file_path = dest
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    duration = info.get("duration") or 0.0
    return {
        "youtube_id": video_id,
        "youtube_url": f"https://www.youtube.com/watch?v={video_id}",
        "file_path": str(file_path) if file_path else "",
        "file_size": file_path.stat().st_size if file_path and file_path.exists() else 0,
        "youtube_duration": float(duration),
        "title": info.get("title") or "",
        "artist": info.get("artist") or info.get("creator") or info.get("channel") or "",
    }


def _locate(outdir: Path, video_id: str, ext: str) -> Optional[Path]:
    direct = outdir / f"{video_id}.{ext}"
    if direct.exists():
        return direct
    cands = list(outdir.glob(f"{video_id}.*"))
    return cands[0] if cands else None


def search_and_download(artist: str, title: str, *, expected_duration: Optional[float] = None,
                        genre: str = "other", language: str = M.LANG_OTHER,
                        source: str = M.SOURCE_ONDEMAND, max_attempts: int = 3) -> Optional[dict]:
    """Busca 'artist title' en YouTube y descarga la mejor coincidencia. Devuelve un dict de pista o None."""
    if db.is_blacklisted(M.BLACKLIST_ARTIST, artist):
        db.log_event(f"Artista en lista negra, se omite: {artist}", "info")
        return {"skipped": True, "reason": "blacklist_artist", "artist": artist, "title": title}

    cfg = load_settings()
    outdir = Path(cfg["download_dir"])
    outdir.mkdir(parents=True, exist_ok=True)

    query = f"{artist} {title}" if artist else title
    cands = _search_candidates(query)
    chosen = _best_candidate(cands, artist, title, expected_duration)
    if not chosen:
        db.log_event(f"No se encontró en YouTube: {artist} - {title}", "warning")
        return None

    last_err = None
    for vid_id in [chosen["id"]] + [c["id"] for c in cands[:max_attempts] if c["id"] != chosen["id"]]:
        try:
            info = _download_by_id(vid_id, outdir, artist=artist, title=title)
            if not info.get("file_path"):
                raise DownloadError("No se generó ningún fichero de audio")
            actual = info.get("youtube_duration") or 0.0
            # None = sin verificar (no se pudo comparar); 0.0 = se comparó y salió mal
            match = None
            if expected_duration and actual:
                tol = float(cfg.get("duration_tolerance", 0.20))
                diff = abs(actual - expected_duration) / max(expected_duration, 1)
                match = max(0.0, 1.0 - diff)
            return {
                "title": title,
                "artist": artist,
                "genre": genre,
                "language": language,
                "source": source,
                "status": M.STATUS_DOWNLOADED,
                "duration": expected_duration or actual,
                "youtube_id": info["youtube_id"],
                "youtube_url": info["youtube_url"],
                "file_path": info["file_path"],
                "file_size": info["file_size"],
                "match_score": round(match, 3) if match is not None else None,
                "added_at": None,  # lo rellena db
            }
        except Exception as e:  # noqa: BLE001
            last_err = e
            db.log_event(f"Fallo descarga {vid_id}: {e}", "warning")
            continue
    db.log_event(f"Descarga imposible: {artist} - {title} ({last_err})", "warning")
    return None


def download_playlist(url: str, *, genre: str = "other", language: str = M.LANG_OTHER,
                      source: str = M.SOURCE_ONDEMAND) -> list[dict]:
    """Descarga cada vídeo de una playlist de YouTube. Devuelve lista de pistas."""
    cfg = load_settings()
    outdir = Path(cfg["download_dir"])
    outdir.mkdir(parents=True, exist_ok=True)
    opts = _ydl_opts(outdir)
    opts["extract_flat"] = "in_playlist"
    with download_lock:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    entries = info.get("entries") or []
    results = []
    for e in entries:
        if not e or not e.get("id"):
            continue
        title = e.get("title") or ""
        artist = e.get("artist") or e.get("creator") or e.get("channel") or ""
        try:
            res = search_and_download(artist, title, genre=genre, language=language, source=source)
            if res and not res.get("skipped"):
                results.append(res)
        except Exception as ex:  # noqa: BLE001
            db.log_event(f"Fallo en playlist: {title}: {ex}", "warning")
    return results
