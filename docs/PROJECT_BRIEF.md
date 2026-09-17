# 🧭 RadioPV · Briefing maestro para agentes de IA (Claude)

> Este documento explica **todo el proyecto de arriba a abajo** para que un agente de IA (Claude)
> con acceso a esta carpeta entienda qué es, cómo funciona, qué hay hecho y qué falta, y pueda
> **ayudar con los planteamientos y la construcción**. Léelo junto a `docs/00_INDEX.md`.
> Todo el código está en `F:\EspacioCodigo\RadioPV`.

---

## 1. Qué es RadioPV

**Un "Spotify propio" construido desde YouTube.** Busca y descarga música conocida (reggaetón, pop,
rock, bachata, salsa, cumbia, flamenco, dance, rap, italiano, francés, portugués…), la cataloga a
fondo (año real, género, idioma, BPM, energía, mood/etiquetas, era, featurings, carátulas, fotos,
discografía) y permitirá **reproducirla y personalizarla** (recomendaciones, mix diario, radios,
playlists automáticas) — en **web y móvil**, con **cuentas de usuario** para familia y amigos.

---

## 2. Pipeline completo (de la ingesta al producto)

```
┌────────────────── INGESTA ─────────────────────────────────────────────┐
│ 1. Descubrimiento                                                  │
│    · Listas de éxitos reales (Apple es/us/mx/ar/co/br/it/fr/gb),   │
│      Los 40, éxitos por décadas (curatos), barrido por años        │
│      (1965→2024), y EXPANSIÓN de artistas (relacionados de Deezer). │
│    · Fuente: DeezerAPI (sin clave) + Apple RSS + playlist curadas. │
│ 2. Descarga                                                          │
│    · yt-dlp busca "artista - título" en YouTube, valida duración,   │
│      baja solo audio y lo convierte a MP3 con ffmpeg.               │
│    · Guarda en E:\Musica\descargas (bruto) y organiza en            │
│      E:\Musica\catalogada\<Artista>\[Año] Álbum\.                    │
│ 3. Enriquecimiento (revisor de metadatos)                            │
│    · Relee Deezer: año REAL (álbum de estudio original), álbum,      │
│      artistas/feat, explicit.                                       │
│    · librosa → BPM y energía; derivación de tags/moods y era.        │
│    · Carátulas y fotos → locales (data/covers, data/artists).        │
│    · Perfiles de artista + discografía (artist_albums).              │
│ 4. Almacenamiento                                                    │
│    · SQLite data/radiov.db (catálogo, 889 canciones) + FTS5 + índices│
│      + lista negra + eventos + artist_pool (expansión).              │
└───────────────────────────────────────────────────────────────────────┘
                              │  (recolector: radiov/agent.py en worker)
                              ▼
┌────────────── BACKEND (online, multi-usuario) ────────────────────────┐
│  · FastAPI + SQLAlchemy (backend/app) · auth JWT+bcrypt ·          │
│    endpoints: auth, tracks (filtros/FTS), artists, library         │
│    (play/like/skip), playlists, recommend/daily/radio.             │
│  · BD: SQLite local (data/backend.db) o PostgreSQL con DATABASE_URL.│
│  · PERSONALIZACIÓN: perfil de gustos → recommend (content),        │
│    radio(seed), daily mix.                                          │
│  · (pendiente) /stream/{id} (MP3 con Range) + /media/* (imágenes),  │
│    y el WORKER de playlists automáticas.                            │
└───────────────────────────────────────────────────────────────────────┘
                              │  (API REST, JWT)
              ┌───────────────┴───────────────┐
              ▼                               ▼
      WEB (React, reusado)             MÓVIL (Flutter, reusado)
   de vendor/spotify-web          de vendor/Flutter-Musive-app
   → clonado/adaptado              → clonado/adaptado
```

---

## 3. Estado actual (lo que YA existe y funciona)

| Bloque | Estado |
|---|---|
| **Recolector** (`radiov/`) | ✅ Descarga, cataloga, revisa metadatos, fotos/carátulas, discografías. Funciona en worker. |
| **Catálogo** | ✅ 889 canciones · 40+ campos · FTS · 12+ índices · perfiles + discografías (5.793 álbumes) · imágenes locales. |
| **Backend API** (`backend/`) | ✅ FastAPI + SQLAlchemy + auth (JWT/bcrypt) + endpoints + migración desde SQLite. **Corre en `http://127.0.0.1:8000`** (docs en `/docs`). |
| **Recomendación content-based** | ✅ Probada (gustar flamenco → sugiere flamenco), + daily + radio. |
| **Docs** | ✅ `docs/00_INDEX` … `docs/07_CROSS_PLATFORM_BLUEPRINT` + `ARCHITECTURE`, `PLAYER_DESIGN`, `PLAYLISTS_UI_DESIGN`. |
| **PostgreSQL** | ✅ Modelos portables (`DATABASE_URL`); usa `create_all` (producido: Alembic). |

### Datos relevantes del entorno
- **Python 3.12** en `.venv`; se usa **uv** para instalar (pip se cuelga en este equipo por proxy/sandbox).
- **FFmpeg** presente. **Node 24 + npm + git** presentes.
- **Sandbox**: el sistema bloquea escribir fuera de `F:\EspacioCodigo\RadioPV` (la música va en `E:\Musica`,
  así que la app se lanza con **acceso ampliado**). `git clone` falla por credenciales (schannel) → se
  bajan los repos como **tarball** (ver abajo).
