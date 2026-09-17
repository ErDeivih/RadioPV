# 🎛️ RadioPV · Motor de personalización, playlists y worker — FASE F4

> Tareas **W-01 … W-07** (fase F4). Detalle ejecutable de la fase F4 de [`09_IMPLEMENTATION_PLAN.md`](09_IMPLEMENTATION_PLAN.md).
> Sustituye y concreta a `03_PERSONALIZATION.md` y `04_PLAYLISTS_WORKER.md`, que describen el
> algoritmo **ideal**; esto describe el que se puede ejecutar **con los datos que existen**.

---

## 0. Punto de partida honesto

Lo que hay hoy en `backend/app/routers/recommend.py` funciona, pero:

- **Carga el catálogo entero en Python en cada petición** (`query.all()` + `sort` en memoria), y
  `daily()` lo carga **dos veces**. Con 1114 filas pasa; con 20.000 y varios usuarios, no.
- **Sin señales, puntúa 0 a todo**: un usuario nuevo recibe un orden arbitrario.
- Las features disponibles de verdad son `genre`, `era`, `artist`, `bpm` y `energy`. **`valence` es
  NULL en el 100 % de las filas** y `danceability`/`acousticness`/`loudness` no existen. Y `energy`
  está saturada hasta que se aplique T-20 (60 % de las canciones valen exactamente 1.0).

Conclusión: **hoy la recomendación es "más de lo mismo", no descubrimiento.** Esta fase lo arregla en
tres pasos: extraer, precomputar y añadir la señal que falta (popularidad y diversidad).

---

## W-01 · Extraer la personalización a su propio módulo

**Primero los tests, luego mover.** Escribir `backend/tests/test_recommend.py` que fije el
comportamiento actual (dado un usuario con 2 likes de flamenco, las 5 primeras recomendaciones son
flamenco), y **después** mover `_profile`, `_score` y `_candidates` a
`backend/app/personalization.py` sin tocar la lógica. Si el test sigue verde, el movimiento fue limpio.

```python
# backend/app/personalization.py
"""Perfil de gustos y puntuación de canciones. Lo usan los endpoints y el worker."""
from collections import Counter
from datetime import datetime, timedelta
import math

PESOS = {"like": 3.0, "play_completo": 1.0, "play_medio": -1.0,
         "skip_tardio": -2.0, "skip_inmediato": -3.0}
SEMIVIDA_DIAS = 90.0


def peso_recencia(cuando: datetime) -> float:
    """Los gustos recientes pesan más: w = exp(-dias/90)."""
    dias = max(0.0, (datetime.utcnow() - cuando).total_seconds() / 86400)
    return math.exp(-dias / SEMIVIDA_DIAS)
```

---

## W-02 · Perfil con recencia y señales implícitas

Hoy `_profile` solo mira `reactions.liked`. Con `plays.seconds_listened` (T-08) ya se puede aplicar la
tabla de pesos que `03_PERSONALIZATION.md` prometía:

```python
def señales(user_id: int, db) -> dict[int, float]:
    """track_id -> peso acumulado (con recencia)."""
    acc: dict[int, float] = {}

    for r in db.query(models.Reaction).filter_by(user_id=user_id):
        w = peso_recencia(r.updated_at or datetime.utcnow())
        if r.liked:
            acc[r.track_id] = acc.get(r.track_id, 0) + PESOS["like"] * w
        if r.skipped:
            acc[r.track_id] = acc.get(r.track_id, 0) + PESOS["skip_tardio"] * w

    for p in db.query(models.Play).filter_by(user_id=user_id):
        w = peso_recencia(p.played_at)
        seg, dur = (p.seconds_listened or 0), 0
        t = db.get(models.Track, p.track_id)
        dur = (t.duration or 0) if t else 0
        if p.completed or (dur and seg >= dur * 0.9):
            k = "play_completo"
        elif dur and seg < dur * 0.30:
            k = "skip_inmediato" if seg < 15 else "skip_tardio"
        else:
            k = "play_medio"
        acc[p.track_id] = acc.get(p.track_id, 0) + PESOS[k] * w
    return acc
```

El perfil (`taste_profile`) pasa a ser la **media ponderada** de los vectores de las canciones con
peso **positivo**. Guardarlo en la tabla y refrescarlo desde el worker, no en cada petición.

---

