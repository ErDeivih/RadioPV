# 🌐 RadioPV · Especificación de la app web (React) — FASE F3

> Detalle ejecutable de la fase F3 de [`09_IMPLEMENTATION_PLAN.md`](09_IMPLEMENTATION_PLAN.md).
> Requiere **F0 y F1 terminadas** (sin `/stream` no hay nada que reproducir).
> Todo lo que aquí se afirma sobre el repo de origen está verificado sobre el código real.

---

## 1. Punto de partida

| | |
|---|---|
| Repo | `vendor/spotify-web` — React **19** + TS + Redux Toolkit + Vite + **antd 5** |
| ⚠️ | `vendor/spotify-react-web-client-main` está **vacío** (la extracción del tarball falló). Ignorarlo o borrarlo. |
| Páginas | `Home · Search · Album · Artist · Playlist · LikedSongs · User · Browse · Discography · Genre · 404` |
| Servicios | `albums · artist · auth · categories · episodes · player · playlists · search · users` |
| Slices | `album · artist · auth · browse · discography · editPlaylistModal · genre · home · language · likedSongs · playingNow · playlist · profile · queue · search · searchHistory · spotify · ui · yourLibrary` |
| Scripts | `yarn dev` · `yarn build` · `yarn preview` |

**Lo que ya trae y hay que conservar** (`src/axios.ts`): limitador de concurrencia (3 peticiones
simultáneas), **caché de GETs en IndexedDB** (24 h) y *backoff* ante 429. Está bien pensado; solo hay
que cambiar a qué API apunta.

### Paso 0

```powershell
Copy-Item -Recurse vendor\spotify-web frontend
cd frontend
Remove-Item -Recurse -Force .git -ErrorAction SilentlyContinue
yarn install
```

**No editar dentro de `vendor/`.** `vendor/` es la referencia intacta; se trabaja en `frontend/`.

`frontend/.env`:

```
VITE_API_URL=http://127.0.0.1:8000
VITE_APP_NAME=RadioPV
```

---

## 2. La decisión que ahorra el 80 % del trabajo: capa adaptadora

Los `services/`, `slices/` e `interfaces/` están modelados sobre la API de Spotify: objetos anidados
(`album.images[]`, `artists[]`, `uri`, `duration_ms`) y paginación `{items, total, next}`. Reescribir
`src/interfaces/*.d.ts` obliga a tocar prácticamente **todos** los componentes.

**En vez de eso**: se traduce nuestro `TrackOut` a la forma que la UI ya espera, en un único módulo.
Se tocan **~10 ficheros en lugar de ~60** y las páginas, los slices y los componentes siguen
funcionando sin cambios.

### `src/api/types.ts` (nuevo)

```ts
/** Lo que devuelve la API de RadioPV (ver docs/02_API.md). */
export interface TrackOut {
  id: number; title: string; artist: string; album?: string | null;
  year?: number | null; era?: string | null; genre?: string | null; language?: string | null;
  bpm?: number | null; energy?: number | null; tags?: string | null;
  is_remix: boolean; explicit: boolean;
  duration?: number | null;            // segundos
  cover?: string | null;               // "/media/covers/693008911.jpg"
  feat?: string | null; rank?: number | null; gain_db?: number | null;
}

export interface ArtistOut {
  id: number; name: string; image?: string | null;
  nb_fan?: number | null; track_count?: number | null;
}

export interface PlaylistOut {
  id: number; name: string; description?: string | null; type: string; n_tracks: number;
}
```

### `src/api/adapt.ts` (nuevo)

