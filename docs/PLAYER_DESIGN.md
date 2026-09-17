# 🎧 RadioPV · Diseño del reproductor estilo Spotify

> Documento de arquitectura y diseño para la futura app de reproducción tipo **Spotify / Deezer**.
> No se implementa todavía: aquí se deja **todo indicado** (funcionalidades, arquitectura, base de
> datos, índices, consultas, motor de recomendación y fases) a partir del catálogo que ya tenemos.

Referencias usadas:
- Personalización a gran escala en Spotify con Cassandra: https://www.engineering.atspotify.com/2015/1/personalization-at-spotify-using-cassandra
- Caso de uso de Cassandra en Spotify (playlists / recomendación): https://planetcassandra.org/usecases/spotify/391/
- Funciones de Deezer (Flow, mixes, radios, letras, offline, ecualizador…): https://play.google.com/store/apps/details?id=deezer.android.app
- Lista de funciones de Deezer (App Store): https://apps.apple.com/cy/app/deezer-music-podcast-player/id292738169

---

## 1. Visión

RadioPV ya es un **catálogo musical completo y enriquecido** (833 canciones · 40 columnas · FTS5 ·
perfiles de artista · discografías · carátulas locales). El siguiente paso es la **capa de reproducción
y personalización** para convertirlo en un "Spotify propio":

- **Tú decides** qué suena, pero la app te **ayuda** con mixes, recomendaciones, radios y listas
  inteligentes.
- **Local y privado**: todo se lee de tu disco y de tu BD (sin depender de servidores de terceros).

---

## 2. Funcionalidades de referencia (Spotify / Deezer)

| Categoría | Funciones destacadas |
|---|---|
| **Reproducción** | Play/pausa, siguiente/anterior, cola, aleatorio, repetir, seek, crossfade, **gapless**, **ecualizador**, normalización de volumen, salida por dispositivo. |
| **Personalización** | **Mix diario/Discover**, **Flow** (Deezer: radio infinita según tu gusto), **radio por canción/artista**, "porque escuchaste X", recomendaciones por mood/contexto. |
| **Listas** | Playlists propias, **smart playlists** (reglas automáticas), listas colaborativas, orden/arrastre, "tus 100 más escuchadas". |
| **Biblioteca** | Guardar/me gusta, álbumes/artistas seguidos, descargados para **offline**. |
| **Descubrimiento** | Charts, novedades, listas por género/era, búsqueda con **autocompletado**, búsqueda por letra. |
| **Contenido** | **Letras**, créditos, artistas relacionados, discografía, radios. |
| **Datos** | Historial de escucha, gráficos de hábitos, "wrapped". |
| **Social** | Compartir canciones/listas, colaboración (opcional en nuestra versión mono-usuario). |

---

## 3. Arquitectura (conceptual)

```
┌───────────────────────────────────────────────────────────────┐
│  Capa de presentación (Streamlit)                              │
│   · Reproductor (player) · "Para ti" · Playlists · Biblioteca │
│   · Estadísticas · Búsqueda (FTS + facetas)                    │
└──────────────────────────────┬────────────────────────────────┘
                               │
┌──────────────────────────────▼────────────────────────────────┐
│  Servicio de reproducción y cola                               │
│   · PlaybackService (cola, shuffle, crossfade, gapless, EQ)   │
│   · Registra record_play / react (👍 👎)                       │
│   · Gestiona la salida (auriculares / memoria interna)         │
└──────────────────────────────┬────────────────────────────────┘
                               │
┌──────────────────────────────▼────────────────────────────────┐
│  Servicio de personalización / recomendación                   │
│   · compute_taste_profile() → perfil de gustos                 │
│   · recommend() → content-based + señales implícitas           │
│   · daily_mix(), radio(seed), smart playlists                  │
│   · (futuro) vectors de embeddings + colaborativo              │
└──────────────────────────────┬────────────────────────────────┘
                               │
┌──────────────────────────────▼────────────────────────────────┐
│  Capa de datos                                                │
│   · SQLite (catálogo + señales de usuario) → ya existe         │
│   · FTS5 (búsqueda) · imágenes locales · audio cache           │
│   · (opcional) cache en memoria/Redis para recomendaciones     │
└───────────────────────────────────────────────────────────────┘
```

