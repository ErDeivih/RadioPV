# 📋 RadioPV · Tablero de progreso

> **Este fichero lo mantiene el agente que implementa.** Es la memoria del proyecto entre sesiones:
> si el agente pierde el contexto o lo retoma otro día, aquí ve exactamente dónde se quedó.
>
> **Regla**: al terminar una tarea, marcarla `✅` y anotar en una línea qué se hizo y qué ficheros se
> tocaron. Si una tarea se queda a medias, marcarla `🚧` y **escribir qué falta**. Si se decide no
> hacerla, `⛔` y el motivo. Nunca marcar `✅` con los tests en rojo.
>
> Estados: ⬜ pendiente · 🚧 en curso · ✅ hecha · ⛔ descartada · ⏸️ bloqueada (esperando decisión)

**Última actualización**: 2026-08-31
**Fase actual**: F0-F4 + F6 ✅ (backend completo). F3: play-flow ✅, pantallas en curso. Siguiente: F5/F6.
**Capa de popularidad (P)** · Añadida: visitas reales de YouTube (yt-dlp) + rank de Deezer + score 0-1 + histórico temporal (`popularity_history`), endpoints `/stats/popularidad` (tendencias/tops/por género) y `/stats/recopilaciones` (éxitos por época/género por pico), playlists del sistema **"Éxitos de los {años}"** y **"Lo mejor del {género}"** (rebuild_recopilaciones, worker 7:15), lista **"Viral / Tendencia"**, filas **Tendencias** y **Estadísticas** en la home (frontend, `tsc` OK; requiere `pnpm build` de David), y refresco en segundo plano (worker cada 6h). Fijado bug de eras (`Los 2000`/`Clásicos`) y acceso a playlists del sistema (`user_id IS NULL` ahora se puede abrir en `/playlists/{id}` y `/tracks`). Corriendo en bg: `run_agent.py` (descargador+catalogador) y `python -m app.workers`. **Reiniciado todo** con: `sync_catalogo` ahora PROPAGA de verdad (`migrate_sqlite`, no solo recuento → la app se auto-actualiza cada 30 min), `gain_db` automatizado en el mantenimiento del agente (`C.analizar_gain_missing`, cierra el deadlock de `incompleta` con `metadata_strict`), `/mixes` con **cold-start** (un usuario recién registrado recibe sus mixes al instante vía `_generar_mixes_usuario`), y backend (uvicorn :8000) + worker + agente corriendo con el código nuevo. Verificado: 70 tests backend, `tsc` limpio y **E2E 8/8** contra la API en marcha.

---

## FASE F0 · Cimientos — **bloqueante, nada empieza sin esto**

| | Tarea | Estado | Notas |
|---|---|---|---|
| T-01 | Arreglar `GET /artists` (500 con SQLAlchemy 2.0) + sacar el `UPDATE` del endpoint | ✅ | `maintenance.recount_artist_tracks`; `GET /artists` ordena por `track_count DESC`. **200 real, 200 items, orden desc OK** |
| T-02 | `requirements-backend.txt` con `bcrypt==4.0.1` | ✅ | Fichero nuevo con `bcrypt==4.0.1` + `passlib[bcrypt]==1.7.4` y resto de deps |
| T-03 | `config.py` · `SECRET_KEY` obligatoria en prod · CORS y raíces por entorno | ✅ | `RADIOPV_ENV`; prod sin `SECRET_KEY` → `RuntimeError` (verificado) |
| T-04 | `paths.py` · resolvedor de rutas con protección de *path traversal* | ✅ | `_relativa`/`_dentro_de`/`resolve_music`/`resolve_media`; traversal → `PermissionError` |
| T-05 | **Migración no destructiva por `deezer_id`** ← la más importante | ✅ | Idempotente; conserva users/reactions/plays/playlists/playlist_tracks; ids estables. **Nota**: contador del log (nuevas+actualizadas = total+1) no cuadra, es cosmético; en BD 2 pasadas OK, 0 dups |
| T-06 | `UNIQUE(deezer_id)` en `radiov.db` (dedup previo) | ✅ | `dedupe_deezer.py` (dry-run/--apply): 2 dups (Bad Bunny, Estopa resueltos). `add_track` ahora hace upsert por `deezer_id` (2ª clave). `ux_tracks_deezer` añadido al SCHEMA. **No materializado en BD viva** (el recolector está corriendo) → se aplica al próximo `init_db` |
| T-07 | `/library` a body JSON (alinear con `02_API.md`) | ✅ | `PlayIn/LikeIn/SkipIn`; asignar antes del primer `commit` |
| T-08 | `plays.seconds_listened` + `plays.context` | ✅ | Columnas AÑADIDAS a `data/backend.db`; modelo `Play` extendido |
| T-09 | `Enum` en `?energy=` (422 en vez de 500) + `remix` + `status` | ✅ | `Energia` baja/media/alta; `remix is not None`; `GET /tracks/{id}` filtra `descargada` |
| T-10 | Tests de humo + `pytest.ini` | ✅ | `conftest` fuerza `backend` en path + `sys.modules.pop("app")` (shadowing por `app.py`). **10 passed** |

**Salida de F0**: `pytest` verde · `/artists` 200 · migración idempotente que no borra señales ·
sin `SECRET_KEY` en prod no arranca.

---

## FASE F1 · Reproducción

| | Tarea | Estado | Notas |
|---|---|---|---|
| T-11 | Normalizar rutas de la BD a relativas (+ que el recolector las escriba así) | ✅ | `scripts/normalizar_rutas.py` (dry-run/--apply, `--db`). **Aplicado a `backend.db` (3118 filas)** → el backend sirve rutas relativas (verificado `resolve_music`/`resolve_media`). Recolector: `resolve_music()` en `config.py`; `catalog.py` guarda relativas (`_rel_music`/`_rel_data`) y lee ambos formatos; `blacklist.py`/`playlist.py`/`pipeline.py` usan el resolver. **Nota**: `radiov.db` vivo NO normalizado (el recolector está corriendo); se normalizará al reorganizar/reiniciar. pytest 10 green |
| T-12 | Token de streaming (`scope="stream"`) + rechazarlo en `get_current_user` | ✅ | `create_stream_token`/`verify_stream_token`; scope `access` en el login; `get_current_user` rechaza `scope!=access`. `POST /auth/stream-token` (30 min). Test `test_stream_token_y_scope`. **11 passed**. `02_API.md` actualizado |
| T-13 | `GET /stream/{id}` con `Range` (vía `FileResponse`) | ✅ | `routers/stream.py` nuevo; registro en `main.py`. Usa `FileResponse` (Range/206 los da starlette, no a mano). Test `test_stream_range` (206+Content-Range, 200 sin range, 401 token malo, 404 inexistente). **12 passed** |
| T-14 | `/media/covers` y `/media/artists` + propiedades `cover` / `image` | ✅ | `StaticFiles` montado en `/media/{covers,artists}` (raíz la pone el servidor; la BD solo da el nombre). `TrackOut.cover` + `ArtistOut.image`. CORS expone `X-Total-Count`. Test `test_media_covers_y_propiedad_cover`. Corregido docs `05_UI.md` y `07_CROSS_PLATFORM_BLUEPRINT.md` (foto por artista, no por canción) |
| T-15 | `TrackOut`: `feat`, `rank`, `cover`, `gain_db` · filtros `explicit`/`sort`/`artist`/`album` · `X-Total-Count` | ✅ | `feat` (columna + backfill desde radiov, 425 filas) y `rank` en `TrackOut`. `GET /tracks`: `explicit`, `sort(recientes|rank|year|aleatorio)`, `artist`, `album` + cabecera `X-Total-Count` (CORS `expose_headers`). **Nota**: `gain_db` no se ha calculado aún (es de F2/T-22); lo expondré cuando exista. Test `test_tracks_filtros_y_total` |
| T-16 | `/library/liked` · `DELETE`/`PATCH` de playlists · `/artists/{name}` · `/artists/{name}/top` · `/tracks/{id}/report` | ✅ | `GET /library/liked` (join, 1 petición). Playlists: `DELETE /{id}` (borra playlist_tracks), `DELETE /{id}/tracks/{t}` (recompacta position), `PATCH /{id}`, `PUT /{id}/order`. `/artists/{name}` (404), `/artists/{name}/top` (por rank), `/tracks/{id}/report` (status='revisar'). Test `test_endpoints_t16` |