```ts
import type { TrackOut, ArtistOut, PlaylistOut } from './types';

const API = import.meta.env.VITE_API_URL as string;
const img = (p?: string | null) => (p ? API + p : undefined);
const PLACEHOLDER = '/images/playlist.png';   // ya existe en public/images

export const toArtist = (a: ArtistOut) => ({
  id: String(a.id), name: a.name, type: 'artist', uri: `radiopv:artist:${a.name}`,
  images: a.image ? [{ url: img(a.image)!, height: 640, width: 640 }] : [],
  followers: { total: a.nb_fan ?? 0 }, genres: [], external_urls: { spotify: '' },
});

export const toTrack = (t: TrackOut) => ({
  id: String(t.id),
  name: t.title,
  duration_ms: Math.round((t.duration ?? 0) * 1000),
  explicit: t.explicit,
  track_number: 1, disc_number: 1, is_local: false, is_playable: true,
  popularity: Math.round(((t.rank ?? 0) / 1_000_000) * 100),
  uri: `radiopv:track:${t.id}`,
  preview_url: null,
  external_urls: { spotify: '' }, external_ids: {}, available_markets: [],
  artists: [{ id: t.artist, name: t.artist, type: 'artist', uri: `radiopv:artist:${t.artist}` }],
  album: {
    id: t.album ?? '', name: t.album ?? '', album_type: 'album',
    release_date: t.year ? String(t.year) : '',
    images: [{ url: img(t.cover) ?? PLACEHOLDER, height: 640, width: 640 }],
    artists: [{ id: t.artist, name: t.artist, type: 'artist' }],
    uri: `radiopv:album:${t.artist}::${t.album ?? ''}`,
  },
  // extras propios: la UI de Spotify los ignora, los nuestros los usan
  radiopv: { bpm: t.bpm, energy: t.energy, era: t.era, genre: t.genre,
             tags: t.tags, feat: t.feat, gain_db: t.gain_db ?? 0 },
});

export const toPlaylist = (p: PlaylistOut, cover?: string) => ({
  id: String(p.id), name: p.name, description: p.description ?? '',
  type: 'playlist', uri: `radiopv:playlist:${p.id}`,
  images: [{ url: cover ?? PLACEHOLDER, height: 640, width: 640 }],
  tracks: { total: p.n_tracks, items: [] },
  owner: { id: 'me', display_name: 'RadioPV' }, public: false, collaborative: false,
});

/** Envoltorio de paginación que la UI espera (items/total/next). */
export const toPage = <T,>(items: T[], total: number, limit: number, offset: number) => ({
  items, total, limit, offset,
  next: offset + limit < total ? String(offset + limit) : null,
  previous: offset > 0 ? String(Math.max(0, offset - limit)) : null,
  href: '',
});
```

> `toPage` se alimenta de la cabecera **`X-Total-Count`** que añade T-15. Recordar que el backend debe
> enviar `Access-Control-Expose-Headers: X-Total-Count` o el navegador **no la ve** (fallo silencioso
> clásico: `total` siempre 0).

---

## 3. Ficheros a tocar (y solo estos)

### 3.1 `src/axios.ts`

```ts
const path = import.meta.env.VITE_API_URL as string;          // ← era https://api.spotify.com/v1
const CACHEABLE_PATH = /^\/(tracks|artists|playlists)(\/|$)/; // ← catálogo nuestro
```

- El token se lee de `localStorage` igual que antes, pero es **nuestro JWT**.
- En **401**: no re-lanzar el OAuth de Spotify → limpiar el token y despachar `authActions.logout()`
  para que aparezca el modal de login.
- **Conservar** el limitador de concurrencia y la caché de IndexedDB: siguen siendo útiles.
- ⚠️ **Invalidar la caché de IndexedDB al desplegar** (`cacheKeyFor` con un prefijo de versión); si no,
  usuarios con datos de Spotify cacheados verán basura tras el cambio.

### 3.2 `src/api/auth.ts` (nuevo) — sustituye a `utils/spotify/login.ts`

