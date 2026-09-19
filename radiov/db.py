from __future__ import annotations

import datetime as _dt
import re
import sqlite3
from pathlib import Path
from typing import Any, Optional

from .config import DB_PATH, ensure_dirs, load_settings
from . import models as M

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    album TEXT,
    release_date TEXT,
    year INTEGER,
    genre TEXT,
    language TEXT,
    bpm REAL,
    tempo_est INTEGER DEFAULT 0,
    energy REAL,
    rms REAL,
    gain_db REAL,
    valence REAL,
    tags TEXT,
    era TEXT,
    is_remix INTEGER DEFAULT 0,
    explicit INTEGER DEFAULT 0,
    duration REAL,
    deezer_id TEXT,
    album_id TEXT,
    artist_id TEXT,
    cover_url TEXT,
    artist_image_url TEXT,
    cover_path TEXT,
    artist_image_path TEXT,
    youtube_id TEXT UNIQUE,
    youtube_url TEXT,
    file_path TEXT,
    file_size INTEGER,
    rank INTEGER,
    source TEXT,
    status TEXT,
    match_score REAL,
    added_at TEXT,
    analyzed_at TEXT,
    reviewed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist);
CREATE INDEX IF NOT EXISTS idx_tracks_genre ON tracks(genre);
CREATE INDEX IF NOT EXISTS idx_tracks_lang ON tracks(language);
CREATE INDEX IF NOT EXISTS idx_tracks_year ON tracks(year);
CREATE INDEX IF NOT EXISTS idx_tracks_status ON tracks(status);
CREATE INDEX IF NOT EXISTS idx_tracks_title ON tracks(title);
CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(album);
CREATE INDEX IF NOT EXISTS idx_tracks_bpm ON tracks(bpm);
CREATE INDEX IF NOT EXISTS idx_tracks_deezer ON tracks(deezer_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_tracks_deezer ON tracks(deezer_id) WHERE deezer_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tracks_source ON tracks(source);

CREATE TABLE IF NOT EXISTS blacklist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,          -- artist | song
    value TEXT NOT NULL,         -- nombre de artista, o titulo|artista
    reason TEXT,
    active INTEGER DEFAULT 1,
    created_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_blacklist ON blacklist(kind, value);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    level TEXT,
    message TEXT
);

CREATE TABLE IF NOT EXISTS agent_state (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS artist_pool (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    genre TEXT,
    language TEXT,
    expanded INTEGER DEFAULT 0,
    source TEXT,
    added_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_tracks_genre_year ON tracks(genre, year);
CREATE INDEX IF NOT EXISTS idx_tracks_status_added ON tracks(status, added_at);

CREATE TABLE IF NOT EXISTS artists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    deezer_id TEXT,
    image_url TEXT,
    image_path TEXT,
    nb_fan INTEGER,
    nb_album INTEGER,
    genre TEXT,
    language TEXT,
    track_count INTEGER DEFAULT 0,
    added_at TEXT
);

CREATE TABLE IF NOT EXISTS artist_albums (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artist_name TEXT,
    artist_id TEXT,
    album_id TEXT,
    title TEXT,
    year INTEGER,
    cover_url TEXT,
    added_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_artist_albums ON artist_albums(artist_name);

CREATE TABLE IF NOT EXISTS reactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER UNIQUE,
    liked INTEGER DEFAULT 0,
    skipped INTEGER DEFAULT 0,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_reactions_track ON reactions(track_id);

CREATE TABLE IF NOT EXISTS plays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER,
    played_at TEXT,
    source TEXT
);
CREATE INDEX IF NOT EXISTS idx_plays_track ON plays(track_id);
CREATE INDEX IF NOT EXISTS idx_plays_time ON plays(played_at);

CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    description TEXT,
    type TEXT DEFAULT 'user',
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS playlist_tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    playlist_id INTEGER,
    track_id INTEGER,
    position INTEGER,
    added_at TEXT,
    UNIQUE(playlist_id, track_id)
);
CREATE INDEX IF NOT EXISTS idx_pt_playlist ON playlist_tracks(playlist_id, position);

