# 🚧 RadioPV · Plan de implementación ejecutable (handoff para un agente)

> **Para quién es este documento.** Para un agente de IA (DeepSeek u otro) con acceso de escritura a
> `F:\EspacioCodigo\RadioPV` que va a **implementar** los arreglos y las fases. Está escrito para
> ejecutarse **de arriba abajo, sin saltarse el orden**, y es **autocontenido**: no hace falta leer
> nada más para empezar, aunque conviene tener a mano `docs/08_REVIEW.md` (por qué de cada cosa) y
> `docs/02_API.md` (contrato).
>
> **Mapa de documentos**: este plan cubre **F0-F2 al detalle** (tareas `T-01 … T-23`) y resume el
> resto. Las fases finales tienen su propio documento, con el mismo nivel de detalle y código:
> [`10_FRONTEND_SPEC.md`](10_FRONTEND_SPEC.md) (web) · [`11_WORKER_SPEC.md`](11_WORKER_SPEC.md)
> (`W-01…W-07`) · [`12_MOBILE_SPEC.md`](12_MOBILE_SPEC.md) (`MB-01…MB-08`) ·
> [`13_DEPLOY_SPEC.md`](13_DEPLOY_SPEC.md) (`DP-01…DP-08`). El estado de cada tarea se lleva en
> [`PROGRESS.md`](PROGRESS.md).
>
> Origen de las tareas: auditoría del **2026-08-28** sobre el código y los datos reales
> (`docs/08_REVIEW.md`). Los identificadores **C1-C5** y **I1-I10** de este plan son los de esa auditoría.

---

## 0. Reglas de trabajo (leer antes de escribir una sola línea)

1. **Orden**: las fases se hacen en orden. `F0` es prerrequisito de todo lo demás. Dentro de una fase,
   las tareas se pueden reordenar salvo que digan lo contrario.