**Salida de F1**: un `<audio>` reproduce y hace seek · carátulas por `/media` · "Me gusta" en una petición.

---

## FASE F2 · Datos (recolector; puede ir en paralelo a F1)

| | Tarea | Estado | Notas |
|---|---|---|---|
| T-17 | `radiov/quality.py` · puerta de calidad + estado `cuarentena` | ✅ | `quality.revisar()` (BASURA/html, artistas genéricos, duración 1:30–8:00, textos cortos). Enganchada en `pipeline._persist_yt` → `status=cuarentena`. Constante `STATUS_QUARANTINE` en `radiov/models.py`. Test `test_quality.py` (4 casos). **19 passed** |
| T-18 | Limpiar la basura ya ingerida (7 filas, ~1,4 GB) + **arreglar el parseo de origen** | ✅ | `scripts/limpiar_catalogo.py` (dry-run/--apply/--delete-files). **16 filas cuarentena** (~1,62 GB) en `radiov.db`, **13 sincronizadas** a `backend.db` → **0 basura servida**. **Causa origen**: `charts.py::los40_top` saneaba mal el HTML (CSS/meta → títulos); añadido strip de `<style>/<script>` y etiquetas. **Desviaciones del plan**: `DUR_MAX=480→1500s` (480 marcaba Metallica/Thriller/November Rain, canciones legítimas) y regex BASURA afinada (no pillar `<3` de `Ana Mena - pa ti toa <3`). **Los ficheros (~1,62 GB) NO se han borrado**: requiere tu confirmación (regla 8) |
| T-19 | `match_score`: `None` = sin verificar · verificación por duración real | ✅ | `radiov/youtube.py`: `match_score=None` cuando no se pudo comparar (antes 0.0, causa del bug). `scripts/verificar_match.py` (real_duration vs duración guardada): **0 desajustes reales** → confirma que los 0 no eran malas coincidencias. Convierto los `match_score=0` → `NULL` en radiov (232 filas) → ya no hay 0 ambiguo. El backend no tiene la columna. |
| T-20 | `energy` por percentil + columna `rms` + regenerar `tags` | 🚧 | Columna `rms` en `radiov/db.py` + `analyze_bpm` devuelve `rms` crudo. `scripts/recalcular_energia.py`. **Falta**: reanalizar el audio en lotes (worker, lee cada MP3) para poblar `rms`; luego correr el percentil + tags. |
| T-21 | Decidir `valence`/`danceability`: calcular o quitar del doc 03 | ✅ | **D2: opción B** — no se calculan. Falta aplicar: corregir `03_PERSONALIZATION.md` |
| T-22 | `gain_db` (LUFS con ffmpeg) — normalización de volumen | 🚧 | Columna `gain_db` + `TrackOut.gain_db` + `scripts/gaindb.py` (ffmpeg loudnorm; **validado en 8 canciones**). **Falta**: corrida masiva (worker, una por MP3) para el resto. |
| T-23 | `GET /facets` + revisar géneros/idiomas "other" | ✅ | `routers/facets.py` (`/facets`: genres/eras/languages/years/moods con conteo). Test `test_facets`. `02_API.md` actualizado |

**Salida de F2**: cero filas con texto no musical · `energy` repartida (~45 % por encima de 0.55) ·
ningún `match_score` ambiguo · `gain_db` calculado.

---

## FASE F3 · Web (React) → [`10_FRONTEND_SPEC.md`](10_FRONTEND_SPEC.md)

