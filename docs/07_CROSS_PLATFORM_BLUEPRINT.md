# 📱🌐 RadioPV · Blueprint completo Web + Móvil con backend común (estudio en profundidad)

> **ESTADO REAL (2026-08-30):** La web (React) está implementada y verificada — **esa es la app de
> móvil**, desplegada como **PWA instalable** (manifest con iconos 192/512 maskable + service worker que
> cachea la carcasa, nunca el audio ni la API + Media Session para los controles en pantalla de
> bloqueo/auriculares). **El bloque móvil (Flutter/Musive) está APLAZADO y NO bloquea el proyecto**:
> no hay SDK de Flutter instalable en ningún entorno (la lista de egreso bloquea `storage.googleapis.com`
> y GitHub; solo pasan pypi y npm), así que no hay analizador de Dart y no compensa escribir la app a
> ciegas. `mobile/` (copia de Musive) queda como referencia; el estado vivo está en `PROGRESS.md`.

> Estudio de los dos repos **descargados** (`vendor/spotify-web` y `vendor/Flutter-Musive-app`) para
> construir una **app completa multiplataforma** con **un backend común** (el nuestro). Sin programar:
> esto define qué reutilizar, qué archivos tocar, flujos, BD, comunicación y fases.

---

## 1. Estudio en disco (qué hay realmente)

### A) `vendor/spotify-web` (React + TS + Redux + Vite + antd)
**Arquitectura**:
- **API cliente** (`src/axios.ts`): baseURL `https://api.spotify.com/v1`, con **limitador de concurrencia (3)**,
  **caché IndexedDB** para GETs de catálogo (24h), y manejo de **401 (re-login)** y **429 (backoff)**.
- **Servicios** (`src/services/*`): `auth, player, playlists, albums, artist, search, users, categories, episodes`.
- **Store Redux** (`src/store/slices/*`): `auth, ui, playingNow, queue, yourLibrary, profile, search,
  home, album, artist, playlist, discography, genre, browse, likedSongs, searchHistory, editPlaylistModal…`.
- **Interfaces** (`src/interfaces/*`): `track, artist, album, playlists, user, player, api, devices, episode…`.
- **Utils Spotify** (`src/utils/spotify/*`): `login` (OAuth Spotify), `webPlayback` (SDK), `getDeviceIcon`, `sumTracksLength`.
- **Páginas** (`src/pages/*`): Home, Search (Con tabs: Songs/Albums/Artists/Playlists), Album, Artist,
  Playlist, LikedSongs, User (Home/Playlists/Artists/Songs), Browse, Discography, Genre, 404.
- **Componentes** (`src/components/*`): Layout (Navbar, Library, NowPlaying, PlayingBar), Lists (carousels),
  SongsTable, Slider, Drawers (Library/PlayingNow), Modals (Login, EditPlaylist, Language), FullScreen, Tooltip, Icons, Actions.
- **Constantes** (`src/constants/spotify.ts`): URIs de playlists "Made for you/Trending/Ranking" de Spotify y
  **rutas de imágenes por defecto** (`images/playlist.png`, `artist.png`, `liked-songs.png`, `equaliser.gif`).

**Qué aprovechar**: toda la UI/pantallas/componentes y la **lógica de red** (concurrencia/caché/errores).
**Qué reemplazar**: `axios.ts` baseURL → nuestra API; `services/*` → nuestros endpoints; `login` → nuestro
JWT; `webPlayback` → `<audio>`; `constants/spotify` → nuestras playlists/imágenes; interfaces → nuestro esquema.

### B) `vendor/Flutter-Musive-app` (Flutter + Dart)
**Arquitectura**:
- `lib/api/url.dart`: `baseUrl = 'cryptic-forest-99443.herokuapp.com'`, `basePath = '/api/v1'` (backend Node).
- `lib/repositories/*`: `get_home_page, get_one_song, get_search_results, get_artists_data, get_genre_data`.
- `lib/models/*`: `song_model, user, user_model, catagory, loading_enum`.
- `lib/screens/*`: home, search_page, search_results, library, liked_songs, playlist, artist_profile,
  genre_page, recently_played, add_to_playlist, current_playing, bottom_nav_bar.
