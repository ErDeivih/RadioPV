from datetime import datetime
from sqlalchemy import (Column, Integer, BigInteger, String, Float, Boolean, Text, DateTime,
                        ForeignKey, UniqueConstraint, Index)
from .database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    display_name = Column(String(120), default="")
    is_admin = Column(Boolean, default=False)
    token_version = Column(Integer, default=0)        # para revocar sesiones al logout
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)


class Track(Base):
    __tablename__ = "tracks"
    id = Column(Integer, primary_key=True)
    title = Column(String(255), index=True)
    artist = Column(String(255), index=True)
    album = Column(String(255))
    release_date = Column(String(20))
    year = Column(Integer, index=True)
    genre = Column(String(60), index=True)
    language = Column(String(10), index=True)
    bpm = Column(Float)
    energy = Column(Float)
    gain_db = Column(Float)              # normalización de volumen (T-22)
    valence = Column(Float)
    danceability = Column(Float)
    tags = Column(Text)
    era = Column(String(10), index=True)
    is_remix = Column(Boolean, default=False)
    explicit = Column(Boolean, default=False)
    feat = Column(Text)                      # artistas invitados / colaboradores
    file_path = Column(Text)
    cover_url = Column(Text)
    cover_path = Column(Text)
    artist_image_url = Column(Text)
    artist_image_path = Column(Text)
    deezer_id = Column(String(40), unique=True, index=True)
    album_id = Column(String(40))
    artist_id = Column(String(40))
    duration = Column(Float)
    rank = Column(Integer)
    source = Column(String(40))
    status = Column(String(20), default="descargada")
    # --- popularidad (P) ---
    youtube_id = Column(String(40), index=True)
    yt_views = Column(BigInteger, default=0)      # visitas YouTube (último refresco)
    yt_likes = Column(BigInteger, default=0)
    popularidad = Column(Float, default=0.0)      # score 0-1 (views + rank)
    __table_args__ = (
        Index("ix_tracks_genre_year", "genre", "year"),
        Index("ix_tracks_bpm_energy", "bpm", "energy"),
        Index("ix_tracks_era_energy", "era", "energy"),
    )

    @property
    def cover(self) -> str | None:
        from .paths import media_filename
        n = media_filename(self.cover_path)
        return f"/media/covers/{n}" if n else None


class Artist(Base):
    __tablename__ = "artists"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, index=True)
    deezer_id = Column(String(40))
    image_url = Column(Text)
    image_path = Column(Text)
    nb_fan = Column(Integer)
    nb_album = Column(Integer)
    genre = Column(String(60))
    language = Column(String(10))
    track_count = Column(Integer, default=0)

    @property
    def image(self) -> str | None:
        from .paths import media_filename
        n = media_filename(self.image_path)
        return f"/media/artists/{n}" if n else None


class ArtistAlbum(Base):
    __tablename__ = "artist_albums"
    id = Column(Integer, primary_key=True)
    artist_name = Column(String(255), index=True)
    artist_id = Column(String(40))
    album_id = Column(String(40))
    title = Column(String(255))
    year = Column(Integer)
    cover_url = Column(Text)


class Reaction(Base):
    __tablename__ = "reactions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    track_id = Column(Integer, ForeignKey("tracks.id"), index=True)
    liked = Column(Integer, default=0)
    skipped = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("user_id", "track_id", name="uq_user_track"),)


class Play(Base):
    __tablename__ = "plays"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    track_id = Column(Integer, ForeignKey("tracks.id"), index=True)
    played_at = Column(DateTime, default=datetime.utcnow, index=True)
    source = Column(String(40))
    completed = Column(Integer, default=0)
    seconds_listened = Column(Float)
    context = Column(String(40))        # playlist:12 | radio:88 | daily | search | artist


class Playlist(Base):
    __tablename__ = "playlists"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    name = Column(String(255))
    description = Column(Text)
    type = Column(String(20), default="user")
    # Nombre del fichero de portada dentro de MEDIA_ROOT/covers (solo el nombre, igual que en
    # Track.cover_path: la raiz la monta el servidor).
    cover_path = Column(Text)
    # Lista compartida con los demas usuarios. Por defecto NO: una lista es privada hasta que su
    # dueno dice lo contrario. (La interfaz ofrecia «hacer publica» desde el principio, pero esta
    # columna no existia: el aviso decia que se habia hecho publica y no cambiaba nada.)
    public = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    @property
    def cover(self) -> str | None:
        """URL con la que la interfaz pide la portada de la lista."""
        from .paths import media_filename
        n = media_filename(self.cover_path)
        return f"/media/covers/{n}" if n else None


class PlaylistTrack(Base):
    __tablename__ = "playlist_tracks"
    id = Column(Integer, primary_key=True)
    playlist_id = Column(Integer, ForeignKey("playlists.id"), index=True)
    track_id = Column(Integer, ForeignKey("tracks.id"), index=True)
    position = Column(Integer)
    added_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("playlist_id", "track_id", name="uq_pt"),)


class TasteProfile(Base):
    __tablename__ = "taste_profile"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, index=True)
    preferred_genres = Column(Text)
    preferred_artists = Column(Text)
    preferred_eras = Column(Text)
    bpm_mean = Column(Float)
    energy_mean = Column(Float)
    updated_at = Column(DateTime, default=datetime.utcnow)


class Similar(Base):
    __tablename__ = "similar"
    id = Column(Integer, primary_key=True)
    track_a = Column(Integer, ForeignKey("tracks.id"), index=True)
    track_b = Column(Integer, ForeignKey("tracks.id"))
    score = Column(Float)
    __table_args__ = (UniqueConstraint("track_a", "track_b", name="uq_similar"),
                      Index("ix_similar_a_score", "track_a", "score"))


class Mix(Base):
    __tablename__ = "mixes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    kind = Column(String(30))              # daily | discover | on_repeat | radar
    seed = Column(String(80))
    tracks_json = Column(Text)             # [12, 45, 88, …]
    explicacion = Column(Text)             # R5 · "porque escuchas mucho a Estopa"
    created_at = Column(DateTime, default=datetime.utcnow)


class SmartPlaylist(Base):
    __tablename__ = "smart_playlists"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)   # NULL = del sistema
    name = Column(String(120))
    filters = Column(Text)                 # JSON
    enabled = Column(Boolean, default=True)


class Request(Base):
    __tablename__ = "requests"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    text = Column(Text)                    # "Artista - Título" pedido desde la app
    status = Column(String(20), default="pendiente")   # pendiente | descargada | fallida
    created_at = Column(DateTime, default=datetime.utcnow)


class Follow(Base):
    __tablename__ = "follows"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    artist_name = Column(String(255), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("user_id", "artist_name", name="uq_follow"),)


class PopularitySample(Base):
    """P · serie temporal de popularidad por pista: una fila por (fuente, métrica, momento).
    Permite ver *cuándo* fue popular una canción y detectar tendencias (subidas/bajadas)."""
    __tablename__ = "popularity_history"
    id = Column(Integer, primary_key=True)
    track_id = Column(Integer, ForeignKey("tracks.id"), index=True, nullable=False)
    source = Column(String(20))                  # youtube | deezer | spotify
    metric = Column(String(20))                  # views | rank | plays
    valor = Column(Float)
    sampled_at = Column(DateTime, default=datetime.utcnow, index=True)