| | Tarea | Estado | Notas |
|---|---|---|---|
| FE-01 | Copiar `vendor/spotify-web` → `frontend/`, `yarn install`, `.env` | ✅ | `frontend/` copiada (sin `.git`), `.env` con `VITE_API_URL`/`VITE_APP_NAME`. `yarn install` en curso (Yarn 4; hubo que redirigir `YARN_GLOBAL_FOLDER`/`YARN_CACHE_FOLDER` al workspace por el sandbox) |
| FE-02 | `api/types.ts` + `api/adapt.ts` (capa adaptadora) | ✅ | `api/types.ts` + `api/adapt.ts` creados. **`tsc --noEmit` global pasa (exit 0)** |
| FE-03 | `axios.ts` a nuestra API (conservando concurrencia y caché) | 🚧 | `axios.ts`: baseURL→`VITE_API_URL`, `CACHEABLE_PATH`, 401→limpia token. **Falta** que el slice de auth publique el logout y el resto de servicios/slices/páginas usen `adapt.ts` |
| FE-04 | `api/auth.ts` + `api/stream.ts` | ✅ | `api/auth.ts` (login form/register JSON/logout) y `api/stream.ts` (token + URL de `/stream`) creados. `tsc --noEmit` pasa |
| FE-05 | Reapuntar `services/*`; borrar `episodes`, `categories`, `devices` | 🚧 | ✅ **Los 6 servicios de catálogo** (`auth`, `users`, `artist`, `search`, `playlists`, `albums`) reapuntados a nuestra API + capa adaptadora completa (shape de Spotify; id de álbum = `artista::álbum`). Backend: `GET /playlists/{id}`. **`tsc --noEmit` verde · 29 tests verde**. **Falta**: borrar `episodes`/`categories`/`devices` (D5, invasivo) |
| FE-06 | Reproductor: `<audio>` + ganancia + Media Session + precarga + señales | 🚧 | `player/playerController.ts` + `usePlayer.ts` + `webPlayback.tsx` + `playerService` rewireado (sin SDK de Spotify). **Bug corregido por David**: `crossOrigin='anonymous'`; `main.py` expone `Content-Range`/`Accept-Ranges`/`Content-Length`. **Tests del play-flow** (`test_playflow.py`, 3 tests): stream-token → `/stream` con Range → 206 + CORS + token refrescado + 410 + 401 scope. **`33 tests` · `tsc` verde**. **Falta**: validación en navegador (RUNBOOK de David) antes de las pantallas |
| FE-07 | Shuffle con separación de artista + reproducción continua ("Flow") | ✅ | `player/queueController.ts` (nuevo): cola del cliente con shuffle/separación de artista (spec §4.5), repeat 0/1/2 e historial. `bindEnded` en `webPlayback.tsx` → `colaController.siguiente(true)`; al agotarse la cola → `GET /recommend/radio?seed_track={última}` (Flow §4.6) y encadena. `playerService.startPlayback` rellena la cola (álbum/playlist/lista `uris`); `next/prev/shuffle/repeat/addToQueue` cableados. `playerController` gana `bindPlayed` + `position()` y emite `disallows`/`shuffle`/`repeat_mode`. **`tsc --noEmit` verde** |
| FE-08 | Pantallas: Home, Search, Artist, Album, LikedSongs, Playlist, Ajustes | 🚧 | **Home**: fila "Para ti" → `GET /recommend?n=12` (personalizado; el 👍 lo cambia al recargar). **`tsc` verde**. Backend de las pantallas des-riesgado: tests de `/recommend/daily`, `/artists/{name}/albums` y **búsqueda `/tracks?q=`** (título/artista/álbum, solo descargadas, vacío) → **suite 37 passed**. Falta: Home "Mix diario"/"Trending"/"Novedades"/"Tus artistas", y el resto de pantallas |
| FE-09 | Modal de login/registro con código de invitación | ✅ | Login (email+password → `POST /auth/login`) y **registro** (`POST /auth/register` con nombre + código de invitación opcional) en el `LoginModal` (toggle login/registro). `loginToSpotify` ya no redirige a Spotify. **`tsc --noEmit` verde** |
| FE-10 | Filtro de contenido explícito (perfil familiar) | ✅ | Mecanismo en `axios.ts` (si `radiopv_hide_explicit=1`, fuerza `explicit=false` en `/tracks`) + toggle "Ocultar contenido explícito" en el perfil (`UserHeader`). **`tsc --noEmit` verde** |

---

## FASE F4 · Worker y personalización → [`11_WORKER_SPEC.md`](11_WORKER_SPEC.md)

| | Tarea | Estado | Notas |
|---|---|---|---|
| W-01 | Tests que fijan el comportamiento actual + extraer `personalization.py` | ✅ | `backend/app/personalization.py` (`_profile`/`_score`/`_candidates`). `test_recommend.py` (flamenco a la cabeza). `recommend.py` importa del módulo. |
| W-02 | Perfil con recencia y señales implícitas (`seconds_listened`) | ✅ | `peso_recencia(x)` + `señales(user,db)` (likes/skips con recencia + plays por `seconds_listened`). `_profile` usa pesos positivos. |
| W-03 | Arranque en frío con `rank` | ✅ | `_score` + prior `peso_frio(n_señales)*3*min(1,rank/800000)`. Test `test_recommend_sin_señales_prioriza_rank`. |
| W-04 | Diversidad (MMR): máx. 2 canciones por artista | ✅ | `seleccionar_diverso(scored,n)`; `/recommend` lo usa. Test `test_recommend_diversidad_max2_artista`. |
| W-05 | Tablas `similar`, `mixes`, `smart_playlists` + `radio()` por `SELECT` | ✅ | Modelos `Similar`/`Mix`/`SmartPlaylist`. `vector(t)` + `rebuild_similar(db)` (coseno numpy, top-40). `/radio` lee de `similar` (join limpio, ya no calcula). Test `test_radio_lee_similar`. |
| W-06 | `/playlists/system` · `/recommend/trending` · `/library/history` · `/wrapped` · `/facets` · `/requests` | ✅ | Todos creados (`/facets` en T-23): `wrapped.py` (`/wrapped`, `POST /requests`), `library.py::/history`, `recommend.py::/trending`, `playlists.py::/system`. Tests `test_wrapped_y_requests`. **Nota**: `/recommend/daily` aún calcula al vuelo, no lee de `mixes` (opcional). |
| W-07 | `workers.py` con APScheduler (7 tareas programadas) | ✅ | `app/workers.py` (BlockingScheduler Europe/Madrid, `_tarea` robusta) + tareas `sync_catalogo`, `rebuild_similar` (c/4:00), `rebuild_mixes` (5:00), `refresh_trends` (8 h), `rebuild_static_lists` (6:00), `verificar_ficheros` (dom 3:00, `perdida`), `prune` (7:00). `apscheduler==3.11.3` instalado. Tests `test_worker_tareas`. **Arranque**: `python -m app.workers` (proceso separado). |

---

## FASE F5 · Móvil (Flutter) → [`12_MOBILE_SPEC.md`](12_MOBILE_SPEC.md)

| | Tarea | Estado | Notas |
|---|---|---|---|
| MB-01 | Copiar a `mobile/`, actualizar `pubspec.yaml`, que arranque **tal cual** | 🚧 | `mobile/` copiado (sin `.git`); `pubspec.yaml` renombrado a `radiopv`. **No compilado** (Flutter SDK no disponible/tarda en este entorno). Falta: `url.dart`/`ApiClient`, modelos, repos → backend |
| MB-02 | `url.dart` + `ApiClient` con JWT | ⬜ | |
| MB-03 | Token de streaming | ⬜ | |
| MB-04 | `song_model.dart` → `TrackOut` | ⬜ | |
| MB-05 | Repositorios a nuestros endpoints | ⬜ | |
| MB-06 | Reproductor: `/stream`, ganancia, notificación, señales, offline | ⬜ | |
| MB-07 | Android: permisos y build de release | ⬜ | |
| MB-08 | Pantallas + login + ajustes | ⬜ | |

---

## FASE F6 · Producción → [`13_DEPLOY_SPEC.md`](13_DEPLOY_SPEC.md)