- `lib/utils/*`: `player` (reproductor con notificación), `play_list`, `bottom_play_widget`, `like_button`,
  `recent_search`, `horizontal_songs_list`, `sliver_appbar`, `loading`…
- `lib/controllers/main_controller.dart`, `lib/methods/*` (get_greeting, get_response, log, snackbar…).

**Qué aprovechar**: toda la app móvil (pantallas, reproductor con notificación, cola, likes, caché, búsqueda).
**Qué reemplazar**: `url.dart` → nuestra base; `repositories` → nuestros endpoints; `controllers/user` → nuestro
JWT; `methods/get_response` → nuestro cliente HTTP; el stream de audio → nuestro `/stream/{id}`.

---

## 2. El backend común (NUESTRO FastAPI) — único punto
Ya está y funciona (`backend/`). Añadir para soportar **web+móvil**:
- `GET /stream/{track_id}` → `FileResponse` del MP3 con **soporte `Range`** (seek en web y móvil).
- `GET /media/...` → carátulas/fotos locales. Las carátulas van por `cover` (TrackOut) y las **fotos de
  artista** por `image` (ArtistOut); la foto se pide por artista (`artists.image_path`), no por canción.
- CORS abierto (web) y **URL pública** para el móvil.
- (Opcional) **refresh token** para el cliente web (hoy el JWT dura 24h).

### Comunicación (contratos)
- **Auth**: `POST /auth/login|register` (JSON para React; el Flutter adapta su login), `GET /auth/me`.
- **Catálogo**: `GET /tracks` (+filtros), `GET /artists`, `GET /artists/{name}/albums`.
- **Biblioteca**: `POST /library/{id}/play|like|skip`, `GET /library/reactions`.
- **Playlists**: `GET/POST /playlists`, `GET /playlists/{id}/tracks`, `POST /playlists/{id}/tracks/{track}`.
- **Recomendación**: `GET /recommend`, `/recommend/daily`, `/recommend/radio?seed_track=`.

> Correspondencia de nombres de la API de Spotify → nuestra API (para mapear servicios):
> `GET /me` → `/auth/me` · `GET /tracks` → `/tracks` · `/search` → `/tracks?q=` ·
> `/albums/{id}` → o `/artists/{name}/albums` o un futuro `/albums/{id}` ·
> `/playlists/{id}` → `/playlists/{id}` · `/me/tracks` (liked) → `/library/reactions` ·
> `/me/player/*` (playback) → nuestro `/stream` + estado local de cola.

---

## 3. Base de datos
Nuestro esquema ([`01_SCHEMA.md`](01_SCHEMA.md)) sirve. Ambas apps consumen `tracks/artists`
`artist_albums`, `reactions`, `plays`, `playlists/playlist_tracks`, `taste_profile`. Añadir si se
necesita: `devices` (para el selector de dispositivos del reproductor web) y `similar` (radios).

---

## 4. Adaptación por cliente (archivos exactos)

### Web (`vendor/spotify-web` → `frontend/`)
| Archivo | Cambio |
|---|---|
| `src/axios.ts` | `baseURL` → `http://localhost:8000` (o prod). En 401 → re-login (nuestro JWT) |
| `src/constants/spotify.ts` | URIs de playlists → nuestras playlists (`/playlists/system`); imágenes por defecto → copiar `public/images/*` o nuestras carátulas |
| `src/utils/spotify/login.ts` | Reemplazar por login/registro con nuestro `/auth/login\|register`; guardar `access_token` |
| `src/utils/spotify/webPlayback.tsx` | Reemplazar SDK → `<audio src={streamUrl(trackId)}>` (HTML5) |
| `src/services/*` (auth, player, playlists, albums, artist, search, users…) | Llama a la API de Spotify → apuntar a nuestros endpoints (ver mapeo) |
| `src/store/slices/auth.ts` | `loginToSpotify` → `loginToRadioPV`; `fetchUser` → `/auth/me` |
| `src/interfaces/*` | Mapear a nuestro esquema (son similares: `track, artist, album, playlists, user, player`) |
| `src/pages/Home`, `Search`, `LikedSongs`… | Ya consumen los servicios; al cambiarlos, usan nuestros datos |
| Playback | Los slices `playingNow`, `queue` gestionan la cola en Redux; el `<audio>` reproduce nuestro stream |
| Modal `Login` | Adaptar a login/registro con email+contraseña |

