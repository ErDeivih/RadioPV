# 📚 RadioPV · Índice maestro de documentación

> Esto es el **mapa completo** del proyecto. Lee esto primero; después cada doc de detalle.
> Objetivo: que **otro agente especializado pueda construir la app de reproductor** (tipo Spotify)
> sobre lo que ya existe, sin ambigüedad.

---

## 📄 Documentos

| Doc | Contenido |
|---|---|
| [`NOTES_FOR_AGENT.md`](NOTES_FOR_AGENT.md) | ⭐ **Notas de alto valor** (gotchas del entorno y qué NO romper) |
| [`PROJECT_BRIEF.md`](PROJECT_BRIEF.md) | ⭐ **Briefing maestro** (para agentes/IA: todo el proyecto de la ingesta al producto) |
| [`00_INDEX.md`](00_INDEX.md) | **Índice + auditoría + veredicto** (¿se puede construir ya?) |
| [`01_SCHEMA.md`](01_SCHEMA.md) | **Esquema de base de datos completo** (SQLite local y Postgres/models), tablas, columnas, índices, relaciones |
| [`02_API.md`](02_API.md) | **Contrato de la API** (endpoints FastAPI, request/response, auth, ejemplos) |
| [`03_PERSONALIZATION.md`](03_PERSONALIZATION.md) | **Algoritmos de personalización** (perfil de gustos, recommend, daily, radio, colaborativa, cold start) |
| [`04_PLAYLISTS_WORKER.md`](04_PLAYLISTS_WORKER.md) | **Motor de playlists automáticas + trabajador de actualidad** |
| [`05_UI.md`](05_UI.md) | **Diseño de UI** (IA, páginas, componentes, estados, flujo de reproducción) |
| [`06_BUILD_GUIDE.md`](06_BUILD_GUIDE.md) | **GUÍA DE CONSTRUCCIÓN** (paso a paso para el agente: qué construir, estructura, fases, criterios de aceptación) |
| [`PROMPT_INICIAL.md`](PROMPT_INICIAL.md) | ⭐ **Prompt inicial** para el agente que implementa (copiar y pegar) |
| [`15_RECOMENDACION_Y_CATALOGO.md`](15_RECOMENDACION_Y_CATALOGO.md) | ⭐ **Personalización real y crecimiento del catálogo** (mixes por usuario, tendencias, recolector) |
| [`14_AUDITORIA_FINAL.md`](14_AUDITORIA_FINAL.md) | ⭐ **Auditoría final** + renombrado a RadioNano + batería de pruebas pendiente |
| [`GUIA_ARRANQUE.md`](GUIA_ARRANQUE.md) | ⭐ **Qué tiene que hacer David**: análisis, arranque, pruebas y PWA en el móvil, paso a paso |
| [`ORDEN_DE_TRABAJO.md`](ORDEN_DE_TRABAJO.md) | ⭐ **Cola de trabajo por bloques** para el agente (A-F, una entrega = un bloque entero) |
| [`RUNBOOK_VERIFICACION.md`](RUNBOOK_VERIFICACION.md) | ⭐ **Vuelta de verificación** (~20 min, la ejecuta David: es lo que desbloquea F3 y F5) |
| [`DECISIONES.md`](DECISIONES.md) | ⭐ **Decisiones cerradas** de David (cuarentena, valence, dónde vive el audio, una BD o dos) |
| [`PROGRESS.md`](PROGRESS.md) | ⭐ **Tablero de progreso** (lo mantiene el agente: qué está hecho y qué no) |
| [`10_FRONTEND_SPEC.md`](10_FRONTEND_SPEC.md) | **F3 · App web (React)**: capa adaptadora, reproductor, pantallas |
| [`11_WORKER_SPEC.md`](11_WORKER_SPEC.md) | **F4 · Personalización, playlists automáticas y worker** (W-01…W-07) |
| [`12_MOBILE_SPEC.md`](12_MOBILE_SPEC.md) | **F5 · App móvil (Flutter)** (MB-01…MB-08) |
| [`13_DEPLOY_SPEC.md`](13_DEPLOY_SPEC.md) | **F6 · Producción**: Alembic, Docker, HTTPS, seguridad, copias (DP-01…DP-08) |
| [`09_IMPLEMENTATION_PLAN.md`](09_IMPLEMENTATION_PLAN.md) | ⭐ **Plan de implementación ejecutable** (handoff para el agente que programa: fases F0-F6, tareas T-01…T-28 con código y criterios de aceptación) |
| [`08_REVIEW.md`](08_REVIEW.md) | ⭐ **Revisión completa / auditoría** (fallos críticos, calidad de datos, API que falta, UI y plan revisado) |
| [`07_CROSS_PLATFORM_BLUEPRINT.md`](07_CROSS_PLATFORM_BLUEPRINT.md) | **Blueprint Web + Móvil** (reutiliza los dos repos estudiados: React web + Flutter móvil, con backend común) |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Plan de arquitectura robusta + usuarios/auth + Cassandra vs Postgres |
| [`PLAYER_DESIGN.md`](PLAYER_DESIGN.md) | Diseño del reproductor (PlaybackService, audio features, roadmap) |
| [`PLAYLISTS_UI_DESIGN.md`](PLAYLISTS_UI_DESIGN.md) | Motor de playlists + UI (versión inicial) |

