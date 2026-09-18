from __future__ import annotations

import json
import os
from pathlib import Path

# Directorio raíz del proyecto (el padre de este paquete)
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("RADIOPV_DATA_DIR") or (ROOT / "data"))

# Carpeta base de la música. Configurable por entorno para poder desplegar en Linux:
#   RADIOPV_BASE_MUSIC (o MUSIC_ROOT) -> raíz de la música
# Sin variable y en Windows se mantiene E:/Musica (comportamiento original).
_env_music = os.environ.get("RADIOPV_BASE_MUSIC") or os.environ.get("MUSIC_ROOT")
if _env_music:
    BASE_MUSIC = Path(_env_music)
else:
    BASE_MUSIC = Path("E:/Musica") if os.name == "nt" else Path("/music")

RAW_DIR = Path(os.environ.get("RADIOPV_RAW_DIR") or (BASE_MUSIC / "descargas"))
CATALOG_DIR = Path(os.environ.get("RADIOPV_CATALOG_DIR") or (BASE_MUSIC / "catalogada"))
PLAYLIST_DIR = Path(os.environ.get("RADIOPV_PLAYLIST_DIR") or (BASE_MUSIC / "auriculares"))

# Datos internos de la app (independientes de la carpeta de música)
DB_PATH = DATA_DIR / "radiov.db"
SETTINGS_PATH = DATA_DIR / "settings.json"
BLACKLIST_PATH = DATA_DIR / "blacklist.json"  # respaldo legible (opcional)
COVERS_DIR = DATA_DIR / "covers"       # carátulas de álbum descargadas
ARTIST_IMAGES_DIR = DATA_DIR / "artists"  # fotos de artistas descargadas


def resolve_music(path: str) -> Path:
    """Devuelve la ruta ABSOLUTA de un file_path, acepte la forma absoluta (heredada) o la
    relativa (nueva, cuelga de BASE_MUSIC). El recolector accede al fichero usando esto."""
    p = Path(path)
    return p if p.is_absolute() else (BASE_MUSIC / p)

