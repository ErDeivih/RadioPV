# 🎧 RadioPV

**RadioPV** es una Spotify-like auto-alojada (sin servidores de terceros, sin internet): ingresa
música desde YouTube/yt-dlp y Deezer a un catálogo propio, la sirve con un backend FastAPI y la
reproduces desde una **web React** que además es una **PWA instalable** (esa es la "app" de móvil).

- **Backend** · `backend/` — FastAPI + SQLAlchemy 2.0 + Pydantic v2 + FTS5. Streaming con `Range`,
  tokens por `scope=access|stream`, personalización (perfil con recencia + señales implícitas +
  diversidad), radio por similitud (`similar`), playlists, wrapped, filtro explícito por perfil familiar.
- **Web / PWA** · `frontend/` — React 19 + Vite + antd (hereda de un cliente tipo Spotify, con la capa
  adaptadora `api/adapt.ts`). Cuenta con cola + "Flow" (radio encadenada al agotarse la cola),
  shuffle con separación de artista, repetir, temporizador de apagado, filtro explícito, estadísticas
  y **Media Session** (controles en pantalla de bloqueo/auriculares).
- **Recolector** · `radiov/` — pipeline de ingesta (yt-dlp + Deezer) con puerta de calidad y cuarentena.
- **Móvil** · **La PWA cubre el móvil.** El bloque Flutter (`mobile/`) queda **aplazado** y NO bloquea
  el proyecto (ver `docs/07_CROSS_PLATFORM_BLUEPRINT.md`).

---

## Cómo arrancar

> Entorno: Python 3.12 (el venv está en la **raíz** del repo, no dentro de `backend/`), Node 24 + Yarn.
> Instala dependencias con **`uv`**, no con `pip` (pip se cuelga en este equipo):
> `uv pip install --python .venv\Scripts\python.exe -r requirements-backend.txt`
>
> Variables de entorno reales (las lee `backend/app/config.py`): `RADIOPV_ENV` (`dev`|`prod`),
> **`SECRET_KEY`** (obligatoria si `RADIOPV_ENV=prod`), `ALLOWED_ORIGINS`, `MUSIC_ROOT`,
> `MEDIA_ROOT`, `DATABASE_URL`, `INVITE_CODE`.

### 1. Backend (API)

```powershell
# desde la RAÍZ del repo (F:\EspacioCodigo\RadioPV), no desde backend\
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
# comprobar:  http://127.0.0.1:8000/health   ·   documentación: /docs
```

Datos: `data/backend.db` (BD de backend) y `data/radiov.db` (catálogo del recolector). En producción se
usa `DATABASE_URL`/`MUSIC_ROOT`/`MEDIA_ROOT` (ver `docker-compose.yml`).

### 2. Worker (personalización y mantenimiento)

```powershell
# desde la RAÍZ del repo, en OTRA ventana (es un proceso aparte del API)
$env:PYTHONPATH = "F:\EspacioCodigo\RadioPV\backend"
.venv\Scripts\python.exe -m app.workers
```

APScheduler: sync de catálogo, `rebuild_similar` (radio), `rebuild_mixes`, `refresh_trends`,
`limpiar_catalogo`, `verificar_ficheros`, `prune`.

### 3. Frontend (web)

```bash
cd frontend
yarn install
echo "VITE_API_URL=http://127.0.0.1:8000" > .env   # IP de Tailscale en producción
yarn dev                                            # http://localhost:5173
```

> ⚠️ **Ojo con el `.env` en PowerShell**: si lo escribes con `echo … > .env` o `Set-Content`
> a secas, PowerShell añade un **BOM** y **vite no lee la variable** (falla en silencio). Usa
> `Set-Content -Path .env -Value "VITE_API_URL=http://127.0.0.1:8000" -Encoding utf8NoBOM`.

---

## 📲 Instalar la PWA en el móvil

Con la web servida y accesible (p. ej. por la IP de tu **Tailnet**, opción recomendada):

1. Abre la URL en **Chrome (Android)** → menú ⋮ → **"Añadir a pantalla de inicio"**.
2. En **Safari (iOS)** → **Compartir** → **"Añadir a inicio"**.

Los iconos de 192/512 (`maskable`) y el `manifest.json` (`display: standalone`, `start_url: '/'`,
`theme/background: #101014`) están configurados, y el **service worker** cachea la carcasa (nunca el
audio ni la API). La **Media Session** da los controles de reproducción en pantalla de bloqueo y
auriculares.

---

## 📚 Documentación

Todo el diseño y el estado viven en [`docs/`](docs/):

| Doc | Qué es |
|---|---|
| [`ORDEN_DE_TRABAJO.md`](docs/ORDEN_DE_TRABAJO.md) | Cola de trabajo por bloques (A–F) |
| [`PROGRESS.md`](docs/PROGRESS.md) | **Estado real del proyecto** (tablero + diario) |
| [`02_API.md`](docs/02_API.md) · [`01_SCHEMA`](docs/01_SCHEMA.md) | API y esquema |
| [`03_PERSONALIZATION.md`](docs/03_PERSONALIZATION.md) · [`11_WORKER_SPEC.md`](docs/11_WORKER_SPEC.md) | Personalización y worker |
| [`10_FRONTEND_SPEC.md`](docs/10_FRONTEND_SPEC.md) · [`05_UI.md`](docs/05_UI.md) | Web y UI |
| [`12_MOBILE_SPEC.md`](docs/12_MOBILE_SPEC.md) · [`07_CROSS_PLATFORM_BLUEPRINT.md`](docs/07_CROSS_PLATFORM_BLUEPRINT.md) | Móvil (aplazado) y blueprint |
| [`13_DEPLOY_SPEC.md`](docs/13_DEPLOY_SPEC.md) · [`06_BUILD_GUIDE.md`](docs/06_BUILD_GUIDE.md) | Despliegue y construcción |
| [`RUNBOOK_VERIFICACION.md`](docs/RUNBOOK_VERIFICACION.md) · [`DECISIONES.md`](docs/DECISIONES.md) | Verificación y decisiones |

---

## ⚠️ Pendientes conocidos (datos)

- **T-24** · pasada de análisis de audio para `gain_db` y `energy`.
- **T-27** · reclasificación de género (hay ~144 temas en `other` y algún género mal etiquetado).
