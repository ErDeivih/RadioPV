from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str = ""
    invite_code: Optional[str] = None


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    is_admin: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes = True)


class UserPatchIn(BaseModel):
    display_name: Optional[str] = None
    email: Optional[EmailStr] = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class TrackOut(BaseModel):
    id: int
    title: str
    artist: str
    album: Optional[str] = None
    year: Optional[int] = None
    era: Optional[str] = None
    genre: Optional[str] = None
    language: Optional[str] = None
    bpm: Optional[float] = None
    energy: Optional[float] = None
    gain_db: Optional[float] = None
    tags: Optional[str] = None
    is_remix: bool = False
    explicit: bool = False
    feat: Optional[str] = None
    rank: Optional[int] = None
    yt_views: Optional[int] = None
    yt_likes: Optional[int] = None
    popularidad: Optional[float] = None
    youtube_id: Optional[str] = None
    # NO se exponen `file_path`, `cover_path` ni `artist_image_path`: son rutas del sistema de
    # ficheros del servidor y estas respuestas salen también en peticiones SIN autenticar
    # (`/tracks` es público), así que contaban cómo está organizado el disco. El panel de
    # administración sí las necesita y las lee de `/admin/tracks`, que va por otra vía.
    cover_url: Optional[str] = None
    artist_image_url: Optional[str] = None
    deezer_id: Optional[str] = None
    duration: Optional[float] = None
    cover: Optional[str] = None        # url de /media/covers (T-14)
    model_config = ConfigDict(from_attributes = True)


class ArtistOut(BaseModel):
    id: int
    name: str
    image_path: Optional[str] = None
    image_url: Optional[str] = None
    nb_fan: Optional[int] = None
    track_count: Optional[int] = None
    image: Optional[str] = None        # url de /media/artists (T-14)
    model_config = ConfigDict(from_attributes = True)


class AlbumOut(BaseModel):
    title: str
    year: Optional[int] = None
    cover_url: Optional[str] = None
    model_config = ConfigDict(from_attributes = True)


class PlaylistOut(BaseModel):
    # Quien es el dueno: la interfaz lo necesita para saber si puede renombrar o borrar la lista.
    # Sin esto el adaptador ponia un id fijo y NINGUNA lista se reconocia como propia.
    user_id: Optional[int] = None
    id: int
    name: str
    description: Optional[str] = None
    type: str = "user"
    n_tracks: int = 0
    # Portada propia de la lista (url de /media/covers) o None. Antes TODAS las listas de usuario
    # salian con la misma imagen de relleno: no habia forma de subir una.
    cover: Optional[str] = None
    # Lista compartida. La interfaz lo necesita para ofrecer «hacer publica» o «hacer privada».
    public: bool = False
    # Hasta 4 carátulas de sus primeras canciones, para que la interfaz componga un mosaico (el
    # 2×2 de Spotify) en las listas que no tienen portada propia. Antes TODAS las listas generadas
    # salían con el mismo icono gris de relleno y la portada parecía rota.
    collage: list[str] = []
    model_config = ConfigDict(from_attributes = True)


class PlaylistIn(BaseModel):
    name: str
    description: str = ""
    type: str = "user"


class ImportarOut(BaseModel):
    """Resultado de importar una lista de Spotify: lo que ha entrado y lo que falta.

    «Lo que falta» se devuelve A PROPÓSITO: es lo que hace falta para poder decir «de 50 canciones,
    23 están y 27 no» y ofrecer pedirlas al recolector. Sin esto, la interfaz sólo podría decir que
    la lista se ha creado, aunque hubiera entrado una sola canción.
    """
    playlist: "PlaylistOut"
    nombre: str
    total: int
    encontradas: int
    faltan: list[dict] = []
    pedidas: int = 0
    aviso: Optional[str] = None


# La anotación de arriba es una cadena (referencia adelantada a `PlaylistOut`), así que hay que
# resolverla al final del módulo o Pydantic no sabrá qué modelo es.
ImportarOut.model_rebuild()


class MixOut(BaseModel):
    id: int
    kind: str
    seed: Optional[str] = None
    tracks_json: Optional[str] = None
    explicacion: Optional[str] = None
    created_at: datetime
    # La URI con la que la interfaz arranca ESTE mix (`radiopv:mix:radar`). La construye el
    # servidor y no el navegador a propósito: el mismo valor tiene que servir para pedir la lista
    # (`/mixes/{kind}/tracks`) y para marcar en la interfaz cuál de los mixes está sonando. Si cada
    # lado lo armara por su cuenta, un cambio de formato en uno dejaría al otro sin reconocerlo.
    uri: str = ""
    n_tracks: int = 0
    # Hasta 4 carátulas de sus canciones, para el mosaico 2×2: los mixes no tienen portada propia
    # y sin esto las tarjetas de «Hecho para ti» salían como cuadros de texto sin imagen.
    collage: list[str] = []
    model_config = ConfigDict(from_attributes=True)


class PlaylistPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    public: Optional[bool] = None


class ReactionOut(BaseModel):
    liked: list[int]
    skipped: list[int]


class PlayIn(BaseModel):
    source: str = "player"
    completed: int = 0
    seconds_listened: Optional[float] = None
    context: Optional[str] = None          # "playlist:12" | "radio:88" | "search" | "daily"


class LikeIn(BaseModel):
    liked: bool = True


class SkipIn(BaseModel):
    skipped: bool = True
