from __future__ import annotations

# Estados de una pista en el catálogo
STATUS_PENDING = "pendiente"        # candidato descubierto pero aún no descargado
STATUS_DOWNLOADING = "descargando"
STATUS_DOWNLOADED = "descargada"
STATUS_FAILED = "fallida"
STATUS_QUEUED = "en_cola"
STATUS_QUARANTINE = "cuarentena"    # no pasa la puerta de calidad: no se sirve a la app

# Origen de la pista
SOURCE_AGENT = "agente"
SOURCE_ONDEMAND = "bajo_demanda"
SOURCE_PRIORITY = "prioridad"
SOURCE_MANUAL = "manual"

# Procedencia del valor de BPM
TEMPO_UNKNOWN = 0     # sin BPM
TEMPO_BY_GENRE = 1    # estimado por género (fallback)
TEMPO_ANALYZED = 2    # calculado con librosa

# Lista negra
BLACKLIST_ARTIST = "artist"
BLACKLIST_SONG = "song"
BLACKLIST_ACTIVE = 1
BLACKLIST_INACTIVE = 0

# Idiomas
LANG_ES = "es"
LANG_EN = "en"
LANG_OTHER = "other"

# Nombres normalizados (para comparaciones)
LANGUAGE_LABELS = {
    LANG_ES: "Español", LANG_EN: "Inglés", LANG_OTHER: "Otro",
    "it": "Italiano", "fr": "Francés", "pt": "Portugués",
}
GENRE_LABELS = {
    "reggaeton": "Reggaetón",
    "pop": "Pop",
    "rock": "Rock",
    "bachata": "Bachata",
    "salsa": "Salsa",
    "merengue": "Merengue",
    "latin": "Latino/Urbano",
    "dance": "Dance/Electrónica",
    "rap": "Rap/Hip-Hop",
    "ballad": "Balada/Cumbia",
    "cumbia": "Cumbia",
    "corridos": "Corridos/Mexicano",
    "flamenco": "Flamenco",
    "reggae": "Reggae",
    "disco": "Disco/Funk",
    "classical": "Clásica",
    "house": "House",
    "electro": "Electrónica",
    "instrumental": "Instrumental",
    "soundtrack": "Banda Sonora",
    "jazz": "Jazz",
    "blues": "Blues",
    "metal": "Metal",
    "indie": "Indie",
    "folk": "Folk",
    "techno": "Techno",
    "lofibeat": "Lo-Fi",
    "gospel": "Gospel",
    "banda": "Banda",
    "soul": "Soul/R&B",
    "other": "Variado",
}


# Vocabulario de mood/etiquetas que se pueden usar como filtro
MOODS = [
    "chill", "tranquilidad", "relax", "meditacion", "concentracion", "trabajo", "romantica",
    "correr", "sprint", "gimnasio", "swim", "cardio",
    "fiesta", "fiesta temprana", "fiesta puntual", "fiesta tardia", "perreo", "house",
    "disco", "remix", "clasica", "instrumental", "urbano", "pop es 2000s",
    "80s", "90s", "00s", "10s", "20s", "energia alta", "energia baja",
    "playa", "verano", "carretera", "manana", "noche", "triste", "feliz", "epica",
    "lofi", "jazz", "metal", "indie", "soul", "banda", "techno", "sad",
]
