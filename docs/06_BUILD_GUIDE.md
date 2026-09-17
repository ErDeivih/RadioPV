# 🛠️ RadioPV · GUÍA DE CONSTRUCCIÓN (para el agente especializado)

> **ESTADO REAL (2026-08-30):** Construido y verificado: backend FastAPI (F0–F4, 40 tests), la web React en
> `frontend/` (bloques A–D y F en [`ORDEN_DE_TRABAJO.md`](ORDEN_DE_TRABAJO.md)) y el despliegue Docker.
> Este doc describe el plan; el estado vivo está en [`PROGRESS.md`](PROGRESS.md).

> Este es el documento **ejecutivo**: define qué construir, en qué orden, con qué estructura y qué
> criterios de aceptación, **sobre lo que ya existe**. Léelo junto a `01_SCHEMA`, `02_API`,
> `03_PERSONALIZATION`, `04_PLAYLISTS_WORKER`, `05_UI`.

---

## 0. Estado de partida (ya funcionando)
- Catálogo enriquecido (SQLite `data/radiov.db`, 889 canciones) + recolector (`radiov/`).
- **Backend FastAPI** funcional (`backend/`) con auth, tracks, artists, library, playlists, recommend.
- Base migrada a `data/backend.db` (y lista para Postgres con `DATABASE_URL`).
- Documentación completa en `docs/`.

## 1. Objetivo
Construir la **app de reproductor estilo Spotify** (multi-usuario, online) sobre ese backend:
reproductor con cola, personalización, playlists automáticas, y una UI. **Sin romper** el contrato
de la API (`schemas.py`/`02_API.md`) ni el esquema (`01_SCHEMA.md`).

## 2. Estructura objetivo
```
radiov/                 (existe: recolector + catálogo)  —— NO tocar la lógica salvo bug
backend/                (existe: API)  —— extender, no reescribir
  app/
    routers/            añadir: system_playlists, mixes, wrapped, search, lyrics
    personalization.py  mover/extraer `_profile/_score/_candidates` (reutilizar)
    workers.py          tareas programadas (refresh_trends/new_releases/mixes)
  alembic/              migraciones versionadas (sustituir create_all en producción)
  tests/                pytest (auth, tracks, recommend, migraciones)
frontend/               NUEVA app (React + Vite + Tailwind)  → consume la API
  src/
    api/        cliente axios con token
    pages/      Home, Search, Library, Playlists, Artist, Album, Radio, Stats
    components/ Sidebar, TopBar, SearchBar, Card, PlaylistCard, TrackRow,
                PlayerBar, QueuePanel, ProgressBar, VolumeSlider, Dialog, Skeleton…
    store/      estado (redux/zustand) para cola y sesión
    styles/     tema oscuro
infra/                  Dockerfile(s), docker-compose (api+postgres+worker+front), nginx, .env
```

## 3. Orden de trabajo y criterios de aceptación

### FASE A — Consolidar backend (1-2)
- [ ] Extraer lógica de personalización a `personalization.py` (reutilizable).
- [ ] Añadir `GET /recommend/trending`, `GET /playlists/system`, `GET /wrapped`.
- [ ] Añadir **Alembic** (migración inicial desde modelos) y **tests** (pytest: register/login, tracks,
      recommend, migración). **Aceptación**: `pytest` verde; `create_all` eliminado en producción.
- [ ] Soporte **Postgres** probado (`DATABASE_URL`).

### FASE B — Reproductor y señales (2-3)
- [ ] **PlaybackService** (backend): endpoints de cola (set/next/prev/shuffle/repeat) y **historial**.
- [ ] `POST /play` ya existe; ampliar con `completed`/`seconds_listened`.
- [ ] **Aceptación**: al reproducir se registra el play; la cola se mantiene por sesión.

### FASE C — Motor de playlists + worker (3-4)
- [ ] `smart_playlists` (reglas) + generación de playlists `system/mix`.
- [ ] **Worker** (`workers.py`) con APScheduler/Celery: `refresh_trends/new_releases/new_artists/
      rebuild_mixes/rebuild_static_lists/prune`.
- [ ] Tabla `mixes` (precomputado). **Aceptación**: un cron crea "Trending" y "Daily Mix" con datos reales.

### FASE D — APP de reproductor (UI) (4-6)
- [ ] **Frontend** (React+Vite+Tailwind): login/registro, Home (Para ti), Search, Library, Playlists,
      Artist, Album, Radio, Stats.
- [ ] **PlayerBar** completo (play/pausa, sig/ant, shuffle, repeat, seek, volumen, cola).
- [ ] Botones 👍👎 y registro de plays. **Aceptación**: flujo completo (login → home → play → like →
      el personalizado cambia).

### FASE E — Riqueza de datos (opcional)
- [ ] `danceability/valence/acousticness/loudness` (librosa) + `similar` (top-K) + **pgvector**.
- [ ] `lyrics`, biografías (Wikipedia/Wikidata), más fuentes (YouTube/Billboard).

### FASE F — Operativa (6-7)
- [ ] Docker Compose (api + postgres + worker + front) + **HTTPS** (nginx/caddy) + `.env`.
- [ ] Migraciones Alembic + **backup** + healthchecks + logs. **Aceptación**: `docker compose up` levanta todo.

## 4. Contratos que NO se deben romper
- **Tablas** (`01_SCHEMA.md`): añadir columnas/tablas está bien; cambiar el significado no.
- **API** (`02_API.md`): los endpoints existentes → misma request/response.
- **Autenticación**: JWT Bearer; `token_version` para revocar.

## 5. Cómo probar local el backend
```powershell
# terminal 1 (API)
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
# terminal 2 (pruebas)
curl -X POST localhost:8000/auth/register -H "Content-Type: application/json" -d '{"email":"a@b.com","password":"s3cret123"}'
curl localhost:8000/tracks?limit=5
```

## 6. Riesgos / pautas
- **Dependencias**: `bcrypt==4.0.1` (passlib no compatible con 5.x). Para Postgres: `psycopg2-binary`.
- **Idempotencia** en cualquier tarea de descarga/refresh (dedup por `deezer_id`/`youtube_id`).
- **No bloquear la API**: trabajos pesados en *worker*; usar cola.
- **Seguridad**: hash de contraseñas, token, rate-limit login, sanear rutas de fichero (Windows).
- **Legal**: nota de uso personal / respeto a los ToS de YouTube.

## 7. Definición de "hecho"
- Toda la FASE A-F completada (o las acordadas).
- `pytest` verde; aplicación arranca en Docker; flujo usuario (login → escuchar → personalizar) funciona.
- Documentación actualizada en `docs/` si cambia algo.
