# 🎛️ RadioPV · Motor de playlists automáticas + Diseño de UI (plan, sin programar)

> Continúa el plan del reproductor estilo **Spotify/YouTube**. Aquí se define **qué playlists
> automáticas tendremos**, **quién las crea y cada cuánto** (un trabajador en segundo plano) y
> **cómo será la interfaz** (páginas y componentes), **sin implementar todavía**.

---

## PARTE A · Motor de playlists automáticas

### A.1 Tipos de playlists (como Spotify/YouTube)

| Tipo | Ejemplos | Fuente / criterio |
|---|---|---|
| **Tendencias / Actualidad** | "Trending España", "Top 50 Global", "Viral 50", "Los 40", "Éxitos del momento" | Listas de éxitos reales (Apple es/us/mx/ar…, Los 40) + buscador por año actual. **Se refrescan a diario**. |
| **Novedades** | "Novedades de la semana", "Lanzamientos", "Recién salido del horno" | Deezer *editorial/new releases* + tracks con `release_date` muy reciente. **Semanal**. |
| **Nuevos artistas** | "Radar de nuevos", "Artistas emergentes", "Despegue" | Artistas que aparecen en tendencias y **aún no están en tu catálogo** (o con pocas canciones). |
| **Para ti (personal)** | "Daily Mix 1/2/3", "Discover Weekly", "On Repeat", "Time Capsule" | Según el **perfil de gustos** (géneros/eras/BPM/energía) + señales (👍👎/plays). **Mix diario + semanal**. |
| **Por estilo / género** | "Reggaetón", "Pop español", "Rock 80s", "Perreo", "Chill", "Fiesta" | Reglas por `genre`/`tags`/`era`. |
| **Por época** | "80s", "90s", "2000s", "Clásicos" | Regla por `era`/`year`. |
| **Por mood/contexto** | "Para estudiar", "Para correr", "Para la fiesta", "Noche", "Verano" | Reglas por `tags` + `bpm`/`energy`. |
| **Radios / por artista** | "Radio Bad Bunny", "Porque escuchaste X" | **Similitud** (BPM/energía/género/era) alrededor de un seed. |
| **Clubes/institucionales** | "Lo más escuchado del año", "Wrapped" | Agregados por año/popularidad. |

### A.2 Cómo se crean (reglas)
- **Reglas declarativas** (`smart_playlists` con filtros JSON: `{generos, eras, moods, bpm_min/max,
  energia, remix, artistas, year_min/max, orden, limite}`) + **playlists generadas** que las usan.
- **Playlists "vivas"**: se recalculan en un refresh; no se editan a mano (o sí, si se convierten en "user").

### A.3 El trabajador de actualidad (worker)
Un **servicio programado** (APScheduler / Celery+RQ con Redis) que corre en el backend:

- **`refresh_trends()`** (cada 6-12 h): trae listas de éxitos (Apple por país, Los 40) → si la canción
  no está en la BD, la **descarga** (yt-dlp) → la añade a "Trending".
- **`refresh_new_releases()`** (diario): Deezer novedades/editorial → añadir a "Novedades".
- **`discover_new_artists()`** (diario): de las tendencias, artistas nuevos sin presencia en el
  catálogo → "Radar de nuevos".
- **`rebuild_mixes()`** (diario/semanal): regenera los "Daily Mix" y "Discover Weekly" por usuario
  usando `taste_profile` + señales.
- **`rebuild_static_lists()`** (diario): recalcula las listas por estilo/época/mood desde la BD (reglas).
- **`refresh_radios()`** (bajo demanda): al pedir una radio de un artista.
- **`prune()`**: eliminar de playlists automáticas lo que ya no aplique (p. ej. salieron del top),
  sin borrar del catálogo.

**Robustez**: idempotente (dedup por `deezer_id`/`youtube_id`), reintentos con *fallback*, cola
persistente, límites de concurrencia, y **no bloquear la API** (trabajos en segundo plano). Cada
refresh registra en `events` qué cambió.

