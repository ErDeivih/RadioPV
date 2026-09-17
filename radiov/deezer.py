from __future__ import annotations

import time
from typing import Optional

import requests

from .config import load_settings
from . import db
from . import models as M
from . import charts
from . import hits

BASE = "https://api.deezer.com"


class DeezerError(Exception):
    pass


def _norm(x: Optional[str]) -> str:
    return "" if x is None else str(x)


def _year(release_date: Optional[str]) -> Optional[int]:
    if not release_date:
        return None
    try:
        return int(str(release_date)[:4])
    except ValueError:
        return None


class DeezerClient:
    """Cliente ligero de la API pública de Deezer (sin clave)."""

    def __init__(self):
        self.cfg = load_settings()
        self.min_rank = int(self.cfg.get("min_rank", 200000))
        self.min_rank_es = int(self.cfg.get("min_rank_es", 40000))

    def _get(self, path: str, params: dict) -> dict:
        url = f"{BASE}{path}"
        for attempt in range(3):
            try:
                r = requests.get(url, params=params, timeout=20)
                if r.status_code == 200:
                    return r.json()
                if r.status_code == 429:
                    time.sleep(2)
                    continue
                raise DeezerError(f"Deezer HTTP {r.status_code} para {url}")
            except requests.RequestException as e:
                if attempt == 2:
                    raise DeezerError(f"Error de red hacia Deezer: {e}")
                time.sleep(1)
        raise DeezerError(f"Deezer sin respuesta para {path}")

    # ---------- búsqueda ----------
    def search(self, query: str, limit: int = 40, index: int = 0) -> list[dict]:
        data = self._get("/search", {"q": query, "limit": limit, "index": index, "order": "RANKING"})
        return data.get("data", [])

    def search_one_track(self, artist: str, title: str) -> Optional[dict]:
        """Busca exactamente un tema dado artista+título (para peticiones bajo demanda)."""
        q = f'artist:"{artist}" track:"{title}"'
        data = self.search(q, limit=10, index=0)
        if not data:
            # intento más laxo
            q = f"{artist} {title}"
            data = self.search(q, limit=10, index=0)
        if not data:
            return None
        # elegir el resultado con mejor coincidencia de duración/título
        return data[0]

    def search_artist_id(self, name: str) -> Optional[int]:
        """Resuelve el id de Deezer de un artista por nombre."""
        try:
            data = self._get("/search/artist", {"q": name, "limit": 5})
        except DeezerError:
            return None
        for it in data.get("data", []):
            if it.get("name", "").strip().lower() == name.strip().lower():
                return it.get("id")
        if data.get("data"):
            return data["data"][0].get("id")
        return None

    def search_artists(self, name: str, limit: int = 5) -> list[dict]:
        try:
            data = self._get("/search/artist", {"q": name, "limit": limit})
        except DeezerError:
            return []
        return data.get("data", [])

    def search_albums(self, title: str, limit: int = 8) -> list[dict]:
        """Busca álbumes por título y devuelve los que coinciden."""
        try:
            data = self._get("/search/album", {"q": title, "limit": limit})
        except DeezerError:
            return []
        return data.get("data", [])

    def album_tracks(self, album_id: int) -> list[dict]:
        try:
            data = self._get(f"/album/{album_id}/tracks", {"limit": 100})
        except DeezerError:
            return []
        return data.get("data", [])

    def related_artists(self, artist_id: int, limit: int = 20) -> list[dict]:
        try:
            data = self._get(f"/artist/{artist_id}/related", {"limit": limit})
        except DeezerError:
            return []
        return data.get("data", [])

    def artist_top(self, artist_id: int, limit: int = 12) -> list[dict]:
        """Temas más populares de un artista."""
        try:
            data = self._get(f"/artist/{artist_id}/top", {"limit": limit})
        except DeezerError:
            return []
        return data.get("data", [])

    def track_detail(self, track_id: str) -> dict:
        return self._get(f"/track/{track_id}", {})

    def artist_detail(self, artist_id: str) -> dict:
        return self._get(f"/artist/{artist_id}", {})

    def album_detail(self, album_id: str) -> dict:
        """Detalle de álbum: trae `genres.data[].name` (los géneros reales viven en el álbum,
        no en /artist/{id}). Nuevo para generos_artistas.py."""
        return self._get(f"/album/{album_id}", {})

    def artist_albums(self, artist_id: str, limit: int = 30) -> list[dict]:
        try:
            data = self._get(f"/artist/{artist_id}/albums", {"limit": limit})
        except DeezerError:
            return []
        return data.get("data", [])

    # ---------- normalización de un resultado a nuestro modelo ----------
    def to_track(self, item: dict, *, genre: str, language: str, source: str) -> dict:
        artist = item.get("artist", {}).get("name", "") if isinstance(item.get("artist"), dict) else item.get("artist", "")
        album = item.get("album", {})
        album_name = album.get("title", "") if isinstance(album, dict) else ""
        release = item.get("release_date") or (album.get("release_date") if isinstance(album, dict) else None)
        return {
            "title": _norm(item.get("title_short") or item.get("title")),
            "artist": _norm(artist),
            "album": _norm(album_name),
            "release_date": _norm(release)[:10] or None,
            "year": _year(release),
            "genre": genre,
            "language": language,
            "bpm": item.get("bpm"),
            "duration": float(item.get("duration") or 0),
            "deezer_id": str(item.get("id")),
            "album_id": str(album.get("id")) if isinstance(album, dict) and album.get("id") else None,
            "rank": int(item.get("rank") or 0),
            "source": source,
        }

    def rank_ok(self, rank: int, language: str) -> bool:
        threshold = self.min_rank_es if language == M.LANG_ES else self.min_rank
        return rank >= threshold