## W-03 · Arranque en frío: usar `rank` (hoy sin usar)

`tracks.rank` (popularidad de Deezer) está en la base de datos y **no se usa en ningún sitio**. Es
exactamente lo que falta para el usuario nuevo:

```python
def score(t, prof, peso_frio: float) -> float:
    s = 0.0
    if t.genre in prof["genres"]:  s += 2.5
    if t.era   in prof["eras"]:    s += 1.5
    if t.artist in prof["artists"]: s += 1.5
    if prof.get("bpm_mean") and t.bpm:
        s += max(0.0, 1.0 - abs(t.bpm - prof["bpm_mean"]) / 100.0)
    if prof.get("energy_mean") is not None and t.energy is not None:
        s += max(0.0, 1.0 - abs(t.energy - prof["energy_mean"]) / 0.6)
    # prior de popularidad: manda cuando no hay señales, desaparece cuando las hay
    s += peso_frio * 3.0 * min(1.0, (t.rank or 0) / 800_000)
    return s


def peso_frio(n_señales: int) -> float:
    """1.0 sin señales · ~0.5 con 10 · ~0.1 con 50."""
    return 1.0 / (1.0 + n_señales / 10.0)
```

---

## W-04 · Diversidad (MMR): que el mix no sea monótono

Sin esto, "Para ti" son 20 canciones del mismo artista y género. Se penaliza lo ya elegido:

```python
def seleccionar_diverso(candidatos, n, k_artista=0.6, k_genero=0.3):
    elegidos, vistos_a, vistos_g = [], Counter(), Counter()
    for t in sorted(candidatos, key=lambda x: -x._score):
        penal = k_artista * vistos_a[t.artist] + k_genero * vistos_g[t.genre or ""]
        t._final = t._score - penal
        elegidos.append(t)
    elegidos.sort(key=lambda x: -x._final)
    salida = []
    for t in elegidos:
        if len(salida) >= n:
            break
        if vistos_a[t.artist] >= 2:      # máximo 2 por artista en una lista
            continue
        salida.append(t); vistos_a[t.artist] += 1; vistos_g[t.genre or ""] += 1
    return salida
```

---

## W-05 · Tablas nuevas: `similar` y `mixes`

```python
class Similar(Base):
    __tablename__ = "similar"
    id = Column(Integer, primary_key=True)
    track_a = Column(Integer, ForeignKey("tracks.id"), index=True)
    track_b = Column(Integer, ForeignKey("tracks.id"))
    score = Column(Float)
    __table_args__ = (UniqueConstraint("track_a", "track_b", name="uq_similar"),
                      Index("ix_similar_a_score", "track_a", "score"))


class Mix(Base):
    __tablename__ = "mixes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    kind = Column(String(30))              # daily | discover | on_repeat | radar
    seed = Column(String(80))
    tracks_json = Column(Text)             # [12, 45, 88, …]
    created_at = Column(DateTime, default=datetime.utcnow)


class SmartPlaylist(Base):
    __tablename__ = "smart_playlists"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)   # NULL = del sistema
    name = Column(String(120))
    filters = Column(Text)                 # JSON, ver 04_PLAYLISTS_WORKER §2
    enabled = Column(Boolean, default=True)
```

**`radio(seed)` deja de calcular**: pasa a ser

```sql
SELECT t.* FROM similar s JOIN tracks t ON t.id = s.track_b
WHERE s.track_a = :seed AND t.status = 'descargada'
ORDER BY s.score DESC LIMIT :n
```

`rebuild_similar` calcula el **top-40** por canción. Con 1114 canciones son ~1,2 M de comparaciones:
segundos en numpy, y se hace una vez al día, no por petición.

```python
import numpy as np

def vector(t):
    """Solo features que existen de verdad. Ampliar cuando T-21 añada valence."""
    generos = ["pop","reggaeton","latin","bachata","rock","merengue","salsa",
               "cumbia","corridos","flamenco","dance","other"]
    eras = ["60s","70s","80s","90s","00s","10s","20s"]
    return np.array(
        [ (t.bpm or 120) / 200.0, (t.energy or 0.5) ]
        + [1.0 if t.genre == g else 0.0 for g in generos]
        + [1.0 if t.era == e else 0.0 for e in eras], dtype=np.float32)
```

---

## W-06 · Endpoints nuevos

