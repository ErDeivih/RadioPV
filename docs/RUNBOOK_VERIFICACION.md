# ▶️ RadioPV · Vuelta de verificación (≈20 min, la hace David)

> El agente lleva ~10 rondas escribiendo código de UI que **no puede ejecutar**. Cada ronda añade
> riesgo sin añadir certeza. Esta es la sesión que convierte todo eso en información: ejecutar una
> vez, apuntar qué falla, y devolvérselo. **Es la tarea de mayor valor del proyecto ahora mismo.**
>
> Todo se ejecuta en **PowerShell, en `F:\EspacioCodigo\RadioPV`**. Cada paso dice qué debe pasar.
> Si algo no coincide, **apúntalo y sigue**: no hace falta arreglarlo sobre la marcha.

---

## Paso 0 · Copia de seguridad (30 s)

```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmm"
New-Item -ItemType Directory -Force -Path data\backup | Out-Null
Copy-Item data\radiov.db  "data\backup\radiov-$stamp.db"
Copy-Item data\backend.db "data\backup\backend-$stamp.db"
```

---

## Paso 1 · Las dos cosas que solo puedes ejecutar tú

### 1a · Mover la cuarentena (D1) — ~1,6 GB, reversible

```powershell
.venv\Scripts\python.exe scripts\mover_cuarentena.py            # primero en seco
.venv\Scripts\python.exe scripts\mover_cuarentena.py --apply
```

**Esperado**: los ficheros aparecen bajo `E:\Musica\_cuarentena\` y las filas siguen en la BD como
`cuarentena`. **Nada se borra.** Si en una semana no echas nada de menos, borras esa carpeta tú.

### 1b · La pasada de análisis (T-24) — la que da `energy` y `gain_db`

Estado real ahora: `rms` poblado en **6 de 2268** · `gain_db` en **10** · `energy = 1.0` en **1329**
(59 % del catálogo sigue saturado). **Hasta que esto corra, la normalización de volumen y las facetas
de energía no existen**, por mucho que el código esté escrito.

```powershell
# el recolector debe estar PARADO (si no, nunca converge: sigue añadiendo canciones)
.venv\Scripts\python.exe -m app.workers          # o scripts\analisis_completo.py si el agente lo dejó suelto
```

⚠️ Son ~2268 ficheros y ~19 GB: **esto tarda horas**. Déjalo por la noche. No hace falta esperarlo
para seguir con el paso 2 — el reproductor funciona sin `gain_db`, solo sin normalizar el volumen.

**Comprobación al terminar**:

```powershell
.venv\Scripts\python.exe -c "import sqlite3;c=sqlite3.connect('data/radiov.db');print('rms',c.execute('select count(*) from tracks where rms is not null').fetchone()[0]);print('gain',c.execute('select count(*) from tracks where gain_db is not null').fetchone()[0]);print('energy=1',c.execute('select count(*) from tracks where energy>=1.0').fetchone()[0])"
```
`energy=1` debe bajar de 1329 a **cerca de 0** (el percentil reparte los valores).

---

## Paso 2 · Levantar el backend

```powershell
.venv\Scripts\python.exe -m migrate_sqlite       # sincroniza el catálogo (no destructivo)
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

**Esperado**: arranca sin excepciones y `http://127.0.0.1:8000/health` responde `{"status":"ok"}`.
`--host 0.0.0.0` hace falta para probar desde el móvil después.

En otra ventana:

```powershell
curl http://127.0.0.1:8000/tracks?limit=3
curl http://127.0.0.1:8000/artists?limit=3
curl http://127.0.0.1:8000/facets
```

**Esperado**: los tres responden 200 con datos. `/tracks` debe traer la cabecera `X-Total-Count`.

---

## Paso 3 · La prueba del `Range` (la que valida todo `/stream`)

```powershell
# 1) token de sesión
$t = (Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/auth/login -Body @{username='TU_EMAIL'; password='TU_CLAVE'}).access_token
# 2) token de streaming
$s = (Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/auth/stream-token -Headers @{Authorization="Bearer $t"}).token
# 3) pedir el primer kilobyte
curl.exe -s -D - -o NUL "http://127.0.0.1:8000/stream/1?t=$s" -H "Range: bytes=0-1023"
```

