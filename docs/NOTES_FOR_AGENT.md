# 📌 RadioPV · Notas de alto valor para el agente (Claude)

> Lo **más importante y no obvio** para trabajar en este proyecto sin pisar cables. Complementa a
> `PROJECT_BRIEF.md` (contexto completo) y `docs/00_INDEX.md` (índice).

---

## 1. Qué es (30 segundos)
RadioPV = **"Spotify propio" desde YouTube**: descarga y cataloga música, y vamos a montar una app
**web + móvil** con **backend común** y **cuentas de usuario**, reutilizando dos repos ya descargados
en `vendor/`.

## 2. Las 3 piezas que NO hay que confundir
| Pieza | Carpeta | Base de datos | Propósito |
|---|---|---|---|
| **Recolector** | `radiov/` | `data/radiov.db` (SQLite) | Descarga y cataloga (worker). Frecuenta `E:\Musica\`. |
| **Backend (API)** | `backend/` | `data/backend.db` (SQLite) o `DATABASE_URL` (Postgres) | App online: auth, catálogo, library, playlists, recommend. |
| **Web local antigua** | `app_streamlit_legacy.py` | `data/radiov.db` | UI Streamlit **legacy**. El futuro es el backend + UI nueva. |

> ⚠️ El catálogo (música) está en `E:\Musica\`; las BD (metadatos) están en `data\`. El **backend** no
> necesita los MP3 salvo que sirva `/stream`. No mezclar `radiov.db` con `backend.db`.

## 3. Entorno y "gotchas" (lo que suele romper)
- **`pip` se cuelga** en este equipo (proxy/sandbox) → usar **`uv pip install --python .venv\Scripts\python.exe ...`**.
- **`bcrypt` debe ser `==4.0.1`** (passlib 1.7.4 no es compatible con bcrypt 5.x). Si se actualiza, se rompe login.
- **Sandbox**: solo escribe dentro de `F:\EspacioCodigo\RadioPV`; la música va a `E:\Musica`, así que la app
  se lanza con **acceso ampliado** (o los MP3 no se escriben). El **backend con SQLite/Postgres** no necesita acceso a `E:`.
- **`git clone` falla** por credenciales (schannel). Para re-bajar los repos usar **tarball**:
  `https://github.com/francoborrelli/spotify-react-web-client/archive/refs/heads/main.tar.gz` ·
  `https://github.com/Ansh-Rathod/Flutter-Musive-app/archive/refs/heads/master.tar.gz`.
- **FFmpeg** presente; **Node 24 + npm + git** presentes. Python 3.12 en `.venv`.

## 4. Cómo arrancar el backend (para probar)
```powershell
# migrar el catálogo SQLite → BD del backend (idempotente)
$env:PYTHONPATH="F:\EspacioCodigo\RadioPV\backend"
.venv\Scripts\python.exe -m migrate_sqlite
# arrancar API
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
# docs: http://127.0.0.1:8000/docs  · salud: /health
```
Postgres: `$env:DATABASE_URL="postgresql://user:pass@host/db"` (+`psycopg2-binary`).

## 5. Contratos CONGELADOS (extender, no romper)
- **Esquema**: `docs/01_SCHEMA.md`. Añadir columnas/tablas está bien; cambiar significado no.
- **API**: `docs/02_API.md` + `backend/app/schemas.py`. Mantener request/response.
- Los endpoints de recomendación usan `_profile/_score` en `backend/app/routers/recommend.py`.

## 6. Decisiones ya cerradas (no reabrir)
- **BD principal**: **Postgres** (Cassandra solo para eventos a escala, cuando el volumen lo pida).
- **Recomendación**: content-based (perfil de gustos) + **radio(seed)** + **mix diario**; colaborativa (ALS) si hay usuarios.
- **UI**: **reutilizar** `vendor/spotify-web` (web React) y `vendor/Flutter-Musive-app` (móvil Flutter), **adaptando** la capa de datos/auth/reproducción. Ver `docs/07_CROSS_PLATFORM_BLUEPRINT.md`.
- **La app reproduce; el recolector descarga; el worker crea playlists.**

## 7. Estado (hecho vs pendiente)
- **Hecho**: recolector completo, catálogo 889 canciones (40+ campos, FTS, fotos/carátulas, discografías), backend FastAPI funcional (auth+catálogo+library+playlists+recommend), docs.
- **Pendiente (FASE 1-5)**: `/stream/{id}` (con `Range`) + `/media/*` + CORS/JWT móvil → web React adaptada → móvil Flutter adaptada → motor de playlists + worker → despliegue (Docker+HTTPS+Alembic+tests).

## 8. Rendimiento / buenas prácticas
- El **recuadro editable de Streamlit** era lento → se usó una tabla ligera; **no reintroducir data_editor** con cientos de filas.
- Consultas **en SQL** (no filtrar en Python) con índices/FTS; **caché** de agregados (stats, perfil, mixes).
- Trabajos pesados (descarga, BPM, revisión) en **worker**; no bloquear la API.

## 9. Sugerencia de siguiente paso

> 🚧 **Si vas a implementar, tu documento es [`09_IMPLEMENTATION_PLAN.md`](09_IMPLEMENTATION_PLAN.md)**
> (plan ejecutable, fases F0-F6, tareas con código y criterios de aceptación), y el porqué de cada
> tarea está en [`08_REVIEW.md`](08_REVIEW.md). **Empieza por la FASE F0: es bloqueante.**

- Empezar por **FASE 1** (backend: `/stream/{id}` con Range + `/media/*` + CORS + soporte móvil),
  porque desbloquea web y móvil. Después adaptar React y Flutter.

> **Legal**: uso personal, respeta ToS de YouTube y derechos de autor. Los repos de terceros se usan
> sin ánimo comercial (revisar su licencia).