2. **Copia de seguridad antes de cada fase**:
   ```powershell
   $stamp = Get-Date -Format "yyyyMMdd-HHmm"
   Copy-Item data\radiov.db  "data\backup\radiov-$stamp.db"  -Force
   Copy-Item data\backend.db "data\backend-$stamp.db" -Force
   ```
   (crear `data\backup\` si no existe). **Ninguna tarea que toque datos se ejecuta sin backup previo.**
3. **Cambios mínimos**. No reescribir módulos enteros, no "aprovechar para refactorizar", no cambiar
   estilo ni renombrar. Cada tarea toca los ficheros que dice y nada más.
4. **Nunca borrar señales de usuario** (`users`, `reactions`, `plays`, `playlists`, `playlist_tracks`).
   Ni en migraciones, ni en limpiezas, ni en pruebas contra `data/backend.db`.
5. **`tracks.id` es inmutable para siempre.** La clave natural para deduplicar es `deezer_id`.
   Si una tarea implicase renumerar ids, está mal planteada: parar y avisar.
6. **No tocar `vendor/`** hasta la fase F3 (y entonces se copia a `frontend/`, no se edita en su sitio).
7. **No lanzar el recolector** (`run_agent.py`, `radiov.agent`) sin pedir permiso: descarga música,
   consume disco y red.
8. **No borrar ficheros de `E:\Musica`** sin listarlos primero, enseñar la lista y esperar confirmación.
9. **Si un cambio altera el contrato de la API**, actualizar `docs/02_API.md` **en el mismo commit**.
10. **Tras cada tarea**: `pytest -q` en verde y el servidor arranca. Si no, no se pasa a la siguiente.
11. Comentarios y mensajes de commit **en español**, como el resto del repo.

### Entorno (este equipo)

```powershell
# instalar dependencias  (pip se cuelga en este equipo: usar uv)
uv pip install --python .venv\Scripts\python.exe -r requirements-backend.txt

# arrancar la API
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
# docs: http://127.0.0.1:8000/docs   salud: /health

# tests
.venv\Scripts\python.exe -m pytest -q
```

- Python 3.12 en `.venv` · FFmpeg, Node 24 y git presentes.
- **`bcrypt` debe quedarse en `4.0.1`** (passlib 1.7.4 no funciona con bcrypt 5.x → login roto).
- Versiones instaladas relevantes: `fastapi 0.141.1`, `starlette 1.6.0`, `sqlalchemy 2.0.52`,
  `pydantic 2.13.4`, `python-jose 3.5.0`.
- `git clone` falla por credenciales: bajar repos como **tarball**.

### Estado de partida (verificado el 2026-08-28)

| | |
|---|---|
| `data/radiov.db` | 1114 canciones (catálogo del recolector) |
| `data/backend.db` | 889 canciones (**desincronizado**) |
| Audio | ~9,53 GB en `E:\Musica` |
| Tests | **ninguno** |
| Alembic | **no existe** |

---

# FASE F0 · Cimientos

**Objetivo**: que nada de lo que se construya encima se pierda o haya que rehacerlo.
**Sin esta fase no se empieza la F1.** Tiempo estimado: medio día.

---

## T-01 · Arreglar `GET /artists` (hoy devuelve 500) — **C2**

**Problema**: `db.execute("UPDATE ...")` con una cadena. SQLAlchemy 2.0 lo rechaza:
`ArgumentError: Textual SQL expression should be explicitly declared as text(...)`. Verificado contra
la 2.0.52 instalada. Además ejecuta un `UPDATE` de 365×1114 filas **en cada GET**.

**Ficheros**: `backend/app/routers/artists.py`, **nuevo** `backend/app/maintenance.py`.

`backend/app/maintenance.py` (nuevo):

```python
"""Tareas de mantenimiento del catálogo. Las llama la migración y el worker, NUNCA un endpoint."""
from sqlalchemy import text
from sqlalchemy.orm import Session


def recount_artist_tracks(db: Session) -> int:
    """Recalcula artists.track_count. Devuelve el nº de artistas actualizados."""
    res = db.execute(text(
        "UPDATE artists SET track_count = ("
        "  SELECT COUNT(*) FROM tracks t"
        "  WHERE lower(t.artist) = lower(artists.name) AND t.status = 'descargada')"
    ))
    db.commit()
    return res.rowcount or 0
```

`backend/app/routers/artists.py` — sustituir el cuerpo de `list_artists`:

```python
@router.get("", response_model=list[schemas.ArtistOut])
def list_artists(limit: int = Query(200, le=1000), offset: int = 0,
                 db: Session = Depends(get_db)):
    # NO recalcular aquí: lo hace maintenance.recount_artist_tracks() desde la migración/worker.
    return (db.query(models.Artist)
            .order_by(models.Artist.track_count.desc())
            .offset(offset).limit(limit).all())
```
(añadir `Query` al import de fastapi.)

**Verificación**: `curl http://127.0.0.1:8000/artists?limit=5` → 200 con 5 artistas.
**Hecho cuando**: responde 200 y no escribe en la BD.

---

## T-02 · Dependencias del backend reproducibles

**Problema**: `requirements.txt` solo tiene las del recolector. Nadie puede levantar el backend.

**Fichero**: **nuevo** `requirements-backend.txt`:

```
fastapi>=0.115
uvicorn[standard]>=0.30
sqlalchemy>=2.0
pydantic>=2.7
email-validator>=2.1
passlib[bcrypt]==1.7.4
bcrypt==4.0.1
python-jose[cryptography]>=3.3
python-multipart>=0.0.9
psycopg2-binary>=2.9   ; solo para Postgres
pytest>=8.0
httpx>=0.27            ; TestClient
```

> ⚠️ `bcrypt==4.0.1` es un **pin duro**, no un mínimo. No subirlo.

**Hecho cuando**: `uv pip install --python .venv\Scripts\python.exe -r requirements-backend.txt` termina sin error.

---

## T-03 · Configuración central y `SECRET_KEY` obligatoria en producción — **I9**

**Problema**: `SECRET_KEY = os.environ.get("SECRET_KEY", "cambia-esta-clave")`. Si eso llega a
producción, cualquiera se firma un token de administrador.

**Fichero**: **nuevo** `backend/app/config.py`:

```python
"""Configuración central del backend. Todo lo que dependa del entorno se lee aquí."""
import os
from pathlib import Path

ENV = os.environ.get("RADIOPV_ENV", "dev").lower()        # dev | prod

_DEV_SECRET = "solo-para-desarrollo-no-usar-en-produccion"
SECRET_KEY = os.environ.get("SECRET_KEY") or (_DEV_SECRET if ENV == "dev" else "")
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY es obligatoria con RADIOPV_ENV=prod. "
        "Genérala con: python -c \"import secrets;print(secrets.token_urlsafe(48))\""
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
STREAM_TOKEN_EXPIRE_MINUTES = int(os.environ.get("STREAM_TOKEN_EXPIRE_MINUTES", "30"))

_PROJECT_ROOT = Path(__file__).resolve().parents[2]        # F:\EspacioCodigo\RadioPV

# Raíces de ficheros. En Docker/Linux se sobrescriben por variable de entorno.
MUSIC_ROOT = Path(os.environ.get("MUSIC_ROOT", r"E:\Musica"))
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", str(_PROJECT_ROOT / "data")))

ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()]

# Registro solo por invitación (vacío = registro abierto, solo aceptable en dev)
INVITE_CODE = os.environ.get("INVITE_CODE", "")
```

`backend/app/security.py` — quitar sus constantes y usar las del módulo:

```python
from .config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
```

`backend/app/main.py` — CORS desde configuración:

```python
from .config import ALLOWED_ORIGINS
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS,
                   allow_methods=["*"], allow_headers=["*"])
```

**Hecho cuando**: con `RADIOPV_ENV=prod` y sin `SECRET_KEY`, el arranque **falla** con el mensaje claro.

---

## T-04 · Resolución de rutas: `MUSIC_ROOT` / `MEDIA_ROOT` — **I1**

**Problema**: la BD guarda rutas absolutas de Windows (`E:\Musica\catalogada\...`,
`F:\EspacioCodigo\RadioPV\data\covers\...`). En Docker o Linux no existen.

**Estrategia**: **no romper nada ahora**. Se añade un resolvedor que acepta las dos formas (absoluta
heredada y relativa nueva). Cuando T-11 normalice la BD, el mismo código sigue funcionando.

**Fichero**: **nuevo** `backend/app/paths.py`:

```python
"""Traduce lo que hay guardado en la BD a una ruta real, sea absoluta (heredada) o relativa (nueva)."""
from pathlib import Path, PureWindowsPath
from .config import MUSIC_ROOT, MEDIA_ROOT

_ANCLAS_MUSICA = ("catalogada", "descargas", "auriculares")


def _relativa(guardado: str, anclas: tuple[str, ...]) -> Path:
    p = PureWindowsPath(guardado)
    partes = list(p.parts)
    if p.drive or guardado.startswith(("/", "\\")):       # heredada: recortar por el ancla
        for a in anclas:
            if a in partes:
                return Path(*partes[partes.index(a):])
        return Path(p.name)                                # último recurso: el nombre del fichero
    return Path(*partes)                                   # ya era relativa


def _dentro_de(raiz: Path, destino: Path) -> Path:
    """Evita path traversal: el resultado tiene que colgar de la raíz."""
    raiz_r, destino_r = raiz.resolve(), destino.resolve()
    if raiz_r != destino_r and raiz_r not in destino_r.parents:
        raise PermissionError(f"Ruta fuera de {raiz_r}: {destino_r}")
    return destino_r


def resolve_music(guardado: str | None) -> Path:
    if not guardado:
        raise FileNotFoundError("La canción no tiene file_path")
    return _dentro_de(MUSIC_ROOT, MUSIC_ROOT / _relativa(guardado, _ANCLAS_MUSICA))


def media_filename(guardado: str | None) -> str | None:
    """Devuelve solo el nombre del fichero de una carátula/foto ('693008911.jpg')."""
    return PureWindowsPath(guardado).name if guardado else None


def resolve_media(sub: str, guardado: str | None) -> Path:
    """sub = 'covers' | 'artists'"""
    nombre = media_filename(guardado)
    if not nombre:
        raise FileNotFoundError("Sin imagen")
    return _dentro_de(MEDIA_ROOT / sub, MEDIA_ROOT / sub / nombre)
```

**Test obligatorio** (`backend/tests/test_paths.py`): comprobar que
`resolve_music(r"E:\Musica\catalogada\A\B\x.mp3")` y `resolve_music(r"catalogada\A\B\x.mp3")` dan lo
mismo, y que `resolve_music(r"E:\otra\cosa\..\..\Windows\x.mp3")` lanza `PermissionError`.

---

## T-05 · Migración no destructiva por `deezer_id` — **C1 (la tarea más importante del plan)**

**Problema actual**: `backend/migrate_sqlite.py` hace `.delete()` sobre `PlaylistTrack`, `Reaction`,
`Play`, `Track`, `Artist`, `ArtistAlbum`. Consecuencias: se borran los me-gusta, las reproducciones y
el contenido de las playlists de todos los usuarios, y **los `tracks.id` se renumeran desde 1**, con
lo que todo lo guardado por `track_id` pasa a apuntar a otra canción.

**Sustituir la función `migrate()` completa por esto** (el resto del fichero se conserva):

```python
def migrate() -> None:
    """Sincroniza el catálogo de radiov.db → BD del backend. NO destructivo, idempotente.

    - Empareja por deezer_id; si no hay, por (artista, título) en minúsculas.
    - Inserta lo nuevo, actualiza lo existente y marca 'retirada' lo que ya no está en origen.
    - NUNCA toca users / reactions / plays / playlists / playlist_tracks.
    - tracks.id NUNCA cambia.
    """
    from app.maintenance import recount_artist_tracks

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    con = sqlite3.connect(SRC)
    con.row_factory = sqlite3.Row

    # --- índices de lo que ya hay en destino ---
    por_deezer: dict[str, models.Track] = {}
    por_clave: dict[tuple[str, str], models.Track] = {}
    for t in db.query(models.Track).all():
        if t.deezer_id:
            por_deezer[str(t.deezer_id)] = t
        por_clave[((t.artist or "").lower(), (t.title or "").lower())] = t

    CAMPOS = ("title artist album release_date year genre language bpm energy valence tags era "
              "file_path cover_url cover_path artist_image_url artist_image_path album_id artist_id "
              "duration rank source status").split()

    nuevos = actualizados = 0
    vistos: set[int] = set()

    for row in con.execute("SELECT * FROM tracks"):
        d = dict(row)
        did = str(d["deezer_id"]) if d.get("deezer_id") else None
        clave = ((d.get("artist") or "").lower(), (d.get("title") or "").lower())
        destino = por_deezer.get(did) if did else None
        if destino is None:
            destino = por_clave.get(clave)

        if destino is None:                                   # ---- alta ----
            destino = models.Track(deezer_id=did)
            db.add(destino)
            nuevos += 1
        else:
            actualizados += 1

        for c in CAMPOS:
            if c in d:
                setattr(destino, c, d[c])
        destino.is_remix = bool(d.get("is_remix"))
        destino.explicit = bool(d.get("explicit"))
        destino.status = d.get("status") or "descargada"
        if did:
            destino.deezer_id = did

        db.flush()                                            # asigna id sin cerrar la transacción
        vistos.add(destino.id)
        if did:
            por_deezer[did] = destino
        por_clave[clave] = destino

    db.commit()

    # --- lo que ya no está en origen se RETIRA, no se borra (conserva likes e historial) ---
    retiradas = 0
    for t in db.query(models.Track).filter(models.Track.status == "descargada").all():
        if t.id not in vistos:
            t.status = "retirada"
            retiradas += 1
    db.commit()

    # --- artistas (upsert por nombre) ---
    for row in con.execute("SELECT * FROM artists"):
        d = dict(row)
        a = db.query(models.Artist).filter_by(name=d["name"]).first()
        if a is None:
            a = models.Artist(name=d["name"])
            db.add(a)
        a.deezer_id = str(d["deezer_id"]) if d.get("deezer_id") else None
        a.image_url, a.image_path = d.get("image_url"), d.get("image_path")
        a.nb_fan, a.nb_album = d.get("nb_fan"), d.get("nb_album")
        a.genre, a.language = d.get("genre"), d.get("language")
    db.commit()

    # --- discografía (upsert por artista+album_id, si no por artista+título+año) ---
    existentes = {(x.artist_name, x.album_id or "", x.title or "", x.year or 0)
                  for x in db.query(models.ArtistAlbum).all()}
    for row in con.execute("SELECT * FROM artist_albums"):
        d = dict(row)
        k = (d["artist_name"], str(d["album_id"]) if d.get("album_id") else "",
             d.get("title") or "", d.get("year") or 0)
        if k in existentes:
            continue
        existentes.add(k)
        db.add(models.ArtistAlbum(artist_name=d["artist_name"], artist_id=d.get("artist_id"),
                                  album_id=str(d["album_id"]) if d.get("album_id") else None,
                                  title=d.get("title"), year=d.get("year"),
                                  cover_url=d.get("cover_url")))
    db.commit()

    recount_artist_tracks(db)
    con.close()
    print(f"[OK] nuevas={nuevos} actualizadas={actualizados} retiradas={retiradas} "
          f"| total={db.query(models.Track).count()}")
    db.close()
```

**Verificación (obligatoria, en este orden):**

1. Backup de `data/backend.db`.
2. Anotar antes: `SELECT COUNT(*) FROM reactions;` (hoy 5) y `SELECT id,title FROM tracks LIMIT 3;`.
3. Ejecutar la migración **dos veces seguidas**.
4. Comprobar: `reactions` sigue con las mismas filas · los 3 primeros `id`/`title` son **idénticos** ·
   `tracks` ≈ 1114 · la segunda ejecución dice `nuevas=0`.

**Hecho cuando**: los 4 puntos se cumplen. Si algún `id` cambió, **revertir con el backup**.

---

## T-06 · `UNIQUE(deezer_id)` en el catálogo de origen

**Problema**: `radiov.db` permite `deezer_id` duplicados (hay 2 grupos). El `UNIQUE` solo existe en el
backend, así que el duplicado se detecta tarde.

**Pasos**: (1) script que liste los duplicados y conserve la fila con `match_score` más alto (o la más
antigua si empatan), moviendo la otra a `blacklist`; (2) `CREATE UNIQUE INDEX IF NOT EXISTS
ux_tracks_deezer ON tracks(deezer_id) WHERE deezer_id IS NOT NULL;` en `radiov/db.py`, junto al resto
de índices; (3) añadir el índice al arranque del recolector.

---

## T-07 · Alinear `/library` con `02_API.md` (body JSON) — **C5**

**Problema**: el documento promete body JSON, el código lee query params. Los clientes se escribirán
contra el documento.

`backend/app/schemas.py` — añadir:

```python
class PlayIn(BaseModel):
    source: str = "player"
    completed: int = 0
    seconds_listened: float | None = None
    context: str | None = None          # "playlist:12" | "radio:88" | "search" | "daily"


class LikeIn(BaseModel):
    liked: bool = True


class SkipIn(BaseModel):
    skipped: bool = True
```

`backend/app/routers/library.py` — firmas nuevas (el cuerpo apenas cambia):

```python
@router.post("/{track_id}/play")
def record_play(track_id: int, data: schemas.PlayIn, ...):
    p = models.Play(user_id=user.id, track_id=track_id, source=data.source,
                    completed=data.completed, seconds_listened=data.seconds_listened,
                    context=data.context)

@router.post("/{track_id}/like")
def like(track_id: int, data: schemas.LikeIn, ...):   # usa data.liked

@router.post("/{track_id}/skip")
def skip(track_id: int, data: schemas.SkipIn, ...):   # usa data.skipped
```

Corregir también el patrón "crear fila vacía y commit, luego asignar y commit" → asignar antes del
primer `commit()`.

---

## T-08 · `seconds_listened` y `context` en `plays` — **I3**

`docs/03_PERSONALIZATION.md` pondera por "play completo / 50 % / skip al 30 %", y el modelo solo tiene
`completed`. Sin los segundos, la mitad de esa tabla de pesos no se puede calcular.

`backend/app/models.py`, clase `Play`:

```python
    seconds_listened = Column(Float)
    context = Column(String(40))        # playlist:12 | radio:88 | daily | search | artist
```

Como todavía se usa `create_all`, añadir las columnas a mano una vez:

```sql
ALTER TABLE plays ADD COLUMN seconds_listened FLOAT;
ALTER TABLE plays ADD COLUMN context VARCHAR(40);
```

Actualizar `docs/01_SCHEMA.md`.

---

## T-09 · `?energy=` debe devolver 422, no 500 — **I8**

`{"Baja":…}[energy]` lanza `KeyError` con cualquier otro valor (`"alta"` en minúscula incluido).

`backend/app/routers/tracks.py`:

```python
from enum import Enum

class Energia(str, Enum):
    baja = "Baja"
    media = "Media"
    alta = "Alta"

# en la firma:  energy: Optional[Energia] = None
# en el cuerpo: lo, hi = {"Baja": (0, .3), "Media": (.3, .55), "Alta": (.55, 1.01)}[energy.value]
```

Arreglar de paso: `remix` (hoy `if remix:` ignora `False` → usar `if remix is not None:`) y que
`GET /tracks/{id}` no devuelva canciones con `status != 'descargada'`.

---

## T-10 · Tests de humo (sin esto, "contrato congelado" no significa nada)

**Ficheros**: `backend/tests/__init__.py`, `backend/tests/conftest.py`, `backend/tests/test_smoke.py`,
`backend/tests/test_paths.py`, `pytest.ini`.

`conftest.py` — BD temporal, **nunca** la de verdad:

```python
import os, tempfile, pytest
os.environ["DATABASE_URL"] = "sqlite:///" + tempfile.mkstemp(suffix=".db")[1].replace("\\", "/")
os.environ.setdefault("RADIOPV_ENV", "dev")

from fastapi.testclient import TestClient          # noqa: E402
from app.main import app                            # noqa: E402


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


@pytest.fixture(scope="session")
def token(client):
    r = client.post("/auth/register", json={"email": "t@t.com", "password": "clave-larga-1",
                                            "display_name": "T"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]
```

`test_smoke.py` — mínimo exigible:

```python
def test_health(client):
    assert client.get("/health").json()["status"] == "ok"

def test_login_y_me(client, token):
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["email"] == "t@t.com"

def test_tracks_lista(client):
    assert client.get("/tracks?limit=5").status_code == 200

def test_artists_no_revienta(client):     # regresión de C2
    assert client.get("/artists?limit=5").status_code == 200

def test_energy_invalida_es_422(client):  # regresión de I8
    assert client.get("/tracks?energy=alta").status_code == 422

def test_like_con_body_json(client, token):   # regresión de C5
    h = {"Authorization": f"Bearer {token}"}
    assert client.post("/library/1/like", json={"liked": True}, headers=h).status_code in (200, 404)
```

`pytest.ini`:

```ini
[pytest]
pythonpath = backend
testpaths = backend/tests
```

**Hecho cuando**: `pytest -q` en verde. **A partir de aquí, ninguna tarea se cierra con tests en rojo.**

### ✅ Criterio de salida de F0
`pytest` verde · `/artists` responde 200 · la migración es idempotente y no borra señales ·
`RADIOPV_ENV=prod` sin `SECRET_KEY` no arranca · `requirements-backend.txt` instala del tirón.

---

# FASE F1 · Reproducción (lo que desbloquea web y móvil)

**Objetivo**: que una canción del catálogo se pueda reproducir desde un navegador y desde el móvil,
con seek, y que la UI tenga los endpoints que necesita.

---

## T-11 · Normalizar las rutas de la BD a relativas — **I1** (hacer *después* de T-04)

**Script**: `scripts/normalizar_rutas.py` (crear carpeta `scripts/`). Con `--dry-run` por defecto y
`--apply` para escribir. Actúa sobre `data/radiov.db` **y** `data/backend.db`.

Reglas de conversión:

| columna | de | a |
|---|---|---|
| `tracks.file_path` | `E:\Musica\catalogada\A\[2025] X\y.mp3` | `catalogada\A\[2025] X\y.mp3` |
| `tracks.cover_path` | `F:\...\data\covers\693008911.jpg` | `covers\693008911.jpg` |
| `artists.image_path` | `F:\...\data\artists\123.jpg` | `artists\123.jpg` |

El script **no** mueve ni renombra ficheros; solo reescribe cadenas. Debe imprimir cuántas filas
cambiaría y una muestra de 5 antes/después.

**Además**, para que el recolector siga generando rutas relativas de aquí en adelante: en
`radiov/catalog.py`, donde se hace `db.update_track(..., file_path=str(dest))` /
`cover_path=str(dest)`, guardar `str(dest.relative_to(BASE_MUSIC))` y `str(dest.relative_to(DATA_DIR))`
respectivamente. `radiov/config.py` ya define `BASE_MUSIC`, `CATALOG_DIR`, `COVERS_DIR` y
`ARTIST_IMAGES_DIR`: usarlos, no rutas literales.

> Como `backend/app/paths.py` acepta las dos formas, el sistema funciona **antes, durante y después**
> de esta tarea. Por eso T-04 va primero.

---

## T-12 · Token de streaming — **I2**

**El problema de fondo**: `<audio src="...">` **no puede enviar la cabecera `Authorization`**. Por eso
`/stream` necesita autenticarse por la URL.

**Decisión tomada**: un **token de streaming corto y con ámbito propio** (`scope="stream"`), válido
30 minutos para cualquier canción de ese usuario. Un solo token por sesión de escucha, no uno por
canción (menos viajes de ida y vuelta).

`backend/app/security.py` — añadir el ámbito al token normal y crear el de streaming:

```python
from .config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, STREAM_TOKEN_EXPIRE_MINUTES


def create_access_token(user_id: int, token_version: int) -> str:
    payload = {"sub": str(user_id), "ver": token_version, "scope": "access",
               "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_stream_token(user_id: int) -> str:
    payload = {"sub": str(user_id), "scope": "stream",
               "exp": datetime.utcnow() + timedelta(minutes=STREAM_TOKEN_EXPIRE_MINUTES)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_stream_token(t: str) -> int:
    try:
        payload = jwt.decode(t, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("scope") != "stream":
            raise JWTError("ámbito incorrecto")
        return int(payload["sub"])
    except (JWTError, ValueError, KeyError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token de streaming inválido o caducado")
```

⚠️ **En `get_current_user`, rechazar los tokens que no sean `scope == "access"`** (tolerando los
antiguos sin `scope` durante la transición). Si no, un token de streaming filtrado en un log o en el
historial del navegador serviría como sesión completa.

`backend/app/routers/auth.py` — nuevo endpoint:

```python
@router.post("/stream-token")
def stream_token(current: models.User = Depends(get_current_user)):
    return {"token": create_stream_token(current.id),
            "expires_in": STREAM_TOKEN_EXPIRE_MINUTES * 60}
```

---

## T-13 · `GET /stream/{track_id}` — **el endpoint que desbloquea todo**

> **No implementar el manejo de `Range` a mano.** Comprobado: `starlette 1.6.0` (instalado) ya emite
> `206`, `Content-Range`, `Accept-Ranges` y `416` en `FileResponse`. Escribirlo a mano es introducir
> bugs de seek gratis.

**Fichero**: **nuevo** `backend/app/routers/stream.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models
from ..paths import resolve_music
from ..security import verify_stream_token

router = APIRouter(tags=["stream"])


@router.get("/stream/{track_id}")
def stream(track_id: int, t: str = Query(..., description="token de /auth/stream-token"),
           db: Session = Depends(get_db)):
    verify_stream_token(t)                                  # 401 si no vale
    tr = db.get(models.Track, track_id)
    if not tr or tr.status != "descargada":
        raise HTTPException(404, "Canción no disponible")
    try:
        ruta = resolve_music(tr.file_path)
    except (FileNotFoundError, PermissionError):
        raise HTTPException(404, "Canción sin fichero asociado")
    if not ruta.exists():
        # 410: el catálogo la conoce pero el fichero no está → el worker debe re-descargarla
        raise HTTPException(410, "El fichero ya no está en disco")
    return FileResponse(ruta, media_type="audio/mpeg",
                        headers={"Cache-Control": "private, max-age=3600",
                                 "Accept-Ranges": "bytes"})
```

Registrar en `main.py` (`from .routers import ..., stream` y añadirlo al bucle de `include_router`).

**Contrato resultante** (documentar en `02_API.md`):

```
GET /stream/{id}?t=<token>
  200 / 206   audio/mpeg · Accept-Ranges: bytes · Content-Range (en 206) · ETag
  401  token ausente, caducado o de otro ámbito
  404  canción inexistente, retirada o sin fichero
  410  el fichero ya no está en disco  → disparar re-descarga
  416  rango no satisfacible
```

**Verificación** (la prueba de fuego del seek):

```powershell
curl -s -D - -o NUL "http://127.0.0.1:8000/stream/1?t=<TOKEN>" -H "Range: bytes=0-1023"
# Debe responder: HTTP/1.1 206 Partial Content  +  Content-Range: bytes 0-1023/<total>
```
Y en un navegador: `<audio controls src="http://127.0.0.1:8000/stream/1?t=...">` debe **sonar y
permitir arrastrar la barra**.

---

## T-14 · `/media/**` para carátulas y fotos

`backend/app/main.py`:

```python
from fastapi.staticfiles import StaticFiles
from .config import MEDIA_ROOT

for sub in ("covers", "artists"):
    d = MEDIA_ROOT / sub
    d.mkdir(parents=True, exist_ok=True)
    app.mount(f"/media/{sub}", StaticFiles(directory=d), name=f"media_{sub}")
```

**Nunca** servir el `cover_path` de la BD como ruta libre: la BD aporta el **nombre del fichero**, la
raíz la pone el servidor.

Y para que el cliente no tenga que saber nada de rutas, añadir **propiedades** a los modelos
(`backend/app/models.py`):

```python
    # en Track
    @property
    def cover(self) -> str | None:
        from .paths import media_filename
        n = media_filename(self.cover_path)
        return f"/media/covers/{n}" if n else None

    # en Artist
    @property
    def image(self) -> str | None:
        from .paths import media_filename
        n = media_filename(self.image_path)
        return f"/media/artists/{n}" if n else None
```

y exponerlas en `schemas.TrackOut` (`cover: Optional[str] = None`) y `schemas.ArtistOut`
(`image: Optional[str] = None`). Pydantic con `from_attributes=True` lee propiedades sin más.

> **I6**: `tracks.artist_image_path` está **vacío en las 1114 filas**; las fotos viven en la tabla
> `artists` (521/521 tienen `image_path`). La UI debe pedir la foto por artista, **no** por canción.
> Corregir esa afirmación en `docs/05_UI.md` y en `docs/07_CROSS_PLATFORM_BLUEPRINT.md`.

---

## T-15 · Campos que ya están en la BD y no se exponen — **I4**

`schemas.TrackOut` — añadir: `feat` (341 canciones lo tienen), `rank` (popularidad de Deezer, hoy sin
usar en ningún sitio), `cover` (T-14). `explicit` y `duration` ya están.

`backend/app/routers/tracks.py` — nuevos parámetros de `GET /tracks`:

- `explicit: Optional[bool]` → **filtro de contenido explícito** (160 temas marcados). Es la base del
  perfil familiar; sin él, la app no es apta para menores.
- `sort: Literal["recientes","rank","year","aleatorio"] = "recientes"`.
- `artist: Optional[str]` (exacto, para la página de artista).
- `album: Optional[str]` (para la página de álbum).

**Paginación sin romper el contrato**: `GET /tracks` **sigue devolviendo una lista**; se añade la
cabecera **`X-Total-Count`** con el total sin paginar (y `Access-Control-Expose-Headers:
X-Total-Count` en el CORS, o el navegador no la ve). Así el scroll infinito funciona y ningún cliente
existente se rompe.

---

## T-16 · Endpoints que la UI da por hechos — **I10**

| Endpoint | Por qué | Nota de implementación |
|---|---|---|
| `GET /library/liked` → `TrackOut[]` | hoy `/library/reactions` da **solo ids** → la pantalla "Me gusta" haría N+1 | `join` de `reactions` con `tracks`, `liked=1` |
| `DELETE /playlists/{id}` | no se puede borrar una playlist | borrar antes sus `playlist_tracks` |
| `DELETE /playlists/{id}/tracks/{track}` | no se puede quitar una canción | recompactar `position` |
| `PATCH /playlists/{id}` | renombrar / cambiar descripción | |
| `PUT /playlists/{id}/order` con `[track_id,…]` | reordenar arrastrando | reescribe `position` |
| `GET /artists/{name}` → `ArtistOut` | página de artista (el móvil la necesita) | 404 si no existe |
| `GET /artists/{name}/top` → `TrackOut[]` | "top canciones" del artista | ordenar por `rank` |
| `POST /tracks/{id}/report` | "esta canción está mal" | inserta en `blacklist` + marca `status='revisar'` |

Todos comprueban `user_id` (una playlist ajena responde 404, **no** 403: no se filtra su existencia).

### ✅ Criterio de salida de F1
Un `<audio>` en el navegador reproduce y hace seek · las carátulas se ven por `/media/covers/...` ·
la pantalla "Me gusta" se puede pintar con **una** petición · `pytest` verde con un test de `206`.

---

# FASE F2 · Sanear los datos (en paralelo a F1; es trabajo del recolector)

**Por qué no es opcional**: construir dos clientes sobre un catálogo con un 20 % sin verificar y una
feature saturada es construir sobre arena. En el plan anterior esto estaba en una "FASE E opcional".

---

## T-17 · Puerta de calidad en la ingesta — **C4**

**Fichero**: **nuevo** `radiov/quality.py`:

```python
"""Puerta de calidad: decide si una pista puede entrar al catálogo público."""
import re

DUR_MIN, DUR_MAX = 90.0, 480.0          # 1:30 – 8:00
ARTISTAS_PROHIBIDOS = {"deezer", "disney", "various artists", "various", "topic", "unknown"}
BASURA = re.compile(r"[<>{}]|charset|font-weight|http[s]?://|&nbsp;|&#\d+;|^\s*$", re.I)


def revisar(rec: dict) -> tuple[bool, str]:
    """Devuelve (aceptada, motivo). Si aceptada=False, la pista va a 'cuarentena'."""
    titulo, artista = (rec.get("title") or ""), (rec.get("artist") or "")
    if BASURA.search(titulo) or BASURA.search(artista):
        return False, "texto no musical (HTML/CSS) en título o artista"
    if artista.strip().lower() in ARTISTAS_PROHIBIDOS:
        return False, f"artista genérico: {artista}"
    d = rec.get("duration") or 0
    if d and not (DUR_MIN <= d <= DUR_MAX):
        return False, f"duración fuera de rango: {d:.0f}s"
    if len(titulo.strip()) < 2 or len(artista.strip()) < 2:
        return False, "título o artista demasiado cortos"
    return True, ""
```

**Enganche**: en `radiov/pipeline.py`, justo antes de insertar en la BD. Si no pasa →
`status="cuarentena"` (nuevo estado) y `db.log_event(motivo, "warning")`. **Nunca** se descarta en
silencio: queda en la BD para poder revisarla.

Y en el backend, `status == "descargada"` sigue siendo el único que se sirve → la cuarentena no llega
a la app sin tocar ni una línea del API.

---

## T-18 · Limpiar la basura que ya está dentro — **C4**

**Script**: `scripts/limpiar_catalogo.py`, `--dry-run` por defecto.

Marca `status='cuarentena'` en las filas que no pasan `quality.revisar()`. Casos conocidos hoy:

| artista — título | duración | fichero |
|---|---|---|
| Deezer — Ruido blanco para dormir | 36.000 s | **1.025 MB** |
| Disney — Zoo | 13.229 s | 344 MB |
| Deezer — Ruido blanco relajante | 3.591 s | 106 MB |
| Deezer — Lluvia de impermeable | 930 s | 25 MB |
| `meta charset="utf - 8"/` | 56 s | — |
| `color:#1565b3;font-weight:700}.c - h-p` | 65 s | — |
| Free Cover Venezuela — Eddy Herrera & Raquel Bustamante | 881 s | 28 MB |

El script **lista los MP3 y su tamaño total (~1,4 GB) y espera confirmación explícita** antes de
borrar nada de `E:\Musica` (regla 8).

**Y arreglar el origen**: averiguar qué fuente de descubrimiento produjo `meta charset=...` y
`color:#1565b3;...` — es un parseo de HTML sin sanear en el barrido de listas de éxitos
(`radiov/hits.py` / `radiov/charts.py`). La puerta de calidad tapa el síntoma; esto es la causa.

---

## T-19 · `match_score`: distinguir "sin verificar" de "mala coincidencia" — **C4**

**Causa exacta** (`radiov/youtube.py:205-209`): si no hay `expected_duration`, `match` se queda en
`0.0`. Por eso hay 221 filas a 0 — **no son malas coincidencias, son sin verificar**, y hoy es
imposible distinguirlas.

1. En `youtube.py`: `match_score = None` cuando no se pudo comparar; `0.0` solo cuando se comparó y
   salió mal.
2. **Verificación a posteriori** (`scripts/verificar_match.py`): para cada fila con `match_score` nulo
   o 0, calcular la duración real del fichero con `catalog.real_duration()` (ya existe) y compararla
   con la de Deezer. `match = max(0, 1 - |real-esperada|/esperada)`.
3. Lo que quede por debajo de **0.6** → `status='revisar'` y aparece en la cola de reparación
   (T-16, `POST /tracks/{id}/report`).

---

## T-20 · `energy` por percentil — **C3**

**Problema medido**: `energy = min(1.0, rms / 0.15)` deja **673 de 1114 canciones (60 %) en
exactamente 1.0**. El filtro "Alta" devuelve el 87 % del catálogo y el término de energía del
recomendador es prácticamente constante.

1. **Guardar el crudo**: nueva columna `rms REAL` en `tracks` (`radiov/db.py`). En
   `catalog.analyze_bpm`, guardar `rms` **sin normalizar**, además de `energy`.
2. **Normalizar por percentil sobre el corpus** (`scripts/recalcular_energia.py`):

```python
filas = [(id, rms) for id, rms in cur.execute(
    "SELECT id, rms FROM tracks WHERE rms IS NOT NULL ORDER BY rms")]
n = len(filas)
for pos, (tid, _) in enumerate(filas):
    energy = round((pos + 0.5) / n, 3)        # uniforme 0-1 por construcción
    cur.execute("UPDATE tracks SET energy=? WHERE id=?", (energy, tid))
```

3. Para las filas sin `rms` (todas las actuales), reanalizar con `catalog.analyze_bpm` en lotes; es
   lento (lee cada MP3) → tarea de worker, no interactiva.
4. **Regenerar `tags`** después (`catalog.derive_tags`, que usa los umbrales `>=0.55` / `<=0.3`): con
   la energía repartida, "energia alta" vuelve a significar algo.

**Verificación**: `SELECT COUNT(*) FROM tracks WHERE energy >= 0.55` debe quedar en ~45 %, no en 87 %.

---

## T-21 · `valence` / `danceability`: decidir — **I5**

Hoy `valence` es **NULL en las 1114 filas** y `danceability`/`acousticness`/`loudness` ni existen,
pero `docs/03_PERSONALIZATION.md` construye el vector de canción sobre ellas. Hay que cerrar la brecha
en una de las dos direcciones:

- **(A)** Calcularlas con librosa (ya instalado): `valence` ≈ combinación de modo mayor/menor +
  centroide espectral; `danceability` ≈ regularidad del pulso + fuerza del onset. Aproximado pero útil.
- **(B)** Quitarlas del documento 03 y describir el algoritmo que de verdad corre (género + era +
  artista + bpm + energía).

**No dejar el documento prometiendo lo que el código no hace.** Si se elige (A), el cálculo va al
mismo paso que T-20 (una sola lectura del MP3 para todo).

---

## T-22 · Normalización de volumen (`gain_db`) — **la mejora más perceptible de todo el plan**

El audio viene de YouTube: cada canción tiene un nivel distinto y el salto entre temas es brutal. Es
*el* defecto que delata a un reproductor casero, y no está en ningún documento.

1. Nueva columna `gain_db REAL` en `tracks`.
2. En la ingesta (y en un script de recuperación para las 1114 actuales):
   ```
   ffmpeg -i "<mp3>" -af loudnorm=I=-14:print_format=json -f null -
   ```
   Leer `input_i` (LUFS medidos) del JSON → `gain_db = -14.0 - input_i` (objetivo −14 LUFS, el mismo
   que usa Spotify). ffmpeg ya está instalado.
3. Exponer `gain_db` en `TrackOut`.
4. El cliente lo aplica: en web con un `GainNode` de Web Audio API sobre el `<audio>`; en Flutter con
   el `volume` del player ajustado por la ganancia.

---

## T-23 · Contenido y facetas

- `GET /facets` → valores reales con su conteo (géneros, eras, moods, idiomas) para que la UI no los
  lleve escritos a fuego.
- **Ojo con dos datos** al diseñar pantallas: `is_remix=1` solo en **7** canciones (la faceta "remix"
  no da para una sección), y el catálogo está **muy sesgado a lo reciente** (20s: 483 · 10s: 290 ·
  00s: 225 · 90s: 53 · 80s: 29 · 70s: 15 · 60s: 3). Una sección "80s" o "Clásicos" se vería vacía: o
  se equilibra el descubrimiento por décadas en el recolector, o la UI no promete esas secciones.
- `género = "other"` (144) e `idioma = "other"` (120) son demasiado para navegar por facetas: merece
  una pasada de reclasificación.

### ✅ Criterio de salida de F2
Cero filas con texto no musical · `energy` repartida (~45 % por encima de 0.55) · ninguna fila con
`match_score` ambiguo · `gain_db` calculado · ~1,4 GB recuperados.

---

# FASE F3 · Web (React)

> 📄 **Detalle completo con código: [`10_FRONTEND_SPEC.md`](10_FRONTEND_SPEC.md).**
> Lo de aquí abajo es el resumen; ese documento es el que se sigue al programar.

**Punto de partida**: `vendor/spotify-react-web-client-main` (React + TS + Redux + Vite + antd).
**Copiar** a `frontend/` (no editar dentro de `vendor/`).

## Decisión de arquitectura: **capa adaptadora, no reescritura**

Los `services/`, `slices/` e `interfaces/` del repo están modelados sobre la API de Spotify (objetos
anidados: `album.images[]`, `artists[]`, `uri`, paginación `items/total/next`). Reescribir
`interfaces/*` obliga a tocar prácticamente todos los componentes.

**En su lugar**: un módulo `src/api/adapt.ts` que traduzca nuestro `TrackOut` a la forma que la UI ya
espera. Se tocan ~10 ficheros en lugar de ~60 y la UI sigue funcionando sin cambios.

```ts
// src/api/adapt.ts
export const toSpotifyTrack = (t: TrackOut) => ({
  id: String(t.id),
  name: t.title,
  duration_ms: Math.round((t.duration ?? 0) * 1000),
  explicit: t.explicit,
  uri: `radiopv:track:${t.id}`,
  artists: [{ id: t.artist, name: t.artist, type: 'artist' }],
  album: { id: t.album ?? '', name: t.album ?? '',
           images: t.cover ? [{ url: API_BASE + t.cover, height: 640, width: 640 }] : [],
           release_date: t.year ? String(t.year) : '' },
  // extras propios de RadioPV que la UI puede ignorar
  radiopv: { bpm: t.bpm, energy: t.energy, era: t.era, genre: t.genre, gain_db: t.gain_db },
});
```

## Ficheros a tocar (y solo estos)

| Fichero | Cambio |
|---|---|
| `src/axios.ts` | `baseURL` → `import.meta.env.VITE_API_URL`; en 401 → refrescar/relogin con nuestro JWT |
| `src/utils/spotify/login.ts` | reemplazar OAuth por `POST /auth/login` \| `/auth/register`; guardar el token |
| `src/utils/spotify/webPlayback.tsx` | **quitar el SDK de Spotify** → `<audio>` HTML5 con `src={streamUrl(id)}` |
| `src/services/*` | apuntar a nuestros endpoints y pasar por `adapt.ts` |
| `src/store/slices/auth.ts` | `fetchUser` → `/auth/me` |
| `src/constants/spotify.ts` | URIs de playlists → `/playlists/system`; imágenes por defecto locales |
| `src/components/Modals/Login` | email + contraseña (+ código de invitación) |

## Añadir (no está en el repo original y aquí importa)

1. **`streamUrl(id)`**: pide `/auth/stream-token` una vez, lo cachea, lo refresca a los ~25 min y
   construye `${API}/stream/${id}?t=${token}`.
2. **Media Session API** (~30 líneas): controles en la pantalla de bloqueo, en los auriculares y en el
   centro de notificaciones, con carátula. Es lo que hace que parezca una app nativa.
   ```ts
   navigator.mediaSession.metadata = new MediaMetadata({
     title: t.title, artist: t.artist, album: t.album ?? '',
     artwork: [{ src: API + t.cover, sizes: '512x512', type: 'image/jpeg' }] });
   navigator.mediaSession.setActionHandler('nexttrack', next);
   ```
3. **Precarga de la siguiente canción** cuando quedan ~20 s (un `<audio>` oculto con `preload`), para
   que no haya silencio entre temas.
4. **Ganancia por canción** (`gain_db` de T-22) con un `GainNode` de Web Audio.
5. **Shuffle con restricción**: barajar evitando dos canciones seguidas del mismo artista. El aleatorio
   uniforme suena mal y se nota enseguida.
6. **`POST /library/{id}/play`** al empezar, y al terminar/saltar enviar `seconds_listened` y `context`.

## Lo que NO se hace
Cola en el servidor, selector de dispositivos, tabla `devices`. Eso es **Spotify Connect**, un proyecto
en sí mismo. La cola vive en Redux, en el cliente. Como mucho, más adelante,
`GET/PUT /me/playback-state` con `{track_id, position_ms}` para "continuar donde lo dejaste".

### ✅ Criterio de salida de F3
Registro → login → Home → reproducir con seek → me gusta → las recomendaciones cambian. Todo contra
nuestra API, sin una sola llamada a Spotify.

---

# FASE F4 · Playlists automáticas + worker

> 📄 **Detalle completo con código: [`11_WORKER_SPEC.md`](11_WORKER_SPEC.md)** (tareas W-01 … W-07).

## W-01 … W-05 · Precomputar en vez de calcular en cada petición — **I7**

Hoy `recommend`/`radio`/`daily` cargan **todo el catálogo en Python** en cada petición (`query.all()`
+ `sort` en memoria) — justo lo que prohíbe `NOTES_FOR_AGENT.md`. Con 1114 filas aguanta; con 20.000 y
varios usuarios, no.

1. Extraer `_profile/_score/_candidates` a `backend/app/personalization.py` (sin cambiar el
   comportamiento; los tests lo fijan primero).
2. Tabla `similar(track_a, track_b, score)` con el **top-40 vecinos** por canción, recalculada por el
   worker. `radio(seed)` pasa a ser un `SELECT … ORDER BY score DESC LIMIT n`.
3. Tabla `mixes(user_id, kind, seed, tracks_json, created_at)` regenerada de madrugada.
   `/recommend/daily` sirve el JSON precomputado.

## W-02 · Arranque en frío: usar `rank` — **I4**

Sin likes, `_profile` devuelve listas vacías y `_score` da **0 a todo**: el orden final es arbitrario.
Y `rank` (popularidad de Deezer) está en la BD **sin usarse en ningún sitio**.

```python
s += 0.5 * (t.rank or 0) / 1_000_000 * peso_frio     # peso_frio: 1.0 sin señales → 0.0 con muchas
```

Añadir además **diversidad (MMR)**: penalizar repetir artista/género dentro de la misma lista, o el
mix diario sale monótono.

## W-07 · Worker

`backend/app/workers.py` con APScheduler (más simple que Celery aquí; no hace falta Redis):

| Tarea | Cadencia | Qué hace |
|---|---|---|
| `sync_catalogo` | 30 min | ejecuta la migración **no destructiva** de T-05 |
| `recount_artist_tracks` | tras cada sync | lo que se sacó del endpoint en T-01 |
| `rebuild_similar` | diaria | top-K vecinos |
| `rebuild_mixes` | diaria (madrugada) | daily mix por usuario |
| `refresh_trends` / `new_releases` | 6-12 h | listas de éxitos → playlists `system` |
| `verificar_ficheros` | semanal | detecta `file_path` que ya no existen → marca y re-descarga |
| `recalcular_energia` | tras cada lote de análisis | T-20 |

**Proceso separado** del de la API (`python -m app.workers`). Nunca dentro del proceso de uvicorn con
`--reload`.

---

# FASE F5 · Móvil (Flutter)

> 📄 **Detalle completo con código: [`12_MOBILE_SPEC.md`](12_MOBILE_SPEC.md)** (tareas MB-01 … MB-08).

`vendor/Flutter-Musive-app` → copiar a `mobile/`.

| Fichero | Cambio |
|---|---|
| `lib/api/url.dart` | `baseUrl` → nuestra URL; `basePath` → `''` |
| `lib/repositories/*` | home → `/tracks?sort=rank` · search → `/tracks?q=` · artista → `/artists/{name}` · playlists → `/playlists` |
| `lib/models/song_model.dart` | mapear a `TrackOut` |
| `lib/controllers/main_controller.dart` | login con `POST /auth/login` (JWT) |
| `lib/utils/player.dart` | `/stream/{id}?t=…`; mantener notificación y caché |
| `android/app/src/main/AndroidManifest.xml` | permiso de red; en local `usesCleartextTraffic="true"`; en producción HTTPS |

**Aprovechar lo que ya trae**: reproductor con notificación, cola, y **caché/offline** — que en una app
de música propia es de lo más valorado. `just_audio` **sí** puede enviar cabeceras, pero se usa el
mismo token en la query que en la web para no tener dos caminos de autenticación.

---

# FASE F6 · Despliegue

> 📄 **Detalle completo con código: [`13_DEPLOY_SPEC.md`](13_DEPLOY_SPEC.md)** (tareas DP-01 … DP-08).

## DP-01 · Decidir **antes** de escribir el `docker-compose`: ¿dónde viven los 9,5 GB?

Ningún documento lo responde y **condiciona el código de `/stream`**:

| Opción | Cómo | Pros | Contras |
|---|---|---|---|
| **A. API en casa + túnel** ← recomendada para empezar | el backend corre en el PC, expuesto con Cloudflare Tunnel o Tailscale | coste 0, el audio no se mueve, HTTPS resuelto | depende de que el PC esté encendido; sube por tu fibra |
| **B. VPS + audio en object storage** (R2/B2/S3) | `/stream` devuelve un **302 a una URL firmada** | escala, disco barato | coste mensual, subir 9,5 GB, egreso |
| **C. VPS con disco grande** | todo junto | simple | caro por GB |

Escribir `/stream` de forma que el cambio A→B sea **una función** (`servir_audio(track)` que devuelve
`FileResponse` o `RedirectResponse`), no una reescritura.

## DP-02 … DP-08 · Producción

- **Alembic** sustituyendo a `create_all` (`alembic init`, migración inicial desde los modelos). A
  partir de F0 ya hay cambios de esquema (`seconds_listened`, `context`, `rms`, `gain_db`): meterlos
  como primera migración.
- **Docker Compose**: `api` + `postgres` + `worker` + `web` (estático con nginx/caddy). En Windows, la
  música se monta **en solo lectura**: `- E:/Musica:/musica:ro` con `MUSIC_ROOT=/musica`.
- **HTTPS** (Caddy resuelve el certificado solo).
- **Copia de seguridad diaria de `data/*.db`**. El audio se puede volver a descargar; **la base de
  datos no**: contiene 1114 fichas enriquecidas y todas las señales de los usuarios. Es la póliza más
  barata del proyecto y hoy no existe.
- **Cerrar el registro**: `INVITE_CODE` obligatorio (T-03) — `POST /auth/register` hoy no pide nada.
- **Límite de intentos en `/auth/login`** (fuerza bruta trivial hoy).
- `ALLOWED_ORIGINS` con los dominios reales, no `*`.
- **Nota legal**: mientras es un catálogo personal en tu red, es asunto privado. Al abrirlo por HTTPS a
  "familia y amigos" con cuentas, pasa a ser **distribución** de audio derivado de YouTube, que
  jurídicamente es otra cosa. Mitigación razonable: acceso solo por invitación, círculo cerrado, sin
  indexar y sin ánimo de lucro. Que sea una decisión consciente, no una omisión.

---

# Anexo A · Deuda menor (hacer al pasar por el fichero, no como tarea propia)

- `db.query(...).get()` → `db.get(Model, id)` (obsoleto en SQLAlchemy 2.0).
- `class Config: from_attributes` → `model_config = ConfigDict(from_attributes=True)` (Pydantic 2).
- `my_playlists()` hace un `COUNT` por playlist (N+1) → un `GROUP BY`.
- `HTTPException` importado dentro de la función en `tracks.py`.
- `list_artists(limit=200)` sin tope (resuelto en T-01 con `Query(le=1000)`).
- Contraseña mínima de 8 → 10 caracteres.
- **Deriva de cifras en la documentación**: `PLAYER_DESIGN` dice 833, `06_BUILD_GUIDE` y
  `PROJECT_BRIEF` dicen 889, la realidad son 1114. Dejar de escribir números fijos, o generarlos.
- `01_SCHEMA.md` lista tablas que no existen en `models.py` (`smart_playlists`, `mixes`, `lyrics`,
  `similar`, `sessions`): marcarlas como **previstas**, no como esquema vigente.
- `ARCHITECTURE.md` dedica media página a Cassandra: la decisión ya es "no". Reducirlo a una línea
  para que ningún agente futuro reabra el debate.

# Anexo B · Funcionalidades pendientes de decidir (producto, no técnica)

Ordenadas por relación valor/esfuerzo:

1. **Perfil familiar con filtro de contenido explícito** (el dato ya está; será la primera petición).
2. **Reproducción continua tipo "Flow"**: al acabar la cola, seguir con la radio del último tema en vez
   de parar. Con `radio()` ya implementado es casi gratis y cambia la sensación de uso.
3. **"Añadir a continuación"** (distinto de "añadir al final").
4. **Sleep timer**.
5. **Historial navegable** ("escuchado recientemente") — ya se puede sacar de `plays`.
6. **Contador de reproducciones por canción**: hace que la biblioteca se sienta tuya.
7. **Estado vacío útil**: con 1114 canciones habrá búsquedas sin resultados → botón "pedir esta
   canción" que la encola en el recolector. Convierte una frustración en una función.
8. **PWA instalable**: da el 80 % de la experiencia móvil antes de tener el APK.
9. **Letras** (`lyrics` está en el esquema y la tabla no existe).
10. **Wrapped / estadísticas**.

---

# Anexo C · Orden de un vistazo

```
F0  cimientos      T-01 … T-10   ← BLOQUEANTE, medio día
F1  reproducción   T-11 … T-16   ← desbloquea web y móvil
F2  datos          T-17 … T-23   ← en paralelo a F1 (es del recolector)
F3  web            FE  → 10_FRONTEND_SPEC.md   capa adaptadora + Media Session + gain + shuffle
F4  worker         W-01 … W-07 → 11_WORKER_SPEC.md   precomputar; quita carga a la API
F5  móvil          MB-01 … MB-08 → 12_MOBILE_SPEC.md   Flutter con offline
F6  despliegue     DP-01 … DP-08 → 13_DEPLOY_SPEC.md   (DP-01 primero: dónde vive el audio)
```

**Si solo se puede hacer una cosa hoy**: T-05 (migración no destructiva). Es la única de esta lista
que, si no se hace, **destruye datos que ya existen**.

---

*Plan derivado de la auditoría `docs/08_REVIEW.md` (2026-08-28), hecha sobre el código y los datos
reales. Donde la documentación previa y el código discrepan, este plan sigue al código.*
