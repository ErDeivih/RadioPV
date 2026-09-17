# 🚀 RadioPV · Producción: migraciones, Docker, seguridad y copias — FASE F6

> Tareas **DP-01 … DP-08**. Detalle ejecutable de la fase F6 de
> [`09_IMPLEMENTATION_PLAN.md`](09_IMPLEMENTATION_PLAN.md).

---

## DP-01 · La decisión que va PRIMERO: ¿dónde viven los 9,5 GB de audio?

**Ningún documento anterior lo respondía, y condiciona el código de `/stream`.**

| Opción | Cómo | A favor | En contra |
|---|---|---|---|
| **A · API en casa + túnel** ← **recomendada para empezar** | el backend corre en el PC de siempre, expuesto con **Cloudflare Tunnel** o **Tailscale** | coste 0 · el audio no se mueve · HTTPS y certificado resueltos · nada que sincronizar | el PC tiene que estar encendido · la subida de tu fibra es el techo (2-3 oyentes a la vez van sobrados) |
| **B · VPS + audio en almacenamiento de objetos** (R2 / B2 / S3) | `/stream` devuelve un **302 a una URL firmada** | escala · el VPS no necesita disco | coste mensual · subir 9,5 GB · cada canción nueva hay que subirla |
| **C · VPS con disco grande** | todo junto | simple de entender | caro por GB · sincronizar el catálogo a mano |

**Cómo dejar la puerta abierta** — escribir el servicio de audio de forma que cambiar de A a B sea una
función, no una reescritura:

```python
# backend/app/audio.py
from fastapi.responses import FileResponse, RedirectResponse
from .config import STORAGE          # "local" | "s3"
from .paths import resolve_music


def servir_audio(track):
    if STORAGE == "local":
        return FileResponse(resolve_music(track.file_path), media_type="audio/mpeg",
                            headers={"Cache-Control": "private, max-age=3600"})
    return RedirectResponse(url_firmada(track.file_path, segundos=300), status_code=302)
```

`/stream` llama a `servir_audio(tr)` y no sabe nada más. **Hacerlo así desde el principio** aunque hoy
solo exista la opción A.

---

## DP-02 · Alembic (sustituir a `create_all`)

Hoy `main.py` hace `Base.metadata.create_all(bind=engine)`: crea tablas nuevas pero **no modifica las
existentes**, así que cualquier columna añadida después no aparece. Desde F0 ya hay cambios
(`plays.seconds_listened`, `plays.context`, `tracks.rms`, `tracks.gain_db`, y en F4 `similar`, `mixes`,
`smart_playlists`).

```powershell
uv pip install --python .venv\Scripts\python.exe alembic
cd backend
alembic init alembic
```

`alembic/env.py`:

```python
from app.database import Base, DATABASE_URL
from app import models                       # noqa: F401  (registra todas las tablas)
target_metadata = Base.metadata
config.set_main_option("sqlalchemy.url", DATABASE_URL)
```

```powershell
alembic revision --autogenerate -m "esquema inicial"
alembic upgrade head
```

Y en `main.py`, **quitar `create_all` cuando `RADIOPV_ENV=prod`**:

```python
if ENV != "prod":
    Base.metadata.create_all(bind=engine)     # comodidad solo en desarrollo
```

⚠️ Antes de la primera `autogenerate` contra una BD que ya tiene datos: `alembic stamp head` para que
no intente crear lo que ya existe.

---

## DP-03 · Postgres

```powershell
$env:DATABASE_URL = "postgresql+psycopg2://radiopv:clave@localhost:5432/radiopv"
alembic upgrade head
.venv\Scripts\python.exe -m migrate_sqlite       # el catálogo entra por la migración no destructiva
```

Diferencias a vigilar al saltar de SQLite:

- **Sensible a mayúsculas**: `ilike` funciona en ambos, pero `like` no se comporta igual. Revisar
  `tracks.py`.