### A.4 Almacenamiento
- `playlists` (tipo `system|mix|user`), `playlist_tracks` (posición).
- `mixes` (JSON con el resultado precomputado) para servir deprisa sin recalcular.
- `smart_playlists` (reglas) para listas regenerables.

---

## PARTE B · Diseño de la interfaz (páginas y componentes)

> Orientativo para una **SPA (React + Vite)** con un **reproductor tipo Spotify**. Si se decide
> reutilizar Streamlit, las secciones son análogas pero con componentes de Streamlit.

### B.1 Estructura de navegación
```
┌─────────────────────┬──────────────────────────────────────────────┐
│  Sidebar            │  Contenido                                   │
│  · Inicio ("Para ti")│  · Home · Search · Library · Playlists ·     │
│  · Buscar           │    Artist · Album · Radios · Stats/Wrapped   │
│  · Biblioteca       │                                              │
│  · Playlists        │                                              │
│  · Artistas         │                                              │
│  · Estadísticas     │                                              │
│  · Ajustes          │                                              │
└─────────────────────┴──────────────────────────────────────────────┘
            ┌──────────────────────────────────────────────┐
            │  PlayerBar (fija abajo): cover · título ·      │
            │  controles · seek · volumen · cola · EQ        │
            └──────────────────────────────────────────────┘
```

### B.2 Páginas
- **Inicio / Para ti**: saludo, filas horizontales de tarjetas → "Recomendadas para ti",
  "Daily Mix 1/2/3", "Trending", "Novedades", "Radar de nuevos", "Tus artistas".
- **Buscar**: barra con **autocompletado** (FTS) + chips de faceta (género, era, mood, energía,
  idioma) + cuadrícula de resultados (tarjetas con carátula).
- **Biblioteca**: canciones guardadas, álbumes, artistas seguidos, descargas; filtros.
- **Playlists**: lista (user + automáticas) y detalle (portada, nº, reproducir/aleatorio, lista de
  tracks, añadir/eliminar, reordenar).
- **Artista**: cabecera (foto, nombre, fans), discografía, top canciones, artistas relacionados,
  "playlist/radio" del artista.
- **Álbum**: portada, año, lista de pistas.
- **Radio / Mix**: seed → reproducción sin fin de temas parecidos.
- **Estadísticas / Wrapped**: hábitos, top artistas, minutos, evolución.

### B.3 Componentes (design system)
- `Sidebar`, `TopBar`, `SearchBar` (autocomplete), `Card` (carátula, título, subtítulo, botón
  ▶️ al hover), `PlaylistCard`, `TrackRow` (lista con cola), `PlayerBar`, `VolumeSlider`,
  `ProgressBar` (seek), `QueuePanel`, `IconButton`, `PrimaryButton`, `Badge`, `Spinner/Skeleton`,
  `EmptyState`, `Toast` (errores), `Dialog` (añadir a playlist), `SegmentedControl` (facetas).
- **Estados en cada vista**: cargando (skeleton), vacío ("no hay resultados"), error, offline.
- **Accesibilidad y responsive**: móvil (player minimizado), teclado, focus.

### B.4 Flujo de reproducción
1. El usuario pulsa ▶️ en una tarjeta/fila → `POST /play` + se añade a la **cola**.
2. El **PlayerBar** muestra cover/título/controles; el **queue** permite siguiente/anterior.
3. Los botones 👍/👎 registran `reactions` → alimentan el perfil y los mixes.
4. Si el usuario abre una **playlist/radio**, se carga su `tracks_json` (mixes precomputados).

---

## PARTE C · Orden de trabajo sugerido

1. **Motor de playlists** (reglas + `smart_playlists` + `playlists/playlist_tracks`).
2. **Worker de tendencias** (`refresh_trends/new_releases/new_artists`) sobre la API existente.
3. **Personalización** (mixes diarios/radio) reutilizando `recommend()`/`radio()` ya hechos.
4. **UI** (SPA o Streamlit) conectada a la API: Home, Search, Library, Playlists, Player, Stats.

---

> **Nota legal**: mantener la nota de uso personal y respeto a los ToS de YouTube y derechos de autor.