```ts
import Axios from 'axios';
const API = import.meta.env.VITE_API_URL as string;
const raw = Axios.create({ baseURL: API });

export const login = async (email: string, password: string) => {
  const form = new URLSearchParams({ username: email, password });   // OAuth2PasswordRequestForm
  const { data } = await raw.post('/auth/login', form,
    { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } });
  localStorage.setItem('access_token', data.access_token);
  return data;                                    // { access_token, token_type, user }
};

export const register = (email: string, password: string, display_name: string, invite?: string) =>
  raw.post('/auth/register', { email, password, display_name, invite_code: invite })
     .then(r => { localStorage.setItem('access_token', r.data.access_token); return r.data; });

export const logout = async () => {
  try { await raw.post('/auth/logout', {}, { headers: auth() }); } finally {
    localStorage.removeItem('access_token'); localStorage.removeItem('stream_token');
  }
};

const auth = () => ({ Authorization: 'Bearer ' + localStorage.getItem('access_token') });
```

> **Ojo**: `/auth/login` usa `OAuth2PasswordRequestForm` (formulario, campo `username` con el email),
> **no** JSON. `/auth/register` sí es JSON. Es la incoherencia más fácil de sufrir aquí.

### 3.3 `src/api/stream.ts` (nuevo) — el token de reproducción

```ts
const API = import.meta.env.VITE_API_URL as string;
let token: string | null = null;
let expira = 0;

export const streamToken = async (): Promise<string> => {
  if (token && Date.now() < expira - 60_000) return token;
  const r = await fetch(`${API}/auth/stream-token`, {
    method: 'POST',
    headers: { Authorization: 'Bearer ' + localStorage.getItem('access_token') },
  });
  if (!r.ok) throw new Error('No se pudo obtener el token de reproducción');
  const d = await r.json();
  token = d.token; expira = Date.now() + d.expires_in * 1000;
  return token!;
};

export const streamUrl = async (trackId: number | string) =>
  `${API}/stream/${trackId}?t=${encodeURIComponent(await streamToken())}`;
```

**Por qué existe**: `<audio src>` **no puede enviar la cabecera `Authorization`**, así que la
autenticación viaja en la URL con un token de ámbito `stream` y 30 minutos de vida (ver T-12).

### 3.4 `src/services/*` — mapeo endpoint a endpoint

| Servicio / método | Antes (Spotify) | Ahora (RadioPV) |
|---|---|---|
| `auth.fetchUser` | `GET /me` | `GET /auth/me` |
| `search.*` | `GET /search?type=…` | `GET /tracks?q=` + `GET /artists?q=` |
| `albums.fetchAlbum` | `GET /albums/{id}` | `GET /tracks?artist=X&album=Y` |
| `artist.fetchArtist` | `GET /artists/{id}` | `GET /artists/{name}` |
| `artist.fetchTopTracks` | `GET /artists/{id}/top-tracks` | `GET /artists/{name}/top` |
| `artist.fetchAlbums` | `GET /artists/{id}/albums` | `GET /artists/{name}/albums` |
| `playlists.fetch*` | `GET /playlists/{id}` | `GET /playlists` · `GET /playlists/{id}/tracks` |
| `playlists.add/remove` | `POST/DELETE …/tracks` | `POST/DELETE /playlists/{id}/tracks/{track}` |
| `users.fetchLiked` | `GET /me/tracks` | **`GET /library/liked`** (una sola petición) |
| `users.saveTrack` | `PUT /me/tracks` | `POST /library/{id}/like` con body `{"liked":true}` |
| `player.play/pause/seek` | `PUT /me/player/*` | **borrar**: lo gestiona el `<audio>` local |
| `player.recentlyPlayed` | `GET /me/player/recently-played` | `GET /library/history` (F4) |
| Home "Made for you" | URIs fijas de Spotify | `GET /recommend` · `/recommend/daily` · `/playlists/system` |

**Servicios a borrar enteros**: `episodes.ts` (no hay podcasts) y `categories.ts` (o reapuntarlo a
`GET /facets`). También `utils/spotify/getDeviceIcon.tsx` y todo lo relativo a `devices`.

