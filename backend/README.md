# RadioPV · Backend (API online multi-usuario)

Backend en **FastAPI + SQLAlchemy** para convertir RadioPV en una app **online** con **cuentas de
usuario, catálogo y personalización** (estilo Spotify). Por defecto usa SQLite (para desarrollo
local); con `DATABASE_URL` usa **PostgreSQL**.

## Puesta en marcha

```powershell
cd F:\EspacioCodigo\RadioPV
# instalar backend (en el venv ya están); si no:
#   uv pip install --python .venv\Scripts\python.exe -r backend\requirements.txt

# 1) migrar tu SQLite del catálogo (data/radiov.db) a la BD del backend (data/backend.db)
$env:PYTHONPATH="F:\EspacioCodigo\RadioPV\backend"
.venv\Scripts\python.exe -m migrate_sqlite

# 2) arrancar la API
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Prueba: `http://127.0.0.1:8000/health` · docs interactivas: `http://127.0.0.1:8000/docs`

## Usar PostgreSQL (para producción/online)

```powershell
$env:DATABASE_URL = "postgresql://usuario:pass@localhost:5432/radiov"
# (instalar psycopg2: uv pip install psycopg2-binary)
.venv\Scripts\python.exe -m migrate_sqlite     # vuelca el catálogo en Postgres
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

> Detalles de arquitectura y diseño (usuario/auth, personalización, robustez) en
> [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) y [`docs/PLAYER_DESIGN.md`](../docs/PLAYER_DESIGN.md).

## Endpoints

| Método | Ruta | Qué hace |
|---|---|---|
| POST | `/auth/register` | Crear cuenta (email+contraseña) |
| POST | `/auth/login` | Login → token JWT |
| GET  | `/auth/me` | Usuario actual |
| POST | `/auth/logout` | Revoca el token |
| GET  | `/tracks` | Listar/filtrar catálogo (`q, genre, language, year, era, mood, energy, remix, limit, offset`) |
| GET  | `/tracks/{id}` | Detalle de canción |
| GET  | `/artists` | Perfiles de artista (con foto y nº de canciones) |
| GET  | `/artists/{name}/albums` | Discografía |
| POST | `/library/{track}/play` | Registrar reproducción |
| POST | `/library/{track}/like` | Me gusta |
| POST | `/library/{track}/skip` | Saltar |
| GET  | `/library/reactions` | Gustos/saltos del usuario |
| GET/POST | `/playlists` | Listar/crear playlists |
| GET  | `/playlists/{id}/tracks` | Canciones de una playlist |
| POST | `/playlists/{id}/tracks/{track}` | Añadir canción |
| GET  | `/recommend?n=` | Recomendaciones (por perfil de gustos) |
| GET  | `/recommend/daily` | Mix diario |
| GET  | `/recommend/radio?seed_track=` | Radio por similitud |

## Estructura

```
backend/
  app/
    main.py        FastAPI + routers + CORS
    database.py    engine/sesión (DATABASE_URL)
    models.py      modelos SQLAlchemy (usuarios, catálogo, señales, playlists)
    schemas.py     Pydantic (validación)
    security.py    hash bcrypt + JWT + dependencia de usuario
    routers/
      auth.py tracks.py artists.py library.py playlists.py recommend.py
  migrate_sqlite.py   migra el catálogo SQLite → BD del backend (idempotente)
  requirements.txt
```