Claves:
- El **catálogo es solo-lectura** en el cliente (la app no descarga música; el **recolector** lo hace). La UI muestra lo que hay.
- Los **"hecho para ti"/trending** se cargan de `GET /recommend`, `/playlists/system` (autogeneradas por el worker).

### Móvil (`vendor/Flutter-Musive-app` → `mobile/`)
| Archivo | Cambio |
|---|---|
| `lib/api/url.dart` | `baseUrl` → `http://localhost:8000`; `basePath` → `''` |
| `lib/repositories/*` | apuntar a nuestros endpoints (home → `/tracks`, search → `/tracks?q=`, playlists → `/playlists`, artist → `/artists/{name}`, song → `/stream/{id}`) |
| `lib/models/song_model.dart` | mapear a nuestro `TrackOut` (id, title, artist, cover…) |
| Login/`controllers/main_controller` | `POST /auth/login` (JWT) en lugar del backend Node |
| `lib/utils/player.dart` | reproducir desde `/stream/{id}`; mantener notificación/caché |
| **Android** | permiso de red; en local `usesCleartextTraffic=true`; en prod, HTTPS |

---

## 5. Flujos de usuario (web y móvil)
1. **Registro/Login** → `POST /auth/register|login` → guardar token → `GET /auth/me` (perfil).
2. **Inicio** → Home carga "Recomendadas", "Trending", "Tus artistas" (`/recommend`, `/playlists/system`, `/artists`).
3. **Buscar** → `GET /tracks?q=` (FTS) + facetas.
4. **Reproducir** → `<audio>` / `player` con `GET /stream/{id}`; se guarda `POST /library/{id}/play`.
5. **Me gusta / saltar** → `POST /library/{id}/like|skip` → refina el perfil y los mixes.
6. **Playlists** → crear (`POST /playlists`), añadir (`POST /playlists/{id}/tracks/{track}`), reproducir.
7. **Personalización** → `GET /recommend|daily|radio` (el worker refresca las listas automáticas).

### Flujo del backend (catálogo/novedades)
`recolector/worker` → descarga y etiqueta (revisor) → `tracks` actualizada → el **worker de actualidad**
(`refresh_trends/new_releases/mixes`) crea playlists automáticas → la UI las sirve.

---

## 6. Fases de construcción
| Fase | Contenido | Resultado |
|---|---|---|
| **1. Backend para ambas** | `/stream/{id}` (Range) + `/media/*` + CORS + JWT móvil (+ refresh) | Base lista para web y móvil |
| **2. Web (React)** | Adaptar axios/services/auth/webPlayback/interfaces; imágenes locales | Web funcional estilo Spotify |
| **3. Móvil (Flutter)** | url/repositories/login/player → nuestra API | App Android/iOS funcional |
| **4. Playlists + worker** | playlists automáticas + tendencias/novedades + mixes | "Para ti" y trending dinámicos |
| **5. Despliegue** | Docker (api+postgres+worker+web) + HTTPS + APK/AAB | Multiplataforma publicable |

**Nota de esfuerzo**: el backend está; el grueso es la **adaptación de las dos UIs** (capa de datos/red),
no su reescritura — ambas son completas.

---

## 7. Riesgos / pautas
- **Los repos apuntan a Spotify (web) y Node (móvil)**: se reemplaza la capa de datos/red, no se reescribe la UI.
- **Streaming**: web `<audio>` con Range; móvil con notificación en segundo plano (el Flutter ya lo trae,
  solo hay que apuntarlo a `/stream`).
- **Caché/errores**: el React trae concurrencia + IndexedDB + 401/429; reutilizarlo tal cual.
- **Imágenes por defecto**: copiar `public/images/*` del React al front; o usar nuestras carátulas locales.
- **Backend**: no romper contratos (`02_API.md`); idempotencia en workers; legal (uso personal, ToS YouTube).

---

> Ver también: `00_INDEX` · `01_SCHEMA` · `02_API` · `03_PERSONALIZATION` · `04_PLAYLISTS_WORKER` ·
> `05_UI` · `06_BUILD_GUIDE`. Repos en `vendor/` para estudiar/adaptar.