### 3.5 `src/constants/spotify.ts`

Sustituir las URIs fijas de playlists de Spotify por identificadores nuestros, servidos por
`GET /playlists/system`. Las imágenes por defecto (`images/playlist.png`, `artist.png`,
`liked-songs.png`, `equaliser.gif`) **ya están** en `public/images`: se conservan.

### 3.6 `src/utils/spotify/webPlayback.tsx` → **borrar** y sustituir por el reproductor propio

Todo el SDK de Spotify (`Spotify.Player`, polling de estado, espera de dispositivo) desaparece.

---

## 4. El reproductor (aquí es donde se gana o se pierde la app)

### `src/player/usePlayer.ts` (nuevo)

Un único `<audio>` creado una vez, con cuatro cosas que separan un reproductor casero de uno bueno:

```ts
import { useEffect, useRef } from 'react';
import { streamUrl } from '../api/stream';

export function usePlayer() {
  const audio = useRef<HTMLAudioElement>();
  const ctx = useRef<AudioContext>();
  const gain = useRef<GainNode>();
  const precarga = useRef<HTMLAudioElement>();   // (3) precarga de la siguiente

  // (1) Ganancia por canción: normalización de volumen (gain_db, ver T-22)
  const init = () => {
    if (audio.current) return;
    const a = new Audio(); a.crossOrigin = 'anonymous'; a.preload = 'auto';
    // ⚠️ 'anonymous', NUNCA 'use-credentials': con credenciales el navegador exige
    // Access-Control-Allow-Credentials y un origen concreto; si falla, el elemento queda
    // "tainted" y createMediaElementSource devuelve SILENCIO sin error claro.
    const c = new AudioContext();
    const src = c.createMediaElementSource(a);
    const g = c.createGain();
    src.connect(g); g.connect(c.destination);
    audio.current = a; ctx.current = c; gain.current = g;
  };

  const play = async (track: any) => {
    init();
    gain.current!.gain.value = Math.pow(10, (track.radiopv?.gain_db ?? 0) / 20);
    audio.current!.src = await streamUrl(track.id);
    await ctx.current!.resume();          // los navegadores exigen un gesto del usuario
    await audio.current!.play();
    mediaSession(track);                  // (2)
    fetch(`${API}/library/${track.id}/play`, {                   // (4) señal
      method: 'POST', headers: { ...jsonAuth() },
      body: JSON.stringify({ source: 'player', context: contextoActual() }),
    });
  };
  // …
}
```

### (2) Media Session API — ~30 líneas que hacen que parezca nativa

Controles en la **pantalla de bloqueo del móvil**, en los botones de los auriculares y en el centro de
notificaciones, con carátula:

```ts
const mediaSession = (t: any) => {
  if (!('mediaSession' in navigator)) return;
  navigator.mediaSession.metadata = new MediaMetadata({
    title: t.name, artist: t.artists[0].name, album: t.album.name,
    artwork: [{ src: t.album.images[0].url, sizes: '512x512', type: 'image/jpeg' }],
  });
  navigator.mediaSession.setActionHandler('play',  () => audio.current!.play());
  navigator.mediaSession.setActionHandler('pause', () => audio.current!.pause());
  navigator.mediaSession.setActionHandler('nexttrack', siguiente);
  navigator.mediaSession.setActionHandler('previoustrack', anterior);
  navigator.mediaSession.setActionHandler('seekto', (d) => { audio.current!.currentTime = d.seekTime!; });
};
```

### (3) Precarga de la siguiente

Cuando queden **~20 s**, crear un `<audio>` oculto con la URL de la siguiente y `preload="auto"`. Sin
esto hay un silencio de uno o dos segundos entre temas que se nota muchísimo.

### (4) Señales de escucha

- Al empezar: `POST /library/{id}/play` con `{source, context}`.
- Al terminar o saltar: `POST /library/{id}/play` con `seconds_listened` y `completed`.
- Saltar antes del 30 % ⇒ además `POST /library/{id}/skip` con `{"skipped": true}`.

