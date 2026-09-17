# 🔌 RadioPV · Contrato de la API (FastAPI)

> Base: `http://localhost:8000`. Docs interactivas en `/docs`. **Auth**: JWT Bearer en
> `Authorization: Bearer <token>`. Los endpoints de **biblioteca/playlists/recommend requieren auth**;
> **tracks/artists** son públicos (catálogo).

## Auth
| Método | Ruta | Body / params | Respuesta |
|---|---|---|---|
| POST | `/auth/register` | `{"email","password","display_name"}` | `{"access_token","token_type","user":{...}}` |
| POST | `/auth/login` | form `username`(=email), `password` | igual que register |
| GET | `/auth/me` | — | `{"id","email","display_name","is_admin","created_at"}` |
| POST | `/auth/logout` | — | `{"ok":true}` (revoca el token vía `token_version`) |
| POST | `/auth/stream-token` | — | `{"token","expires_in"}` (token corto, 30 min, `scope=stream`. Para `<audio>` por URL; NO sirve como sesión) |

Ejemplo login (OAuth2 form):
```
POST /auth/login   Content-Type: application/x-www-form-urlencoded
username=ana@x.com&password=s3cret123
```

## Catálogo
| Método | Ruta | Params / body | Respuesta |
|---|---|---|---|
| GET | `/tracks` | query: `q, genre, language, year, era, mood, energy(Baja|Media|Alta), remix, limit, offset` | `TrackOut[]` |
| GET | `/tracks/{id}` | — | `TrackOut` |
| GET | `/artists` | `limit` | `ArtistOut[]` (con `track_count`) |
| GET | `/artists/{name}` | — | `ArtistOut` (404 si no existe) |
| GET | `/artists/{name}/top` | `limit` | `TrackOut[]` (por `rank` desc) |
| GET | `/artists/{name}/albums` | — | `AlbumOut[]` |
| POST | `/tracks/{id}/report` | — | `{"ok":true,"status":"revisar"}` |
| GET | `/facets` | — | `{"genres":[…],"eras":[…],"languages":[…],"years":[…],"moods":[…]}` (valor+conteo) |

## Streaming (auth por URL)
| Método | Ruta | Params | Respuesta |
|---|---|---|---|
| GET | `/stream/{track_id}` | `t` = token de `/auth/stream-token` | `200/206 audio/mpeg` · `Accept-Ranges: bytes` · `Content-Range` en 206 · `401` token inválido · `404` canción inexistente/retirada/sin fichero · `410` fichero fuera de disco · `416` rango no satisfacible |

> **CORS**: `Access-Control-Expose-Headers: X-Total-Count, Content-Range, Accept-Ranges, Content-Length`
> — el navegador necesita ver `Content-Range` para que el `seek` del `<audio>` funcione limpio.
> El `<audio>` usa `crossOrigin='anonymous'` (NO `use-credentials`): con credenciales el elemento queda
> `tainted` y el `GainNode` devuelve silencio sin error.

`TrackOut`:
```json
{"id":1,"title":"Rosas","artist":"La Oreja de Van Gogh","album":"[...]","year":2004,
 "era":"00s","genre":"pop","bpm":107.7,"energy":0.5,"tags":"...","is_remix":false,
 "explicit":false,"file_path":"...","cover_path":"...","cover_url":"...",
 "artist_image_path":"...","artist_image_url":"...","deezer_id":"...","duration":202.2}
```
`ArtistOut`: `{id,name,image_path,image_url,nb_fan,track_count}`.
`AlbumOut`: `{title,year,cover_url}`.

## Biblioteca (auth)
| Método | Ruta | Body | Respuesta |
|---|---|---|---|
| POST | `/library/{track}/play` | `{"source":"player","completed":0}` | `{"ok":true}` |
| POST | `/library/{track}/like` | `{"liked":true}` | `{"ok":true}` |
| POST | `/library/{track}/skip` | `{"skipped":true}` | `{"ok":true}` |
| GET | `/library/reactions` | — | `{"liked":[id,...],"skipped":[id,...]}` |
| GET | `/library/liked` | — | `TrackOut[]` (join de reactions+tracks en 1 petición) |

## Playlists (auth)
| Método | Ruta | Body | Respuesta |
|---|---|---|---|
| GET | `/playlists` | — | `PlaylistOut[]` (con `n_tracks`) |
| POST | `/playlists` | `{"name","description","type"}` | `PlaylistOut` |
| GET | `/playlists/{id}/tracks` | — | `TrackOut[]` |
| POST | `/playlists/{id}/tracks/{track}` | — | `{"ok":true}` |
| DELETE | `/playlists/{id}` | — | `{"ok":true}` (borra antes sus `playlist_tracks`) |
| DELETE | `/playlists/{id}/tracks/{track}` | — | `{"ok":true}` (recompacta `position`) |
| PATCH | `/playlists/{id}` | `{"name"?,"description"?}` | `PlaylistOut` |
| PUT | `/playlists/{id}/order` | `[track_id,…]` | `{"ok":true}` (reescribe `position`) |

`PlaylistOut`: `{id,name,description,type,n_tracks}`.

## Recomendación (auth)
| Método | Ruta | Params | Respuesta |
|---|---|---|---|
| GET | `/recommend` | `n, mood` | `TrackOut[]` (por perfil de gustos, diverso: máx. 2 por artista) |
| GET | `/recommend/daily` | `n` | `TrackOut[]` (mix: recomendar + aleatorio) |
| GET | `/recommend/radio` | `seed_track, n` | `TrackOut[]` (lee de la tabla `similar`, < 50 ms) |
| GET | `/recommend/trending` | `n` | `TrackOut[]` (por `rank` de Deezer) |
| GET | `/library/history` | `limit` | `TrackOut[]` (historial de plays, sin repetir) |
| GET | `/playlists/system` | — | `PlaylistOut[]` (Trending, Novedades…) |

---

## Notas de implementación (para el agente)
- **Mantener estos contratos** (SI se cambia algo, actualizar `schemas.py` y este doc).
- Cambiar el modelo a **Postgres**: `DATABASE_URL=postgresql://user:pass@host/db` (+`psycopg2-binary`).
- Los endpoints de **recomendación** deben usar `recommend()/radio()/daily()` reutilizando `_profile/_score`.
- Añadir si se necesita: `GET /recommend/trending`, `GET /playlists/system`, `GET /wrapped`,
  `GET /search` (combinar FTS + facetas). Documentar aquí al añadirlos.