CREATE TABLE IF NOT EXISTS taste_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user TEXT DEFAULT 'default',
    liked_tracks INTEGER DEFAULT 0,
    preferred_genres TEXT,
    preferred_artists TEXT,
    preferred_eras TEXT,
    bpm_mean REAL,
    energy_mean REAL,
    updated_at TEXT
);
"""

_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS tracks_fts USING fts5(title, artist, album, content='', tokenize='unicode61');
CREATE TRIGGER IF NOT EXISTS trg_tracks_ai AFTER INSERT ON tracks BEGIN
  INSERT INTO tracks_fts(rowid, title, artist, album) VALUES (new.id, new.title, new.artist, new.album);
END;
CREATE TRIGGER IF NOT EXISTS trg_tracks_ad AFTER DELETE ON tracks BEGIN
  INSERT INTO tracks_fts(tracks_fts, rowid, title, artist, album) VALUES ('delete', old.id, old.title, old.artist, old.album);
END;
CREATE TRIGGER IF NOT EXISTS trg_tracks_au AFTER UPDATE ON tracks BEGIN
  INSERT INTO tracks_fts(tracks_fts, rowid, title, artist, album) VALUES ('delete', old.id, old.title, old.artist, old.album);
  INSERT INTO tracks_fts(rowid, title, artist, album) VALUES (new.id, new.title, new.artist, new.album);
END;
"""


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def get_conn() -> sqlite3.Connection:
    ensure_dirs()
    # `timeout` es el `busy_timeout` de SQLite: cuánto ESPERA si otro proceso tiene la base
    # cogida, antes de rendirse con «database is locked». Con 30 s iba justo: el análisis de
    # audio (que lee cada MP3) y el recolector escriben a la vez en esta misma base.
    conn = sqlite3.connect(str(DB_PATH), timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=60000;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        # migración: columna 'feat' para artistas invitados / colaboradores
        cols = [r[1] for r in conn.execute("PRAGMA table_info(tracks)").fetchall()]
        if "feat" not in cols:
            conn.execute("ALTER TABLE tracks ADD COLUMN feat TEXT")
        if "energy" not in cols:
            conn.execute("ALTER TABLE tracks ADD COLUMN energy REAL")
        if "rms" not in cols:
            conn.execute("ALTER TABLE tracks ADD COLUMN rms REAL")
        if "gain_db" not in cols:
            conn.execute("ALTER TABLE tracks ADD COLUMN gain_db REAL")
        if "valence" not in cols:
            conn.execute("ALTER TABLE tracks ADD COLUMN valence REAL")
        if "tags" not in cols:
            conn.execute("ALTER TABLE tracks ADD COLUMN tags TEXT")
        if "era" not in cols:
            conn.execute("ALTER TABLE tracks ADD COLUMN era TEXT")
        if "is_remix" not in cols:
            conn.execute("ALTER TABLE tracks ADD COLUMN is_remix INTEGER DEFAULT 0")
        if "explicit" not in cols:
            conn.execute("ALTER TABLE tracks ADD COLUMN explicit INTEGER DEFAULT 0")
        if "reviewed_at" not in cols:
            conn.execute("ALTER TABLE tracks ADD COLUMN reviewed_at TEXT")
        if "album_id" not in cols:
            conn.execute("ALTER TABLE tracks ADD COLUMN album_id TEXT")
        if "artist_id" not in cols:
            conn.execute("ALTER TABLE tracks ADD COLUMN artist_id TEXT")
        if "cover_url" not in cols:
            conn.execute("ALTER TABLE tracks ADD COLUMN cover_url TEXT")
        if "artist_image_url" not in cols:
            conn.execute("ALTER TABLE tracks ADD COLUMN artist_image_url TEXT")
        if "cover_path" not in cols:
            conn.execute("ALTER TABLE tracks ADD COLUMN cover_path TEXT")
        if "artist_image_path" not in cols:
            conn.execute("ALTER TABLE tracks ADD COLUMN artist_image_path TEXT")
        # --- Corrector (verificación contra internet y contra el propio audio) ---
        if "verificado_at" not in cols:
            conn.execute("ALTER TABLE tracks ADD COLUMN verificado_at TEXT")
        if "veredicto" not in cols:
            conn.execute("ALTER TABLE tracks ADD COLUMN veredicto TEXT")
        if "veredicto_detalle" not in cols:
            conn.execute("ALTER TABLE tracks ADD COLUMN veredicto_detalle TEXT")
        if "audio_huella" not in cols:
            conn.execute("ALTER TABLE tracks ADD COLUMN audio_huella REAL")
        # índices de columnas recién migradas
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_veredicto ON tracks(veredicto)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_era ON tracks(era)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_energy ON tracks(energy)")
        acols = [r[1] for r in conn.execute("PRAGMA table_info(artists)").fetchall()]
        if "image_path" not in acols:
            conn.execute("ALTER TABLE artists ADD COLUMN image_path TEXT")
        # búsqueda full-text (FTS5)
        conn.executescript(_FTS)
        # rellena el índice FTS con las filas existentes (si está vacío)
        n_fts = conn.execute("SELECT COUNT(*) FROM tracks_fts").fetchone()[0]
        n_tracks = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        if n_fts < n_tracks:
            conn.execute("DELETE FROM tracks_fts")
            rowids = [r[0] for r in conn.execute("SELECT id FROM tracks").fetchall()]
            for i in range(0, len(rowids), 500):
                chunk = rowids[i:i + 500]
                conn.executemany(
                    "INSERT INTO tracks_fts(rowid, title, artist, album) "
                    "SELECT id, title, artist, album FROM tracks WHERE id=?",
                    [(c,) for c in chunk])
        conn.execute("ANALYZE")
        conn.commit()
    finally:
        conn.close()


def log_event(message: str, level: str = "info") -> None:
    """Apunta un evento del recolector. **Nunca lanza.**

    POR QUÉ
    -------
    Esto se llamaba desde los manejadores de errores (`except Exception: db.log_event(...)`) y
    desde el bucle del agente. Si la base estaba cogida —otro proceso escribiendo, un análisis
    largo— el `INSERT` fallaba con «database is locked»… **dentro del propio manejador de
    errores**. La excepción se escapaba del `except`, mataba el HILO del recolector y el
    contenedor seguía «arriba» sin hacer absolutamente nada: ni descargaba, ni avisaba.
    Medido: el recolector llevaba días parado y desde fuera parecía vivo.

    Perder una línea del registro es molesto; perder el recolector entero, no. Si no se puede
    escribir en la base, se escribe en la salida de error, que al menos queda en `docker logs`.
    """
    try:
        conn = get_conn()
    except Exception as e:  # noqa: BLE001
        print(f"[events] no se pudo abrir la base para registrar «{message}»: {e}", flush=True)
        return
    try:
        conn.execute("INSERT INTO events(ts,level,message) VALUES(?,?,?)", (_now(), level, message))
        conn.commit()
    except Exception as e:  # noqa: BLE001
        print(f"[events] no se pudo registrar «{message}» ({level}): {e}", flush=True)
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def add_track(rec: dict, *, youtube_id: Optional[str] = None) -> int:
    """Inserta o actualiza una pista. Devuelve su id. La clave única es youtube_id."""
    yid = rec.get("youtube_id") or youtube_id
    conn = get_conn()
    try:
        if yid:
            row = conn.execute("SELECT id FROM tracks WHERE youtube_id=?", (yid,)).fetchone()
            if row:
                fields = [c for c in rec if c not in ("id", "youtube_id")]
                sets = ", ".join(f"{c}=?" for c in fields)
                conn.execute(f"UPDATE tracks SET {sets}, youtube_id=? WHERE id=?",
                             [rec.get(c) for c in fields] + [yid, row["id"]])
                conn.commit()
                return row["id"]
        # Segunda clave única: deezer_id. Si ya existe, actualiza en lugar de duplicar
        # (imprescindible para que el índice UNIQUE no rompa la inserción retroalimentada).
        did = rec.get("deezer_id")
        if did:
            row = conn.execute("SELECT id FROM tracks WHERE deezer_id=?", (did,)).fetchone()
            if row:
                fields = [c for c in rec if c not in ("id", "deezer_id", "youtube_id")]
                sets = ", ".join(f"{c}=?" for c in fields)
                conn.execute(f"UPDATE tracks SET {sets}, deezer_id=? WHERE id=?",
                             [rec.get(c) for c in fields] + [did, row["id"]])
                conn.commit()
                return row["id"]
        cols = list(rec.keys())
        q = ", ".join("?" * len(cols))
        verq = "?" if "youtube_id" in cols and rec.get("youtube_id") else "NULL"
        conn.execute(f"INSERT INTO tracks({','.join(cols)}) VALUES({q})", [rec.get(c) for c in cols])
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    finally:
        conn.close()


def track_exists(youtube_id: str) -> bool:
    conn = get_conn()
    try:
        return conn.execute("SELECT 1 FROM tracks WHERE youtube_id=?", (youtube_id,)).fetchone() is not None
    finally:
        conn.close()


# ------------------------------------------------------------------ ¿esta canción ya está?
# EL PROBLEMA
# -----------
# La misma canción llega escrita de mil maneras: «Feid - HAXTA EL DÍA FINAL», «FEID - Haxta el dia
# final (Official Video)», «Feid - Haxta el Día Final (feat. X)». Y de un mismo tema hay el vídeo
# oficial, el lyric video y el audio: **vídeos distintos para la misma canción**. Comparando por
# texto exacto (que es lo que se hacía) nada de eso coincide, así que el PC volvía a bajar y a enviar
# canciones que el servidor ya tenía, y en la biblioteca aparecían dos, tres y hasta cuatro fichas
# del mismo tema (una de ellas sin fichero, porque el fichero bueno era el de la otra).
#
# LA CLAVE
# --------
# `clave_cancion` deja «artista|título» en una forma comparable: sin acentos, sin mayúsculas, sin
# los paréntesis de relleno (feat., official video, lyrics, HD…) y sin signos. Lo que NO se quita es
# lo que distingue versiones de verdad —«remix», «en vivo», «extended»—: un remix y el original son
# canciones distintas y tienen que seguir siéndolo.
_RUIDO_PARENTESIS_RE = re.compile(
    r"\((?:[^)]*\b(?:official|oficial|video|vídeo|audio|lyric[s]?|letra|hd|4k|visualizer|"
    r"prod\.?|music\s+video|full\s+album)\b[^)]*)\)|\[[^\]]*\]",
    re.I)
_FEAT_RE = re.compile(r"(?:^|[\s(\[])(?:feat\.?|ft\.?|with|con)\s.*$", re.I)
_NO_ALFANUM_RE = re.compile(r"[^a-z0-9 ]+")


def clave_cancion(artist: str, title: str) -> str:
    """Clave normalizada «artista|título» para reconocer la MISMA canción escrita de otra forma.

    Se usa igual en el PC y en el servidor: si cada uno normalizara a su manera, la comprobación no
    serviría de nada.
    """
    import unicodedata

    def limpiar(texto: str) -> str:
        t = _RUIDO_PARENTESIS_RE.sub(" ", str(texto or ""))
        t = _FEAT_RE.sub(" ", t)
        t = "".join(c for c in unicodedata.normalize("NFD", t.lower())
                    if unicodedata.category(c) != "Mn")     # fuera tildes
        t = _NO_ALFANUM_RE.sub(" ", t)
        return " ".join(t.split())

    return f"{limpiar(artist)}|{limpiar(title)}"


def indice_de_claves() -> set[str]:
    """Todas las claves de la biblioteca, en UNA consulta.

    Así se pueden comprobar cientos de candidatos sin preguntar a la base por cada uno: el agente
    baraja 20-25 resultados por búsqueda y comprobar cada uno con una consulta aparte era trabajo
    repetido a cambio de nada.
    """
    conn = get_conn()
    try:
        return {clave_cancion(r["artist"] or "", r["title"] or "")
                for r in conn.execute("SELECT artist, title FROM tracks")}
    finally:
        conn.close()


def pista_existente(*, youtube_id: Optional[str] = None, deezer_id: Optional[str] = None,
                    artist: str = "", title: str = "",
                    claves: Optional[set] = None) -> Optional[int]:
    """El id de la ficha que YA representa esta canción, o None. **Sin bajar nada.**

    Se mira por orden de fiabilidad:
      1. el **vídeo** de YouTube (si es el mismo vídeo, es la misma grabación, se llame como se
         llame);
      2. el **id de Deezer** (misma ficha de tienda);
      3. la **clave normalizada** de artista y título (para los vídeos distintos de la misma
         canción, que es el caso que se colaba).
    """
    conn = get_conn()
    try:
        if youtube_id:
            r = conn.execute("SELECT id FROM tracks WHERE youtube_id=?", (youtube_id,)).fetchone()
            if r:
                return r["id"]
        if deezer_id:
            r = conn.execute("SELECT id FROM tracks WHERE deezer_id=?", (str(deezer_id),)).fetchone()
            if r:
                return r["id"]
        if artist or title:
            clave = clave_cancion(artist, title)
            if claves is None:
                claves = {clave_cancion(x["artist"] or "", x["title"] or "")
                          for x in conn.execute("SELECT artist, title FROM tracks")}
            if clave in claves:
                r = conn.execute("SELECT id FROM tracks WHERE lower(artist)=? AND lower(title)=?",
                                 (_norm(artist), _norm(title))).fetchone()
                if r:
                    return r["id"]
                # La clave coincide pero el texto exacto no: es la misma canción con otro nombre
                # («(Official Video)», «feat.»…). Se devuelve la primera que case por clave.
                for x in conn.execute("SELECT id, artist, title FROM tracks"):
                    if clave_cancion(x["artist"] or "", x["title"] or "") == clave:
                        return x["id"]
        return None
    finally:
        conn.close()


def track_exists_by_artist_title(artist: str, title: str) -> bool:
    return pista_existente(artist=artist, title=title) is not None


def track_exists_by_deezer(deezer_id: str) -> bool:
    if not deezer_id:
        return False
    conn = get_conn()
    try:
        return conn.execute("SELECT 1 FROM tracks WHERE deezer_id=?", (deezer_id,)).fetchone() is not None
    finally:
        conn.close()


def get_track_id_by_artist_title(artist: str, title: str) -> Optional[int]:
    conn = get_conn()
    try:
        r = conn.execute("SELECT id FROM tracks WHERE lower(artist)=? AND lower(title)=?",
                         (_norm(artist), _norm(title))).fetchone()
        return r["id"] if r else None
    finally:
        conn.close()


def update_track(track_id: int, **fields) -> None:
    if not fields:
        return
    conn = get_conn()
    try:
        sets = ", ".join(f"{c}=?" for c in fields)
        conn.execute(f"UPDATE tracks SET {sets} WHERE id=?", [fields[c] for c in fields] + [track_id])
        conn.commit()
    finally:
        conn.close()


def rellenar_huecos(track_id: int, campos: dict) -> list[str]:
    """Rellena SÓLO los campos que están vacíos en la ficha. Devuelve qué se rellenó.

    Es la fusión segura para cuando llega una canción que ya existe: lo que hay no se pisa nunca
    (puede ser mejor: un BPM medido, una carátula ya descargada, un `youtube_id` que ya funciona) y
    sólo se aprovecha lo nuevo para tapar huecos. Así, tener la misma canción dos veces no estropea
    la que ya sonaba.
    """
    if not campos:
        return []
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM tracks WHERE id=?", (track_id,)).fetchone()
        if not row:
            return []
        columnas = set(row.keys())
        rellenos: list[str] = []
        for campo, valor in campos.items():
            if campo in ("id",) or campo not in columnas or valor in (None, ""):
                continue
            if row[campo] in (None, ""):
                conn.execute(f"UPDATE tracks SET {campo}=? WHERE id=?", (valor, track_id))
                rellenos.append(campo)
        if rellenos:
            conn.commit()
        return rellenos
    finally:
        conn.close()


def delete_track(track_id: int) -> None:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM tracks WHERE id=?", (track_id,))
        conn.commit()
    finally:
        conn.close()


def _fts_match(query: str) -> Optional[str]:
    """Construye una consulta FTS5 segura a partir de un texto (solo palabras + prefijo)."""
    toks = re.findall(r"[0-9A-Za-zÁ-ÿ_]+", query or "")
    if not toks:
        return None
    return " ".join(f'"{t}"*' for t in toks)


def get_tracks(
    *,
    artist: Optional[str] = None,
    genre: Optional[str] = None,
    language: Optional[str] = None,
    year: Optional[int] = None,
    status: Optional[str] = None,
    only_analyzed: bool = False,
    search: Optional[str] = None,
    era: Optional[str] = None,
    tags: Optional[list[str]] = None,
    energy_min: Optional[float] = None,
    energy_max: Optional[float] = None,
    is_remix: Optional[bool] = None,
    order: str = "added_at DESC",
    limit: Optional[int] = None,
    offset: int = 0,
) -> list[dict]:
    conn = get_conn()
    try:
        sql = "SELECT * FROM tracks WHERE 1=1"
        params: list[Any] = []
        if artist:
            sql += " AND artist=?"
            params.append(artist)
        if genre:
            sql += " AND genre=?"
            params.append(genre)
        if language:
            sql += " AND language=?"
            params.append(language)
        if year:
            sql += " AND year=?"
            params.append(year)
        if era:
            sql += " AND era=?"
            params.append(era)
        if status:
            sql += " AND status=?"
            params.append(status)
        if only_analyzed:
            sql += " AND bpm IS NOT NULL"
        if energy_min is not None:
            sql += " AND energy >= ?"
            params.append(energy_min)
        if energy_max is not None:
            sql += " AND energy < ?"
            params.append(energy_max)
        if is_remix:
            sql += " AND is_remix=1"
        if tags:
            for tg in tags:
                sql += " AND tags LIKE ?"
                params.append(f"%{tg}%")
        if search:
            # búsqueda full-text (rápida) con recuperación a LIKE
            used_fts = False
            m = _fts_match(search)
            if m:
                try:
                    ids = [r[0] for r in conn.execute(
                        "SELECT rowid FROM tracks_fts WHERE tracks_fts MATCH ? ORDER BY bm25(tracks_fts) LIMIT 3000",
                        (m,)).fetchall()]
                    if ids:
                        ph = ",".join("?" * len(ids))
                        sql += f" AND id IN ({ph})"
                        params += ids
                        used_fts = True
                except Exception:  # noqa: BLE001
                    used_fts = False
            if not used_fts:
                like = f"%{search}%"
                sql += " AND (title LIKE ? OR artist LIKE ? OR album LIKE ?)"
                params += [like, like, like]
        sql += f" ORDER BY {order}"
        if limit:
            sql += " LIMIT ? OFFSET ?"
            params.append(int(limit))
            params.append(offset)
        else:
            sql += " LIMIT -1 OFFSET ?"
            params.append(offset)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def count_tracks(**filters) -> int:
    conn = get_conn()
    try:
        sql = "SELECT COUNT(*) AS n FROM tracks WHERE 1=1"
        params: list[Any] = []
        for col in ("artist", "genre", "language", "year", "status"):
            v = filters.get(col)
            if v is not None:
                sql += f" AND {col}=?"
                params.append(v)
        if filters.get("only_analyzed"):
            sql += " AND bpm IS NOT NULL"
        return conn.execute(sql, params).fetchone()["n"]
    finally:
        conn.close()


def get_track_by_id(track_id: int) -> Optional[dict]:
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM tracks WHERE id=?", (track_id,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def get_tracks_needing_bpm(limit: int = 200) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM tracks WHERE status=? AND bpm IS NULL ORDER BY id LIMIT ?",
            (M.STATUS_DOWNLOADED, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def distinct_values(col: str) -> list[str]:
    assert col in ("artist", "genre", "language")
    conn = get_conn()
    try:
        rows = conn.execute(f"SELECT DISTINCT {col} FROM tracks WHERE {col} IS NOT NULL ORDER BY {col}").fetchall()
        return [r[col] for r in rows]
    finally:
        conn.close()


def distinct_years() -> list[int]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT DISTINCT year FROM tracks WHERE year IS NOT NULL ORDER BY year DESC").fetchall()
        return [r["year"] for r in rows]
    finally:
        conn.close()


def distinct_eras() -> list[str]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT DISTINCT era FROM tracks WHERE era IS NOT NULL ORDER BY era").fetchall()
        return [r["era"] for r in rows]
    finally:
        conn.close()


def stats() -> dict:
    conn = get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) n FROM tracks").fetchone()["n"]
        downloaded = conn.execute("SELECT COUNT(*) n FROM tracks WHERE status=?", (M.STATUS_DOWNLOADED,)).fetchone()["n"]
        analyzed = conn.execute("SELECT COUNT(*) n FROM tracks WHERE bpm IS NOT NULL").fetchone()["n"]
        byg = {r["genre"]: r["n"] for r in conn.execute("SELECT genre, COUNT(*) n FROM tracks GROUP BY genre").fetchall()}
        byl = {r["language"]: r["n"] for r in conn.execute("SELECT language, COUNT(*) n FROM tracks GROUP BY language").fetchall()}
        size_bytes = conn.execute("SELECT COALESCE(SUM(file_size),0) s FROM tracks").fetchone()["s"]
        black_artists = conn.execute(
            "SELECT COUNT(*) n FROM blacklist WHERE kind=? AND active=1", (M.BLACKLIST_ARTIST,)).fetchone()["n"]
        black_songs = conn.execute(
            "SELECT COUNT(*) n FROM blacklist WHERE kind=? AND active=1", (M.BLACKLIST_SONG,)).fetchone()["n"]
        return {
            "total": total, "downloaded": downloaded, "analyzed": analyzed,
            "by_genre": byg, "by_language": byl,
            "size_bytes": size_bytes,
            "blacklist_artists": black_artists, "blacklist_songs": black_songs,
        }
    finally:
        conn.close()


def random_tracks(n: int = 15, mood: Optional[str] = None, genre: Optional[str] = None) -> list[dict]:
    """Muestra aleatoria del catálogo (para 'recomendaciones del día')."""
    import random
    conn = get_conn()
    try:
        sql = "SELECT * FROM tracks WHERE status=? AND file_path IS NOT NULL AND file_path != ''"
        params: list[Any] = [M.STATUS_DOWNLOADED]
        if genre:
            sql += " AND genre=?"
            params.append(genre)
        rows = conn.execute(sql, params).fetchall()
        tracks = [dict(r) for r in rows]
    finally:
        conn.close()
    if mood:
        tracks = [t for t in tracks if mood in (t.get("tags") or "")]
    if not tracks:
        return []
    k = min(n, len(tracks))
    return random.sample(tracks, k)


def catalog_progress() -> dict:
    """Cuántas canciones tienen BPM, energía, metadatos revisados y etiquetas."""
    conn = get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) n FROM tracks").fetchone()["n"]
        bpm = conn.execute("SELECT COUNT(*) n FROM tracks WHERE bpm IS NOT NULL").fetchone()["n"]
        energy = conn.execute("SELECT COUNT(*) n FROM tracks WHERE energy IS NOT NULL").fetchone()["n"]
        reviewed = conn.execute("SELECT COUNT(*) n FROM tracks WHERE reviewed_at IS NOT NULL").fetchone()["n"]
        tagged = conn.execute("SELECT COUNT(*) n FROM tracks WHERE tags IS NOT NULL AND tags!=''").fetchone()["n"]
    finally:
        conn.close()
    return {"total": total, "bpm": bpm, "energy": energy, "reviewed": reviewed, "tagged": tagged}


