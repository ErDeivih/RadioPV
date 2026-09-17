# 🗄️ RadioPV · Esquema de base de datos

> Fuente de verdad para cualquier agente. Hay **dos** implementaciones que deben mantenerse en sintonía:
> 1. **SQLite local del catálogo** (`radiov/db.py` + `data/radiov.db`) — la usa el recolector/agente.
> 2. **Backend** (`backend/app/models.py` + `data/backend.db` o Postgres vía `DATABASE_URL`) — la app online.

Ambas reflejan el mismo modelo lógico. La tabla de abajo es la referencia.

---

## Tablas principales

### `tracks` (catálogo / items)
| campo | tipo | notas |
|---|---|---|
| id | INTEGER PK | |
| title | TEXT | índice |
| artist | TEXT | índice |
| album | TEXT | |
| release_date | TEXT | fecha del álbum (YYYY-MM-DD) |
| year | INTEGER | índice · **año real** (revisor) |
| genre | TEXT | índice |
| language | TEXT | es/en/it/fr/pt/other · índice |
| bpm | FLOAT | índice |
| energy | FLOAT | 0-1 · índice |
| valence / danceability / acousticness / loudness | FLOAT | **propuestos** (librosa) |
| tags | TEXT | lista "chill, fiesta, 90s…" |
| era | TEXT | 80s/90s/00s/10s/20s · índice |
| is_remix | BOOL | |
| explicit | BOOL | |
| file_path | TEXT | MP3 en `E:\Musica\catalogada\...` |
| cover_url / cover_path | TEXT | carátula (URL y **local**) |
| artist_image_url / artist_image_path | TEXT | foto del artista (URL y **local**) |
| deezer_id | TEXT unique índice | |
| album_id / artist_id | TEXT | |
| duration | FLOAT | |
| rank | INTEGER | popularidad Deezer |
| source | TEXT | agente / prioridad / bajo_demanda… |
| status | TEXT | descargada / fallida… |
| added_at / analyzed_at / reviewed_at | TEXT | control |
| feat | TEXT | colaboradores ("Bomba Estéreo") |

**Índices**: `artist, genre, language, year, status, title, album, bpm, deezer_id, source, era, energy`,
compuestos `(genre, year)`, `(status, added_at)`, y (en el backend) `(bpm, energy)`, `(era, energy)`.
**FTS5**: `tracks_fts(title, artist, album)` con triggers automáticos (búsqueda full-text).

### `artists` (perfiles)
`id, name (unique, case-correct), deezer_id, image_url, image_path, nb_fan, nb_album, genre, language, track_count`

### `artist_albums` (discografía)
`id, artist_name, artist_id, album_id, title, year, cover_url` · índice por `artist_name`.

### Señales del usuario (backend / online)
- `users(id, email UNIQUE, hashed_password, display_name, is_admin, token_version, created_at, last_login)`
- `sessions` (opcional; aquí se usa **JWT** con `token_version` para revocar). Si prefieres tablas: `id, user_id, token UNIQUE, expires_at, ip, user_agent`.
- `reactions(user_id, track_id, liked, skipped, updated_at, UNIQUE(user_id, track_id))` → 👍👎
- `plays(user_id, track_id, played_at, source, completed, seconds_listened)` → **evento**
- `playlists(user_id, name, description, type(user|system|mix), created_at, updated_at)`
- `playlist_tracks(playlist_id, track_id, position, added_at, UNIQUE(playlist_id, track_id))`
- `taste_profile(user_id UNIQUE, preferred_genres, preferred_artists, preferred_eras, bpm_mean, energy_mean, updated_at)`
- `smart_playlists(user_id, name, filters(JSON), enabled)` → reglas regenerables
- `mixes(user_id, kind, seed, tracks_json, created_at)` → resultados precomputados
- `lyrics(track_id, text, language, source)` → letras
- `similar(track_a, track_b, score)` → similitud precomputada

### Catálogo local (radiov/db.py) tiene además
`blacklist`, `events` (log), `agent_state`, `artist_pool` (para el recolector). En el backend online
esas no hacen falta (la app usa la API).

---

## Relaciones / constraints
- `reactions.user_id → users.id`, `.track_id → tracks.id` (FK), `UNIQUE(user_id, track_id)`.
- `playlists.user_id → users.id`; `playlist_tracks.playlist_id → playlists.id`, `.track_id → tracks.id`.
- `plays.user_id → users.id`, `.track_id → tracks.id`.
- `tracks.deezer_id UNIQUE` (dedup).

---

## Estrategia de indexación (para recomendación y búsqueda)
- **Búsqueda**: FTS5 sobre `title/artist/album` (y futuro `lyrics`). Facetas con índices normales.
- **Recomendación** (content): agregar `(bpm, energy, valence)` y `similar` precomputada; en Postgres usar
  **pgvector** para similitud por vector de features.
- **Señales**: `plays(user_id, played_at)`, `reactions(user_id, track_id)`, `playlist_tracks(playlist_id, position)`.

---

## Migración
- **SQLite local → Backend**: `backend/migrate_sqlite.py` (idempotente, dedup por `deezer_id` / artista+título).
- **Postgres**: los `models.py` de SQLAlchemy son portables; cambiar `DATABASE_URL`. Para producción se
  recomienda **Alembic** (migraciones versionadas) en lugar de `create_all`.
