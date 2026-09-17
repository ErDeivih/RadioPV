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
    file_path: Optional[str] = None
    cover_path: Optional[str] = None
    cover_url: Optional[str] = None
    artist_image_path: Optional[str] = None
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
    id: int
    name: str
    description: Optional[str] = None
    type: str = "user"
    n_tracks: int = 0
    model_config = ConfigDict(from_attributes = True)


class PlaylistIn(BaseModel):
    name: str
    description: str = ""
    type: str = "user"


class MixOut(BaseModel):
    id: int
    kind: str
    seed: Optional[str] = None
    tracks_json: Optional[str] = None
    explicacion: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PlaylistPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


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
