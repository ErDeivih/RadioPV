from __future__ import annotations

import datetime
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from .config import load_settings, DATA_DIR, BASE_MUSIC, resolve_music


def _rel_music(path: str) -> str:
    """Ruta relativa a BASE_MUSIC (fallback: la misma si ya no cuelga de él)."""
    p = Path(path)
    try:
        return str(p.relative_to(BASE_MUSIC))
    except ValueError:
        return str(p)


def _rel_data(path: str) -> str:
    """Ruta relativa a DATA_DIR (fallback: la misma si ya no cuelga de él)."""
    p = Path(path)
    try:
        return str(p.relative_to(DATA_DIR))
    except ValueError:
        return str(p)
from . import models as M
from . import db

# Medianas aproximadas de BPM por género (usadas si no se analiza el audio).
GENRE_MEDIAN_BPM = {
    "reggaeton": 96, "pop": 118, "rock": 122, "bachata": 115, "salsa": 100,
    "merengue": 135, "latin": 100, "dance": 124, "rap": 88, "ballad": 68,
    "cumbia": 100, "corridos": 95, "flamenco": 110, "reggae": 90, "disco": 118,
    "house": 124, "electro": 126, "classical": 90, "instrumental": 90, "soundtrack": 95,
    "jazz": 105, "blues": 80, "metal": 140, "indie": 118, "folk": 110, "techno": 130,
    "lofibeat": 78, "gospel": 90, "banda": 105, "soul": 96,
    "other": 112,
}

_ACCENTS = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n"}


def _deaccent(s: str) -> str:
    for k, v in _ACCENTS.items():
        s = s.replace(k, v)
    return s


_LANG_HINTS = {
    "es": ["de", "la", "el", "los", "las", "mi", "tu", "te", "por", "que", "amor", "noche",
           "corazon", "baila", "vida", "quiero", "contigo", "como", "para", "nena", "mundo",
           "dame", "hasta", "fuego", "corazon", "puedes"],
    "it": ["amore", "vita", "notte", "cuore", "ti", "che", "per", "non", "solo", "dolce",
           "bella", "mi", "tua", "sempre", "anima"],
    "fr": ["amour", "vie", "nuit", "coeur", "je", "tu", "que", "pour", "pas", "mon", "mes",
           "toi", "chan", "dans", "avec", "tout"],
    "pt": ["amor", "vida", "noite", "coracao", "voce", "que", "para", "nao", "so", "minha",
           "teu", "mundo", "cancao", "sempre", "coisa"],
    "en": ["you", "the", "love", "me", "your", "my", "heart", "time", "never", "night",
           "baby", "tonight", "dream", "life", "world", "say", "feel", "away", "let", "how"],
}


def detect_language(title: str, artist: str = "") -> str:
    """Estima el idioma de una canción usando pistas léxicas. Devuelve es/en/it/fr/pt/other."""
    text = _deaccent(f"{title} {artist}".lower())
    words = re.findall(r"[a-z]+", text)
    if not words:
        return M.LANG_OTHER
    scores = {}
    for lang, hints in _LANG_HINTS.items():
        hits = sum(1 for h in hints if h in words)
        if hits:
            scores[lang] = hits
    if not scores:
        return M.LANG_OTHER
    best = max(scores, key=scores.get)
    # en español los marcadores son muy comunes; require al menos 2 para decir 'es'
    if best == "es" and scores["es"] < 2 and len(scores) > 1:
        return M.LANG_EN if scores.get("en") else M.LANG_OTHER
    return best


def guess_genre(title: str = "", artist: str = "") -> str:
    cfg = load_settings()
    kw = cfg.get("genre_keywords", {})
    text = _deaccent(f"{title} {artist}".lower())
    best, best_hits = "other", 0
    for genre, words in kw.items():
        hits = sum(1 for w in words if re.search(rf"\b{re.escape(w)}\b", text))
        if hits > best_hits:
            best, best_hits = genre, hits
    return best


# Género del ÁLBUM de Deezer (la fuente de verdad de los géneros). Mapa Deezer→nuestro vocabulario.
DEEZER_GENRE_MAP = {
    "metal": "rock", "heavy metal": "rock", "hard rock": "rock", "classic rock": "rock",
    "rock": "rock", "pop rock": "rock", "punk rock": "rock", "rock'n'roll": "rock",
    "rock and roll": "rock", "punk": "rock", "alternative rock": "rock", "indie rock": "rock",
    "indie": "rock", "alternative": "rock", "grunge": "rock", "glam rock": "rock",
    "progressive rock": "rock", "garage rock": "rock", "rockabilly": "rock",
    "reggaeton": "reggaeton", "reggaeton colombiano": "reggaeton", "latin": "latin",
    "latin pop": "latin", "pop": "pop", "pop-folk": "pop", "k-pop": "pop", "j-pop": "pop",
    "french pop": "pop", "italo-pop": "pop", "pop latino": "latin",
    "flamenco": "flamenco", "copla": "flamenco", "flamenco fusion": "flamenco",
    "rumba": "latin", "r&b": "r&b", "soul": "soul", "rap": "rap", "hip hop": "rap",
    "hip-hop": "rap", "hip-hop/rap": "rap", "hip hop/rap": "rap", "trap": "rap",
    "gangsta rap": "rap", "hip hop/r&b": "rap", "crunk": "rap",
    "salsa": "salsa", "salsa y sone": "salsa", "bachata": "bachata",
    "merengue": "merengue", "cumbia": "cumbia", "cumbia sonidera": "cumbia",
    "corridos": "corridos", "corridos tumbados": "corridos", "ranchera": "ballad",
    "dance": "dance", "edm": "dance", "dancehall": "dance", "electro dance": "dance",
    "electronic": "electro", "dance/electronic": "electro", "electronic/dance": "electro",
    "electro": "electro", "techno": "electro", "trance": "electro", "drum & bass": "electro",
    "dubstep": "electro", "house": "house", "deep house": "house", "tech house": "house",
    "progressive house": "house", "disco": "disco", "ballad": "ballad", "classical": "classical",
    "opera": "classical", "orchestral": "classical", "symphony": "classical", "orchestra": "classical",
    "instrumental": "instrumental", "soundtrack": "instrumental", "movies": "instrumental",
    "film score": "instrumental", "score": "instrumental", "movie soundtrack": "instrumental",
    "new age": "instrumental", "ambient": "instrumental", "reggae": "reggae", "ska": "reggae",
    "gospel": "soul", "soul music": "soul", "funk": "soul", "disco funk": "soul",
    "rhythm and blues": "r&b", "blues": "soul",
}
KNOWN_GENRES = set(DEEZER_GENRE_MAP.values())
# Override manual (va por encima de Deezer): lo que la heurística/álbum etiqueta mal y sabemos.
SOBRESCRIBIR = {
    "metallica": "rock", "loquillo": "rock", "loquillo y los trogloditas": "rock",
    "apocalyptica": "rock", "karamelo santo": "rock", "apollo 3": "rock",
    "el fary": "flamenco", "estopa": "flamenco", "camela": "flamenco", "los chichos": "flamenco",
    "drake": "rap", "eminem": "rap", "kendrick lamar": "rap", "ice cube": "rap",
    "50 cent": "rap", "j cole": "rap", "travis scott": "rap", "lil baby": "rap",
    "hans zimmer": "instrumental", "ludovico einaudi": "classical", "vangelis": "instrumental",
    "natanael cano": "corridos", "junior h": "corridos", "los angeles azules": "cumbia",
    "celia cruz": "salsa", "editors": "rock", "cat stevens": "rock",
}