**Esperado, literalmente**:

```
HTTP/1.1 206 Partial Content
content-range: bytes 0-1023/<algún número grande>
accept-ranges: bytes
content-type: audio/mpeg
```

Si sale **200** en vez de 206 → el `Range` no se está aplicando (mira que no haya un proxy delante).
Si sale **404** → esa canción no existe o no está `descargada`: prueba otro id de `/tracks`.
Si sale **410** → la fila existe pero el MP3 no está en disco (ruta mal resuelta).

---

## Paso 4 · El frontend (aquí es donde se juega todo)

```powershell
cd frontend
yarn dev
```

Abre lo que diga (normalmente `http://127.0.0.1:5173`), regístrate o entra, y comprueba **cinco cosas
en este orden**. Ten abierta la consola del navegador (F12) y la pestaña **Red**.

| # | Qué probar | Esperado | Si falla, apunta |
|---|---|---|---|
| 1 | Que carga el Home | filas con carátulas, sin peticiones a `api.spotify.com` en la pestaña Red | qué petición da error y su código |
| 2 | **Darle al play** | **suena** | si la barra avanza pero **no hay sonido**, es el problema de CORS del `<audio>` (ver abajo) |
| 3 | **Arrastrar la barra** | salta al instante; en Red se ven peticiones con **206** | si recarga la canción entera o no salta |
| 4 | Buscar algo | resultados al escribir | |
| 5 | 👍 en una canción y recargar `/recommend` | la lista cambia | |

### ⚠️ El fallo que espero que aparezca (y que ya he corregido)

El código tenía `crossOrigin = 'use-credentials'` en el `<audio>` (era un error **mío**, estaba en la
spec y el agente lo copió). Con credenciales, el navegador exige `Access-Control-Allow-Credentials` y
un origen concreto; al no cumplirse, el elemento queda *tainted* y el `GainNode` devuelve **silencio,
sin error claro**: la barra avanza, el reloj corre, y no se oye nada.

Ya está cambiado a `'anonymous'` en `playerController.ts` y `usePlayer.ts`, y he ampliado
`expose_headers` en `main.py` con `Content-Range`, `Accept-Ranges` y `Content-Length`.

**Si aun así no suena**: mira la consola. Un mensaje de CORS mencionando `/stream` confirma que sigue
por ahí; si no hay ninguno y el `AudioContext` aparece como `suspended`, es que el navegador exige un
gesto del usuario (hay que llamar a `ctx.resume()` dentro del click).

---

## Paso 5 · Devolverle esto al agente

Copia y rellena:

```
Vuelta de verificación hecha. Resultados:
- Backend arranca: SÍ / NO (error: ...)
- /tracks, /artists, /facets: OK / fallan (...)
- /stream con Range: 206 / 200 / otro (...)
- Home carga: SÍ / NO (...)
- Suena al dar al play: SÍ / NO (consola dice: ...)
- El seek funciona: SÍ / NO
- Búsqueda: OK / (...)
- Like cambia /recommend: SÍ / NO
- D1 (mover cuarentena): hecho / pendiente
- T-24 (pasada de análisis): lanzada / terminada / pendiente  → rms=___ gain=___ energy1=___
Errores de consola que he visto (pega aquí los 3 primeros):
...
```

Con eso el agente arregla en una ronda lo que a ciegas le costaría cinco.

---

## Prioridad de lo que queda (respuesta a la pregunta del agente)

**Primero F3 (play-flow y pantallas), después F5 (móvil).** No es por preferencia: el flujo de
reproducción es la pieza con más trampas (gesto del usuario para el `AudioContext`, CORS del
`<audio>`, `Range`, refresco del token a mitad de canción, la ganancia). Hacer el móvil antes
significa escribir **una segunda implementación a ciegas de un flujo que todavía no se ha visto
funcionar ni una vez** — y cuando falle, no se sabrá si es del backend, del contrato o del cliente.

Cuando el play-flow funcione en web, el Flutter es una traducción de algo ya probado.