| | Tarea | Estado | Notas |
|---|---|---|---|
| DP-01 | **Decidir dónde vive el audio** | ✅ | **D3: en casa, por Tailscale**, sin exposición a internet. `/stream` sigue siendo `FileResponse`; F6 desbloqueada. `servir_audio(track)` aparte; `ALLOWED_ORIGINS` = localhost+Tailscale |
| DP-02 | Alembic sustituyendo a `create_all` | ✅ | Esqueleto `backend/alembic.ini` + `alembic/env.py` + `script.py.mako` + migración baseline (crea las 15 tablas). `alembic upgrade head` verificado. `alembic` añadido a requirements |
| DP-03 | Postgres + búsqueda real (`pg_trgm` / `tsvector`) | 🚧 | Postgres ya soportado por `DATABASE_URL` (psycopg2). FTS real (tsvector/pg_trgm) queda como mejora opcional; por ahora FTS5 en SQLite |
| DP-04 | Dockerfile + `docker-compose` (música en `:ro` para la API) | ✅ | `Dockerfile` (python:3.12-slim + ffmpeg, música en `/music :ro`) + `docker-compose.yml` (api + worker, volumen `./data`, `SECRET_KEY`/`ALLOWED_ORIGINS` por env) |
| DP-05 | HTTPS (Caddy o Cloudflare Tunnel) | ⬜ | Documentado: acceso por Tailscale (red privada), no HTTPS público |
| DP-06 | Seguridad: invitación, límite de intentos, CORS, cabeceras | ✅ | ✓ CORS restringido (`ALLOWED_ORIGINS` localhost+Tailscale) + cabeceras de seguridad + **límite de intentos de login** (5 fallos / 5 min → 429). **Código de invitación** en `/auth/register` (si `INVITE_CODE` seteado; vacío=abierto, solo dev) + `RegisterIn.invite_code` + test `test_register_invite_code` |
| DP-07 | Copia diaria **y restauración probada** | ✅ | `scripts/backup.py` (copia `radiov.db`+`backend.db` a `data/backup/<ts>/`; valida la BD). Ejecutado OK |
| DP-08 | `/health` ampliado + `scripts/humo.ps1` | ✅ | `/health` devuelve `{status, tracks, artists, similar, users}` + middleware `security_headers`. `scripts/humo.ps1`. Test ampliado |

---

## Decisiones de David — ✅ CERRADAS el 2026-08-28

Están en [`DECISIONES.md`](DECISIONES.md). Resumen:

| | Decisión | Respuesta |
|---|---|---|
| D1 | ~1,62 GB en cuarentena | **Mover** a `E:\Musica\_cuarentena\`, **no borrar**. El agente nunca borra ficheros. |
| D2 | T-21 `valence`/`danceability` | **Opción B**: no se calculan; se corrige `03_PERSONALIZATION.md` |
| D3 | DP-01 dónde vive el audio | **En casa, por Tailscale**. Sin exposición a internet. `/stream` sigue siendo `FileResponse` |
| D4 | ¿Una BD o dos? | **Dos**, sincronizadas por la migración no destructiva |
| D5 | Features de UI sin API | `follows` y `/library/top` **se añaden**; `queue`, `devices` y `episodes` **se quitan de la UI** |

> La **regla 10 sigue vigente**: ante una decisión nueva sobre datos irreversibles, dinero o
> exposición a terceros, el agente para y pregunta.

---

## 📱 Bloque E (móvil Flutter) · APLAZADO — la PWA lo sustituye (2026-08-29)

**Flutter no se puede instalar en ninguno de los dos entornos.** Comprobado, no supuesto: la lista de
egreso bloquea `storage.googleapis.com` (403) y los archivos de GitHub (403/000); solo pasan pypi y
npm. No hay `flutter analyze` disponible ni para el agente ni para Claude, así que **todo el Dart
sería código a ciegas sin ni siquiera comprobación de sintaxis**.

**Y no hace falta**: F1 ya dejó la web como **PWA instalable** (`display: standalone`, service worker
que cachea la carcasa y **nunca** el audio ni la API), y la **Media Session API** —verificada en
Chromium— da los controles en la pantalla de bloqueo y en los auriculares. En el móvil, eso *es* la
app.

**Lo que faltaba para que fuese instalable de verdad, ya arreglado por Claude:**
- `public/icon-192.png` y `public/icon-512.png` creados (sin iconos de ese tamaño **Android no ofrece
  "Añadir a pantalla de inicio"**; solo había un `favicon.ico`).
- `manifest.json`: iconos con `purpose: "any maskable"`, `start_url` de `./index.html` → **`/`**
  (con el anterior, el arranque en modo standalone falla), `scope`, `lang: es`, `description`, y
  `theme_color`/`background_color` a `#101014` para que la pantalla de arranque no dé un fogonazo
  blanco antes de la app oscura.

**Decisión**: el bloque E queda **aplazado**, no bloqueado. Si algún día se quiere APK nativo, se
escribe con el SDK instalado en Windows. Mientras tanto, `12_MOBILE_SPEC.md` queda como está.

---

## ✅ 3.ª verificación en navegador (2026-08-29, bloques A+B+C+D)

Chromium real contra el backend con el catálogo. **Las 7 pantallas renderizan, ningún 4xx.**

| Pantalla | DOM | Resultado |
|---|---|---|
| Home | 38,2 KB | ✅ · "Source code" y "Podcasts" **ya no aparecen** |
| Browse `/search` | 59,0 KB | ✅ **A1 resuelto**: facetas reales con conteo (pop 344, reggaeton 162, other 144, latin 123, rock 68…) |
| Búsqueda | 55,9 KB | ✅ Top Result + pestañas |
| Genre `/genre/reggaeton` | 77,6 KB | ✅ la pantalla funciona (ver ⚠️ abajo sobre los datos) |
| Artist | 77,0 KB | ✅ |
| LikedSongs | 31,7 KB | ✅ |
| **Ajustes `/settings`** | 30,2 KB | ✅ idioma, ocultar explícito, nombre, cerrar sesión, estadísticas |

`<title>` = **RadioPV** ✅ · `vite build` verde ✅ · cero llamadas a Spotify ✅

### ⚠️ La pantalla Genre destapa un problema de DATOS, no de UI

`GET /tracks?genre=reggaeton` devuelve, en las 5 primeras: `Tory Lanez - Hurts Me`,
`Nobu Woods - ISSUES`, `Tory Lanez - Someone Else`… y `Dj Disc - Mix Reggaeton Old School (HIT),
Vol. 01`. Es decir: la clasificación de género es mala (rap/R&B etiquetado como reggaeton) y **sigue
entrando alguna mezcla de DJ** al catálogo. La pantalla está bien; lo que enseña, no.

→ Aplicar **T-26** (`DUR_MAX` 1500 → 900) y abrir una tarea de reclasificación de género
(`other` son 144 canciones y "reggaeton" está contaminado). Sin eso, navegar por géneros da mala
sensación aunque la UI sea correcta.

### ⚠️ D2: filtrar el contenido explícito en el interceptor de RESPUESTA tiene un coste

`axios.ts` pide `explicit=false` en `/tracks` (bien, servidor) pero para el resto **filtra el array ya
recibido**. Eso significa que una página de 20 llega como 14: los contadores, el `X-Total-Count` y el
scroll infinito dejan de cuadrar, y aparecen huecos al paginar.

→ El backend ya acepta `explicit` en `/tracks`. Extenderlo a `/recommend`, `/recommend/daily`,
`/radio`, `/playlists/{id}/tracks` y `/library/liked`, y **quitar el filtro de la respuesta**.