`context` debe ser `"playlist:12"`, `"radio:88"`, `"daily"`, `"search"` o `"artist"` — el motor de
personalización (F4) lo usa para no tratar igual un descubrimiento que una escucha buscada.

### (5) Shuffle con restricción de artista

El aleatorio uniforme repite artistas y suena mal:

```ts
export const barajarConSeparacion = <T extends { artists: { name: string }[] }>(xs: T[]) => {
  const r = [...xs].sort(() => Math.random() - 0.5);
  for (let i = 1; i < r.length; i++) {
    if (r[i].artists[0].name === r[i - 1].artists[0].name) {
      const j = r.findIndex((x, k) => k > i && x.artists[0].name !== r[i - 1].artists[0].name);
      if (j > -1) [r[i], r[j]] = [r[j], r[i]];
    }
  }
  return r;
};
```

### (6) Reproducción continua ("Flow")

Cuando la cola se agota, en vez de parar: `GET /recommend/radio?seed_track={última}` y encolar. Con
`radio()` ya implementado es casi gratis y cambia por completo la sensación de uso.

---

## 5. Pantallas: qué cambia respecto al repo original

| Página | Cambio |
|---|---|
| **Home** | filas: "Para ti" (`/recommend`), "Mix diario" (`/recommend/daily`), "Trending" y "Novedades" (`/playlists/system`), "Tus artistas" (`/artists`) |
| **Search** | `GET /tracks?q=` con *debounce* (ya usa `use-debounce`) + chips de faceta desde `GET /facets` |
| **Artist** | `GET /artists/{name}` + `/top` + `/albums`; botón **"Radio de este artista"** |
| **Album** | `GET /tracks?artist=&album=` |
| **LikedSongs** | `GET /library/liked` (**una** petición, no N+1) |
| **Playlist** | añadir borrar, renombrar y reordenar (`react-drag-listview` ya está en las dependencias) |
| **Browse / Genre** | por géneros y eras reales de `GET /facets` |
| **User** | perfil + **ajuste "ocultar contenido explícito"** (filtro familiar) |
| **Discography** | `GET /artists/{name}/albums` |

**Nuevo — Ajustes**: interruptor de contenido explícito, idioma, y **cerrar sesión**.

⚠️ Al diseñar Home y Browse, dos datos del catálogo real: `is_remix=1` solo en **7** canciones (una
sección "Remixes" saldría vacía) y la distribución por décadas está muy sesgada a lo reciente
(20s: 483 · 10s: 290 · 00s: 225 · 90s: 53 · 80s: 29 · 70s: 15 · 60s: 3). **No prometer secciones que
el catálogo no puede llenar.**

**Estado vacío útil**: cuando una búsqueda no da resultados, ofrecer *"pedir esta canción"* →
`POST /requests` que la encola en el recolector. Convierte una frustración en una función.

---

## 6. Criterios de aceptación de F3

- [ ] Registro y login contra nuestra API; el token persiste al recargar.
- [ ] Home carga sin una sola llamada a `api.spotify.com` (comprobar en la pestaña Red).
- [ ] Reproducir una canción **suena** y la barra de progreso **permite arrastrar** (206 en la pestaña Red).
- [ ] Cambio de canción **sin silencio** perceptible (precarga activa).
- [ ] El volumen entre canciones distintas es **uniforme** (ganancia aplicada).
- [ ] Controles en la pantalla de bloqueo del móvil, con carátula.
- [ ] 👍 cambia `/recommend` en la siguiente carga.
- [ ] "Me gusta" se pinta con **una** petición.
- [ ] Crear playlist, añadir, quitar, reordenar y borrar.
- [ ] Con el filtro de explícito activo, ninguna canción marcada aparece en ninguna lista.
- [ ] `yarn build` sin errores de TypeScript.
