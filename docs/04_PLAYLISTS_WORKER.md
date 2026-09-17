# 🎛️ RadioPV · Motor de playlists automáticas + trabajador de actualidad

> Qué playlists tendremos, cómo se generan y **quién las refresca** (trabajador en segundo plano).

## 1. Tipos de playlists

| Tipo | Regla / fuente | Cadencia |
|---|---|---|
| **Trending** ("Top 50", "Viral", "Los 40") | Apple hit-lists (es,us,mx,ar…) + Los 40 | cada 6-12 h |
| **Novedades** ("Lanzamientos") | Deezer novedades + `release_date` reciente | diaria |
| **Nuevos artistas** ("Radar") | artistas de tendencias sin presencia en el catálogo | diaria |
| **Para ti** (Daily Mix, Discover Weekly) | `taste_profile` + señales | diaria/semanal |
| **Por estilo/género/época/mood** | reglas en `smart_playlists` | diaria |
| **Radio por artista** | similitud a un artista | bajo demanda |
| **Institucionales** ("Wrapped") | agregados | semanal |

## 2. Reglas declarativas (`smart_playlists.filters` JSON)
```json
{"generos":["reggaeton"],"eras":["00s"],"moods":["fiesta"],"bpm_min":100,"bpm_max":145,
 "energia":"Alta","remix":true,"artistas":["Bad Bunny"],"year_min":2000,"year_max":2015,
 "orden":"-added_at","limite":50}
```

## 3. Trabajador (scheduler)
Un proceso programado (APScheduler o Celery/RQ con Redis) que llama:
- `refresh_trends()` → trae listas de éxitos; si una canción no está en la BD, la **descarga** (yt-dlp);
  la añade a "Trending". Idempotente (dedup por `deezer_id`/`youtube_id`).
- `refresh_new_releases()` → Deezer novedades.
- `discover_new_artists()` → artistas nuevos → "Radar".
- `rebuild_mixes()` → regenera Daily Mix / Discover por usuario (usa `recommend`).
- `rebuild_static_lists()` → recalcula listas por reglas.
- `refresh_radios()` → bajo demanda (radio de un artista).
- `prune()` → quita de playlists automáticas lo que ya no aplique (sin borrar del catálogo).

**Robustez**: cola persistente (sobrevive reinicios), reintentos con *backoff*, límites de concurrencia,
logs en `events`, y **no bloquear la API** (trabajos en segundo plano).

## 4. Almacenamiento
- `playlists` (tipo `system|mix|user`), `playlist_tracks` (posición).
- `mixes` (JSON con resultado) para servir rápido.
- `smart_playlists` (reglas) para regenerar.

## 5. API para servir
- `GET /playlists/system` → playlists automáticas.
- `GET /playlists/{id}/tracks` → contenido (o `mixes.tracks_json` si es un mix).
- `POST /mixes/refresh` → forzar regeneración (admin).

---

## Notas para el agente que lo implemente
- Usar el `backend/` y el **recolector `radiov/`** (que ya descarga y revisa) llamándolo desde el worker,
  o como servicio aparte.
- **No duplicar** el trabajo de descarga: el worker solo *descubre/etiqueta*; la descarga la hace el
  recolector (o el worker si es un proceso con yt-dlp).
- Mantener idempotencia y dedup para no hinchar la BD.
