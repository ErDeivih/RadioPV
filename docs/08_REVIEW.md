# 🔍 RadioPV · Revisión completa del proyecto (auditoría técnica)

> Revisión hecha leyendo el código real (`backend/app/**`, `radiov/**`), las dos bases de datos y toda
> la documentación. Cada hallazgo lleva **evidencia** (lo que se ve en el repo o en los datos) y
> **arreglo propuesto**. Fecha: 2026-08-28. Complementa a `PROJECT_BRIEF.md` y `NOTES_FOR_AGENT.md`.

---

## 0. Veredicto en diez líneas

El proyecto **encaja bien en lo grande**: la separación recolector → catálogo → API → clientes es la
correcta, el esquema es sensato, la documentación es mejor que la de la mayoría de proyectos de este
tamaño, y reutilizar dos repos de UI en vez de escribirlos es una decisión acertada.

Los problemas no están en el plano, están en **tres costuras**:

1. **Las dos bases de datos no están unidas, están enfrentadas**: la migración borra las señales del
   usuario y reasigna los `id` de las canciones. Es un fallo de diseño, no un bug menor.
2. **El catálogo tiene basura y una `energy` saturada** que deja la recomendación casi ciega.
3. **Faltan decisiones de producto que condicionan el código**: dónde viven los 9,5 GB de audio, cómo
   se autentica el `<audio>`, y quién manda en la cola de reproducción.

Además hay **un endpoint que hoy devuelve 500** (`GET /artists`) y **desajustes entre `02_API.md` y el
código** que romperían la FASE 2 en silencio. Todo eso es barato de arreglar **ahora** y caro después.

---

## 1. Lo que está bien (no tocarlo)

- **La separación de responsabilidades** (recolector descarga · API sirve · worker genera listas) es
  correcta y escala. Mantenerla.
- **El esquema de datos** (`tracks` + `artists` + `artist_albums` + señales por `user_id`) es el
  adecuado. La idea de *eventos inmutables + agregados derivados* de `ARCHITECTURE.md` es la buena.
- **Reutilizar `vendor/spotify-web` y `vendor/Flutter-Musive-app`** en vez de escribir dos UIs.
- **JWT con `token_version`** para revocar sesiones: simple y suficiente.
- **`DATABASE_URL`** desde el principio: el salto a Postgres será casi gratis.
- **Buena noticia verificada**: `starlette 1.6.0` (instalado) ya implementa `Range` en `FileResponse`
  (206, `Content-Range`, 416). `/stream` no hay que escribirlo a mano: son ~10 líneas.

---

## 2. Fallos CRÍTICOS

### 🔴 C1 · La migración destruye los datos de usuario y reasigna los `id` de las canciones

**Evidencia** — `backend/migrate_sqlite.py`:

```python
db.query(models.PlaylistTrack).delete()
db.query(models.Reaction).delete()
db.query(models.Play).delete()
db.query(models.Track).delete()
```

**Por qué es crítico.** Cada vez que se sincronice el catálogo:
- se borran **todos los me-gusta, reproducciones y contenidos de playlists** de todos los usuarios;
- las playlists sobreviven **vacías** (se borran sus `playlist_tracks`, no ellas);
- los `tracks.id` se **reasignan desde 1** en el nuevo orden de importación. Es decir, **el `id` de una
  canción no es estable**. Cualquier cosa guardada por `track_id` (like, play, playlist, mix
  precomputado, caché del cliente web o móvil) apunta después a **otra canción distinta**.

Esto no es teórico: `radiov.db` tiene ya **1114** canciones y `backend.db` **889**. La próxima
sincronización es exactamente el momento en que se pierde todo.

**Arreglo (elegir uno):**

- **(A) Recomendado — una sola base.** El recolector escribe directamente en la BD del backend
  (los mismos modelos SQLAlchemy, o un endpoint interno `POST /admin/tracks`). Desaparece la
  duplicidad, desaparece la migración, el catálogo está siempre al día en la app.
- **(B) Si se mantienen las dos**: convertir `migrate_sqlite` en un **UPSERT por `deezer_id`** que
  (1) **nunca** toca `users`, `reactions`, `plays`, `playlists`, `playlist_tracks`; (2) inserta lo
  nuevo, actualiza lo existente, y marca `status='retirada'` lo que ya no está (sin borrar la fila).

**En ambos casos, regla nueva e innegociable**: `tracks.id` es **inmutable para siempre**. La clave
natural para deduplicar es `deezer_id`; el `id` es solo una referencia estable.

> Y hoy `radiov.db` **no tiene `UNIQUE` en `deezer_id`** (hay 2 grupos duplicados). En `backend.db` sí.
> Añadir el índice único en origen.