- **Booleanos reales**: `is_remix`/`explicit` dejan de ser 0/1. El código ya usa `bool()`, pero
  comprobar las consultas escritas a mano.
- **Búsqueda**: aquí es donde Postgres gana. Sustituir el `ILIKE '%q%'` por `pg_trgm` o
  `to_tsvector('spanish', title || ' ' || artist)` con índice GIN. Es el momento de cumplir lo que
  `02_API.md` promete desde el principio ("FTS").
- **`similar` y vectores**: si se llega a features numéricas de verdad, `pgvector` para el vecindario.

---

## DP-04 · Docker

`backend/Dockerfile`:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-backend.txt .
RUN pip install --no-cache-dir -r requirements-backend.txt
COPY backend/ ./backend/
COPY radiov/  ./radiov/
ENV PYTHONPATH=/app/backend
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
```

`docker-compose.yml`:

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: radiopv
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: radiopv
    volumes: [pgdata:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U radiopv"]
      interval: 10s

  api:
    build: { context: ., dockerfile: backend/Dockerfile }
    environment:
      DATABASE_URL: postgresql+psycopg2://radiopv:${DB_PASSWORD}@db:5432/radiopv
      SECRET_KEY: ${SECRET_KEY}
      RADIOPV_ENV: prod
      MUSIC_ROOT: /musica
      MEDIA_ROOT: /media
      ALLOWED_ORIGINS: https://radiopv.tudominio.com
      INVITE_CODE: ${INVITE_CODE}
    volumes:
      - E:/Musica:/musica:ro          # SOLO LECTURA: la app nunca escribe en el catálogo
      - ./data:/media:ro
    depends_on: { db: { condition: service_healthy } }
    ports: ["8000:8000"]

  worker:
    build: { context: ., dockerfile: backend/Dockerfile }
    command: ["python", "-m", "app.workers"]
    environment: *api-env            # las mismas variables que api
    volumes:
      - E:/Musica:/musica            # el worker SÍ escribe (descargas, análisis)
      - ./data:/media
    depends_on: { db: { condition: service_healthy } }

  web:
    build: { context: ./frontend }
    ports: ["8080:80"]

volumes: { pgdata: {} }
```

> **`:ro` en el volumen de la API no es un detalle**: garantiza que un fallo en el backend nunca pueda
> tocar tus 9,5 GB de música. El worker es el único que escribe ahí.

**Comprobación obligatoria tras el primer `docker compose up`**: `MUSIC_ROOT=/musica` significa que
las rutas de la BD tienen que ser **relativas** (T-11). Si `/stream` devuelve 404 dentro de Docker y
funciona fuera, es exactamente eso.

---

## DP-05 · HTTPS

**Caddy** resuelve el certificado solo (`Caddyfile`):

```
radiopv.tudominio.com {
    handle /api/* {
        uri strip_prefix /api
        reverse_proxy api:8000
    }
    handle {
        # SPA: servir el build de React con fallback a /index.html, para que entrar directo
        # a rutas tipo /artist/Bad Bunny no dé 404 (solo el /api/* va al backend).
        root * /srv/web
        try_files {path} /index.html
        file_server
    }
}
```

> **F6 / fallback SPA**: si en vez de Caddy se sirve el build con nginx (`web:80`), el `server`
> de nginx debe llevar `try_files $uri $uri/ /index.html;`. El fallback falta si ves 404 al
> recargar o entrar directo a una ruta del cliente (`/artist/…`, `/genre/…`, `/settings`).

Con **Cloudflare Tunnel** (opción A de DP-01) ni siquiera hace falta abrir puertos en el router:
`cloudflared tunnel --url http://localhost:8000`.

⚠️ Si el audio va por un proxy, subir el tiempo máximo de respuesta y **no comprimir** `audio/mpeg`
(ya está comprimido: gzip solo gasta CPU).

---

## DP-06 · Seguridad antes de abrir a internet