# ---------- Ajustes por defecto ----------
DEFAULT_SETTINGS: dict = {
    # Carpetas de música
    "base_music_dir": str(BASE_MUSIC),
    "download_dir": str(RAW_DIR),          # "en bruto": todo lo descargado
    "catalog_dir": str(CATALOG_DIR),        # organizada por artista/año/álbum + etiquetas
    "playlist_dir": str(PLAYLIST_DIR),       # selecciones para auriculares
    "keep_raw_copy": True,                  # True: deja copia en descargas + copia en catalogada. False: mueve.
    "organize_by": "artist_album",          # organización de catalogada: artist_album | artist_year

    # Calidad de audio descargado (bestaudio se convierte a mp3)
    "audio_format": "mp3",
    "audio_quality": "0",  # 0 = calidad variable más alta

    # ------- Fuente (Deezer) -------
    "min_rank": 200000,          # umbral de popularidad (Deezer). Evita canciones con pocas visitas.
    "min_rank_es": 40000,        # el español "levanta la mano": umbral más laxo.
    "max_results_per_query": 40, # cuántos candidatos probar por cada búsqueda semilla.
    "client_requests": 1,        # peticiones en paralelo (mantener 1 para no saturar).

    # ------- Catálogo -------
    "analyze_bpm": True,               # calcular BPM real con librosa.
    "bpm_sample_seconds": 30,          # analizar solo los primeros N segundos.
    "use_genre_fallback_bpm": True,    # si no hay BPM, estimar con la mediana del género.
    "duration_tolerance": 0.20,        # tolerancia para validar que el vídeo coincide con la canción.

    # ------- Agente automático -------
    "agent_enabled_by_default": False,  # si arranca al abrir la web.
    "agent_sleep_seconds": 1.0,         # pausa entre descargas para evitar bloqueos de YouTube.
    "agent_downloads_per_seed_per_pass": 3,  # cuotas pequeñas: baraja dentro de cada fuente y pasa rápido (más aleatorio).
    "max_artists_per_pass": 8,               # artistas a expandir por cada semilla "explore".
    "maintenance_interval_minutes": 15,      # cada cuánto corre solo el revisor de metadatos + re-análisis de BPM.
    "default_folder_per_artist": False, # organizar en subcarpetas por artista.

    # ------- Techo y ritmo (D11/D12/C2) -------
    "disk_cap_gb": 60,               # D11 · techo del catálogo en E:\Musica (GB). El recolector para al llegar.
    "downloads_per_day": 150,        # D12 · descargas diarias (sostenido, no una ráfaga).
    "decade_pre2000_quota": 1,       # C2 · de cada `decade_quota_denominator` descargas, `decade_pre2000_quota` para pre-2000.
    "decade_quota_denominator": 4,
    "metadata_strict": True,         # C4 · si falta year/genre/language/bpm/energy/gain_db/duration/carátula → 'incompleta'.


    # ------- Prioridades (caja del Panel) -------
    "priority_artist_songs": 12,   # canciones a bajar por cada artista prioritario.
    "priority_album": "all",        # "all" (todas las pistas del álbum) o número.
    "priority_sleep_seconds": 1.0,  # pausa entre descargas prioritarias.

    # ------- Lengua / género (heurística) -------
    "default_language": "other",        # usado cuando no se detecta.
    "spanish_hint_words": ["de", "la", "el", "los", "las", "mi", "tu", "te", "por", "que",
                           "amor", "noche", "corazon", "baila", "corazón", "vida", "quiero",
                           "contigo", "nena", "mundo", "un", "una", "como", "para"],
    "genre_keywords": {
        "reggaeton": ["reggaeton", "reguetón", "reggaetón", "dembow", "perreo", "trap"],
        "pop": ["pop", "pop latino", "pop inglés", "girl band", "boy band"],
        "rock": ["rock", "rock clásico", "hard rock", "rock en español", "indie rock"],
        "bachata": ["bachata", "bachat"],
        "salsa": ["salsa", "salsa dura"],
        "merengue": ["merengue"],
        "latin": ["latino", "latin", "urbano", "cumbia", "reggae"],
        "cumbia": ["cumbia", "cumbias"],
        "corridos": ["corridos", "corridos tumbados", "corrido", "mexicano", "regional"],
        "flamenco": ["flamenco", "sevillanas", "rumba"],
        "dance": ["dance", "electro", "edm", "house", "disco"],
        "disco": ["disco", "funk"],
        "house": ["house", "deep house", "tech house", "progressive house"],
        "electro": ["electro", "edm", "electronic", "trance", "techno"],
        "classical": ["clasica", "classical", "piano", "orquesta", "sinfonia", "einaudi", "beethoven"],
        "instrumental": ["instrumental", "soundtrack", "banda sonora", "ost", "vangelis", "zimmer"],
        "jazz": ["jazz", "swing", "bossa", "bossanova", "blues"],
        "blues": ["blues", "rhythm and blues"],
        "metal": ["metal", "heavy metal", "death metal", "nu metal"],
        "indie": ["indie", "indie pop", "indie rock"],
        "folk": ["folk", "cantautor", "singer songwriter", "chanson"],
        "techno": ["techno", "minimal", "hardstyle"],
        "lofibeat": ["lofi", "lo-fi", "chill beats", "lofi hip hop"],
        "gospel": ["gospel", "soul", "coral"],
        "banda": ["banda", "norteño", "tejano", "mariachi"],
        "soul": ["soul", "rnb", "r&b"],
        "rap": ["rap", "hip hop", "hip-hop", "trap lirico"],
        "reggae": ["reggae", "reggaeton", "ska"],
        "ballad": ["balada", "ballad", "romantica", "ranchera", "corrido"],
    },
    # Temas/géneros y artistas conocidos que el agente recorre de forma automática.
    #  - mode "genre_artists": coge los temas más famosos de cada artista (curado → música conocida).
    #  - mode "query": coge lo trending por popularidad en Deezer.
    "agent_seeds": [
        # Listas de éxitos reales (Apple Music, varios países) → artistas → expansión continua
        {"mode": "hits_apple", "country": "es", "genre": "latin", "language": "es", "limit": 20},
        {"mode": "hits_apple", "country": "us", "genre": "pop", "language": "en", "limit": 20},
        {"mode": "hits_apple", "country": "mx", "genre": "latin", "language": "es", "limit": 20},
        {"mode": "hits_apple", "country": "ar", "genre": "latin", "language": "es", "limit": 20},
        {"mode": "hits_apple", "country": "co", "genre": "latin", "language": "es", "limit": 20},
                                {"mode": "hits_apple", "country": "gb", "genre": "pop", "language": "en", "limit": 20},
        # Lista de Los 40 (España)
        {"mode": "hits_40", "genre": "pop", "language": "es", "limit": 20},
        # Éxitos de diferentes años/épocas (español y en inglés) → artistas → expansión
        {"mode": "year_hits", "language": "es", "genre": "pop"},
        {"mode": "year_hits", "language": "en", "genre": "pop"},
        # Barrido por años concretos (todas las décadas, no solo lo actual)
        {"mode": "year_sweep", "language": "es", "genre": "pop", "years": [1965, 1970, 1975, 1980, 1985, 1990, 1995]},
        {"mode": "year_sweep", "language": "es", "genre": "pop", "years": [2000, 2003, 2005, 2008, 2010, 2012]},
        {"mode": "year_sweep", "language": "es", "genre": "pop", "years": [2014, 2016, 2018, 2020, 2022, 2024]},
        {"mode": "year_sweep", "language": "en", "genre": "pop", "years": [1965, 1970, 1975, 1980, 1985, 1990, 1995, 2000]},
        {"mode": "year_sweep", "language": "en", "genre": "pop", "years": [2003, 2005, 2008, 2010, 2012, 2014, 2016]},
        {"mode": "year_sweep", "language": "en", "genre": "pop", "years": [2018, 2020, 2022, 2024]},
                                # Expansión por géneros desde pocos artistas semilla; crece con artistas relacionados
        {"mode": "explore", "genre": "reggaeton", "language": "es", "seeds": ["Bad Bunny", "KAROL G", "Daddy Yankee"]},
        {"mode": "explore", "genre": "bachata", "language": "es", "seeds": ["Romeo Santos", "Aventura", "Prince Royce"]},
        {"mode": "explore", "genre": "salsa", "language": "es", "seeds": ["Marc Anthony", "Hector Lavoe", "Celia Cruz"]},
        {"mode": "explore", "genre": "merengue", "language": "es", "seeds": ["Juan Luis Guerra", "Elvis Crespo"]},
        {"mode": "explore", "genre": "cumbia", "language": "es", "seeds": ["Los Angeles Azules", "La Sonora Dinamita", "Grupo Niche"]},
        {"mode": "explore", "genre": "corridos", "language": "es", "seeds": ["Natanael Cano", "Peso Pluma", "Junior H"]},
        {"mode": "explore", "genre": "flamenco", "language": "es", "seeds": ["Rosalia", "Fondo Flamenco", "Nina Pastori"]},
        {"mode": "explore", "genre": "pop", "language": "es", "seeds": ["Shakira", "Enrique Iglesias", "Aitana"]},
        {"mode": "explore", "genre": "pop", "language": "en", "seeds": ["Taylor Swift", "Dua Lipa", "Ed Sheeran"]},
        {"mode": "explore", "genre": "rock", "language": "en", "seeds": ["Queen", "AC/DC", "Foo Fighters"]},
        {"mode": "explore", "genre": "rock", "language": "es", "seeds": ["Soda Stereo", "Mana", "Heroes del Silencio"]},
        {"mode": "explore", "genre": "rap", "language": "en", "seeds": ["Drake", "Kendrick Lamar", "Eminem"]},
        {"mode": "explore", "genre": "dance", "language": "en", "seeds": ["Calvin Harris", "David Guetta", "Dua Lipa"]},
        {"mode": "explore", "genre": "reggae", "language": "en", "seeds": ["Bob Marley", "UB40", "Sean Paul"]},
        {"mode": "explore", "genre": "latin", "language": "es", "seeds": ["Maluma", "Rauw Alejandro", "Feid"]},
        {"mode": "explore", "genre": "pop", "language": "it", "seeds": ["Eros Ramazzotti", "Laura Pausini", "Andrea Bocelli"]},
        {"mode": "explore", "genre": "pop", "language": "fr", "seeds": ["Edith Piaf", "Stromae", "Indila"]},
                {"mode": "explore", "genre": "ballad", "language": "en", "seeds": ["Adele", "Celine Dion", "Elton John"]},
        {"mode": "explore", "genre": "disco", "language": "en", "seeds": ["Bee Gees", "ABBA", "Dua Lipa"]},
        {"mode": "explore", "genre": "rock", "language": "it", "seeds": ["Maneskin", "Zucchero"]},
        {"mode": "explore", "genre": "classical", "language": "other", "seeds": ["Ludovico Einaudi", "Hans Zimmer", "Vangelis", "Beethoven"]},
        {"mode": "explore", "genre": "instrumental", "language": "other", "seeds": ["Yiruma", "Max Richter", "Nils Frahm"]},
        {"mode": "explore", "genre": "house", "language": "en", "seeds": ["David Guetta", "Calvin Harris", "Lost Frequencies", "Kygo"]},
        {"mode": "explore", "genre": "electro", "language": "en", "seeds": ["Avicii", "Martin Garrix", "Alan Walker", "Swedish House Mafia"]},
        {"mode": "query", "genre": "pop", "query": "top hits", "language": "en"},
        {"mode": "query", "genre": "reggaeton", "query": "reggaeton hits", "language": "es"},

    # MASHUPS Y REMIXES: canciones que mezclan dos o tres temas, hechas por gente en YouTube.
    # Se buscan por texto (es lo que mejor encuentra ese tipo de contenido).
    {"mode": "query", "genre": "dance", "query": "mashup two songs", "language": "en"},
    {"mode": "query", "genre": "dance", "query": "best mashup mix", "language": "en"},
    {"mode": "query", "genre": "pop", "query": "mashup 3 songs", "language": "en"},
    {"mode": "query", "genre": "reggaeton", "query": "mashup reggaeton", "language": "es"},
    {"mode": "query", "genre": "dance", "query": "remix mashup", "language": "en"},
    ],
    "max_per_artist": 10,
    # Actividades/ritmos: subdivisión de BPM + orientación para el usuario.
    "activities": {
        "correr": {"label": "🏃 Correr", "bpm": [145, 175], "preferred_genres": ["reggaeton", "pop", "dance", "latin"],
                   "desc": "145–175 BPM. Ritmo de zancada típico al correr; mantiene el paso constante."},
        "sprint": {"label": "⚡ Sprint / Series", "bpm": [165, 200], "preferred_genres": ["reggaeton", "rap", "dance", "rock"],
                   "desc": "165–200 BPM. Muy rápido, para series y esfuerzo máximo."},
        "hiit": {"label": "🔥 HIIT / Alta intensidad", "bpm": [140, 175], "preferred_genres": ["reggaeton", "rap", "pop", "dance"],
                 "desc": "140–175 BPM. Alta intensidad intermitente: energía que no decae."},
        "gym": {"label": "🏋️ Gimnasio", "bpm": [115, 155], "preferred_genres": ["reggaeton", "rap", "rock", "pop"],
                "desc": "115–155 BPM. Energía media-alta para entrenar sin ir acelerado."},
        "cardio": {"label": "❤️ Cardio", "bpm": [120, 155], "preferred_genres": ["pop", "reggaeton", "dance", "latin"],
                   "desc": "120–155 BPM. Constante y rítmico para sesiones de cardio."},
        "calentamiento": {"label": "🔥 Calentamiento", "bpm": [100, 125], "preferred_genres": ["pop", "latin", "dance"],
                          "desc": "100–125 BPM. Para arrancar el cuerpo sin forzar."},
        "fiesta": {"label": "🎉 Fiesta", "bpm": [100, 145], "preferred_genres": ["reggaeton", "pop", "salsa", "merengue", "dance"],
                   "desc": "100–145 BPM. Bailable y fácil de seguir."},
        "swim": {"label": "🏊 Nadar", "bpm": [120, 165], "preferred_genres": ["reggaeton", "latin", "pop", "dance"],
                 "desc": "120–165 BPM. Para bracear a un compás constante en el agua."},
        "romantica": {"label": "💞 Romántica", "bpm": [70, 100], "preferred_genres": ["ballad", "salsa", "bachata", "pop"],
                      "desc": "70–100 BPM. Lenta y melódica, para un ratito tranquilo."},
        "concentracion": {"label": "📚 Concentración", "bpm": [55, 85], "preferred_genres": ["ballad", "pop", "latin", "rock"],
                          "desc": "55–85 BPM. Tempo tranquilo para estudiar o leer."},
        "relax": {"label": "🧘 Relax / Chill", "bpm": [50, 75], "preferred_genres": ["ballad", "latin", "pop", "flamenco"],
                  "desc": "50–75 BPM. Para descansar, sin distraer."},
        "meditacion": {"label": "🕊️ Meditación", "bpm": [40, 60], "preferred_genres": ["ballad", "flamenco", "latin"],
                       "desc": "40–60 BPM. Muy lento, para meditar o dormir."},
        "conduccion": {"label": "🚗 Conducir", "bpm": [90, 130], "preferred_genres": ["pop", "rock", "latin", "reggaeton"],
                       "desc": "90–130 BPM. Fácil de escuchar en ruta, sin poner nervioso."},
        "trabajo": {"label": "💼 Trabajo", "bpm": [80, 115], "preferred_genres": ["pop", "rock", "latin", "jazz"],
                    "desc": "80–115 BPM. De fondo, amable y sin sobresaltos."},
    },
    # Tamaño máximo de una subselección generada
    "max_playlist_size": 200,
}