---

### 🔴 C2 · `GET /artists` devuelve 500 con la SQLAlchemy instalada

**Evidencia** — `backend/app/routers/artists.py`:

```python
db.execute("UPDATE artists SET track_count = (SELECT COUNT(*) ...)")
```

En SQLAlchemy **2.0** ya no se acepta una cadena en `Session.execute()`. Comprobado contra la versión
instalada (2.0.52):

```
ArgumentError: Textual SQL expression 'SELECT 1' should be explicitly declared as text('SELECT 1')
```

**Además**, aunque se arregle, el endpoint ejecuta un `UPDATE` con `lower()` sobre 365 artistas × 1114
canciones **en cada petición GET**: sin índice utilizable y escribiendo en la BD en una lectura.

**Arreglo**: envolver en `text()` y —más importante— **sacar el recálculo del endpoint**. `track_count`
lo actualiza el recolector/worker cuando cambia el catálogo, no el usuario que abre una pantalla.

---

### 🔴 C3 · `energy` está saturada: el 60 % del catálogo vale exactamente 1.0

**Evidencia** — `radiov/catalog.py:123`:

```python
energy = round(min(1.0, rms / 0.15), 3)   # normalizado aproximado a 0-1
```

Distribución real sobre 1114 canciones:

| tramo | 0.0 | 0.1 | 0.2 | 0.3 | 0.4 | 0.5 | 0.6 | 0.7 | 0.8 | 0.9 | **1.0** |
|---|---|---|---|---|---|---|---|---|---|---|---|
| nº | 3 | 16 | 27 | 23 | 47 | 46 | 71 | 70 | 72 | 66 | **673** |

**Consecuencias en cadena:**
- El filtro del API (`Baja/Media/Alta`) da **Alta = 973 de 1114 (87 %)**. La faceta no sirve para nada.
- En `recommend._score`, el término `1 - |energy - energy_mean|/0.6` es casi **constante** → no aporta
  información. Lo mismo en `radio()`.
- Los `tags` derivados ("energia alta", "fiesta", "gimnasio") heredan el error: `derive_tags` usa el
  umbral `energy >= 0.55`, que cumple casi todo el catálogo.

**Arreglo**: normalizar por **percentil sobre el corpus** en lugar de dividir por una constante
mágica. Es decir: `energy = rank_percentil(rms)` recalculado periódicamente (una pasada por la tabla).
Así la distribución es uniforme 0-1 por construcción y las facetas parten el catálogo en tercios reales.
Guardar además el `rms` crudo en una columna para poder recalcular sin volver a leer los MP3.

---

### 🔴 C4 · El catálogo contiene basura descargada como si fuera música

**Evidencia** (consultas sobre `radiov.db`):

| fila | duración | tamaño |
|---|---|---|
| `Deezer — Ruido blanco para dormir` | 36.000 s (10 h) | **1.025 MB** |
| `Disney — Zoo` | 13.229 s (3,7 h) | 344 MB |
| `Deezer — Ruido blanco relajante` | 3.591 s | 106 MB |
| `Deezer — Lluvia de impermeable` | 930 s | 25 MB |
| `meta charset="utf — 8"/` | 56 s | — |
| `color:#1565b3;font-weight:700}.c — h-p` | 65 s | — |
| `Free Cover Venezuela — Eddy Herrera & Raquel Bustamante` | 881 s | 28 MB |

Las dos filas con `charset` y `font-weight` son **fragmentos de HTML/CSS** que el descubrimiento
parseó como "artista - título" y **descargó**. Y 1,4 GB de los 9,5 GB totales son ruido blanco.

Peor: **221 canciones (20 %) tienen `match_score = 0`**, incluidas piezas conocidísimas (*Rosas*,
*Yonaguni*, *AL GOLPITO*). Distribución: `>=0.8` → 878 · `0.5-0.8` → 12 · `<0.5` → 3 · `=0` → 221.

**Causa exacta** (`radiov/youtube.py:205-209`):

```python
match = 0.0
if expected_duration and actual:
    ...
    match = max(0.0, 1.0 - diff)
```

Si no había `expected_duration` (Deezer no la dio), `match_score` se queda en **0.0**. Es decir, el 0
no significa "coincidencia pésima" sino **"no se pudo comprobar"** — y ambos casos comparten el mismo
valor, así que hoy es imposible distinguirlos. El resultado práctico es el mismo: para una de cada
cinco canciones **no hay ninguna garantía de que el audio descargado sea la canción correcta**.