**Clave de personalización (modelo de Spotify con Cassandra)** — Spotify usa tablas tipo
`items` (tracks/artistas/álbumes), `playlists`, `user_taste` y anotaciones etiquetadas. Nosotros lo
adaptamos a relacional/SQLite: el catálogo (`tracks/artists/artist_albums`) ya es el "items", y
añadimos las **señales del usuario** (`reactions`, `plays`) y el **perfil** (`taste_profile`).

---

## 4. Modelo de datos

### 4.1 Ya existente (base)
- `tracks` (40 columnas): artista, álbum, **carátula/foto local**, año real, género, idioma,
  BPM, energía, **tags/moods**, era, remix, feat, explicit, popularidad, deezer_id, youtube_id…
- `artists` (perfiles) y `artist_albums` (discografía).
- `tracks_fts` (búsqueda full-text).
- `reactions` (me gusta/salto), `plays` (historial), `playlists` + `playlist_tracks`,
  `taste_profile`.

### 4.2 Propuestas (para la app de reproductor)

**1) Más características de audio** (para recomendaciones finas y "modos").
Añadir a `tracks`: `danceability REAL`, `valence REAL`, `acousticness REAL`,
`loudness REAL`, `key INTEGER`, `mode INTEGER`, `instrumentalness REAL`.
Se calculan con `librosa`/`essentia` (ya tenemos BPM y energía). Índice compuesto
`(bpm, energy, valence)`.

**2) Tabla `user_profiles`** (por si hubiera varios perfiles):
`id, name, created_at`.

**3) Tabla `radio` / mixes generados**:
`mix_id, kind (daily/radio/flow/mood), seed_track, seed_artist, created_at, tracks_json`.

**4) Tabla `smart_playlists`** (reglas reutilizables):
`id, name, filters TEXT (JSON: {generos, eras, mood, bpm_min, bpm_max, energia, remix...}), enabled`.

**5) Tabla `lyrics`**:
`track_id, text, language, source, added_at` (para búsqueda por letra y visualización).

**6) Tabla `devices`** (salidas): auriculares internos, USB, etc. (simple).

### 4.3 Índices recomendados
- `plays(track_id, played_at)` ✓, `reactions(track_id)` ✓, `playlist_tracks(playlist_id, position)` ✓.
- `tracks(genre, year)` ✓, `(status, added_at)` ✓, `era`, `energy` ✓.
- Añadir: `tracks(danceability)` cuando exista; `lyrics(track_id)`; índice compuesto de recomendación
  `(genre, era, bpm)`.

### 4.4 Consultas clave (ya implementadas)
- `record_play`, `react`, `create_playlist`, `add_to_playlist`, `get_playlists`, `get_playlist_tracks`.
- `compute_taste_profile`, `recommend(n)`, `daily_mix(n)`.

---

## 5. Motor de personalización

### 5.1 Señales (inputs)
- **Explícitas**: 👍/👎 (`reactions`), ratings, seguimiento de artistas.
- **Implícitas**: reproducciones completas vs saltos (`plays` + `skipped`), repeticiones, tiempo
  escuchado, omitidas al 30%.

### 5.2 Perfil de gusto (content-based)
Agregar las señales *liked/no-skipped* en `taste_profile`: géneros, artistas, eras, `bpm_mean`,
`energy_mean` (y futuro `valence_mean`, `danceability_mean`). Con eso, `recommend()` puntúa candidatos
no escuchados por cercanía (género, era, artista, BPM, energía).

### 5.3 Motores
- **Content-based**: por características del perfil (ya funciona).
- **Colaborativo (implicit feedback)**: en mono-usuario no hay "otros", pero se puede simular con
  **clusters de canciones** (similitud entre canciones) → "porque escuchaste X".
- **Híbrido / seed (radio)**: dado un seed (canción/artista/mood), clúster de vecinos por
  *feature vector* `(bpm, energy, valence, era, genre, tags)` → lista ordenada por distancia.