def stats_detail() -> dict:
    """Datos agregados para la página de estadísticas (anos, decadas, generos, artistas, BPM...)."""
    conn = get_conn()
    try:
        by_year = [dict(r) for r in conn.execute(
            "SELECT year, COUNT(*) n FROM tracks WHERE year IS NOT NULL GROUP BY year ORDER BY year").fetchall()]
        by_decade = [dict(r) for r in conn.execute(
            "SELECT CAST(year/10 AS INTEGER)*10 d, COUNT(*) n FROM tracks WHERE year IS NOT NULL GROUP BY d ORDER BY d").fetchall()]
        by_genre = [dict(r) for r in conn.execute(
            "SELECT COALESCE(genre,'other') g, COUNT(*) n FROM tracks GROUP BY g ORDER BY n DESC").fetchall()]
        by_lang = [dict(r) for r in conn.execute(
            "SELECT COALESCE(language,'other') l, COUNT(*) n FROM tracks GROUP BY l ORDER BY n DESC").fetchall()]
        top_artists = [dict(r) for r in conn.execute(
            "SELECT artist, COUNT(*) n FROM tracks WHERE artist IS NOT NULL GROUP BY artist ORDER BY n DESC LIMIT 25").fetchall()]
        by_source = [dict(r) for r in conn.execute(
            "SELECT COALESCE(source,'') s, COUNT(*) n FROM tracks GROUP BY s ORDER BY n DESC").fetchall()]
        bpm_values = [r["bpm"] for r in conn.execute(
            "SELECT bpm FROM tracks WHERE bpm IS NOT NULL").fetchall()]
        # por BPM/estado del catálogo
        bins = conn.execute(
            "SELECT CASE WHEN bpm IS NULL THEN 'sin_BPM' "
            "WHEN bpm<60 THEN '40-60' WHEN bpm<80 THEN '60-80' WHEN bpm<100 THEN '80-100' "
            "WHEN bpm<120 THEN '100-120' WHEN bpm<140 THEN '120-140' WHEN bpm<160 THEN '140-160' "
            "WHEN bpm<180 THEN '160-180' ELSE '180+' END b, COUNT(*) n "
            "FROM tracks GROUP BY b").fetchall()
        return {
            "by_year": by_year, "by_decade": by_decade, "by_genre": by_genre,
            "by_lang": by_lang, "top_artists": top_artists, "by_source": by_source,
            "bpm_values": bpm_values, "bpm_bins": [dict(r) for r in bins],
        }
    finally:
        conn.close()