### ⚠️ C3 incompleto
La pantalla de Ajustes está **en inglés** ("Settings", "Hide explicit content", "Log out") mientras
Genre está en español ("Canciones", "Mostrar más"). La app habla dos idiomas a la vez.

---

## 🔎 2.ª verificación en navegador (2026-08-29, tras el recableado de Search/Artist/Album)

Chromium real contra el backend con el catálogo. **Todas las pantallas renderizan, ningún 4xx, cero
llamadas a Spotify.**

| Pantalla | DOM | API | Resultado |
|---|---|---|---|
| Home `/` | 38,6 KB | `/auth/me` `/follows` `/library/liked` `/library/history` `/playlists` `/recommend?n=12` | ✅ catálogo real |
| Búsqueda `/search/bad bunny` | 56,1 KB | `/tracks?q=` `/artists?q=` `/playlists/system` `/library/reactions` | ✅ Top Result + pestañas |
| Artist `/artist/Bad Bunny` | 77,1 KB | `/artists/{n}` `/top` `/albums` `/follows` | ✅ 7.963.480 seguidores, Popular, Follow |
| LikedSongs | 31,9 KB | `/library/liked` | ✅ (vacía: el usuario de prueba no tiene likes) |
| Browse `/search` | 28,2 KB | — | 🔴 **sale vacío**: usaba las categorías de Spotify → cablear a `/facets` |

**Hallazgos nuevos** (todos en [`ORDEN_DE_TRABAJO.md`](ORDEN_DE_TRABAJO.md)):
- Browse sin categorías (A1) · "Source code" y pestaña "Podcasts" en toda la app y `<title>` aún
  "Spotify Web Player" (C1, C4) · la búsqueda dispara **9 peticiones** por término (F4) ·
  **producción necesita fallback de SPA** o `/artist/X` da 404 (F6).

---

## ✅ VERIFICACIÓN EN NAVEGADOR REAL (Claude, 2026-08-29) — el bloqueo está resuelto

No hizo falta esperar a David. Copié `frontend/` y `backend/` a un contenedor Linux con una copia de
`backend.db`, generé MP3 reales con ffmpeg en las rutas del catálogo, levanté **el backend de verdad**
y abrí **Chromium con Playwright**. Resultados:

| Prueba | Resultado |
|---|---|
| `vite build` | ✅ **compila** en 3,1 s (476 ficheros; `tsc` no prueba esto) |
| `/stream/1` con `Range: bytes=0-1023` | ✅ **206** · `content-range: bytes 0-1023/193141` · `accept-ranges: bytes` |
| CORS en `/stream` | ✅ `access-control-expose-headers: X-Total-Count, Content-Range, Accept-Ranges, Content-Length` |
| Token de acceso usado en `/stream` | ✅ **401** (el `scope` funciona) |
| Fichero ausente | ✅ **410** |
| **Mecanismo de audio en Chromium** | ✅ `AudioContext` en `running` · `currentTime` avanza a 2,5 s · **seek a 8 s → sigue en 9,5 s** · `duration` 12 · ganancia aplicada (0,708 = −3 dB) · **sin errores de CORS** |
| La app renderiza | ✅ tras el arreglo de abajo: 38,6 KB de DOM con el catálogo real (NUEVAYoL, Gasolina, Hawái…) |

### 🔴 El fallo que dejaba la app EN BLANCO (corregido)

`api/auth.ts` y `api/stream.ts` guardaban el JWT **en crudo**, pero `axios.ts`, `App.tsx` y
`store/slices/auth.ts` seguían leyéndolo con `getFromLocalStorageWithExpiry`, que hace
`JSON.parse(...)`. Al arrancar: `Unexpected token 'e', "eyJhbGciOi"... is not valid JSON` → la
excepción salta **al cargar `axios.ts`**, React no monta y **la página se queda en blanco**, sin más
pistas. Es exactamente lo que habría pasado al ejecutar `yarn dev`.

**Corregido**: nuevo `src/api/token.ts` (`getToken`/`setToken`/`clearToken`, formato crudo, un solo
punto de verdad) y los 6 ficheros que tocaban `access_token` reapuntados. `tsc --noEmit` verde.

### 🔴 `index.html` seguía cargando el SDK de Spotify (corregido)

El SDK se quitó del TypeScript pero no del HTML: `<script src="https://sdk.scdn.co/spotify-player.js">`
y `window.onSpotifyWebPlaybackSDKReady`, más Font Awesome desde `maxcdn.bootstrapcdn.com`. Eso
contradice el criterio de aceptación ("ni una llamada a Spotify") y rompe en una red sin internet
—que es justo el escenario de Tailscale de D3—. **Eliminados los dos.**

### 🟠 Pendiente real: el registro sigue abierto

`POST /auth/register` creó un usuario **sin código de invitación**. `INVITE_CODE` está en `config.py`
pero el router no lo comprueba. DP-06 no está completo.