def metadata_for(artist: str, title: str) -> dict:
    """Obtiene el año/álbum de una canción para peticiones bajo demanda."""
    client = DeezerClient()
    it = client.search_one_track(artist, title)
    if not it or not it.get("id"):
        return {}
    meta: dict = {"deezer_id": str(it.get("id"))}
    album = it.get("album")
    if isinstance(album, dict) and album.get("title"):
        meta["album"] = album.get("title")
    return enrich_meta(meta)


def enrich_meta(meta: dict) -> dict:
    """Completa el año y el álbum de un candidato consultando el detalle de la pista en Deezer."""
    deezer_id = meta.get("deezer_id")
    if not deezer_id or meta.get("year"):
        return meta
    try:
        client = DeezerClient()
        it = client.track_detail(deezer_id)
        release = it.get("release_date")
        if release:
            release = str(release)[:10]
            if not meta.get("release_date"):
                meta["release_date"] = release
            if not meta.get("year"):
                meta["year"] = _year(release)
        album = it.get("album")
        if isinstance(album, dict) and album.get("title") and not meta.get("album"):
            meta["album"] = album.get("title")
    except DeezerError:
        pass
    return meta


def discover_seed(seed: dict, client: DeezerClient) -> list[dict]:
    """Devuelve candidatos (normalizados) para una semilla concreta.

    Modos:
      - "hits_apple": éxitos actuales de un país (Apple Music) → artistas → expansión.
      - "year_hits": éxitos curados de diferentes años/épocas → artistas → expansión.
      - "explore": expande desde artistas semilla hacia artistas relacionados (crecimiento continuo, no listas cerradas).
      - "genre_artists": artistas de un género (modo clásico).
      - "query": búsqueda trending.
    """
    mode = seed.get("mode", "query")
    if mode == "hits_apple":
        return _discover_hits_apple(seed, client)
    if mode == "hits_40":
        return _discover_hits_40(seed, client)
    if mode == "year_sweep":
        return _discover_year_sweep(seed, client)
    if mode == "year_hits":
        return _discover_year_hits(seed, client)
    if mode == "explore":
        return _discover_explore(seed, client)
    if mode == "genre_artists":
        return _discover_by_artists(seed, client)
    return _discover_by_query(seed, client)