- **Mixes**: `daily_mix` (perfil + aleatorio), `mood_mix` (por tags), `radio(seed)`.

### 5.4 Similitud entre canciones (tabla candidata)
`similar(id, track_a, track_b, score)` precomputada (o calcular on-the-fly para radio). Con 5000 canciones,
la tabla de pares puede crecer; se recomienda **limitar** a los K vecinos más parecidos por canción
(cálculo por `bpm/energy/valence/era/genre/tags` + normalización).

### 5.5 Cold start
Si no hay señales aún: recomendar por **popularidad**, por **moods/era** elegidos, o **aleatorio con
sesgo a no-repetir**. El perfil se calibra al empezar a dar 👍/👎.

---

## 6. Reproductor (PlaybackService) — funcionalidades

- **Estado**: `playing`, `paused`, `position`, `queue`, `history`.
- **Controles**: play/pausa, siguiente/anterior (historias), seek, **shuffle**, **repeat** (off/all),
  **crossfade**, **gapless**, **volumen**, **normalización**.
- **Cola**: añadir a cola, "a continuación", reordenar, borrar.
- **Auriculares/offline**: exportar a la carpeta `auriculares/` (ya existe) o copiar a memoria interna;
  reproducir desde archivo local o por streaming.
- **EQ**: presets (bajo/medio/agudo) vía `pydub`/`ffmpeg` (opcional) o puramente visual en la UI.
- **Registro**: cada reproducción → `record_play(source=...)` para alimentar el perfil.

---

## 7. Búsqueda y descubrimiento

- **FTS5** (ya) sobre título/artista/álbum; ampliar a `lyrics` y `tags`.
- **Facetas** (ya): género, idioma, año, era, mood, energía, remix, artista.
- **Autocompletado**: FTS con prefijo (`token*`) → sugerencias al teclear.
- **Charts/covers**: ya está el catálogo de éxitos; se puede exponer "éxitos de X año" como radio.

---

## 8. API / servicios (conceptual)

- `POST /play` (track, source) → `record_play`.
- `POST /react` (track, like/skip).
- `GET /recommend?n=&mood=` · `GET /daily_mix` · `GET /radio?seed=`.
- `GET/POST /playlists` · `POST /playlists/{id}/tracks`.
- `GET /search?q=` (FTS).
- `GET /stats` (hábitos, wrapped).

---

## 9. Rendimiento

- BD SQLite indexada + FTS5. A miles de canciones sigue ágil (consultas de 2-20 ms).
- **Cache** de agregados (stats, perfil, mixes) con TTL corto (ya parcial).
- Recomendaciones: precomputar `similar` o limitar vecinos para no hacer O(N²) por petición.
- Imágenes locales (ya) para que carguen al instante y offline.
- Trabajos pesados (audio analysis, enriquecimiento) en **worker en segundo plano**.

---

## 10. Fases (roadmap)

- **F1 (ya)**: catálogo enriquecido + búsqueda rápida + perfiles/carátulas/discografía.
- **F2**: reproductor (PlaybackService) + registro de reproducciones y 👍/👎.
- **F3**: "Para ti" (mix diario, radio por canción/artista/mood) con el motor actual.
- **F4**: playlists + smart playlists + "tus más escuchadas".
- **F5**: más características de audio (danceability/valence…), similitud entre canciones.
- **F6**: letras, wrapped, ecualizador, crossfade/gapless, más fuentes de éxitos y biografías.

---

## 11. Estado actual vs pendiente

**Ya**: catálogo enriquecido, FTS, perfiles de artista, discografía, imágenes locales, reacciones,
historial, playlists, perfil de gusto, recomendación content-based, mix diario.

**Pendiente para el reproductor**: PlaybackService (UI de reproducción con registro), botones
👍/👎 en la UI, página "Para ti", gestión de playlists en UI, características de audio extra,
similitud entre canciones, letras, EQ/crossfade/gapless.

---

## 12. Aviso legal

Mantener la misma nota que el README: descargas para **uso personal**, respetando los ToS de
YouTube y los derechos de autor.