**Código ya existente** (para referencia del agente):
- `backend/` → API FastAPI (auth, tracks, artists, library, playlists, recommend) + migración desde SQLite.
- `radiov/` → recolector de catálogo (yt-dlp, Deezer, librosa, revisor de metadatos) — la fuente de datos.
- `data/radiov.db` → catálogo SQLite (889 canciones) · `data/backend.db` → BD del backend (migrada).

---

## 🔎 Auditoría: ¿se puede construir la app de reproductor con lo que hay?

### ✅ Lo que YA está (hecho y probado)
| Bloque | Estado |
|---|---|
| **Catálogo** (tracks, artistas, discografías, carátulas/fotos locales, tags/moods, BPM, energía, era, FTS) | ✅ Completo y enriquecido |
| **Recolector** (descarga, revisión de metadatos, perfiles, imágenes) | ✅ Funciona (worker en `radiov/agent.py`) |
| **Backend API** (FastAPI + SQLAlchemy + auth JWT + migración) | ✅ Funciona y es multi-usuario |
| **Endpoints**: auth, tracks (filtros/búsqueda), artists, library (play/like/skip), playlists, recommend (content/daily/radio) | ✅ Funcionando |
| **Recomendación content-based** (perfil de gustos) | ✅ Probada (al gustar flamenco → sugiere flamenco) |
| **Robustez de datos** (índices, FTS, dedup, revisión idempotente) | ✅ |
| **PostgreSQL** | ✅ Preparado (cambia `DATABASE_URL`) |

### ⚠️ Lo que FALTA para la app de reproductor (trabajo del agente)
| Hueco | Qué construir |
|---|---|
| **Frontend / Player UI** | SPA (React) **o** Streamlit: Home, Search, Library, Playlists, Artista, Álbum, **PlayerBar**, cola. |
| **PlaybackService** | Cola, shuffle, repeat, seek, crossfade, gapless, EQ, historial → `record_play`. |
| **Motor de playlists automáticas** | `smart_playlists` (reglas) + playlists `system/mix` + `mixes` precomputados. |
| **Trabajador de actualidad** | `refresh_trends/new_releases/new_artists/rebuild_mixes/prune` (programado). |
| **Más audio-features y similitud** | `danceability/valence/acousticness/loudness` + tabla `similar` (top-K vecinos) + pgvector. |
| **Contenido extra** | Letras (`lyrics`), biografías (Wikipedia/Wikidata), más fuentes (YouTube/Billboard). |
| **Operativa / despliegue** | Docker (API + Postgres + worker + front), HTTPS, migraciones **Alembic**, **tests** (pytest), backup. |

### 🧭 Veredicto
**SÍ se puede construir.** La parte difícil (catálogo + API + auth + recomendación + datos) está hecha y
verificada. Lo que queda es la **capa de presentación/reproducción, la automatización de playlists y
la operativa** — más mecánico una vez que el backend y sus contratos están claros. Los documentos de la
tabla definen **qué y cómo** construir cada pieza.

---

## 🚀 Cómo usar esta documentación (para el agente especializado)
1. Lee [`01_SCHEMA.md`](01_SCHEMA.md) y [`02_API.md`](02_API.md) → entiende el **contrato de datos y API**.
2. Lee [`06_BUILD_GUIDE.md`](06_BUILD_GUIDE.md) → **plan de construcción fase a fase**.
3. Consulta [`03_PERSONALIZATION.md`](03_PERSONALIZATION.md) y [`04_PLAYLISTS_WORKER.md`](04_PLAYLISTS_WORKER.md)
   para los algoritmos y el worker.
4. Consulta [`05_UI.md`](05_UI.md) para la interfaz.
5. Usa el `backend/` existente como base y **no rompas el contrato** (mantén los mismos endpoints/models).

> **Nota legal**: uso personal y respeto a los ToS de YouTube y derechos de autor.