def _discover_hits_apple(seed: dict, client: DeezerClient) -> list[dict]:
    """Lista de éxitos actuales de un país. Añade los artistas al pool para expandirlos luego."""
    genre = seed.get("genre", "pop")
    language = seed.get("language", M.LANG_OTHER)
    country = seed.get("country", "es")
    limit = int(seed.get("limit", 30))
    out: list[dict] = []
    seen: set[str] = set()
    for rec in charts.apple_top_songs(country, limit=limit):
        artist = charts.primary_artist(rec.get("artist") or "")
        title = rec.get("title") or ""
        if not title or not artist:
            continue
        db.pool_add(artist, genre, language, "apple")
        key = f"{artist.lower()}|{title.lower()}"
        if key in seen or db.is_blacklisted(M.BLACKLIST_ARTIST, artist):
            continue
        seen.add(key)
        out.append({"artist": artist, "title": title, "genre": genre, "language": language,
                    "source": M.SOURCE_AGENT, "deezer_id": None, "rank": 0, "duration": 0})
    return out[:limit]


def _discover_hits_40(seed: dict, client: DeezerClient) -> list[dict]:
    """Lista de Los 40 (España). Mejor esfuerzo: si no devuelve nada, se ignora."""
    genre = seed.get("genre", "pop")
    language = seed.get("language", M.LANG_ES)
    limit = int(seed.get("limit", 20))
    out: list[dict] = []
    seen: set[str] = set()
    for rec in charts.los40_top(limit=limit * 2):
        artist = charts.primary_artist(rec.get("artist") or "")
        title = rec.get("title") or ""
        if not artist or not title:
            continue
        db.pool_add(artist, genre, language, "los40")
        key = f"{artist.lower()}|{title.lower()}"
        if key in seen or db.is_blacklisted(M.BLACKLIST_ARTIST, artist):
            continue
        seen.add(key)
        out.append({"artist": artist, "title": title, "genre": genre, "language": language,
                    "source": M.SOURCE_AGENT, "deezer_id": None, "rank": 0, "duration": 0})
    return out[:limit]


def _discover_year_sweep(seed: dict, client: DeezerClient) -> list[dict]:
    """Éxitos de años concretos (no solo actuales): busca por consultas de año.

    El revisor luego fija el año real. Evita resultados ruidosos (recopilaciones largas).
    """
    genre = seed.get("genre", "pop")
    language = seed.get("language", M.LANG_ES)
    years = seed.get("years") or [seed.get("year")]
    per_year = int(seed.get("per_year", 14))
    out: list[dict] = []
    seen: set[str] = set()
    for y in years:
        for q in (f"hits {y}", f"éxitos {y}", f"{y} hits", f"canciones {y}"):
            try:
                items = client.search(q, limit=15, index=0)
            except DeezerError:
                break
            for it in items:
                if len([x for x in out if x.get("year") == y]) >= per_year:
                    break
                track = client.to_track(it, genre=genre, language=language, source=M.SOURCE_AGENT)
                if not track["artist"] or len(track.get("title") or "") > 60:
                    continue
                key = f"{track['artist'].lower()}|{track['title'].lower()}"
                if key in seen or db.is_blacklisted(M.BLACKLIST_ARTIST, track["artist"]):
                    continue
                seen.add(key)
                track["year"] = y       # pista; el revisor confirmará el año real
                out.append(track)
            if len([x for x in out if x.get("year") == y]) >= per_year:
                break
    return out