| Punto | Estado hoy | Qué hacer |
|---|---|---|
| `SECRET_KEY` | valor por defecto en el código | T-03: **abortar el arranque** si falta en `prod` |
| Registro | **abierto a cualquiera** | `INVITE_CODE` obligatorio; 400 si no coincide |
| Fuerza bruta en login | sin límite | `slowapi` u otro: 5 intentos / 15 min por IP |
| CORS | `allow_origins=["*"]` | los dominios reales |
| Contraseña | mínimo 8 | mínimo 10 + rechazar las 1000 más comunes |
| Token de streaming | (nuevo) | 30 min, `scope="stream"`, y `get_current_user` **rechaza** ese ámbito |
| `/media` y `/stream` | (nuevo) | siempre desde raíz fija con validación de ruta (T-04) |
| Cabeceras | — | `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` |
| Registro de accesos | — | log de `/auth/login` con IP: si se abre a internet, hay que poder mirar |

---

## DP-07 · Copias de seguridad (hoy no existen)

**El audio se puede volver a descargar. La base de datos no.** Contiene 1114 fichas enriquecidas
(año real, BPM, energía, tags, carátulas, discografías) y **todas las señales de los usuarios**.
Rehacer eso serían días de descargas y análisis.

`scripts/backup.ps1`:

```powershell
$dest = "D:\Backups\RadioPV"          # OTRO disco físico
New-Item -ItemType Directory -Force -Path $dest | Out-Null
$stamp = Get-Date -Format "yyyyMMdd"

# SQLite: usar .backup, NO copiar el fichero en caliente
& .venv\Scripts\python.exe -c "import sqlite3,sys; s=sqlite3.connect('data/radiov.db'); d=sqlite3.connect(sys.argv[1]); s.backup(d); d.close(); s.close()" "$dest\radiov-$stamp.db"

# Postgres
# docker compose exec -T db pg_dump -U radiopv radiopv | gzip > "$dest\radiopv-$stamp.sql.gz"

Get-ChildItem $dest -Filter *.db | Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 14 | Remove-Item -Force      # conservar 14 días
```

Programarlo con el Programador de tareas de Windows, a diario.
**Y probar la restauración una vez.** Una copia que nunca se ha restaurado no es una copia.

---

## DP-08 · Puesta en marcha y vigilancia

- `GET /health` ya existe → ampliarlo: comprobar la BD y que `MUSIC_ROOT` es accesible.
- `healthcheck` en `docker-compose` para `api` y `worker`.
- Logs a fichero con rotación; los errores del worker también en la tabla `events`.
- **Prueba de humo de despliegue** (guardar como `scripts/humo.ps1`): registro → login →
  `/tracks` → `/stream` con `Range` (esperar **206**) → `/media/covers/...` → like → `/recommend`.
  Si alguno falla, el despliegue no está bien, por muy verde que esté todo lo demás.

---

## Nota legal (decidir conscientemente, no por omisión)

Mientras RadioPV sea un catálogo personal en tu propia red, es un asunto privado. En el momento en que
se abre por HTTPS a "familia y amigos" con cuentas de usuario, pasa a ser **distribución** de audio
derivado de YouTube, y eso jurídicamente es otra cosa. Mitigación razonable: **acceso solo por
invitación**, círculo cerrado y pequeño, sin indexar en buscadores, sin ánimo de lucro y sin
publicitarlo. Conviene que esté escrito y decidido, no dado por supuesto.

---

## Criterios de aceptación de F6

- [ ] `docker compose up` levanta `db`, `api`, `worker` y `web` sin intervención.
- [ ] `/stream` funciona **dentro** de Docker (rutas relativas correctas).
- [ ] HTTPS con certificado válido.
- [ ] `alembic upgrade head` en una BD vacía deja el esquema completo.
- [ ] Registro **imposible** sin código de invitación.
- [ ] Copia diaria automática **y una restauración probada**.
- [ ] `scripts/humo.ps1` pasa entero contra el dominio real.