def genero_de_album(album_id, client=None) -> str:
    """Género del artista a partir de un álbum de Deezer (`genres.data`). Si no es fiable → 'other'
    (regla: no inventar, NUNCA 'pop' por defecto). Necesita red; se pasa `client` o se crea."""
    from collections import Counter
    from .deezer import DeezerClient
    client = client or DeezerClient()
    try:
        alb = client.album_detail(str(album_id))
    except Exception:  # noqa: BLE001
        return "other"
    cont = Counter()
    for g in (alb.get("genres") or {}).get("data", []) or []:
        nm = (g.get("name") or "").strip().lower()
        if not nm:
            continue
        norm = DEEZER_GENRE_MAP.get(nm, nm)
        if norm in KNOWN_GENRES:
            cont[norm] += 1
    return cont.most_common(1)[0][0] if cont else "other"


def guess_genre(title: str = "", artist: str = "", album_id=None, client=None) -> str:
    """Clasifica por el ÁLBUM de Deezer (no por palabras clave). Fallback 'other'. Respeta el
    override manual de artistas conocidos."""
    if artist:
        a = artist.strip().lower()
        if a in SOBRESCRIBIR:
            return SOBRESCRIBIR[a]
    if album_id:
        return genero_de_album(album_id, client)
    return "other"


def con_cuota_decadas(candidates: list[dict], pre2000_q: int = 1, denom: int = 4) -> list[dict]:
    """C2 · reserva una cuota para pre-2000: de cada `denom` candidatos, hasta `pre2000_q` serán
    de antes del año 2000 (para que 'Clásicos' y la 'Cápsula del tiempo' no nazcan vacías)."""
    viejos = [c for c in candidates if (c.get("year") or 0) < 2000]
    nuevos = [c for c in candidates if (c.get("year") or 0) >= 2000]
    out, i = [], 0
    while nuevos or viejos:
        if i % denom < pre2000_q and viejos:
            out.append(viejos.pop(0))
        elif nuevos:
            out.append(nuevos.pop(0))
        else:
            out.append(viejos.pop(0))
        i += 1
    return out


def _ffmpeg_decode(src: Path, dst: Path, seconds: int) -> bool:
    try:
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-i", str(src), "-t", str(seconds), "-ac", "1", "-ar", "22050", str(dst)]
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        return r.returncode == 0 and dst.exists()
    except Exception:
        return False