def _discover_year_hits(seed: dict, client: DeezerClient) -> list[dict]:
    """Éxitos curados por épocas/años. Añade los artistas al pool para expandirlos luego."""
    genre = seed.get("genre", "pop")
    language = seed.get("language", M.LANG_ES)
    out: list[dict] = []
    for artist, title in hits.get_hits(language):
        db.pool_add(artist, genre, language, "year_hits")
        if db.is_blacklisted(M.BLACKLIST_ARTIST, artist):
            continue
        if db.track_exists_by_artist_title(artist, title):
            continue
        if db.is_blacklisted(M.BLACKLIST_SONG, f"{title}|{artist}"):
            continue
        out.append({"artist": artist, "title": title, "genre": genre, "language": language,
                    "source": M.SOURCE_AGENT, "deezer_id": None, "rank": 0, "duration": 0})
    return out


def _discover_explore(seed: dict, client: DeezerClient) -> list[dict]:
    """Expansión continua: desde artistas semilla hacia artistas relacionados (BFS)."""
    genre = seed.get("genre", "pop")
    language = seed.get("language", M.LANG_OTHER)
    seeds = [charts.primary_artist(s) for s in seed.get("seeds", [])]
    max_artists = int(client.cfg.get("max_artists_per_pass", 8))

    expanded = {p["name"] for p in db.pool_all(expanded=1)}
    names: list[str] = []
    for s in seeds:
        if s and s not in names and s not in expanded:
            names.append(s)
    for p in db.pool_all(expanded=0):
        if p["name"] not in names and p["name"] not in expanded:
            names.append(p["name"])

    out: list[dict] = []
    for name in names[:max_artists]:
        aid = client.search_artist_id(name)
        if not aid:
            db.pool_mark_expanded(name)
            continue
        for t in client.artist_top(aid, limit=int(client.cfg.get("max_per_artist", 10))):
            track = client.to_track(t, genre=genre, language=language, source=M.SOURCE_AGENT)
            if track["artist"] and db.is_blacklisted(M.BLACKLIST_ARTIST, track["artist"]):
                continue
            out.append(track)
        # añade artistas relacionados al pool para seguir expandiendo
        for ra in client.related_artists(aid, limit=12):
            rn = charts.primary_artist(ra.get("name", ""))
            if rn:
                db.pool_add(rn, genre, language, "related")
        db.pool_add(name, genre, language, "seed")
        db.pool_mark_expanded(name)
    return out


def _discover_by_artists(seed: dict, client: DeezerClient) -> list[dict]:
    genre = seed.get("genre", "other")
    language = seed.get("language", M.LANG_OTHER)
    artists = seed.get("artists", [])
    limit = int(client.cfg.get("max_per_artist", 10))
    out: list[dict] = []
    seen: set[str] = set()
    for name in artists:
        if db.is_blacklisted(M.BLACKLIST_ARTIST, name):
            continue
        aid = client.search_artist_id(name)
        if not aid:
            db.log_event(f"No se encontró artista en Deezer: {name}", "info")
            continue
        for it in client.artist_top(aid, limit=limit):
            track = client.to_track(it, genre=genre, language=language, source=M.SOURCE_AGENT)
            key = f"{track['artist'].lower()}|{track['title'].lower()}"
            if key in seen:
                continue
            seen.add(key)
            if db.is_blacklisted(M.BLACKLIST_ARTIST, track["artist"]):
                continue
            out.append(track)
        if seed.get("stop"):
            break
    return out


def _discover_by_query(seed: dict, client: DeezerClient) -> list[dict]:
    query = seed.get("query", "")
    genre = seed.get("genre", "other")
    language = seed.get("language", M.LANG_OTHER)
    max_res = int(client.cfg.get("max_results_per_query", 40))
    out: list[dict] = []
    for index in range(0, max_res, 50):
        try:
            items = client.search(query, limit=50, index=index)
        except DeezerError as e:
            db.log_event(f"Deezer: {e}", "warning")
            break
        if not items:
            break
        for it in items:
            rank = int(it.get("rank") or 0)
            if not client.rank_ok(rank, language):
                continue
            track = client.to_track(it, genre=genre, language=language, source=M.SOURCE_AGENT)
            if db.is_blacklisted(M.BLACKLIST_ARTIST, track["artist"]):
                continue
            out.append(track)
        if len(items) < 50:
            break
    return out