# ---------- Lista negra ----------
def _norm(value: str) -> str:
    return " ".join(value.lower().split())


def add_blacklist(kind: str, value: str, reason: str = "") -> bool:
    conn = get_conn()
    try:
        cur = conn.execute("SELECT id, active FROM blacklist WHERE kind=? AND value=?", (kind, _norm(value))).fetchone()
        if cur:
            conn.execute("UPDATE blacklist SET active=1, reason=? WHERE id=?", (reason, cur["id"]))
            conn.commit()
            return False
        conn.execute("INSERT INTO blacklist(kind,value,reason,active,created_at) VALUES(?,?,?,?,?)",
                     (kind, _norm(value), reason, M.BLACKLIST_ACTIVE, _now()))
        conn.commit()
        return True
    finally:
        conn.close()


def remove_blacklist(blacklist_id: int) -> None:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM blacklist WHERE id=?", (blacklist_id,))
        conn.commit()
    finally:
        conn.close()


def get_blacklist(kind: Optional[str] = None) -> list[dict]:
    conn = get_conn()
    try:
        if kind:
            rows = conn.execute("SELECT * FROM blacklist WHERE kind=? AND active=1 ORDER BY value", (kind,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM blacklist WHERE active=1 ORDER BY kind, value").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def is_blacklisted(kind: str, value: str) -> bool:
    conn = get_conn()
    try:
        return conn.execute("SELECT 1 FROM blacklist WHERE kind=? AND value=? AND active=1",
                            (kind, _norm(value))).fetchone() is not None
    finally:
        conn.close()


def purge_blacklisted_tracks() -> int:
    """Elimina de la biblioteca y del disco las canciones (y artistas) de la lista negra."""
    conn = get_conn()
    try:
        black_artists = [r["value"] for r in conn.execute(
            "SELECT value FROM blacklist WHERE kind=? AND active=1", (M.BLACKLIST_ARTIST,)).fetchall()]
        black_songs = [r["value"] for r in conn.execute(
            "SELECT value FROM blacklist WHERE kind=? AND active=1", (M.BLACKLIST_SONG,)).fetchall()]
        deleted = 0
        tracks = conn.execute("SELECT id, artist, title, file_path FROM tracks").fetchall()
        for t in tracks:
            hit = _norm(t["artist"]) in black_artists or _norm(f"{t['title']}|{t['artist']}") in black_songs
            if hit:
                fp = t["file_path"]
                if fp:
                    try:
                        Path(fp).unlink(missing_ok=True)
                    except OSError:
                        pass
                conn.execute("DELETE FROM tracks WHERE id=?", (t["id"],))
                deleted += 1
        conn.commit()
        return deleted
    finally:
        conn.close()


# ---------- Estado del agente (persistente) ----------
def get_state(key: str, default: Optional[str] = None) -> Optional[str]:
    conn = get_conn()
    try:
        r = conn.execute("SELECT value FROM agent_state WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default
    finally:
        conn.close()


def set_state(key: str, value: str) -> None:
    conn = get_conn()
    try:
        conn.execute("INSERT INTO agent_state(key,value) VALUES(?,?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        conn.commit()
    finally:
        conn.close()


def recent_events(limit: int = 80) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------- Pool de artistas (para expansión continua del agente) ----------
def pool_add(name: str, genre: str, language: str, source: str = "") -> bool:
    """Añade un artista al pool (si no estaba). Devuelve True si era nuevo."""
    name = _norm(name)
    if not name:
        return False
    conn = get_conn()
    try:
        cur = conn.execute("SELECT id FROM artist_pool WHERE name=?", (name,)).fetchone()
        if cur:
            conn.commit()
            return False
        conn.execute("INSERT INTO artist_pool(name,genre,language,expanded,source,added_at) "
                     "VALUES(?,?,?,0,?,?)", (name, genre, language, source, _now()))
        conn.commit()
        return True
    finally:
        conn.close()


def pool_all(genre: Optional[str] = None, language: Optional[str] = None,
             expanded: Optional[int] = None, limit: int = 5000) -> list[dict]:
    conn = get_conn()
    try:
        sql = "SELECT * FROM artist_pool WHERE 1=1"
        params: list[Any] = []
        if genre:
            sql += " AND genre=?"
            params.append(genre)
        if language:
            sql += " AND language=?"
            params.append(language)
        if expanded is not None:
            sql += " AND expanded=?"
            params.append(expanded)
        sql += " ORDER BY id LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def pool_mark_expanded(name: str, genre: Optional[str] = None) -> None:
    name = _norm(name)
    conn = get_conn()
    try:
        conn.execute("UPDATE artist_pool SET expanded=1 WHERE name=?", (name,))
        conn.commit()
    finally:
        conn.close()


# ---------- Perfiles de artista ----------
def upsert_artist(name: str, *, deezer_id=None, image_url=None, nb_fan=None, nb_album=None,
                  genre=None, language=None) -> int:
    """Inserta o actualiza un perfil de artista (conservando las mayúsculas). Devuelve su id."""
    name = (name or "Desconocido").strip()
    genre = genre or "other"
    language = language or M.LANG_OTHER
    conn = get_conn()
    try:
        cur = conn.execute("SELECT id FROM artists WHERE lower(name)=lower(?)", (name,)).fetchone()
        if cur:
            sets = ["name=?"]
            vals: list[Any] = [name]
            for col, val in (("deezer_id", deezer_id), ("image_url", image_url),
                             ("nb_fan", nb_fan), ("nb_album", nb_album)):
                if val is not None:
                    sets.append(f"{col}=COALESCE({col}, ?)")
                    vals.append(val)
            for col, val in (("genre", genre), ("language", language)):
                if val is not None:
                    sets.append(f"{col}=?")
                    vals.append(val)
            conn.execute(f"UPDATE artists SET {', '.join(sets)} WHERE id=?", vals + [cur["id"]])
            conn.commit()
            return cur["id"]
        conn.execute("INSERT INTO artists(name,deezer_id,image_url,nb_fan,nb_album,genre,language,added_at) "
                     "VALUES(?,?,?,?,?,?,?,?)",
                     (name, deezer_id, image_url, nb_fan, nb_album, genre, language, _now()))
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    finally:
        conn.close()


def get_artists(limit: int = 500) -> list[dict]:
    conn = get_conn()
    try:
        conn.execute("UPDATE artists SET track_count = "
                     "(SELECT COUNT(*) FROM tracks WHERE lower(artist)=lower(artists.name))")
        conn.commit()
        rows = conn.execute("SELECT * FROM artists ORDER BY track_count DESC, name LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def set_artist_image_path(name: str, path: str) -> None:
    conn = get_conn()
    try:
        conn.execute("UPDATE artists SET image_path=? WHERE lower(name)=lower(?)", (path, name))
        conn.commit()
    finally:
        conn.close()


def set_artist_albums(artist_name: str, albums: list[tuple]) -> None:
    """albums: lista de (album_id, title, year, cover_url). Reemplaza la discografía del artista."""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM artist_albums WHERE artist_name=?", (artist_name,))
        now = _now()
        for alb in albums:
            conn.execute(
                "INSERT INTO artist_albums(artist_name, album_id, title, year, cover_url, added_at) "
                "VALUES(?,?,?,?,?,?)",
                (artist_name, str(alb[0]), alb[1], alb[2], alb[3], now))
        conn.commit()
    finally:
        conn.close()


def get_artist_albums(artist_name: str) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM artist_albums WHERE artist_name=? ORDER BY year DESC",
                            (artist_name,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------- Estilo Spotify: historial, reacciones, playlists ----------
def record_play(track_id: int, source: str = "player") -> None:
    conn = get_conn()
    try:
        conn.execute("INSERT INTO plays(track_id, played_at, source) VALUES (?,?,?)",
                     (track_id, _now(), source))
        conn.commit()
    finally:
        conn.close()


def react(track_id: int, liked: bool | None = None, skipped: bool | None = None) -> None:
    conn = get_conn()
    try:
        if conn.execute("SELECT 1 FROM reactions WHERE track_id=?", (track_id,)).fetchone():
            if liked is not None:
                conn.execute("UPDATE reactions SET liked=?, updated_at=? WHERE track_id=?",
                             (1 if liked else 0, _now(), track_id))
            if skipped is not None:
                conn.execute("UPDATE reactions SET skipped=?, updated_at=? WHERE track_id=?",
                             (1 if skipped else 0, _now(), track_id))
        else:
            conn.execute("INSERT INTO reactions(track_id, liked, skipped, updated_at) VALUES (?,?,?,?)",
                         (track_id, 1 if liked else 0, 1 if skipped else 0, _now()))
        conn.commit()
    finally:
        conn.close()


def get_reactions() -> dict[str, set[int]]:
    conn = get_conn()
    try:
        liked = {r["track_id"] for r in conn.execute("SELECT track_id FROM reactions WHERE liked=1")}
        skipped = {r["track_id"] for r in conn.execute("SELECT track_id FROM reactions WHERE skipped=1")}
        return {"liked": liked, "skipped": skipped}
    finally:
        conn.close()


def create_playlist(name: str, type: str = "user", description: str = "") -> int:
    conn = get_conn()
    try:
        conn.execute("INSERT INTO playlists(name,description,type,created_at,updated_at) VALUES(?,?,?,?,?)",
                     (name, description, type, _now(), _now()))
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    finally:
        conn.close()


def add_to_playlist(playlist_id: int, track_id: int) -> None:
    conn = get_conn()
    try:
        pos = conn.execute("SELECT COALESCE(MAX(position),0)+1 p FROM playlist_tracks WHERE playlist_id=?",
                           (playlist_id,)).fetchone()["p"]
        conn.execute("INSERT OR IGNORE INTO playlist_tracks(playlist_id, track_id, position, added_at) "
                     "VALUES(?,?,?,?)", (playlist_id, track_id, pos, _now()))
        conn.execute("UPDATE playlists SET updated_at=? WHERE id=?", (_now(), playlist_id))
        conn.commit()
    finally:
        conn.close()


def get_playlists() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT p.*, (SELECT COUNT(*) FROM playlist_tracks pt WHERE pt.playlist_id=p.id) n_tracks "
                            "FROM playlists p ORDER BY p.updated_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_playlist_tracks(playlist_id: int) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT t.* FROM playlist_tracks pt JOIN tracks t ON t.id=pt.track_id "
            "WHERE pt.playlist_id=? ORDER BY pt.position", (playlist_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------- Perfil de gustos y recomendación (content-based) ----------
def compute_taste_profile() -> dict:
    """Agrega tus 'me gusta' en un perfil (géneros/artistas/eras/BPM/energía preferidos)."""
    reac = get_reactions()
    liked = reac["liked"]
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM tracks WHERE id IN (%s)" % ",".join("?" * len(liked)),
                            list(liked)).fetchall() if liked else []
    finally:
        conn.close()
    tracks = [dict(r) for r in rows]
    genres = {}
    artists = {}
    eras = {}
    bpms, energies = [], []
    for t in tracks:
        if t.get("genre"):
            genres[t["genre"]] = genres.get(t["genre"], 0) + 1
        if t.get("artist"):
            artists[t["artist"]] = artists.get(t["artist"], 0) + 1
        if t.get("era"):
            eras[t["era"]] = eras.get(t["era"], 0) + 1
        if t.get("bpm"):
            bpms.append(t["bpm"])
        if t.get("energy") is not None:
            energies.append(t["energy"])
    prof = {
        "liked_tracks": len(tracks),
        "preferred_genres": [g for g, _ in sorted(genres.items(), key=lambda x: -x[1])[:6]],
        "preferred_artists": [a for a, _ in sorted(artists.items(), key=lambda x: -x[1])[:12]],
        "preferred_eras": [e for e, _ in sorted(eras.items(), key=lambda x: -x[1])[:6]],
        "bpm_mean": round(sum(bpms) / len(bpms), 1) if bpms else None,
        "energy_mean": round(sum(energies) / len(energies), 3) if energies else None,
    }
    conn = get_conn()
    try:
        conn.execute("UPDATE taste_profile SET liked_tracks=?, preferred_genres=?, preferred_artists=?, "
                     "preferred_eras=?, bpm_mean=?, energy_mean=?, updated_at=? WHERE user='default'",
                     (prof["liked_tracks"], ",".join(prof["preferred_genres"]),
                      ",".join(prof["preferred_artists"]), ",".join(prof["preferred_eras"]),
                      prof["bpm_mean"], prof["energy_mean"], _now()))
        if conn.total_changes == 0:
            conn.execute("INSERT INTO taste_profile(user, liked_tracks, preferred_genres, preferred_artists, "
                         "preferred_eras, bpm_mean, energy_mean, updated_at) VALUES('default',?,?,?,?,?,?,?)",
                         (prof["liked_tracks"], ",".join(prof["preferred_genres"]),
                          ",".join(prof["preferred_artists"]), ",".join(prof["preferred_eras"]),
                          prof["bpm_mean"], prof["energy_mean"], _now()))
        conn.commit()
    finally:
        conn.close()
    return prof


def _score_track(t: dict, prof: dict) -> float:
    s = 0.0
    if t.get("genre") in prof["preferred_genres"]:
        s += 2.5
    if t.get("era") in prof["preferred_eras"]:
        s += 1.5
    if t.get("artist") in prof["preferred_artists"]:
        s += 1.5
    if prof.get("bpm_mean") and t.get("bpm"):
        s += max(0.0, 1.0 - abs(t["bpm"] - prof["bpm_mean"]) / 100.0)
    if prof.get("energy_mean") is not None and t.get("energy") is not None:
        s += max(0.0, 1.0 - abs(t["energy"] - prof["energy_mean"]) / 0.6)
    return s


def recommend(n: int = 20, seed: Optional[dict] = None) -> list[dict]:
    """Recomienda canciones no escuchadas ni marcadas, según tu perfil de gustos."""
    import random
    prof = compute_taste_profile()
    reac = get_reactions()
    excluded = reac["liked"] | reac["skipped"] | {p["track_id"] for p in _recent_plays(300)}
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM tracks WHERE status=? AND file_path IS NOT NULL AND file_path != ''",
            (M.STATUS_DOWNLOADED,)).fetchall()
    finally:
        conn.close()
    cands = [dict(r) for r in rows if r["id"] not in excluded]
    if not cands:
        cands = [dict(r) for r in rows]
    if seed:
        prof_s = {"preferred_genres": seed.get("preferred_genres", prof["preferred_genres"]),
                  "preferred_eras": [seed.get("era")] if seed.get("era") else prof["preferred_eras"],
                  "preferred_artists": prof["preferred_artists"],
                  "bpm_mean": seed.get("bpm"), "energy_mean": seed.get("energy")}
        cands = sorted(cands, key=lambda t: -_score_track(t, prof_s))
    else:
        cands = sorted(cands, key=lambda t: -_score_track(t, prof))
    return cands[:n]


def _recent_plays(limit: int) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT DISTINCT track_id FROM plays ORDER BY played_at DESC LIMIT ?",
                            (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def daily_mix(n: int = 20) -> list[dict]:
    """Mix diario: una mezcla de recomendaciones y aleatorio."""
    import random
    recs = recommend(n // 2)
    ids = {t["id"] for t in recs}
    rest = [t for t in random_tracks(n) if t["id"] not in ids]
    return (recs + rest)[:n]