def analyze_bpm(file_path: str, sample_seconds: Optional[int] = None) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Calcula BPM real, energía (RMS normalizada) y el RMS crudo con librosa.

    Devuelve (bpm, energy, rms) o (None, None, None) si no se puede.
    """
    p = resolve_music(file_path)
    if not p.exists():
        return None, None, None
    cfg = load_settings()
    seconds = sample_seconds or int(cfg.get("bpm_sample_seconds", 30))
    try:
        import numpy as np  # noqa: F401
        import librosa
        import soundfile as sf
    except Exception as e:  # noqa: BLE001
        db.log_event(f"librosa no disponible: {e}", "warning")
        return None, None, None

    wav = Path(tempfile.gettempdir()) / f"radiov_{p.stem}.wav"
    try:
        if not _ffmpeg_decode(p, wav, seconds):
            return None, None
        y, sr = sf.read(str(wav), dtype="float32")
        if y.ndim > 1:
            y = y.mean(axis=1)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr, start_bpm=120)
        bpm = float(np.atleast_1d(tempo)[0])
        if not (30 <= bpm <= 220):
            bpm = None
        rms = float(np.sqrt(np.mean(y ** 2)))
        energy = round(min(1.0, rms / 0.15), 3)  # normalizado aproximado a 0-1
        return (round(bpm, 1) if bpm else None), energy, round(rms, 6)
    except Exception as e:  # noqa: BLE001
        db.log_event(f"Fallo al analizar el audio de {p.name}: {e}", "warning")
        return None, None, None
    finally:
        if wav.exists():
            try:
                wav.unlink()
            except OSError:
                pass


def write_tags(file_path: str, track: dict) -> None:
    """Inserta metadatos ID3 en el fichero para que el reproductor los muestre bien."""
    p = resolve_music(file_path)
    if not p.exists() or p.suffix.lower() != ".mp3":
        return
    try:
        from mutagen.mp3 import EasyMP3
        audio = EasyMP3(str(p))
        audio["title"] = track.get("title") or ""
        audio["artist"] = track.get("artist") or ""
        if track.get("album"):
            audio["album"] = track["album"]
        if track.get("year"):
            audio["date"] = str(track["year"])
        audio["genre"] = M.GENRE_LABELS.get(track.get("genre"), track.get("genre") or "")
        audio.save()
    except Exception as e:  # noqa: BLE001
        db.log_event(f"No se pudieron escribir etiquetas en {p.name}: {e}", "warning")


def real_duration(file_path: str) -> Optional[float]:
    p = resolve_music(file_path)
    if not p.exists():
        return None
    try:
        from mutagen import File
        audio = File(str(p))
        if audio is not None and audio.info is not None:
            return float(audio.info.length)
    except Exception:  # noqa: BLE001
        pass
    return None


def derive_era(year) -> Optional[str]:
    if not year:
        return None
    y = int(year)
    if y < 1960:
        return "vintage"
    if y < 1970:
        return "60s"
    if y < 1980:
        return "70s"
    if y < 1990:
        return "80s"
    if y < 2000:
        return "90s"
    if y < 2010:
        return "00s"
    if y < 2020:
        return "10s"
    return "20s"


_REMIX_RE = re.compile(
    r"\b(remix|rmx|extended mix|original mix|radio mix|bootleg|dj mix|"
    # MASHUPS: canciones que mezclan dos o tres temas, hechas por gente en YouTube. Se marcan
    # como remix a proposito, para poder buscarlas y sacarlas aparte en la interfaz en vez de
    # que se pierdan mezcladas entre las canciones normales.
    # OJO: muchas NO llevan la palabra «mashup» en el titulo; van como «cancion 1 x cancion 2»
    # o «cancion 1 vs cancion 2», asi que hay que mirar tambien esos cruces.
    r"mashup|mash up|mash-up|megamix|blend|vs\.?|versus|"
    r"\sx\s|"
    # SESIONES Y MEZCLAS DE DJ: suelen ser canciones largas con muchas visitas, y van muy bien
    # para escuchar de un tiron con los auriculares.
    r"session|sessions|dj set|live set|party mix|mixtape|big room|"
    r"edit|vip mix|rework|refix|flip)\b",
    re.I,
)


def is_remix(title: str = "", artist: str = "") -> bool:
    """¿Es un remix, un mashup o una sesión de DJ? (marca de dos valores, para la BD)

    El detalle de QUÉ tipo es lo lleva `radiov.quality.clasificar`, que además limpia el `feat.`
    antes de mirar al artista: así «Basshunter - Now You're Gone (feat. DJ Mental Theo…)» deja de
    contar como sesión de DJ por el colaborador, que era un falso positivo real del catálogo.

    El «dj» se busca SIN exigir un espacio detrás, porque muchos nombres van pegados: `djpino`,
    `djmarko`… Con `\\bdj\\b` no coincidían y esos mashups se perdían sin marcar.
    """
    from .quality import clasificar

    if clasificar(title, artist) is not None:
        return True
    text = f"{title} {artist}"
    return bool(_REMIX_RE.search(text)) or bool(re.search(r"\bdj", text, re.I))


def tipo_de_pista(title: str = "", artist: str = "", duration: float | None = None) -> str | None:
    """'mashup' | 'remix' | 'sesion' | None. Un solo sitio decide qué es cada cosa."""
    from .quality import clasificar

    return clasificar(title, artist, duration)


def derive_tags(bpm=None, energy=None, genre="other", year=None, title="", artist="",
                language="other", is_remix_flag=False) -> list[str]:
    """Devuelve una lista de etiquetas/moods para clasificar la canción."""
    tags: set[str] = set()
    b = bpm
    if b is not None:
        if b < 70:
            tags |= {"meditacion", "tranquilidad", "relax", "chill", "energia baja"}
        elif b < 90:
            tags |= {"chill", "tranquilidad", "relax", "meditacion", "energia baja"}
        elif b < 110:
            tags |= {"chill", "concentracion", "trabajo", "romantica"}
        elif b < 130:
            tags |= {"fiesta", "fiesta temprana", "concentracion", "trabajo", "fiesta puntual"}
        elif b < 150:
            tags |= {"fiesta", "fiesta puntual", "perreo", "gimnasio", "correr", "fiesta tardia"}
        elif b < 175:
            tags |= {"perreo", "fiesta tardia", "fiesta", "gimnasio", "correr", "cardio", "energia alta"}
        else:
            tags |= {"sprint", "energia alta", "fiesta tardia", "perreo"}
    else:
        tags.add("sin bpm")
    if energy is not None:
        if energy >= 0.55:
            tags.add("energia alta")
        elif energy <= 0.3:
            tags.add("energia baja")
    gen = (genre or "").lower()
    g = {"reggaeton": {"perreo", "urbano", "fiesta"},
         "latin": {"urbano", "fiesta"},
         "dance": {"fiesta", "house"},
         "disco": {"fiesta", "disco"},
         "house": {"fiesta", "house"},
         "electro": {"fiesta", "house"},
         "classical": {"clasica", "instrumental", "relax", "concentracion"},
         "instrumental": {"instrumental", "clasica"},
         "soundtrack": {"instrumental", "clasica"},
         "rock": {"gimnasio", "fiesta"},
         "rap": {"trabajo", "gimnasio"},
         "ballad": {"romantica", "tranquilidad"},
         "salsa": {"fiesta", "fiesta tardia"},
         "merengue": {"fiesta", "perreo"},
         "bachata": {"romantica", "tranquilidad", "fiesta tardia"},
         "cumbia": {"fiesta", "perreo"},
         "corridos": {"trabajo"},
         "flamenco": {"relax", "concentracion"},
         "reggae": {"chill", "relax"},
         "jazz": {"chill", "relax", "concentracion", "trabajo"},
         "blues": {"triste", "chill", "relax"},
         "metal": {"gimnasio", "energia alta", "epica"},
         "indie": {"indie", "trabajo", "chill"},
         "folk": {"folk", "acustico", "relax"},
         "techno": {"fiesta", "house", "fiesta tardia"},
         "lofibeat": {"lofi", "chill", "concentracion", "estudio"},
         "gospel": {"clasica", "soul", "feliz"},
         "banda": {"fiesta", "perreo"},
         "soul": {"soul", "romantica", "chill"},
        }.get(gen, set())
    tags |= g
    if is_remix_flag:
        tags.add("remix")
    era = derive_era(year)
    if era:
        tags.add(era)
    if language == "es" and gen == "pop" and era == "00s":
        tags.add("pop es 2000s")
    if language == "es" and gen == "pop":
        tags.add("pop es")
    if language == "es":
        tags.add("es")
    if language == "en":
        tags.add("en")
    return sorted(tags)


def catalog_track(rec: dict) -> dict:
    """Rellena metadatos, idioma, género y BPM de una pista ya descargada."""
    cfg = load_settings()
    rec = dict(rec)
    fp = rec.get("file_path")
    if fp:
        dur = real_duration(fp)
        if dur:
            rec["duration"] = round(dur, 1)

    # idioma
    if not rec.get("language"):
        rec["language"] = detect_language(rec.get("title", ""), rec.get("artist", ""))
    # género
    if not rec.get("genre") or rec.get("genre") == "other":
        if rec.get("title") or rec.get("artist"):
            rec["genre"] = guess_genre(rec.get("title", ""), rec.get("artist", ""))
        else:
            rec["genre"] = rec.get("genre") or "other"

    # BPM + energía
    rec["tempo_est"] = M.TEMPO_UNKNOWN
    if fp and cfg.get("analyze_bpm", True):
        bpm, energy, rms = analyze_bpm(fp)
        if bpm:
            rec["bpm"] = bpm
            rec["tempo_est"] = M.TEMPO_ANALYZED
        if energy is not None:
            rec["energy"] = energy
        if rms is not None:
            rec["rms"] = rms
    if not rec.get("bpm") and cfg.get("use_genre_fallback_bpm", True):
        rec["bpm"] = float(GENRE_MEDIAN_BPM.get(rec.get("genre", "other"), 110))
        rec["tempo_est"] = M.TEMPO_BY_GENRE

    # era, remix y etiquetas de mood
    if not rec.get("era"):
        rec["era"] = derive_era(rec.get("year"))
    if rec.get("is_remix") is None:
        rec["is_remix"] = 1 if is_remix(rec.get("title", ""), rec.get("artist", "")) else 0
    if not rec.get("tags"):
        rec["tags"] = ", ".join(derive_tags(
            bpm=rec.get("bpm"), energy=rec.get("energy"), genre=rec.get("genre"),
            year=rec.get("year"), title=rec.get("title"), artist=rec.get("artist"),
            language=rec.get("language"), is_remix_flag=bool(rec.get("is_remix"))))

    if fp:
        write_tags(fp, rec)
    rec["analyzed_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    return rec


def _safe(s) -> str:
    """Sanitiza un texto para usarlo como nombre de carpeta/archivo en Windows."""
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", str(s or "")).strip().rstrip(".")
    return s[:120].strip() or "sin_nombre"


def organize_track(track: dict) -> Optional[str]:
    """Mueve/copia un tema a catalogada organizado por artista/año/álbum (con etiquetas).

    Devuelve la nueva ruta del fichero (o la original si no se pudo organizar).
    """
    cfg = load_settings()
    src = track.get("file_path")
    if not src:
        return src
    # Trabajar siempre con ruta absoluta internamente (acepta file_path relativo de la BD)
    src = str(resolve_music(src))
    if not Path(src).exists():
        return track.get("file_path")
    catalog = Path(cfg["catalog_dir"])
    artist = _safe(track.get("artist") or "Desconocido")
    album = _safe(track.get("album")) if track.get("album") else None
    year = track.get("year")
    mode = cfg.get("organize_by", "artist_album")

    if mode == "artist_year":
        sub = f"{year} - {album}" if (album and year) else (str(year) if year else album)
    elif album and year:
        sub = f"[{year}] {album}"
    elif album:
        sub = album
    elif year:
        sub = str(year)
    else:
        sub = None

    folder = Path(catalog) / artist / (sub if sub else "")
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        db.log_event(f"No se pudo crear carpeta de catálogo: {e}", "warning")
        return src

    ext = Path(src).suffix or ".mp3"
    base = _safe(f"{artist} - {track.get('title') or 'tema'}")
    dest = folder / f"{base}{ext}"
    i = 2
    while dest.exists() and dest.resolve() != Path(src).resolve():
        dest = folder / f"{base} ({i}){ext}"
        i += 1
    if dest.resolve() == Path(src).resolve():
        return str(dest)  # ya está en su sitio
    try:
        # Si el fichero ya está en catalogada (re-organización), se MUEVE; si viene de la
        # descarga en bruto, se copia (conservando la copia en descargas si keep_raw_copy).
        already_cataloged = str(Path(src).resolve()).startswith(str(catalog.resolve()))
        if already_cataloged or not cfg.get("keep_raw_copy", True):
            os.replace(src, dest)
        else:
            shutil.copy2(src, dest)
        write_tags(str(dest), track)
        return str(dest)
    except OSError as e:
        db.log_event(f"Fallo al organizar {track.get('title')}: {e}", "warning")
        return src


def clean_raw_folder() -> int:
    """Renombra los ficheros 'en bruto' a 'Artista - Título' y elimina intermedios (.webm/.m4a/...)."""
    cfg = load_settings()
    raw = Path(cfg["download_dir"])
    if not raw.exists():
        return 0
    renamed = 0
    conn = db.get_conn()
    try:
        rows = conn.execute("SELECT youtube_id, artist, title FROM tracks WHERE youtube_id IS NOT NULL").fetchall()
    finally:
        conn.close()
    for r in rows:
        src = raw / f"{r['youtube_id']}.mp3"
        if not src.exists():
            continue
        base = _safe(f"{r['artist']} - {r['title']}")
        dest = raw / f"{base}.mp3"
        i = 2
        while dest.exists() and dest.resolve() != src.resolve():
            dest = raw / f"{base} ({i}).mp3"
            i += 1
        if dest.resolve() != src.resolve():
            try:
                os.replace(src, dest)
                renamed += 1
            except OSError:
                pass
    # intermedios y temporales
    removed = 0
    for p in raw.glob("*"):
        if p.name == "_tmp" and p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
            continue
        if p.suffix.lower() in (".webm", ".m4a", ".opus", ".part", ".ytdl"):
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass
    if renamed or removed:
        db.log_event(f"Descargas limpias: {renamed} renombradas, {removed} intermedios borrados", "info")
    return renamed


def reorganize_library() -> int:
    """Reorganiza todas las pistas existentes en catalogada y limpia la carpeta de descargas."""
    cfg = load_settings()
    conn = db.get_conn()
    try:
        rows = conn.execute("SELECT * FROM tracks WHERE file_path IS NOT NULL AND file_path != ''").fetchall()
    finally:
        conn.close()
    moved = 0
    for r in rows:
        t = dict(r)
        new = organize_track(t)
        if new and new != t.get("file_path"):
            size = Path(new).stat().st_size if Path(new).exists() else 0
            db.update_track(t["id"], file_path=_rel_music(new), file_size=size)
            moved += 1
    clean_raw_folder()
    if moved:
        db.log_event(f"Reorganizadas {moved} canciones en catalogada", "info")
    return moved


def _true_song_year(client, detail: dict, track: dict) -> Optional[int]:
    """Año REAL de la canción: prefiere el álbum de estudio original (no recopilaciones/re-ediciones)."""
    alb = detail.get("album") or {}
    rtype = (alb.get("record_type") or "").lower()
    rel = detail.get("release_date")

    def _y(s):
        try:
            return int(str(s)[:4]) if str(s)[:4].isdigit() else None
        except (TypeError, ValueError):
            return None

    if rtype in ("album", "ep"):
        return _y(rel)
    # recopilación/live/etc: busca el álbum de estudio original del tema
    try:
        q = f"{track.get('artist', '')} {track.get('title', '')}".strip()
        for it in client.search(q, limit=8):
            d2 = client.track_detail(str(it.get("id")))
            a2 = d2.get("album") or {}
            if (a2.get("record_type") or "").lower() in ("album", "ep") and d2.get("release_date"):
                yy = _y(d2["release_date"])
                if yy:
                    return yy
    except Exception:  # noqa: BLE001
        pass
    return _y(rel)


def review_metadata(track: dict) -> Optional[dict]:
    """Relee los metadatos desde Deezer (año, álbum, artistas/feat) y corrige la ficha.

    Usado por el 'agente revisor': pasa canción a canción para reafirmar los datos por si
    no se extrajeron bien la primera vez (sobre todo colaboraciones/feat).
    """
    from . import deezer as dz
    try:
        client = dz.DeezerClient()
    except Exception:  # noqa: BLE001
        return None
    did = track.get("deezer_id")
    detail = None
    try:
        if did:
            detail = client.track_detail(did)
        else:
            it = client.search_one_track(track.get("artist", ""), track.get("title", ""))
            if it and it.get("id"):
                did = str(it["id"])
                detail = client.track_detail(did)
    except Exception:  # noqa: BLE001
        return None
    if not detail:
        return None

    updates: dict = {}
    da = detail.get("artist")
    main = da.get("name") if isinstance(da, dict) else ""
    if main and main.strip().lower() not in ((track.get("artist") or "").strip().lower(),):
        updates["artist"] = main

    rel = detail.get("release_date")
    true_year = _true_song_year(client, detail, track)
    if true_year and (not track.get("year") or int(track.get("year")) != true_year):
        updates["year"] = true_year
    if rel:
        updates["release_date"] = str(rel)[:10]
    alb = detail.get("album")
    if isinstance(alb, dict) and alb.get("title") and alb["title"] != track.get("album"):
        updates["album"] = alb["title"]
    if isinstance(alb, dict):
        if alb.get("id") and str(alb["id"]) != track.get("album_id"):
            updates["album_id"] = str(alb["id"])
        cover = alb.get("cover_xl") or alb.get("cover_big") or alb.get("cover_medium")
        if cover and cover != track.get("cover_url"):
            updates["cover_url"] = cover
    # perfil / foto del artista
    da = detail.get("artist")
    if isinstance(da, dict):
        if da.get("id") and str(da["id"]) != track.get("artist_id"):
            updates["artist_id"] = str(da["id"])
        pic = da.get("picture_xl") or da.get("picture_big") or da.get("picture_medium")
        if pic and pic != track.get("artist_image_url"):
            updates["artist_image_url"] = pic
        if da.get("name"):
            db.upsert_artist(da["name"], deezer_id=str(da["id"]) if da.get("id") else None,
                             image_url=pic, nb_fan=da.get("nb_fan"), nb_album=da.get("nb_album"),
                             genre=track.get("genre"), language=track.get("language"))

    contribs = detail.get("contributors") or []
    names = [c.get("name") for c in contribs if c.get("name")]
    if names:
        main_low = (main or track.get("artist") or "").strip().lower()
        feat = ", ".join(n for n in names if n.strip().lower() != main_low)
        if feat and feat != track.get("feat"):
            updates["feat"] = feat

    if detail.get("explicit_lyrics") is not None:
        updates["explicit"] = 1 if detail["explicit_lyrics"] else 0

    # re-deriva era / remix / etiquetas con los datos corregidos
    merged = {**track, **updates}
    era = derive_era(merged.get("year"))
    if era and era != track.get("era"):
        updates["era"] = era
    rem = 1 if is_remix(merged.get("title", ""), merged.get("artist", "")) else 0
    if rem != track.get("is_remix"):
        updates["is_remix"] = rem
    if not merged.get("tags"):
        updates["tags"] = ", ".join(derive_tags(
            bpm=merged.get("bpm"), energy=merged.get("energy"), genre=merged.get("genre"),
            year=merged.get("year"), title=merged.get("title"), artist=merged.get("artist"),
            language=merged.get("language"), is_remix_flag=bool(rem)))

    if updates:
        write_tags(track.get("file_path"), {**track, **updates})
        db.update_track(track["id"], **updates)
        # si cambió año/álbum/artista, reubica el fichero en su carpeta correcta
        if updates.get("year") or updates.get("album") or updates.get("artist"):
            try:
                new_path = organize_track({**track, **updates})
                if new_path and new_path != track.get("file_path"):
                    size = Path(new_path).stat().st_size if Path(new_path).exists() else 0
                    db.update_track(track["id"], file_path=_rel_music(new_path), file_size=size)
            except Exception:  # noqa: BLE001
                pass
    return updates or None


def analyze_energy_missing(limit: int = 20) -> int:
    """Rellena la energía (audio) de canciones que aún no la tienen. Tararea un lote por pasada."""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM tracks WHERE energy IS NULL AND file_path IS NOT NULL AND file_path!='' LIMIT ?",
            (limit,)).fetchall()
    finally:
        conn.close()
    n = 0
    for r in rows:
        t = dict(r)
        _, energy, rms = analyze_bpm(t["file_path"])
        if energy is not None:
            tags = ", ".join(derive_tags(
                bpm=t.get("bpm"), energy=energy, genre=t.get("genre"), year=t.get("year"),
                title=t.get("title"), artist=t.get("artist"), language=t.get("language"),
                is_remix_flag=bool(t.get("is_remix"))))
            db.update_track(t["id"], energy=energy, rms=rms, tags=tags)
            n += 1
    return n


def analizar_gain_missing(limit: int = 20) -> int:
    """Rellena `gain_db` (normalización de volumen a -14 LUFS, ffmpeg loudnorm) de pistas que no lo
    tienen. Con `metadata_strict=True` una pista se marca 'incompleta' si le falta gain_db, y sin
    esto las descargas nuevas se quedarían 'incompleta' para siempre (la app solo publica
    'descargada'). Idempotente y por lotes (como analyze_energy_missing).

    LAS SESIONES LARGAS NO CABÍAN EN EL TIEMPO
    ------------------------------------------
    Medido en el PC: `ffmpeg loudnorm` sobre una sesión de UNA HORA tarda **173 s**, y el límite de
    este subprocess eran **150 s**. Al pasarse, saltaba `TimeoutExpired`, el `except` lo tragaba y la
    ganancia no se calculaba nunca: la sesión se quedaba 'incompleta' para siempre y no llegaba a la
    aplicación. Es decir, justo el contenido más largo —sesiones de DJ, mezclas de una hora, que es
    lo que el usuario más escucha— era el único que no podía publicarse NUNCA.

    Ahora, para ficheros de más de 15 minutos se mide una **muestra de 5 minutos por el medio** y se
    usa esa ganancia. Es una decisión consciente: el volumen de una sesión es constante de principio
    a fin, y lo que se busca es que toda la biblioteca suene al mismo nivel; medir 5 minutos del
    centro da ese dato en 15 s en vez de en 3 minutos por canción.
    """
    import json
    import subprocess
    MUESTRA_MINIMA = 900.0        # a partir de aquí (15 min) se mide una muestra
    LARGO_MUESTRA = 300.0         # 5 minutos
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT id, file_path, duration FROM tracks WHERE gain_db IS NULL "
            "AND file_path IS NOT NULL AND file_path != '' LIMIT ?", (limit,)).fetchall()
    finally:
        conn.close()
    n = 0
    for r in rows:
        t = dict(r)
        p = resolve_music(t["file_path"])
        if not p.exists():
            continue
        dur = float(t.get("duration") or 0)
        muestra = dur > MUESTRA_MINIMA
        # `-ss`/`-t` ANTES de `-i`: así ffmpeg salta directo al trozo y no decodifica lo anterior.
        extra = (["-ss", f"{max(0.0, dur / 2 - LARGO_MUESTRA / 2):.0f}",
                  "-t", f"{LARGO_MUESTRA:.0f}"] if muestra else [])
        try:
            rr = subprocess.run(
                ["ffmpeg", *extra, "-i", str(p),
                 "-af", "loudnorm=I=-14:print_format=json", "-f", "null", "-"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=600 if muestra else 300)
            if rr.returncode != 0:
                continue
            js = json.loads(rr.stderr[rr.stderr.rfind("{"): rr.stderr.rfind("}") + 1])
            i = float(js.get("input_i"))
        except subprocess.TimeoutExpired:
            db.log_event(f"⏱️ La ganancia tardó demasiado y se salta: {t['file_path']}", "warning")
            continue
        except Exception:  # noqa: BLE001
            continue
        if i is not None:
            db.update_track(t["id"], gain_db=round(-14.0 - i, 2))
            n += 1
    return n


def enrich_media(limit: int = 200) -> int:
    """Rellena carátula de álbum y foto del artista (y perfiles) de canciones que no las tienen."""
    from . import deezer as dz
    client = dz.DeezerClient()
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM tracks WHERE file_path IS NOT NULL AND file_path != '' "
            "AND (cover_url IS NULL OR artist_image_url IS NULL OR artist_id IS NULL) LIMIT ?",
            (limit,)).fetchall()
    finally:
        conn.close()
    n = 0
    for r in rows:
        t = dict(r)
        did = t.get("deezer_id")
        detail = None
        try:
            if did:
                detail = client.track_detail(did)
            else:
                it = client.search_one_track(t.get("artist", ""), t.get("title", ""))
                if it and it.get("id"):
                    did = str(it["id"])
                    detail = client.track_detail(did)
        except Exception:  # noqa: BLE001
            continue
        if not detail:
            continue
        upd: dict = {}
        alb = detail.get("album") if isinstance(detail.get("album"), dict) else {}
        if alb.get("id"):
            upd["album_id"] = str(alb["id"])
        cover = alb.get("cover_xl") or alb.get("cover_big") or alb.get("cover_medium")
        if cover:
            upd["cover_url"] = cover
        da = detail.get("artist") if isinstance(detail.get("artist"), dict) else {}
        if da.get("id"):
            upd["artist_id"] = str(da["id"])
        pic = da.get("picture_xl") or da.get("picture_big") or da.get("picture_medium")
        if pic:
            upd["artist_image_url"] = pic
        if not t.get("deezer_id") and did and not db.track_exists_by_deezer(did):
            upd["deezer_id"] = did
        if upd:
            try:
                db.update_track(t["id"], **upd)
            except Exception:  # noqa: BLE001  UNIQUE deezer_id duplicado → reintenta sin él
                upd.pop("deezer_id", None)
                if upd:
                    db.update_track(t["id"], **upd)
        if da.get("name"):
            db.upsert_artist(da["name"], deezer_id=str(da.get("id")) if da.get("id") else None,
                             image_url=pic, nb_fan=da.get("nb_fan"), nb_album=da.get("nb_album"),
                             genre=t.get("genre"), language=t.get("language"))
        n += 1
    if n:
        db.log_event(f"🖼️ Carátulas/fotos rellenadas en {n} canciones", "info")
    return n


def review_all(limit: int = 200, progress: Optional[dict] = None) -> int:
    """Revisa canción a canción (las no revisadas recientemente) y corrige metadatos.

    Usa `reviewed_at` para avanzar por toda la biblioteca en lugar de repetir siempre las primeras.
    `progress` (opcional) permite ver en vivo el tema que se está revisando.
    """
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM tracks "
            "WHERE file_path IS NOT NULL AND file_path != '' "
            "AND (reviewed_at IS NULL OR reviewed_at < datetime('now', '-12 hours')) "
            "ORDER BY id LIMIT ?", (limit,)).fetchall()
    finally:
        conn.close()
    n = 0
    now = datetime.datetime.now().isoformat(timespec="seconds")
    for r in rows:
        t = dict(r)
        if progress is not None:
            progress["current_review"] = f"{t.get('artist')} - {t.get('title')}"
        u = review_metadata(t)
        if u:
            n += 1
        db.update_track(t["id"], reviewed_at=now)
    if rows:
        db.log_event(f"🕵️ Revisados {len(rows)} temas ({n} con cambios)", "info")
    return n


def _download_image(url: str, dest: Path) -> bool:
    import requests
    try:
        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        return True
    except Exception:  # noqa: BLE001
        return False


def fetch_media(limit: int = 50) -> int:
    """Descarga localmente carátulas de álbum y fotos de artista (para no depender de internet)."""
    from .config import COVERS_DIR, ARTIST_IMAGES_DIR
    n = 0
    conn = db.get_conn()
    try:
        tracks = conn.execute(
            "SELECT id, cover_url, cover_path, album_id, deezer_id FROM tracks "
            "WHERE cover_url IS NOT NULL AND cover_path IS NULL LIMIT ?", (limit,)).fetchall()
    finally:
        conn.close()
    for r in tracks:
        t = dict(r)
        key = t.get("album_id") or t.get("deezer_id") or str(t["id"])
        dest = COVERS_DIR / f"{key}.jpg"
        if _download_image(t["cover_url"], dest):
            db.update_track(t["id"], cover_path=_rel_data(str(dest)))
            n += 1
    # fotos de artistas
    conn = db.get_conn()
    try:
        arts = conn.execute(
            "SELECT name, image_url, deezer_id FROM artists "
            "WHERE image_url IS NOT NULL AND image_path IS NULL LIMIT ?", (limit,)).fetchall()
    finally:
        conn.close()
    for r in arts:
        a = dict(r)
        key = a.get("deezer_id") or a["name"]
        dest = ARTIST_IMAGES_DIR / f"{key}.jpg"
        if _download_image(a["image_url"], dest):
            db.set_artist_image_path(a["name"], _rel_data(str(dest)))
            n += 1
    if n:
        db.log_event(f"🖼️ Imágenes locales descargadas: {n}", "info")
    return n


def refresh_artist_profiles(limit: int = 30) -> int:
    """Actualiza perfiles de artista (foto, fans, nº de álbumes) consultando Deezer."""
    from . import deezer as dz
    client = dz.DeezerClient()
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM artists WHERE (nb_fan IS NULL OR image_url IS NULL) AND deezer_id IS NOT NULL LIMIT ?",
            (limit,)).fetchall()
    finally:
        conn.close()
    n = 0
    for r in rows:
        a = dict(r)
        if not a.get("deezer_id"):
            continue
        try:
            d = client.artist_detail(a["deezer_id"])
        except Exception:  # noqa: BLE001
            continue
        pic = d.get("picture_xl") or d.get("picture_big") or d.get("picture_medium")
        db.upsert_artist(a["name"], deezer_id=str(d.get("id")) or a["deezer_id"], image_url=pic,
                         nb_fan=d.get("nb_fan"), nb_album=d.get("nb_album"),
                         genre=a.get("genre"), language=a.get("language"))
        # foto local
        if pic and not a.get("image_path"):
            from .config import ARTIST_IMAGES_DIR
            dest = ARTIST_IMAGES_DIR / f"{a.get('deezer_id')}.jpg"
            if _download_image(pic, dest):
                db.set_artist_image_path(a["name"], _rel_data(str(dest)))
        # discografía (álbumes)
        try:
            albums_raw = client.artist_albums(a["deezer_id"], limit=30)
            albums = []
            for ab in albums_raw:
                y = None
                if ab.get("release_date"):
                    try:
                        y = int(str(ab["release_date"])[:4])
                    except ValueError:
                        y = None
                cover = ab.get("cover_xl") or ab.get("cover_big") or ab.get("cover_medium")
                albums.append((ab.get("id"), ab.get("title"), y, cover))
            if albums:
                db.set_artist_albums(a["name"], albums)
        except Exception:  # noqa: BLE001
            pass
        n += 1
    if n:
        db.log_event(f"🎤 Perfiles de artista actualizados: {n}", "info")
    return n


def catalog_pending() -> int:
    """Analiza BPM de las pistas descargadas que aún no tienen BPM. Devuelve cuántas se procesaron."""
    count = 0
    for rec in db.get_tracks_needing_bpm(limit=200):
        full = catalog_track(rec)
        db.update_track(
            rec["id"],
            bpm=full.get("bpm"),
            tempo_est=full.get("tempo_est", M.TEMPO_UNKNOWN),
            energy=full.get("energy"),
            genre=full.get("genre"),
            language=full.get("language"),
            duration=full.get("duration"),
            era=full.get("era"),
            is_remix=full.get("is_remix", 0),
            tags=full.get("tags"),
            analyzed_at=full.get("analyzed_at"),
        )
        count += 1
    return count


def revisar_extremos_lote(limit: int = 40, buscar_otra: int = 0, *, minutos: float = 0,
                          log=print) -> tuple[int, int, int]:
    """Mira intros y colas de un lote de canciones y devuelve (revisadas, con_algo, cambiadas).

    Se ejecuta DONDE ESTÁ EL AUDIO:
      · en el PC, para lo que va bajando (lo llama su vuelta del recolector);
      · en el servidor, en lotes pequeños desde el worker, para repasar el catálogo que ya estaba
        (su audio está en `/music`).

    Es un trabajo por lotes a propósito: analizar 6.000 canciones de golpe son ~1,7 horas de CPU, y
    el servidor es un portátil de 4 GB que además sirve la aplicación.

    `buscar_otra` = cuántas de las que tienen voz/diálogo se intentan cambiar por otra versión en
    esta pasada (bajar de YouTube tarda, así que va con tope).

    `minutos` = tope de tiempo para TODA la pasada (0 = sin tope). Hace falta: una búsqueda de otra
    versión puede acabar bajando una sesión de una hora (50-100 MB) y eso solo ya son varios minutos.
    Sin tope, esta fase alargaba la vuelta del recolector por encima de los 15 minutos que hay entre
    vuelta y vuelta, y como el candado impide solapar vueltas, **se perdían vueltas de descarga**.
    """
    import json
    import time as _t

    arranque = _t.time()

    def agotado() -> bool:
        return bool(minutos) and (_t.time() - arranque) / 60.0 >= minutos
    import time as _t

    from .extremos import analizar
    from .config import resolve_music

    conn = db.get_conn()
    try:
        filas = conn.execute(
            "SELECT id, title, artist, file_path, duration, youtube_id FROM tracks"
            " WHERE extremos_revisado IS NULL AND file_path IS NOT NULL AND file_path <> ''"
            " ORDER BY (youtube_id IS NOT NULL) DESC, id DESC LIMIT ?", (limit,)).fetchall()
    finally:
        conn.close()
    if not filas:
        return (0, 0, 0)

    revisadas = con_algo = 0
    candidatas: list[dict] = []
    for f in filas:
        if agotado():
            log(f"   (se acabó el tiempo de esta pasada: {revisadas} revisadas)")
            break
        ruta = resolve_music(f["file_path"])
        if not Path(ruta).exists():
            # La ficha dice que hay fichero pero no está: se apunta y no se vuelve a intentar.
            conn = db.get_conn()
            try:
                conn.execute("UPDATE tracks SET extremos_revisado='sin-fichero' WHERE id=?", (f["id"],))
                conn.commit()
            finally:
                conn.close()
            continue
        try:
            r = analizar(ruta, duracion=f["duration"])
        except Exception as e:  # noqa: BLE001
            log(f"   aviso: no se pudo analizar «{f['title']}»: {str(e)[:60]}")
            continue
        revisadas += 1
        conn = db.get_conn()
        try:
            conn.execute(
                "UPDATE tracks SET intro_seg=?, cola_seg=?, extremos_json=?, extremos_revisado=?"
                " WHERE id=?",
                (r.get("intro_seg"), r.get("cola_seg"), json.dumps(r, ensure_ascii=False),
                 _t.strftime("%Y-%m-%dT%H:%M:%S"), f["id"]))
            conn.commit()
        finally:
            conn.close()
        if r.get("intro_seg") or r.get("cola_seg"):
            con_algo += 1
            if r.get("buscar_otra"):
                candidatas.append({**dict(f), **r})

    cambiadas = 0
    if buscar_otra and candidatas:
        from .pipeline import buscar_version_sin_intro

        for cand in candidatas[:buscar_otra]:
            if agotado():
                log("   (se acabó el tiempo: no se buscan más versiones en esta pasada)")
                break
            try:
                res = buscar_version_sin_intro(
                    cand["artist"], cand["title"], cand["id"], cand["file_path"],
                    intro_actual=cand["intro_seg"] or 0, cola_actual=cand["cola_seg"] or 0,
                    duracion=cand["duration"])
                log(f"   {cand['artist']} - {cand['title']}: {res}"[:150])
                if str(res).startswith("cambiada"):
                    cambiadas += 1
            except Exception as e:  # noqa: BLE001
                log(f"   no se pudo buscar otra versión de «{cand['title']}»: {type(e).__name__}")
    return (revisadas, con_algo, cambiadas)


def republicar_completas(limit: int = 2000) -> int:
    """Pasa a 'descargada' las pistas 'incompleta' que ya completan todos los metadatos
    obligatorios (C4 · metadata_strict).

    Con metadata_strict=True, cada descarga nueva se marca 'incompleta' hasta que el análisis
    rellena BPM/energía/gain_db y el revisor trae carátula/metadatos. Sin esta república, esas
    pistas se quedarían 'incompleta' para siempre y la app (que sólo publica 'descargada') no
    las mostraría. Idempotente: no toca las que aún faltan por completar."""
    cfg = load_settings()
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM tracks WHERE status='incompleta' LIMIT ?", (limit,)).fetchall()
    finally:
        conn.close()
    if not rows:
        return 0
    if not cfg.get("metadata_strict", True):                 # modo no estricto: publicar todas
        n = 0
        for r in rows:
            db.update_track(r["id"], status=M.STATUS_DOWNLOADED)
            n += 1
        if n:
            db.log_event(f"✅ {n} incompletas republicadas (modo no estricto)", "info")
        return n
    obligatorios = ("year", "genre", "language", "bpm", "energy", "gain_db", "duration", "cover_url")
    n = 0
    for r in rows:
        t = dict(r)
        # EL AÑO NO PUEDE BLOQUEAR A LO QUE SÓLO EXISTE EN YOUTUBE. Deezer no tiene ficha de un
        # mashup casero ni de una sesión de DJ, así que no hay año que poner. Aquí se exigía igual
        # que en la puerta de entrada, y con eso las canciones bajadas de YouTube se quedaban
        # 'incompleta' PARA SIEMPRE: bajaban, se analizaban, se les ponía hasta la carátula… y no
        # llegaban nunca a la aplicación. Se veía en el registro del recolector como «aviso: 18
        # descargadas aún sin completar» y ahí se quedaban, incluida una sesión de 36 minutos que el
        # usuario había pedido a mano. Ahora, si la canción viene de un vídeo, se publica sin año.
        exigidos = [k for k in obligatorios
                    if not (k == "year" and t.get("youtube_id"))]
        if all(t.get(k) for k in exigidos):
            db.update_track(t["id"], status=M.STATUS_DOWNLOADED)
            n += 1
    if n:
        db.log_event(f"✅ {n} incompletas republicadas a 'descargada'", "info")
    return n


def recuperar_perdidas(limit: int = 10, *, progress: Optional[dict] = None) -> int:
    """Vuelve a descargar las canciones marcadas 'perdida' (su fichero ya no está en el disco).

    POR QUÉ HACÍA FALTA
    -------------------
    `verificar_ficheros` (el worker) marca 'perdida' las canciones cuyo fichero desapareció,
    con la idea de que entran en una "cola de re-descarga"… pero **nadie las volvía a
    descargar**: la canción desaparecía de la aplicación y no volvía **nunca**. Con miles de
    canciones marcadas, eso es un agujero silencioso.

    Y `fulfill_track` NO sirve para esto: lo primero que hace es comprobar si la canción ya está
    en la biblioteca y, como la fila sigue ahí (sólo está marcada 'perdida'), devuelve su id sin
    descargar nada. Por eso hace falta esta función: descarga **y actualiza esa misma fila**, de
    forma que la canción conserva su id, sus "me gusta" y su historial.

    Va de poco en poco a propósito (`limit`): cada canción es una descarga de YouTube, así que no
    conviene lanzar miles de golpe. Se llama desde el mantenimiento del colector, que ya respeta
    el interruptor de ingesta.
    """
    import os

    from . import quality
    from . import youtube as Y

    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM tracks WHERE status=? AND title IS NOT NULL AND title != '' "
            "ORDER BY added_at ASC LIMIT ?",
            (M.STATUS_LOST, limit)).fetchall()
    finally:
        conn.close()
    if not rows:
        return 0

    recuperadas = fallos = 0
    for r in rows:
        t = dict(r)
        if progress is not None:
            progress["current_review"] = f"recuperando: {t.get('artist')} - {t.get('title')}"
        try:
            yt = Y.search_and_download(
                t.get("artist") or "", t.get("title") or "",
                expected_duration=t.get("duration"),
                genre=t.get("genre"), language=t.get("language"),
                source=t.get("source") or M.SOURCE_ONDEMAND,
            )
            if not yt or yt.get("skipped"):
                fallos += 1
                continue

            # Mismos campos que `_persist_yt`, pero sobre la fila que ya existe.
            rec = dict(t)
            rec.update({
                "file_path": yt.get("file_path"),
                "file_size": yt.get("file_size"),
                "duration": yt.get("duration") or t.get("duration"),
                "youtube_id": yt.get("youtube_id") or t.get("youtube_id"),
                "youtube_url": yt.get("youtube_url") or t.get("youtube_url"),
                "match_score": yt.get("match_score"),
                "status": M.STATUS_DOWNLOADED,
            })
            # Organizar en la carpeta catalogada, como en una descarga normal.
            try:
                nuevo = organize_track(rec)
                if nuevo:
                    rec["file_path"] = _rel_music(nuevo)
                    rec["file_size"] = os.path.getsize(nuevo) if os.path.exists(nuevo) else 0
            except Exception as e:  # noqa: BLE001
                db.log_event(f"Organizar al recuperar: {e}", "warning")

            # La puerta de calidad se aplica igual: si vuelve a no pasar, va a cuarentena.
            ok, motivo = quality.revisar(rec)
            if not ok:
                rec["status"] = M.STATUS_QUARANTINE
                db.log_event(f"🚧 Recuperada pero en cuarentena: {t.get('artist')} - "
                             f"{t.get('title')} → {motivo}", "warning")

            db.update_track(t["id"], **{
                k: rec.get(k) for k in
                ("file_path", "file_size", "duration", "youtube_id", "youtube_url",
                 "match_score", "status")
            })
            if rec["status"] == M.STATUS_DOWNLOADED:
                recuperadas += 1
                db.log_event(f"♻️ Recuperada: {t.get('artist')} - {t.get('title')}", "info")
        except Exception as e:  # noqa: BLE001
            fallos += 1
            db.log_event(f"Fallo al recuperar «{t.get('title')}»: {e}", "error")

    if progress is not None:
        progress.pop("current_review", None)
    if recuperadas or fallos:
        db.log_event(f"♻️ Recuperación: {recuperadas} de vuelta, {fallos} sin poder", "info")
    return recuperadas