El arreglo es doble y barato: usar `None` para "sin verificar" (reservando `0.0` para "mala
coincidencia" de verdad), y verificar *a posteriori* con la duración real del fichero —
`catalog.real_duration()` ya existe— contra la duración de Deezer.

**Arreglos:**
1. **Puerta de calidad en la ingesta**: rechazar `duration > 480 s` o `< 90 s` salvo excepción
   explícita; rechazar títulos/artistas que no pasen un saneado mínimo (etiquetas HTML, `{`, `}`, `<`,
   `;`, `charset`, `font-weight`); rechazar artistas genéricos (`Deezer`, `Disney`, `Various`).
2. **Estado `cuarentena`** en vez de `descargada`: nada entra al catálogo público sin pasar la puerta.
   Hoy las 1114 filas tienen `status='descargada'`; no hay forma de aislar lo dudoso.
3. **Recalcular `match_score`** para las 221 filas a 0 y revisar/rebajar las peores.
4. **Botón "esta canción está mal"** en la app → `blacklist` + reintento de descarga. Con 20 % del
   catálogo sin verificar, la app **necesita** un bucle de reparación, no es un extra.
5. Limpieza inmediata: esas 7 filas y ~1,4 GB de disco.

---

### 🔴 C5 · `02_API.md` y el código no dicen lo mismo (rompería la FASE 2 en silencio)

| Endpoint | Documentado | Código real |
|---|---|---|
| `POST /library/{id}/like` | body JSON `{"liked": true}` | **query param** `?liked=true` |
| `POST /library/{id}/skip` | body JSON `{"skipped": true}` | **query param** `?skipped=true` |
| `POST /library/{id}/play` | body `{"source","completed"}` | **query params** |
| `GET /tracks?q=` | "FTS5" | `ILIKE '%q%'` (no hay FTS en `backend.db`) |

El React y el Flutter se escribirán contra `02_API.md`. Si el contrato real es otro, se descubre
depurando, no compilando.

**Arreglo**: cambiar el **código** a body JSON (que es lo documentado y lo correcto para un POST) y,
para la búsqueda, o se implementa FTS en el backend o se corrige el documento. Hacerlo **antes** de
escribir un solo cliente.

---

## 3. Fallos IMPORTANTES

### 🟠 I1 · Rutas absolutas de Windows dentro de la base de datos
`file_path` = `E:\Musica\catalogada\...`, `cover_path` = `F:\EspacioCodigo\RadioPV\data\covers\...`
(889 filas × 2 columnas). En Docker, en Linux o en cualquier despliegue **esas rutas no existen**.

**Arreglo**: `MUSIC_ROOT` y `MEDIA_ROOT` por variable de entorno y **rutas relativas** en la BD
(`catalogada/Bad Bunny/[2025] .../x.mp3`, `covers/693008911.jpg`). Hoy es un `UPDATE`; con web y móvil
ya cableados es una migración con clientes rotos.

### 🟠 I2 · `<audio>` no puede enviar la cabecera `Authorization`
Esto **decide** el contrato de `/stream` y no está resuelto en ningún documento.

- ❌ `/stream` público: cualquiera con la URL se lleva el catálogo entero.
- ✅ **Token de streaming corto firmado en la query** (`/stream/12?t=<jwt 5 min>`): funciona en
  `<audio>` HTML5, en `just_audio` (Flutter) y con `Range`; no expone el JWT de 24 h; caduca solo.
- ❌ Cookie `HttpOnly`: se complica con CORS y no encaja bien en móvil.

**Propuesta**: `GET /stream/{id}?t=…` con token firmado que lleve `{track_id, user_id, exp}`. El
cliente lo pide con `POST /stream/{id}/ticket` (con su Bearer) o lo recibe ya incrustado en `TrackOut`
como `stream_url`.

### 🟠 I3 · `Play` no tiene `seconds_listened`, pero el algoritmo lo necesita
`docs/01_SCHEMA.md` y `docs/03_PERSONALIZATION.md` construyen toda la ponderación sobre
"play completo / 50 % / skip al 30 %"… y `models.Play` solo tiene `completed`. Sin los segundos
escuchados, **la mitad de la tabla de pesos del documento 03 no se puede calcular**.

**Arreglo**: añadir `seconds_listened FLOAT` y `context` (playlist/radio/búsqueda) a `plays`.

### 🟠 I4 · Arranque en frío: sin likes, la recomendación es arbitraria
Con `reactions` vacías, `_profile` devuelve listas vacías y `_score` da **0 a todo**. El orden final es
el que devuelva la BD. Y `rank` (popularidad de Deezer) **existe en el modelo pero no se usa en ningún
sitio ni se expone en `TrackOut`**.

**Arreglo**: prior de popularidad (`rank`) en el score, con peso decreciente según crecen las señales
del usuario. Es gratis, ya está el dato.

### 🟠 I5 · `valence` y `danceability` son NULL en el 100 % de las filas
En `radiov.db` la columna `valence` existe y está vacía (1114/1114 NULL); `danceability`,
`acousticness` y `loudness` ni existen. `migrate_sqlite` **tampoco copia `valence`**. Sin embargo
`03_PERSONALIZATION.md` define el vector de canción sobre esas features.

**Realidad**: hoy la recomendación se apoya en `genre` + `era` + `artist` + `bpm` (y una `energy`
saturada, ver C3). Es "más de lo mismo", no descubrimiento.

**Arreglo**: o se calculan (librosa da aproximaciones razonables de valence/danceability) o se reescribe
el documento 03 para que describa el algoritmo que de verdad se puede ejecutar. Lo que no puede
quedarse es la brecha entre ambos.

### 🟠 I6 · `artist_image_path` está vacío en las 1114 canciones
Las fotos existen (`data/artists`, 521 ficheros, 100 % de los artistas tienen `image_path` en la tabla
`artists`), pero **no están denormalizadas en `tracks`**. `05_UI.md` y el blueprint dicen "usar
`track.artist_image_path`" → no pintaría nada.

**Arreglo**: que la UI resuelva la foto vía `artists` (lo correcto), y quitar esa columna de `tracks` o
rellenarla en el enriquecimiento. Elegir una y documentarla.

### 🟠 I7 · `recommend` y `radio` cargan el catálogo entero en Python en cada petición
`_candidates()` hace `query.all()` y ordena en memoria — justo lo que `NOTES_FOR_AGENT.md` prohíbe.
Con 1114 filas se aguanta; con 20.000 y varios usuarios, no. Y `daily()` vuelve a cargar todo otra vez.

**Arreglo**: tabla `similar` precomputada (top-K vecinos por canción) + `mixes` regenerados por el
worker de madrugada. La petición del usuario pasa a ser un `SELECT`.

### 🟠 I8 · `?energy=` devuelve 500 en vez de 422
`{"Baja":…, "Media":…, "Alta":…}[energy]` lanza `KeyError` con cualquier otro valor (`"alta"` en
minúscula incluido). **Arreglo**: `Enum` en la firma → FastAPI valida y documenta solo.

### 🟠 I9 · `SECRET_KEY` por defecto
`SECRET_KEY = os.environ.get("SECRET_KEY", "cambia-esta-clave")`. Si eso llega a producción, cualquiera
puede **firmarse un token de administrador**. **Arreglo**: si no hay `SECRET_KEY` y no estamos en
modo desarrollo, **abortar el arranque**. Nunca un valor por defecto que funcione.

### 🟠 I10 · Faltan endpoints que la UI da por hechos
Sin ellos hay pantallas que sencillamente no se pueden cablear (detalle en §8).
El más doloroso: `GET /library/reactions` devuelve **solo ids** → la pantalla "Me gusta" tendría que
pedir las canciones una a una (N+1).

---

## 4. Deuda menor (anotar, no bloquea)

- `db.query(...).get()` está obsoleto en SQLAlchemy 2.0 → `db.get(Model, id)`.
- `class Config: from_attributes` → `model_config = ConfigDict(from_attributes=True)` (Pydantic 2).
- `my_playlists()` hace un `COUNT` por playlist (N+1) → un `GROUP BY`.
- `remix=False` se ignora (`if remix:` solo filtra si es verdadero).
- `GET /tracks/{id}` no filtra por `status` (devuelve retiradas/cuarentena).
- `HTTPException` importado dentro de la función en `tracks.py`.
- `list_artists(limit=200)` sin tope máximo (`Query(le=...)`).
- `requirements.txt` **no incluye ninguna dependencia del backend** (fastapi, sqlalchemy, passlib,
  python-jose, uvicorn, python-multipart, email-validator). Nadie puede reproducir el entorno.
  Y falta el pin crítico `bcrypt==4.0.1`.
- **Cero tests.** Con contratos "congelados" y sin un solo test, "congelado" es una intención.
- **Deriva de cifras en la documentación**: `PLAYER_DESIGN` dice 833, `06_BUILD_GUIDE` y el brief dicen
  889, la realidad son 1114. Dejar de escribir números fijos en los docs, o generarlos.
- `01_SCHEMA.md` lista tablas que no existen en `models.py`: `smart_playlists`, `mixes`, `lyrics`,
  `similar`, `sessions`. Marcarlas como *previstas*, no como esquema.

---

## 5. ¿Encaja la arquitectura? Cuatro preguntas grandes sin responder

### 5.1 ¿Una base de datos o dos?
Hoy son dos, mal unidas (C1). **Recomendación: una.** El recolector y la API sobre la misma base
(SQLite ahora, Postgres después). La duplicidad no aporta nada y cuesta la integridad de los datos.

### 5.2 ¿Dónde viven los 9,5 GB de audio en producción?
**Ningún documento lo dice, y condiciona todo el despliegue.** Tres caminos:

| Opción | Cómo | Pros | Contras |
|---|---|---|---|
| **A. API en casa + túnel** (recomendado para empezar) | El backend corre en tu PC, expuesto por Cloudflare Tunnel o Tailscale | Coste 0; el audio no se mueve; HTTPS resuelto | Depende de que el PC esté encendido; subida de tu ADSL/fibra |
| **B. VPS + audio en object storage** (S3/R2/B2) | `/stream` redirige (302) a una URL firmada | Escala, no ocupa disco del VPS | Coste mensual; hay que subir 9,5 GB; egreso |
| **C. VPS con disco grande** | Todo junto | Simple mentalmente | Caro por GB; hay que subir y mantener sincronizado |

La decisión cambia `/stream`: en (A) y (C) es `FileResponse`; en (B) es un **redirect firmado** y el
backend no toca el audio. Conviene escribir `/stream` de forma que ese cambio sea una función.

### 5.3 ¿La cola de reproducción es del servidor o del cliente?
`06_BUILD_GUIDE.md` (FASE B) propone un **PlaybackService** en el backend con `set/next/prev/shuffle/
repeat`. **Recomiendo no hacerlo.** Eso es Spotify Connect (control remoto entre dispositivos), un
proyecto en sí mismo, y no es lo que se pide.

La cola pertenece al **cliente** (Redux en web, el player de Flutter en móvil). Del servidor solo hace
falta:
- `POST /library/{id}/play` (evento, ya existe),
- y opcionalmente `GET/PUT /me/playback-state` → `{track_id, position_ms, updated_at}` para
  "**continuar donde lo dejaste**" al cambiar de dispositivo. Eso son 20 líneas y da el 90 % del valor
  con el 5 % del trabajo.

### 5.4 ¿Adaptar los repos de UI o reescribir su capa de datos?
El repo React tiene servicios, slices e interfaces modelados sobre la API de Spotify (objetos anidados:
`album.images[]`, `artists[]`, `uri`, paginación `items/total/next`). Reescribir `interfaces/*` obliga a
tocar prácticamente todos los componentes.

**Recomendación: capa adaptadora.** Un módulo que traduzca `TrackOut` → la forma que la UI ya espera, y
dejar componentes, slices y páginas intactos. Se tocan ~10 ficheros (`axios.ts`, `services/*`,
`login`, `webPlayback`, `constants/spotify`) en lugar de ~60. Si más adelante interesa, se limpia.
Corolario: conviene que `/tracks` devuelva `{items, total, limit, offset}` en vez de una lista pelada,
porque es lo que la UI ya sabe consumir.

---

## 6. Calidad de los datos (fotografía real de `radiov.db`, 1114 canciones)

| Métrica | Valor | Comentario |
|---|---|---|
| Canciones | 1114 (backend: 889) | desincronizado |
| Con `bpm` / `energy` | 100 % | ✅ pero `energy` saturada (C3) |
| Con `valence` | **0 %** | I5 |
| Con `tags` | 100 % (397 combinaciones) | derivados, no analizados |
| Sin `cover_path` | 66 | 6 % sin carátula |
| Con `artist_image_path` | **0** | I6 (las fotos están en `artists`) |
| Sin `year` / `era` | 16 | |
| `is_remix = 1` | **7** | la faceta "remix" no tiene sentido con 7 filas |
| `explicit = 1` | 160 | **útil y no expuesto** (filtro infantil) |
| Con `feat` | 341 | **no expuesto** en `TrackOut` ni filtrable |
| Idiomas | es 600 · en 254 · **other 120** · it 54 · fr 43 · pt 43 | "other" es un 11 % sin clasificar |
| Géneros | pop 217 · **other 144** · reggaeton 143 · latin 93 · … | "other" es el 2.º "género" |
| Eras | 20s 483 · 10s 290 · 00s 225 · 90s 53 · 80s 29 · 70s 15 · 60s 3 | **muy sesgado a lo reciente** |
| Duplicados (artista+título) | 2 | |
| Duplicados `deezer_id` | 2 | falta `UNIQUE` en origen |
| Tamaño total | 9,53 GB | 1,4 GB es ruido blanco (C4) |

**Dos lecturas de producto**, más allá de los bugs:

- **El catálogo es muy joven**: 70 % de 2010 en adelante, 3 canciones de los 60. Una app con secciones
  "80s", "90s" y "Clásicos" se verá vacía. O se equilibra el descubrimiento por décadas, o la UI no
  promete esas secciones.
- **"other" en género (13 %) e idioma (11 %)** es demasiado para navegar por facetas. Merece una pasada
  de clasificación antes de construir pantallas que dependan de ello.

---

## 7. Contrato propuesto para `/stream` y `/media` (para cerrarlo)

```
GET /stream/{track_id}?t=<token>
    200 / 206  Content-Type: audio/mpeg
               Accept-Ranges: bytes
               Content-Range: bytes {a}-{b}/{total}     (en 206)
               Content-Length, ETag (mtime+size), Cache-Control: private, max-age=3600
    401  token ausente / caducado / de otra canción
    404  track inexistente o status != descargada
    410  el fichero ya no está en disco  → dispara re-descarga en el worker
    416  rango no satisfacible
```

- **Implementación**: `FileResponse(path, media_type="audio/mpeg")` — starlette 1.6 ya gestiona
  `Range`, `206` y `416`. **No escribir el manejo de rangos a mano.**
- **Ruta**: `os.path.join(MUSIC_ROOT, track.file_path_relativo)` + comprobación de que el resultado
  sigue dentro de `MUSIC_ROOT` (`os.path.commonpath`) → sin *path traversal*.
- **Token**: JWT corto `{tid, uid, exp}` firmado con `SECRET_KEY`; 5-10 min; se pide con el Bearer
  normal o se sirve ya incrustado en `TrackOut.stream_url`.

```
GET /media/covers/{fichero}
GET /media/artists/{fichero}
```
Montar `StaticFiles` sobre `MEDIA_ROOT/covers` y `MEDIA_ROOT/artists`. **Nunca** servir el
`cover_path` que venga de la BD como ruta libre: la BD guarda el nombre del fichero, no una ruta.
Cachear agresivo (`max-age=31536000, immutable`), son inmutables por nombre.

---

## 8. API que falta para que la UI se pueda construir

| Endpoint | Para qué | Prioridad |
|---|---|---|
| `GET /stream/{id}` · `GET /media/**` | reproducir y pintar | 🔴 bloqueante |
| `GET /library/liked` → `TrackOut[]` | pantalla "Me gusta" sin N+1 | 🔴 |
| `DELETE /playlists/{id}` · `DELETE /playlists/{id}/tracks/{track}` | editar playlists | 🔴 |
| `PATCH /playlists/{id}` (nombre/desc) · `PUT /playlists/{id}/order` | renombrar / reordenar | 🟠 |
| `GET /artists/{name}` | página de artista (móvil la necesita) | 🔴 |
| `GET /albums/{artist}/{album}` o `GET /tracks?album=` | página de álbum | 🟠 |
| `GET /search?q=` (multi-tipo + autocompletado, FTS) | buscador real | 🟠 |
| `{items,total,limit,offset}` en `/tracks` | paginación e *infinite scroll* | 🟠 |
| `sort=rank\|year\|random` en `/tracks` | "populares", "aleatorio" | 🟠 |
| `GET /facets` (géneros, eras, moods, idiomas con conteo) | chips sin hardcodear | 🟠 |
| `explicit=false` en `/tracks` y `/recommend` | **modo familiar / infantil** | 🟠 |
| `GET /playlists/system` · `GET /recommend/trending` | Home ("Trending", "Novedades") | 🟠 |
| `POST /auth/refresh` | no echar al usuario a las 24 h | 🟠 |
| `GET/PUT /me/playback-state` | "continuar donde lo dejaste" | 🟢 |
| `GET /wrapped` · `GET /stats` | pantalla de hábitos | 🟢 |
| `POST /tracks/{id}/report` | "esta canción está mal" → blacklist + re-descarga | 🟠 (ver C4) |
| `feat`, `rank`, `explicit`, `stream_url` en `TrackOut` | ya están en la BD, no se exponen | 🟠 |

---

## 9. UI y funcionalidades: qué debe haber (y no está pensado)

`05_UI.md` cubre bien la estructura. Lo que falta es de **experiencia de reproducción**, que es donde
se nota si una app de música casera está bien hecha o no:

### Lo que de verdad marca la diferencia

1. **Normalización de volumen (ReplayGain / LUFS).** ⚠️ **El punto más importante de esta sección.**
   El audio viene de YouTube: cada canción tiene un volumen distinto y el salto entre temas es
   brutal. Es *el* defecto que delata a un reproductor casero. Se calcula el *loudness* una vez en la
   ingesta (`ffmpeg -af loudnorm` o `pyloudnorm`), se guarda como `gain_db` en `tracks`, y el player
   aplica la ganancia con un `GainNode` (Web Audio) o el equivalente en Flutter. Barato y transformador.
2. **Media Session API** en la web: controles en la pantalla de bloqueo del móvil, en los auriculares
   y en el centro de notificaciones, con carátula. Son ~30 líneas de JS y parece una app nativa.
3. **Precarga de la siguiente canción** (prefetch del `/stream` siguiente cuando quedan ~20 s) y
   **crossfade corto**. Sin esto hay un silencio entre temas que se nota mucho.
4. **Offline en móvil**: el repo Flutter ya tiene caché. Para una app familiar de música propia,
   descargar en el móvil es de las funciones más valoradas.
5. **Shuffle "de verdad"**: el aleatorio uniforme repite artistas y suena mal. Barajar con
   restricción de "no dos del mismo artista seguidos" (esto es literalmente lo que Spotify hace).

### Funcionalidades de producto que faltan en los documentos

- **Perfiles familiares con filtro de contenido explícito** (`explicit` ya está en la BD, 160 temas).
  Es multi-usuario "para familia y amigos": esto no es opcional, es la primera petición que llegará.
- **Reproducción continua / "Flow"**: cuando acaba la cola, seguir con la radio del último tema en vez
  de parar. Con `radio()` ya implementado es casi gratis y cambia la sensación de la app.
- **"Añadir a continuación"** en la cola (distinto de "añadir al final").
- **Sleep timer** (apagar en X minutos) — trivial y muy usado.
- **Historial de reproducción** navegable ("escuchado recientemente"), que ya se puede sacar de `plays`.
- **Contador de reproducciones por canción** visible: hace que la biblioteca se sienta *tuya*.
- **Marcar canción defectuosa** (ver C4) — con un 20 % sin verificar, hace falta.
- **Estado vacío honesto**: con 1114 canciones habrá búsquedas sin resultados. La UI debería ofrecer
  "pedir esta canción" → encolarla en el recolector. Convierte una frustración en una función.
- **Letras** (`lyrics` está en el esquema y no existe la tabla).
- **PWA instalable**: para el móvil, antes de tener el APK de Flutter, una PWA da el 80 % del valor.

### Lo que yo quitaría del plan

- **PlaybackService con cola en el servidor** (§5.3): mucho trabajo, poco valor aquí.
- **Selector de dispositivos / tabla `devices`**: es Spotify Connect. Fuera.
- **Cassandra**: ya está decidido que no, pero conviene borrar la sección del roadmap para que ningún
  agente futuro la reabra. `ARCHITECTURE.md` dedica media página a justificarla.
- **Ecualizador**: mucho código para poco uso. Después de la normalización de volumen, si acaso.

---

## 10. Seguridad, privacidad y legal

- **`SECRET_KEY` por defecto** (I9): abortar el arranque si falta.
- **Registro abierto**: `POST /auth/register` no pide nada. Si esto se expone a internet, cualquiera se
  crea una cuenta y se descarga tu biblioteca. → **código de invitación** o registro solo por admin.
- **Sin límite de intentos en `/auth/login`**: fuerza bruta trivial. → *rate limit* por IP.
- **CORS `allow_origins=["*"]`**: aceptable con Bearer (no hay cookies), pero hay que **cerrarlo** en
  producción; si algún día se usan cookies, `*` deja de ser válido y falla de forma confusa.
- **`/media` y `/stream`**: servir siempre desde una raíz fija con validación de ruta (§7).
- **Contraseñas**: bcrypt 4.0.1 ✅. Mínimo 8 caracteres es flojo → 10 y comprobación contra lista de
  contraseñas comunes.
- **Copias de seguridad**: el audio es reemplazable (se puede volver a descargar); **la base de datos
  no** — contiene 1114 fichas enriquecidas y todas las señales de los usuarios. Un `.db` copiado a
  diario a otro disco es la póliza más barata del proyecto. Hoy no existe.
- **Legal**: mientras sea un catálogo personal en tu red, es un asunto privado. En el momento en que
  se abre por HTTPS a "familia y amigos" con cuentas, pasa a ser **distribución** de audio derivado de
  YouTube, y eso es otra cosa jurídicamente. La mitigación razonable: acceso solo por invitación,
  círculo cerrado, sin indexar, sin ánimo de lucro, y no publicitarlo. Conviene que esté escrito y
  decidido conscientemente, no por omisión.

---

## 11. Plan revisado (qué haría, en qué orden)

**FASE 0 · Cimientos (medio día, antes de tocar nada más)**
1. Arreglar `GET /artists` (C2) y sacar el `UPDATE` del endpoint.
2. Convertir `migrate_sqlite` en UPSERT no destructivo por `deezer_id`; `UNIQUE(deezer_id)` en
   `radiov.db`; **`tracks.id` inmutable** (C1).
3. Rutas relativas + `MUSIC_ROOT` / `MEDIA_ROOT` (I1).
4. Alinear `/library` con `02_API.md` (body JSON) (C5).
5. `requirements-backend.txt` completo con `bcrypt==4.0.1`.
6. Cuatro tests de humo (register/login, `/tracks`, `/artists`, migración idempotente).

**FASE 1 · Reproducción (lo que desbloquea web y móvil)**
7. `/stream/{id}` con ticket firmado + `/media/**` montado (§7).
8. `seconds_listened` + `context` en `plays` (I3).
9. `GET /library/liked`, `DELETE` de playlists y de canciones, `GET /artists/{name}` (§8).
10. `explicit` como filtro; `feat`, `rank`, `stream_url` en `TrackOut`.

**FASE 2 · Sanear los datos (en paralelo, es del recolector)**
11. Puerta de calidad + estado `cuarentena`; limpiar las 7 filas basura y 1,4 GB (C4).
12. Recalcular `energy` por percentil y regenerar `tags` (C3).
13. Decidir sobre `valence`/`danceability`: calcularlos o quitarlos del documento 03 (I5).
14. `gain_db` (ReplayGain/LUFS) en la ingesta → normalización de volumen (§9.1).

**FASE 3 · Web (React)** — con la capa adaptadora de §5.4, no reescribiendo interfaces.
Añadir Media Session API, prefetch de la siguiente y shuffle con restricción de artista.

**FASE 4 · Playlists automáticas + worker** — `similar` precomputada y `mixes` nocturnos (I7); así
`/recommend` pasa a ser un `SELECT`.

**FASE 5 · Móvil (Flutter)** — con offline, que es donde el repo ya aporta.

**FASE 6 · Despliegue** — decidir §5.2 primero, luego Docker + Alembic + backup + HTTPS.

> Cambio respecto al plan actual: **la FASE 0 no existía** y **el saneado de datos estaba en la FASE E
> "opcional"**. Ambos son prerrequisitos: construir dos clientes sobre un catálogo con un 20 % sin
> verificar y una feature saturada es construir sobre arena.

---

## 12. Checklist accionable (copiable a issues)

- [ ] **C1** `migrate_sqlite` → UPSERT por `deezer_id`, sin borrar señales de usuario
- [ ] **C1** `UNIQUE(deezer_id)` en `radiov.db` · `tracks.id` declarado inmutable
- [ ] **C2** `text()` en `artists.py` + mover `track_count` al worker
- [ ] **C3** `energy` por percentil + guardar `rms` crudo + regenerar `tags`
- [ ] **C4** puerta de calidad en la ingesta + estado `cuarentena` + limpiar 7 filas / 1,4 GB
- [ ] **C4** recalcular `match_score` en las 221 filas a 0
- [ ] **C5** `/library/*` a body JSON · decidir FTS vs `ILIKE` y sincronizar `02_API.md`
- [ ] **I1** rutas relativas + `MUSIC_ROOT` / `MEDIA_ROOT`
- [ ] **I2/§7** `/stream/{id}` con ticket firmado + `/media/**` con `StaticFiles`
- [ ] **I3** `seconds_listened` + `context` en `plays`
- [ ] **I4** prior de popularidad (`rank`) en el score
- [ ] **I5** decidir sobre `valence`/`danceability`
- [ ] **I6** resolver la foto de artista vía `artists` y corregir `05_UI.md`
- [ ] **I7** tabla `similar` + `mixes` nocturnos
- [ ] **I8** `Enum` en `?energy=`
- [ ] **I9** abortar el arranque sin `SECRET_KEY`
- [ ] **I10** endpoints de §8
- [ ] `requirements-backend.txt` + `bcrypt==4.0.1` + tests de humo + Alembic
- [ ] Registro por invitación + *rate limit* en login + backup diario del `.db`
- [ ] `gain_db` (normalización de volumen) + Media Session API + prefetch + shuffle con restricción
- [ ] Filtro de contenido explícito (perfil familiar)
- [ ] Decidir §5.2 (dónde viven los 9,5 GB) antes de escribir el `docker-compose`

---

*Revisión generada leyendo el código y los datos reales, no la documentación. Donde documento y código
discrepan, este informe describe el código.*