- **bcrypt** fijado a **4.0.1** (passlib no es compatible con 5.x).

---

## 4. Objetivo / a dónde queremos llegar

Una **app multiplataforma** (web + Android/iOS) tipo Spotify, **multi-usuario**, **online**,
reutilizando **lo mejor de dos repos ya descargados** en `vendor/`:
- **Web** (`vendor/spotify-web`): React+TS+Redux, UI y capa de red de calidad.
- **Móvil** (`vendor/Flutter-Musive-app`): Flutter, reproductor con notificación, cola, likes, caché.

Con **UN backend común** (el nuestro) y **una BD** (Postgres). La música la descarga el **recolector**;
la app **solo reproduce** lo que hay (no descarga en el navegador).

### Repos descargados
- `vendor/spotify-web` (React) · `vendor/Flutter-Musive-app` (Flutter). Añadidos a `.gitignore`.
- Para reintentar la descarga por tarball (git no funciona por credenciales):
  `https://github.com/francoborrelli/spotify-react-web-client/archive/refs/heads/main.tar.gz`
  `https://github.com/Ansh-Rathod/Flutter-Musive-app/archive/refs/heads/master.tar.gz`

---

## 5. Cómo lo construiremos (plan de fases)

### FASE 1 · Backend para web y móvil (base)
- `GET /stream/{track_id}` → `FileResponse` del MP3 con **soporte `Range`** (seek en web y móvil).
- `GET /media/...` → carátulas/fotos locales (`cover_path`, `artist_image_path`).
- CORS abierto; **refresh token** opcional. **Aceptación**: se puede reproducir en web y móvil.

### FASE 2 · Web (React)
- `axios.ts` baseURL → nuestra API; `services/*` → nuestros endpoints; `login` → nuestro JWT;
  `webPlayback` → `<audio src=/stream/{id}>`; `constants/spotify` → nuestras playlists/imágenes;
  interfaces → nuestro esquema. (Clonar `vendor/spotify-web` → `frontend/`.)

### FASE 3 · Móvil (Flutter)
- `url.dart` → nuestra base; `repositories/*` → nuestros endpoints; login → JWT; `player` → `/stream`;
  permiso de red Android. (Clonar → `mobile/`.)

### FASE 4 · Playlists automáticas + worker
- Motor de playlists (`smart_playlists` + `mixes` + `playlists/playlist_tracks`) y worker
  (`refresh_trends/new_releases/new_artists/rebuild_mixes/prune`) para "Para ti", trending, novedades,
  radar de nuevos, por estilo/época/mood, radios de artistas.

### FASE 5 · Despliegue
- Docker (API + Postgres + worker + web estático) + HTTPS + build APK/AAB. Migraciones **Alembic** + tests + backup.

---

## 6. Decisiones clave ya tomadas (para no discutirlas de nuevo)
- **BD**: **Postgres** como principal (y opcional **Cassandra** para eventos a escala, cuando el volumen lo pida — no ahora). Ver `docs/ARCHITECTURE.md`.
- **Recomendación**: content-based (perfil de gustos) + radio por similitud + mix diario; colaborativa (ALS) si hay bastantes usuarios. Ver `docs/03_PERSONALIZATION.md`.
- **UI**: reutilizar los dos repos (no reescribir). El contrato de **API** y **esquema** están congelados (`docs/01_SCHEMA.md`, `docs/02_API.md`).
- **Recomendación de flujo**: la app reproduce; el recolector descarga; el worker de actualidad crea listas.

---

## 7. Dónde está cada cosa (para el agente)
- **Docs**: `docs/00_INDEX.md` (índice) · `01_SCHEMA` · `02_API` · `03_PERSONALIZATION` · `04_PLAYLISTS_WORKER` · `05_UI` · `06_BUILD_GUIDE` · `07_CROSS_PLATFORM_BLUEPRINT` · `ARCHITECTURE` · `PLAYER_DESIGN` · `PLAYLISTS_UI_DESIGN`.
- **Código fuente**: `radiov/` (recolector) · `backend/` (API) · `app_streamlit_legacy.py` (web local antigua, sin backend) · `run_agent.py`.
- **Datos**: `data/radiov.db` (catálogo), `data/backend.db` (backend), `data/covers|artists|music…`.
- **Repos reutilizables**: `vendor/spotify-web`, `vendor/Flutter-Musive-app`.

---

## 8. Qué hacemos ahora / cómo puedes ayudar (Claude)

> 🚧 **Auditoría y plan ya hechos**: los fallos detectados están en [`08_REVIEW.md`](08_REVIEW.md) y el
> plan de implementación paso a paso en [`09_IMPLEMENTATION_PLAN.md`](09_IMPLEMENTATION_PLAN.md).
> Para programar, ese es el documento a seguir (empezando por la FASE F0, que es bloqueante).

1. **Revisar y refinar** `docs/07_CROSS_PLATFORM_BLUEPRINT.md` y el resto: ¿falta algo? ¿hay mejor
   arquitectura para streaming/web/móvil?
2. **Diseñar el contrato de `/stream`** (Range, content-type, auth opcional) y `/media`.
3. **Confirmar la adaptación** del React y del Flutter (lista exacta de archivos) antes de clonar/cambiar.
4. **Planificar** el Docker/deploy y las migraciones Alembic.

> **Nota legal**: uso personal, respeta ToS de YouTube y derechos de autor. Los repos de terceros se
> reutilizan sin ánimo comercial (aunque siempre revisar su licencia).
