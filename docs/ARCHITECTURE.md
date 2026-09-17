# 🧠 RadioPV · Arquitectura robusta y modelo de personalización (plan definitivo)

> Este documento **repite y repiensa** todo lo aprendido (Spotify + Deezer + Cassandra) para fijar
> cómo debe construirse el sistema cuando se cree, de forma **robusta y sin errores**. No es código:
> es el plano definitivo de datos, usuarios, autenticación, algoritmos y robustez.

---

## 0. Resumen ejecutivo (lo importante)

1. **Stack local correcto**: Python + **SQLite** + Streamlit + yt-dlp + librosa. **No usar Cassandra ahora**.
2. Diseñar para **robustez**: *eventos inmutables* (lo que pasa: plays, likes) y *agregados derivados*
   (perfil, contadores). Migraciones versionadas, transacciones, trabajadores idempotentes, tests, backup.
3. **Multi-usuario preparado desde ya**: `users`, sesiones/auth, y **señales y personalización por usuario**
   (reactions, plays, playlists, taste_profile por `user_id`).
4. **Personalización**: señales (👍👎 + reproducciones + saltos) → **perfil de gusto (vector ponderado y
   con recencia)** → recomendación **content-based** + **colaborativa** (si hay varios usuarios) + **radio/mixes**.

---

## 1. ¿Qué es Cassandra y cómo lo aplica Spotify? ¿Lo usamos?

### Qué es
**Cassandra** es una **base de datos NoSQL, distribuida y de tipo "wide-column"** (modelo
clave→columnas ordenadas, organizada en *keyspaces* y *column families*/tablas). Sus propiedades:

- **Escalado horizontal** (añadir nodos) y **alta disponibilidad** (replicación, sin punto único).
- **Escritura muy rápida y orientada a "append"**: ideal para **eventos masivos** (plays, streams,
  likes) y para leer por clave.
- Se sitúa en el lado **AP** del teorema CAP: prioriza **disponibilidad y partición** sobre la
  consistencia inmediata (eventual).