# ---------- tablas SQL ----------
TRACK_COLUMNS = [
    "id", "title", "artist", "album", "release_date", "year", "genre", "language",
    "bpm", "tempo_est", "duration", "deezer_id", "youtube_id", "youtube_url",
    "file_path", "file_size", "rank", "source", "status", "match_score",
    "added_at", "analyzed_at",
]


def ensure_dirs() -> None:
    # Directorios internos siempre
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    ARTIST_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    # Carpetas de música: si el sistema no deja crearlas (permisos, unidad), no fallar.
    for d in (RAW_DIR, CATALOG_DIR, PLAYLIST_DIR):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass


def load_settings() -> dict:
    """Devuelve la configuración con los valores por defecto fusionados."""
    cfg = dict(DEFAULT_SETTINGS)
    ensure_dirs()
    if SETTINGS_PATH.exists():
        try:
            saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            for k, v in saved.items():
                if k in DEFAULT_SETTINGS and isinstance(DEFAULT_SETTINGS[k], dict) and isinstance(v, dict):
                    merged = dict(DEFAULT_SETTINGS[k])
                    merged.update(v)
                    cfg[k] = merged
                else:
                    cfg[k] = v
        except Exception:
            pass
    # normaliza rutas a absolutas
    cfg["download_dir"] = str(Path(cfg["download_dir"]).resolve())
    cfg["catalog_dir"] = str(Path(cfg["catalog_dir"]).resolve())
    cfg["playlist_dir"] = str(Path(cfg["playlist_dir"]).resolve())
    cfg["base_music_dir"] = str(Path(cfg["base_music_dir"]).resolve())
    return cfg


def save_settings(cfg: dict) -> None:
    ensure_dirs()
    SETTINGS_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