| Endpoint | Devuelve | Origen |
|---|---|---|
| `GET /playlists/system` | `PlaylistOut[]` | playlists con `type='system'` |
| `GET /recommend/trending` | `TrackOut[]` | playlist `system` "Trending" |
| `GET /library/history?limit=50` | `TrackOut[]` | `plays` del usuario, orden descendente, sin repetir |
| `GET /wrapped?period=week\|year` | agregados | top artistas, géneros, minutos, nuevos descubrimientos |
| `GET /facets` | conteos reales | géneros, eras, moods e idiomas con `COUNT(*)` |
| `POST /requests` | `{ok:true}` | encola una canción pedida desde la app (estado vacío de búsqueda) |
| `POST /mixes/refresh` | `{ok:true}` | forzar regeneración (solo admin) |

`/recommend/daily` pasa a **leer de `mixes`**; si no hay mix del día, lo calcula al vuelo una vez y lo
guarda.

---

## W-07 · El worker

**Proceso separado** de la API: `python -m app.workers`. Nunca dentro de uvicorn con `--reload`
(duplicaría cada tarea programada).

```python
# backend/app/workers.py
"""Trabajador en segundo plano. Arranque:  python -m app.workers"""
import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from .database import SessionLocal

log = logging.getLogger("radiopv.worker")


def _tarea(nombre, fn):
    """Envoltorio: sesión propia, errores capturados, nunca tumba el scheduler."""
    def wrapper():
        db = SessionLocal()
        try:
            n = fn(db)
            log.info("[%s] ok %s", nombre, n)
        except Exception:
            log.exception("[%s] FALLÓ", nombre)
        finally:
            db.close()
    return wrapper


def main():
    s = BlockingScheduler(timezone="Europe/Madrid")
    s.add_job(_tarea("sync_catalogo", sync_catalogo), "interval", minutes=30)
    s.add_job(_tarea("rebuild_similar", rebuild_similar), "cron", hour=4)
    s.add_job(_tarea("rebuild_mixes", rebuild_mixes), "cron", hour=5)
    s.add_job(_tarea("refresh_trends", refresh_trends), "interval", hours=8)
    s.add_job(_tarea("rebuild_static_lists", rebuild_static_lists), "cron", hour=6)
    s.add_job(_tarea("verificar_ficheros", verificar_ficheros), "cron", day_of_week="sun", hour=3)
    s.add_job(_tarea("prune", prune), "cron", hour=7)
    log.info("Worker RadioPV en marcha")
    s.start()
```

| Tarea | Cadencia | Qué hace | Regla |
|---|---|---|---|
| `sync_catalogo` | 30 min | ejecuta la migración **no destructiva** (T-05) + `recount_artist_tracks` | idempotente |
| `rebuild_similar` | 04:00 | top-40 vecinos por canción | reemplaza la tabla en una transacción |
| `rebuild_mixes` | 05:00 | mix diario por usuario activo | **no repetir lo escuchado en 7 días** |
| `refresh_trends` | 8 h | listas de éxitos → playlist `system` "Trending" | dedup por `deezer_id`; **no descarga**, solo etiqueta |
| `rebuild_static_lists` | 06:00 | regenera las de `smart_playlists` | |
| `verificar_ficheros` | domingos 03:00 | comprueba que cada `file_path` existe | si falta → `status='perdida'` y a la cola de re-descarga |
| `prune` | 07:00 | limpia de las playlists automáticas lo que ya no aplica | **nunca borra del catálogo** |

**Robustez** (no negociable): cada tarea con su propia sesión de BD, errores capturados y registrados
en `events`, reintentos con espera creciente, y **jamás** dos instancias del worker a la vez (fichero
de bloqueo o `--max-instances 1`).

---

## Criterios de aceptación de F4

- [ ] `GET /recommend/radio?seed_track=X` responde en **< 50 ms** (lee de `similar`, no calcula).
- [ ] Un usuario **sin ninguna señal** recibe canciones populares, no arbitrarias.
- [ ] En 20 recomendaciones no hay **más de 2 canciones del mismo artista**.
- [ ] `GET /playlists/system` devuelve "Trending" con contenido real.
- [ ] El worker sobrevive a un fallo de una tarea (las demás siguen).
- [ ] `sync_catalogo` ejecutado 3 veces seguidas: `nuevas=0` y **ninguna señal de usuario perdida**.