- **Spotify lo usa** para su capa de **personalización y playlists a escala** (miles de millones de
  filas): tablas tipo `items`, `playlists`, `user_taste` y **anotaciones** etiquetadas, con escrituras
  masivas de eventos y lecturas por usuario/clave.
  (Fuente: https://www.engineering.atspotify.com/2015/1/personalization-at-spotify-using-cassandra
   y https://planetcassandra.org/usecases/spotify/391/)

### ¿Lo aplicamos nosotros?
**No, hoy no.** Para una app **local/mono-usuario** (o pocos usuarios) con decenas de miles de
canciones:

| | SQLite | Cassandra |
|---|---|---|
| ACID / transacciones | ✅ fuerte | ⚠️ eventual (solo partición/clave) |
| Operación | cero infra (archivo) | clúster/cloud, nodos |
| Lecturas por clave/tabla pequeña | ✅ muy rápido | ✅ |
| Escala masiva de eventos | ✔️ hasta ~millones | ✅ miles de millones |
| Complejidad | ✅ baja | ⚠️ alta (consistencia, replicación) |

**Decisión**: **SQLite** con **eventos + agregados**. SI algún día la app es **multi-usuario en cloud**
con **millones de señales**, el plan de migración: **Postgres** (relacional/transaccional) primero y,
si el volumen de eventos lo exige, **Cassandra** (o un store de vectores) para las señales y las
proyecciones. Para no reescribir: modelamos las señales como **append-only** (eventos) y las
personalizaciones como **agregados derivados** (proyecciones), que es migrable.

---

## 2. Modelo de datos v2 (robusto y multi-usuario)

Convención: `tracks/artists/artist_albums` = **catálogo** (items). Lo demás = **señales de usuario** (por `user_id`).

### Catálogo (ya existe)
- `tracks` (40 col.): artista, álbum, carátula/foto local, año real, género, idioma, BPM, energía,
  tags/moods, era, remix, feat, explicit, popularidad, deezer_id, youtube_id…
- `artists`, `artist_albums`, `tracks_fts`.

### Nueva capa de usuario
- `users(id, email UNIQUE, password_hash, salt, display_name, is_admin, created_at, last_login)`
- `sessions(id, user_id, token UNIQUE, created_at, expires_at, ip, user_agent)` (revocable)
- `reactions(id, user_id, track_id, liked, skipped, updated_at, UNIQUE(user_id, track_id))`
- `plays(id, user_id, track_id, played_at, source, completed, seconds_listened)`  ← **evento append**
- `library(id, user_id, track_id, added_at, UNIQUE(user_id, track_id))` (guardadas)
- `playlists(id, user_id, name, description, type, created_at, updated_at)`
- `playlist_tracks(id, playlist_id, track_id, position, added_at, UNIQUE(playlist_id, track_id))`
- `smart_playlists(id, user_id, name, filters (JSON), enabled)`
- `user_taste(id, user_id, UNIQUE)`: vector normalizado (bpm, energy, valence, danceability,
  era, género, artistas, tags) + `bpm_mean`, `energy_mean`, `valence_mean`, `preferred_*` (agregado).
- `similar(track_a, track_b, score)` (precomputada, top-K vecinos)
- `mixes(id, user_id, kind (daily/radio/mood/wrapped), seed, tracks_json, created_at)`.
- `lyrics(track_id, text, language, source)`.

### Índices clave
`plays(user_id, played_at)`, `reactions(user_id, track_id)`, `playlist_tracks(playlist_id, position)`,
`library(user_id)`, `similar(track_a)`, `(genre, year)`, `(status, added_at)`, `era`, `energy`, FTS.

---

## 3. Usuarios, registro y login

- **Registro**: validar email único + contraseña. Hash con **argon2/bcrypt** (`passlib`). Guardar
  `password_hash` + `salt`. Nunca la contraseña en claro ni en logs.
- **Login**: verificar hash; crear `session` con **token aleatorio seguro** (secrets.token_urlsafe),
  expiración (p. ej. 30 días), IP/UA. 
- **Logout**: revocar token. **Recuperación**: token de un solo uso (futuro). **2FA**: opcional.
- **Modo local**: un botón "sin cuenta" crea un usuario `local` por defecto para no friccionar.
- **Roles**: `admin` (configuración, borrado masivo, fuentes) vs usuario (gustos, listas).
- **Rate-limit** en login (anti-fuerza bruta) y controles de sesión.

---

## 4. Personalización: algoritmo (cómo se hace)

### 4.1 Señales → perfil
De cada evento se derivan **afinidades**:

- 👍 `like` = **+3** · reproducción completa `play` = **+1** · skip al 30 % = **-2** · 50 % = **-1**.
- **Recencia**: peso exponencial por ventana (90 días) para que el gusto sea "actual".
- `user_taste` = **media ponderada** de los vectores de features de los tracks señalizados
  (normalizado). Deriva `preferred_genres/artists/eras`, `bpm_mean`, `energy_mean`, `valence_mean`.

### 4.2 Vectores y similitud
- **Features** por canción: `bpm`, `energy`, `valence`, `danceability`, `acousticness`, `loudness`,
  `era` (codificada), `genre` (one-hot), `tags` (one-hot). **Normalizar** (z-score/min-max).
- **Similitud**: **coseno** entre vectores. Precomputar `similar` (top-K vecinos por canción) para
  no hacer O(N²) por petición.
- **Clusters**: k-means sobre vectores → grupos de "humor/estilo" para **radios**.

### 4.3 Recomendación
- **Content-based**: `score = coseno(vector_usuarior, vector_cancción) + sesgo_artista + sesgo_género
  + sesgo_era + popularidad(prior)`. Excluir vistas y saltos. Aplicar **MMR** (diversidad) para no
  repetir el mismo artista/género en la lista.
- **Colaborativa (multi-usuario)**: matriz implícita `usuarios×canciones` (plays/likes) →
  **Matrix Factorization (ALS)** o **item-item cosine** sobre co-ocurrencias. Con pocos usuarios,
  item-item cosine es suficiente y simple.
- **Radio(seed)**: vecinos del seed en orden de similitud (usando `similar`).

### 4.4 Diarias y semanales
- **Mix diario**: perfil (content) + aleatorio controlado + diversidad + **"no repetir en 7 días"**.
- **Recomendación semanal / "Wrapped"**: agregados de la semana (top artistas/géneros/horas,
  "nuevos descubrimientos", evolución vs semana anterior, minutos escuchados).
- **Mixes por mood**: cluster/mood de `tags` + features.

### 4.5 Cold start (nuevo usuario)
- Sin señales: **popularidad** + **novedad** (no repetir) + **mood** elegido explícito. A medida que el
  perfil madura, se mezcla con content-based.

---

## 5. Robustez (para que no haya errores)

1. **Migraciones versionadas** (`schema_migrations` con versiones; aplicar en orden; pruebas de cada una).
2. **Transacciones** en escrituras multi-tabla; `WAL`; `PRAGMA foreign_keys=ON`; `ANALYZE`.
3. **Idempotencia** en descarga/revisión (dedup por `deezer_id`/`youtube_id`), **cola persistida**
   (sobrevive reinicios), **reintentos con backoff** y *fallbacks* de red (Deezer/Apple/YouTube).
4. **Validación de metadatos**: revisor con heurística de "año real", normalización y saneado de
   nombres; nunca crashear por datos raros (`try/except` + log). Lista negra persistente.
5. **Workers en segundo plano** (descarga, BPM/energía, revisión) con **cola** y prioridad; sin bloquear
   la UI; límites de concurrencia; el análisis de audio (librosa) es CPU-intensivo → priorizable.
6. **Config** con valores por defecto validados (`settings.json` + `.env`).
7. **Tests** (`pytest`: BD, migraciones, algoritmos de recomendación, parseadores, auth) + CI.
8. **Backup** (API `sqlite.backup`) periódico + **exportación** del catálogo (CSV/JSON).
9. **Logging estructurado** (eventos/errores/warnings) con niveles y sin secretos.
10. **Seguridad**: hash de contraseñas, tokens, rate-limit, saneado de rutas/nombres de fichero (Windows).

---

## 6. Rendimiento a escala

- Todo con índice + FTS; **paginación** (cargar por lotes); **cache** de agregados (perfil, stats, mixes).
- Precomputar `similar`/vecinos y **agregados** (taste, counters) para no recalcular por petición.
- Imágenes locales (ya) para carga instantánea y offline.

---

## 7. Fases y orden de trabajo

- **F1** Catálogo (✅ hecho con carátulas, fotos, discografía, FTS, perfiles).
- **F2** Reproductor (PlaybackService: cola, shuffle, crossfade, gapless, EQ) + registro de `plays` y 👍👎.
- **F3** Personalización (perfil, mixes diarios, radio(seed), wrapped semanal) con el motor content-based.
- **F4** Usuarios y login (multi-usuario) si se decide.
- **F5** Robustez: migraciones versionadas, tests, backup, idempotencia, trabajadores.
- **F6** Extra: más audio-features, colaborativa (ALS), letras, more sources (YouTube/Billboard), biografías.

---

## 8. Conclusión / recomendación práctica

- **Ahora (local)**: quedarse en **SQLite con eventos + agregados**, ya robusto y sin Cassandra.
- **Modelo "event-sourcing-like"** (plays/likes como appends, perfil/mixes como proyecciones) nos deja
  **crecer a Postgres/Cassandra** sin reescribir si algún día es multi-usuario/cloud.
- Construir con **tests, migraciones, idempotencia y backup** desde el primer día para evitar errores.

> **Nota legal**: mantener la nota de uso personal y respeto a los ToS de YouTube y derechos de autor.