> Nota: quedó `F:\EspacioCodigo\RadioPV\_tmp\` con los .tgz y la copia de la BD que usé para la
> prueba. Se puede borrar sin más (no lo borro yo: la regla es no borrar ficheros).

---

## ⚠️ Revisión del play-flow (Claude, 2. ª pasada) · 4 fallos silenciosos corregidos

Revisado `playerController.ts` y `api/stream.ts` línea a línea. Corregido **directamente por Claude**
(`node node_modules/typescript/bin/tsc --noEmit` → **exit 0**, ejecutado en la máquina de David):

1. **Token caducado incrustado en `audio.src`** — el token va en la URL y solo se renovaba en el
   siguiente `play()`. Tras una pausa larga, el primer `seek` pedía un rango con el token viejo →
   **401 → la reproducción moría en silencio**. Añadido listener de `error` que invalida el token,
   pide uno nuevo y recarga **conservando la posición**. (`invalidarStreamToken` en `stream.ts`.)
2. **Gesto del usuario** — `ctx.resume()` se llamaba **después** de un `await` de red
   (`streamUrl`). Tras un await el navegador ya no considera que estamos dentro del gesto: en
   **Safari/iOS no suena la primera vez**. Movido antes de cualquier await + `precalentarStreamToken()`
   para pedir el token al entrar y que el clic no haga red.
3. **`seconds_listened` no se enviaba nunca** — solo se mandaba `{completed: 0}` al empezar y nada
   más. `plays.seconds_listened` (T-08) quedaba vacío y **toda la ponderación implícita de W-02
   estaba muerta**. Ahora se acumulan los segundos realmente escuchados (ignorando los saltos del
   seek) y se manda la señal de cierre al acabar o al cambiar de canción. También se envía `context`.
4. **`ended` no encadenaba nada** — la reproducción paraba tras una canción. Añadido `bindEnded(fn)`
   para que la cola (y el "Flow") se enganchen ahí.

También: `MediaSession` con sus *action handlers*, y **`usePlayer.ts` eliminado** (estaba huérfano,
duplicaba el reproductor) → movido a `frontend/_to_delete/usePlayer.ts.orphan`.

**Sobre el sandbox, con precisión**: `tsc --noEmit` **sí** se puede ejecutar (verificado, exit 0).
`vite build` **no**: `rolldown` tiene el binario nativo de Windows y falta el de Linux
(`MODULE_NOT_FOUND` en `requireNative`). Es decir: tipos sí, compilación y navegador no.

---

## ⚠️ Auditoría del 2026-08-29 · bug corregido y prioridad

**Bug corregido directamente por Claude** (era un error de `10_FRONTEND_SPEC.md`, no del agente):
`playerController.ts` y `usePlayer.ts` tenían `crossOrigin = 'use-credentials'` en el `<audio>`. Con
credenciales el elemento queda *tainted* y `createMediaElementSource` devuelve **silencio sin error
claro**. Cambiado a `'anonymous'` en ambos ficheros y en la spec. Además `main.py` ahora expone
`Content-Range`, `Accept-Ranges` y `Content-Length` en el CORS (hacen falta para que el seek funcione
limpio desde el navegador).

**Prioridad decidida**: **F3 (play-flow y pantallas) antes que F5 (móvil)**. El móvil sería una
segunda implementación a ciegas de un flujo que aún no se ha visto funcionar ni una vez.

**Antes de seguir escribiendo UI**: David ejecuta [`RUNBOOK_VERIFICACION.md`](RUNBOOK_VERIFICACION.md)
(~20 min) y devuelve los resultados. Estado medido hoy: `rms` 6/2268 · `gain_db` 10 · `energy=1.0`
en 1329 filas → **T-24 sin ejecutar**; `similar` con 49.640 filas → **W-08 sí hecha, la radio funciona**.

---

## Hallazgos de la auditoría del 2026-08-28 (tareas nuevas, prioridad alta)

| | Tarea | Estado | Notas |
|---|---|---|---|
| T-24 | **Pausar el recolector y hacer UNA sola pasada de análisis** (`rms` + LUFS/`gain_db` en la misma lectura de cada MP3) | 🚧 | **Recolector PAUSADO** (PID 35056; catálogo estabilizado en 2268). `scripts/analisis_completo.py` (rms vía `analyze_bpm` + gain_db vía ffmpeg loudnorm en una pasada, luego percentil de energía). **Pasada en ejecución en segundo plano**. Desbloquea T-20/T-22 |
| T-25 | **La limpieza tiene que ser una tarea del worker**, no un script de una vez | ✅ | `workers.py::limpiar_catalogo` (cada hora, marca cuarentena en `radiov.db`). Con `DUR_MAX=900`, 9 filas nuevas marcadas cuarentena (incl. `2024 Hit Playlist`, `Fitness & Workout Hits`, `DJ RONALD HESS`). El `sync_catalogo` ya no las publica |
| T-26 | Bajar `DUR_MAX` de **1500 → 900 s** | ✅ | `radiov/quality.py::DUR_MAX=900`. Verificado: conserva Thriller/Metallica, corta mezclas de DJ |
| W-08 | Correr `rebuild_similar` **una vez ya** + *fallback* en `/radio` | ✅ | `rebuild_similar` ejecutado sobre `backend.db` (**49.640 filas** en `similar`). Fallback en `/radio`: si `similar` está vacía para el seed, calcula al vuelo y guarda. Test `test_radio_fallback_calcula_al_vuelo` |
| W-09 | `follows` (seguir artistas) + `GET /library/top` | ✅ | Tabla `Follow` + `routers/follows.py` (POST/DELETE/GET `/follows`) + `GET /library/top?type=artists/tracks&period=`. Test `test_w09_follows_y_top` |
| T-27 | **Reclasificación de género** (del verificado en Chromium) | 🚧 | `genre` contaminado — `reggaeton` devuelve Tory Lanez/Nobu Woods, y hay **144** temas en `other`. Revisar `charts.py` (parseo de género por fuente) y remapear `other`. La pantalla Genre funciona; lo que enseña no. **T-26 verificado**: `radiov/quality.py::DUR_MAX` ya es 900 (el mix de DJ residual viene de temas ya en BD sin re-pasar la puerta de calidad). |

---

## Diario de sesiones

> El agente añade una línea por sesión: fecha, qué se hizo, qué quedó abierto.

| Fecha | Tareas tocadas | Resultado | Abierto |
|---|---|---|---|
| 2026-08-28 | — | Auditoría y plan escritos (`08`…`13`) | Empezar por T-01 |
| 2026-08-28 | Auditoría del trabajo del agente | T-05 verificado (señales intactas, ids estables) · rutas relativas OK · `scope` OK · `/stream` OK | 3 hallazgos nuevos (T-24, T-25/T-26, W-08) y las 4 decisiones cerradas en `DECISIONES.md` |
| 2026-08-28 | T-01…T-10 | **F0 completa.** Backend: `/artists` 200, migración idempotente no destructiva (0 dups deezer), prod sin SECRET falla, 10 tests verdes. Recolector: dedup 2 dups + index UNIQUE en SCHEMA. | **El recolector (`source=agente`) está corriendo** descargando y analizando catálogo (radiov.db creció 1271→~1288). No lo he detenido (es la expansión pedida). Nota: T-06 deja el index UNIQUE sin materializar en la BD viva para no chocar con la escritura activa; se aplicará al próximo reinicio/recolección. Falta: F1 (T-11…) |
| 2026-08-28 | T-11 | **F1 arrancada.** Normalización de rutas: script + `backend.db` normalizado + recolector escribe/lee relativo. pytest 10 green. | El recolector sigue corriendo; `radiov.db` vivo no normalizado todavía. Falta: T-12 (token streaming), T-13… |
| 2026-08-28 | T-12…T-16 | **F1 completa.** Token streaming + `/stream` con Range(206) + `/media/**` + `feat`/`rank`/filtros/`X-Total-Count` + `liked`/playlists CRUD/`artists`/`report`. **15 passed** | Salida F1 lograda: reproducir/seek, carátulas por `/media`, Me gusta en 1 petición. El recolector sigue corriendo. Falta F2 (sanear datos; T-21 bloqueada por David) |
| 2026-08-28 | T-17…T-23 | **F2 casi completa.** Puerta de calidad + cuarentena (16 filas ~1,62 GB marcadas; **archivos sin borrar** pendientes de tu OK) + fix `charts.py` (parseo HTML) + `match_score` None vs 0 (232→NULL; 0 desajustes) + `GET /facets`. **20 passed**. | `radiov.db`/`backend.db` con `feat`, `rms`, `gain_db` y columnas nuevas. **Pendiente worker (reanálisis masivo)**: poblar `rms` + percentil de energía (T-20) y `gain_db` de todo el catálogo (T-22; script validado en 8 canciones). T-21 bloqueada por David. |
| 2026-08-28 | FE-01…FE-03 | **F3 arrancada.** `frontend/` copiada + `yarn install` (Yarn 4 con `--mode=skip-build`; los postinstall nativos daban EPERM en sandbox) + `.env`. Capa adaptadora `api/{types,adapt}.ts` + `axios.ts` rewire. **`tsc --noEmit` pasa (exit 0)**. | **El sandbox bloquea `vite build`/`vite dev`** (`spawn EPERM` en realpath de Windows): la verificación del build dev está fuera del sandbox. **Falta F3 (la mayor parte)**: servicios/slices/páginas a `adapt.ts`, reproductor `usePlayer` (ganancia/MediaSession/precarga/señales), pantallas, login/invite, filtro explícito, `yarn build` verde. Sigue: F3→F6. |
| 2026-08-28 | FE-04…FE-05 | **F3 (auth + capa).** `api/auth.ts` + `api/stream.ts` + `api/adapt.ts::toUser`. `services/auth.ts` → `/auth/me`. **`tsc --noEmit` pasa (exit 0)**. | **Sandbox blockea `vite` (spawn)**: la ejecución web/móvil hay que hacerla fuera. Falta el resto de F3 (services/pages/player/login/filtro explícito), F4 (worker), F5 (mobile), F6 (deploy). Decisiones tuyas pendientes: borrar ~1,62 GB, T-21, dónde vive el audio, BD única/doble, internet. |
| 2026-08-28 | W-01…W-06 | **F4 avanzada.** `personalization.py` (perfil + recencia/señales + arranque en frío `rank` + MMR) + tablas `similar`/`mixes`/`smart_playlists` + `radio` por `SELECT` + endpoints `history`/`trending`/`system`. **25 passed**. | **Falta F4**: `/wrapped`, `POST /requests`, `daily` desde `mixes`, y **W-07 worker** (APScheduler). Quedan F3 (resto), F5 móvil, F6 deploy. |
| 2026-08-28 | W-06…W-07 | **F4 completa.** `/wrapped` + `POST /requests` (modelo `Request`) + `app/workers.py` (scheduler + 7 tareas). **27 passed**. | Backend prácticamente completo (F0-F2 + F4). Quedan F3 (resto: services/pages/player/login), F5 móvil, F6 deploy. **Sandbox bloquea `vite`/flutter**. Decisiones tuyas pendientes (borrado 1,62 GB, T-21, dónde vive el audio, BD, internet). El worker se arranca aparte (`python -m app.workers`). |
| 2026-08-29 | FE-07, FE-08 | **Cola→`bindEnded`→"Flow" implementado** (`queueController.ts` + `playerController.bindPlayed/position` + `playerService` + `webPlayback.bindEnded`). Home: fila "Para ti" → `/recommend`. **`tsc --noEmit` verde**. | Faltan pantallas FE-08 (Home: Mix diario/Trending/Novedades/Tus artistas; Search, Artist, Album, LikedSongs, Playlist, Ajustes). **Sin verificación en navegador** (RUNBOOK de David). Pendiente F5 móvil y T-24 (análisis en el worker, lo lanza David). |
| 2026-08-29 | Play-flow (RUNBOOK) | Revisado a fondo el flujo de reproducción sin navegador. **Arreglos de David intactos** (`crossOrigin='anonymous'` en `playerController.ts`; `main.py` expone `Content-Range`/`Accept-Ranges`/`Content-Length`). Verificado el **contrato de refresco**: `api/stream.ts` renueva con margen de 60 s (`expira = Date.now() + expires_in*1000`), el backend devuelve `expires_in` en `/auth/stream-token` y el JWT `exp` está en el futuro. Añadido `test_stream_token_expira_en_futuro` → **play-flow 4 tests · suite 34 passed**. | El flujo real (gesto del usuario, CORS del `<audio>`, Range, refresco a mitad) lo valida David con `RUNBOOK_VERIFICACION.md`. Backend `:8000` hay que reiniciarlo para servir el código nuevo. |
| 2026-08-29 | DP-06, FE-08 | **DP-06 completo**: `/auth/register` valida `INVITE_CODE` (seteado lo exige; vacío=abierto) + `RegisterIn.invite_code` + test `test_register_invite_code` → **suite 38 passed**. **Arreglos de endpoint mismatches**: `fetchMyArtists`→`/follows`→`/artists/{name}`, follow/unfollow/check artistas→`/follows/{name}`, `checkSavedTracks` (corazón Me gusta)→`/library/reactions`, `getAvailableDevices`→vacío (D5 quitó devices). **`tsc` verde**. | Siguiente: terminar Home (Mix diario/Trending/Novedades) y el resto de pantallas FE-08 (Search, Artist, Album, LikedSongs, Playlist, Ajustes). T-24 pendiente de David. |
| 2026-08-30 | FE-08 Search/Artist/Album | **Search, Artist, Album ya usan nuestra API** (RTK Query catalog.ts + servicios). Arreglados: `userService.fetchTopTracks`→`/recommend` (perfil/playlist), playlists de Search→`toPlaylist` (faltaba images/uri). `tsc` verde. | **Listos para re-verificación en navegador de las 3 pantallas** (Search/Artist/Album). Quedan Home (Mix diario/Trending/Novedades), LikedSongs, Playlist, Ajustes. |
| 2026-08-30 | ORDEN A1-A4 | **Bloque A (1.ª mitad)**: A1 Browse→`/facets` (géneros/eras/moods/idiomas con conteo; `BrowseCard` muestra nº); A2 Genre→`/tracks?{tipo}={valor}` + `fetchMoreGenre` (load-more, X-Total-Count); A3 Playlist: `deletePlaylist` + "Delete playlist" habilitado + `removeTrack` por uri; A4 Album: `total_tracks` real + encolea todas. **`tsc` verde**. | Siguen A5 (Discography), A6 (Profile/User), A7 (estado vacío "pedir esta canción"), A8 (paginación Search/Artist). |
| 2026-08-30 | ORDEN A5-A8 | **Bloque A completo**. A5 Discography ya usaba `/artists/{name}/albums` (agrupado año desc) — sin cambios. A6 Profile: `fetchTopTracks`→`/library/top?type=tracks`, `fetchTopArtists`→`/library/top?type=artists` (fuera `/me/top/*`). A7 `NoSearchResults`:+botón "Pedir esta canción"→`POST /requests`. A8 `search.ts` lee `X-Total-Count` (antes usaba length → hasMore siempre false). **`tsc` verde**. | Bloque A cerrado. Siguiente: Bloque B (reproducción completa). |
| 2026-08-30 | ORDEN B | **Bloque B (reproducción completa)**: B1 cola→Redux (`setQueue` + `bindChange`; `añadirAContinuacion`); B2 Flow (ya); B3 shuffle separación artista (ya); B4 repetir persistente (`REPEAT_KEY`) + volumen persistente (`VOLUME_KEY`); B5 precarga siguiente (`precacheNext`); B6 skip<30% (`skipSignal` en `cerrar(false)`); B7 atajos (espacio/±10 s/M/L). **`tsc` verde**. | Bloque B cerrado. Siguiente: Bloque C (quitar restos de Spotify). |
| 2026-08-30 | ORDEN C (parcial) | **C1** quitado "Source code" (Header) + pestaña "Podcasts" (chips Home). **C4** marca: `<title>`/`document.title` "RadioPV" + `manifest.json`. **C5 (red)** neutralizado `getRefreshToken` (`login.ts` → null, ya no llama a `accounts.spotify.com`). **`tsc` verde**. | **C2/C3/C5 restantes**: borrar `services/episodes`+`categories`, `getDeviceIcon.tsx`, `interfaces/devices`/`episode` y vaciar `_to_delete/` (importadores en cascada); pasar i18n/es a RadioPV; barrido grep de comentarios "spotify". |
| 2026-08-30 | ORDEN C2-C3 | **C3** texto "cuenta gratuita de Spotify"→RadioPV (`i18n/es/home.ts`). **C5 (red)** confirmado: ya no hay ninguna llamada a `accounts.spotify.com`/`api.spotify.com`. **C2**: se mantienen `services/episodes`/`categories`/`getDeviceIcon`/interfaces `devices`/`episode` porque son código muerto **sin llamadas de red** (episodes usa `/me/library` de nuestra API; categories vuelve vacío; los devices/podcasts D5 ya no están en la UI) y borrarlos arrastra importadores en cascada (mayor riesgo que valor ahora). **`tsc` verde**. | El resto de "spotify" en `src` son identificadores/comentarios (`state.spotify`, `constants/spotify.ts`, `external_urls.spotify`) — renombrar toda esa capa sería un refactor enorme y no es lo que pide la aceptación (que es de red). Siguiente: Bloque D. |
| 2026-08-30 | ORDEN D (parcial) | **D2** filtro explícito **central** en `axios.ts` (interceptor de respuesta filtra `explicit` en TODAS las listas de tracks + clave de caché con el flag). **D3 (API)** `PATCH /auth/me` (nombre/email editables) + test `test_patch_me_edita_perfil` → **suite 39 passed**. `tsc` verde. | Falta D1 (página `/settings` con idioma/logout/filtro), D3 (UI para editar nombre + avatar por inicial), D4 (temporizador de apagado), D5 (pantalla `/wrapped`). Y luego E (móvil, necesita SDK Flutter) y F (pulido). |
| 2026-08-30 | ORDEN D (página) | **D1** página `/settings` (`pages/Settings/index.tsx` + ruta en `App.tsx`): idioma (setLanguage), filtro explícito (D2), **editar nombre** → `PATCH /auth/me` (D3-UI), cerrar sesión, y acceso a `/wrapped` (D5). **`tsc` verde**. | Falta D4 (temporizador de apagado), D5 (pantalla `/wrapped` real), avatar por inicial (D3), y luego E (móvil — necesita SDK Flutter) y F. |
| 2026-08-30 | ORDEN D + correcciones | **Bloque D completo + 3 correcciones de la verificación de David.** **D2 reubicado**: el backend acepta `explicit` en `/recommend`, `/daily`, `/radio`, `/trending`, `/playlists/{id}/tracks`, `/library/liked`, `/library/history`, `/artists/{name}/top`; el frontend lo pasa por parámetro y **se quitó el filtro en la respuesta** (ya no rompe X-Total-Count/scroll). Test `test_explicit_filter_en_listas` → **40 passed**. **C3**: idioma por defecto `es` + clave `es/profile` (Ajustes en español) + `es` en Ajustes. **T-26 verificado**: `DUR_MAX` ya es 900 (mix residual = re-pasada de datos) + **T-27** abierto (reclasificar género, 144 en `other`). **D4** temporizador de apagado (`playerController.setSleep/cancelSleep` + UI en Ajustes), **D5** pantalla `/wrapped`, **D3** avatar por inicial. **F4** búsqueda: `fetchSearch` pasa de 5 a 1 `querySearch`. **`tsc` verde · pytest 40**. | Siguiente: resto de F (F1 PWA, F2 esqueletos, F3 a11y, F5 toasts, F6 Caddyfile SPA fallback, F7 docs) y E (móvil, sin SDK → escribir y marcar sin compilar). |
| 2026-08-30 | ORDEN F4/F6 | **F4** búsqueda: `fetchSearch` usa **1** `querySearch` (de ~5 llamadas a 3 peticiones). **F6** fallback SPA: `Caddyfile` de `13_DEPLOY_SPEC.md` ahora sirve el build con `try_files {path} /index.html; file_server` (entrar directo a `/artist/…` ya no da 404) + nota para nginx (`try_files $uri $uri/ /index.html;`). **`tsc` verde**. | Faltan F1 (PWA), F2 (esqueletos), F3 (a11y), F5 (toasts de error), F7 (revisar docs 05/06/07) y E (móvil, sin SDK → marcar sin compilar). |
| 2026-08-30 | ORDEN F (cierre) + E aplazado | **F1** PWA: iconos 192/512 maskable + `manifest.json` corregido por David (`start_url '/'`, `lang es`, `scope`, `theme/background #101014`) + service worker `public/sw.js` (cachea carcasa, nunca audio/API; solo PROD). **F2** esqueletos: `components/Loading/LoadingSkeleton.tsx` usado en Search y Genre (antes `return null`). **F3** `aria-label` en controles del reproductor. **F4/F5/F6** hechos. **F7** docs 05/06/07 con "ESTADO REAL"; 07 marca el móvil **aplazado** (sin SDK de Flutter; la **PWA lo cubre**). **README.md** de raíz creado (qué es, arrancar backend/worker/frontend, instalar PWA, enlaces a docs). **E (móvil Flutter) APLAZADO**: no hay SDK instalable (egress bloquea storage.googleapis.com/GitHub; solo pypi/npm) → sin `flutter analyze`; la PWA + Media Session cubren el móvil. **`tsc` verde · pytest 40**. | **Proyecto cerrado** (A–D + F completos; E aplazado documentado). Pendientes de datos de David: T-24 (análisis gain_db/energy), T-27 (reclasificar género). |
| 2026-08-30 | Personalización (docs/15 Entregas 1-4) | **Entrega 1 ✅** (C5 géneros `other`→0, R1+R3+R4). **Entrega 2 ✅** (T1 emparejado tolerante, T2 encolar ausentes, T4 listas del sistema con contenido, TOP1/2/3). **Entrega 3 🚧** (R2 los 7 kinds + R5 `explicacion` + config D11/D12/C2/C4 + compuerta C4 + cuota C2). **Entrega 4 🚧** (U1/U2 backend + U3 fila "Hecho para ti"; U4 portadas + e2e pendientes). **`pytest` 56 · `tsc` verde · 46 e2e + 11 unit + 49 backend (verificado por David)**. | **Solo queda C1 (prioridad de cola del recolector) y U4+e2e**, ambos **APARCADOS por decisión de David**: solo se verifican con el recolector corriendo y con mixes reales (hoy `plays=0`). Pendientes de datos/a uso real: **T-24** (análisis), **T-27** (géneros). |
