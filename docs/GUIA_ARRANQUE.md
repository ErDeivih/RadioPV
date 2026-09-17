# ▶️ RadioPV · Qué tiene que hacer David, exactamente

> Todo en **PowerShell**, desde `F:\EspacioCodigo\RadioPV`. Cada paso dice qué debe salir.
> Si algo no coincide, apúntalo y sigue: no hace falta arreglarlo sobre la marcha.

---

## PASO 0 · Copia de seguridad (30 segundos, no te lo saltes)

```powershell
cd F:\EspacioCodigo\RadioPV
$stamp = Get-Date -Format "yyyyMMdd-HHmm"
New-Item -ItemType Directory -Force -Path data\backup | Out-Null
Copy-Item data\radiov.db  "data\backup\radiov-$stamp.db"
Copy-Item data\backend.db "data\backup\backend-$stamp.db"
```

---

## PASO 1 · Parar el recolector

El análisis del paso 2 lee cada MP3 del catálogo. Si el recolector sigue descargando, **nunca
termina**: cada hora añade canciones nuevas por analizar.

Cierra la ventana donde corre `run_agent.py` o el agente de `radiov`. Comprueba que no queda ninguno:

```powershell
Get-Process python -ErrorAction SilentlyContinue | Select-Object Id, StartTime, Path
```

---

## PASO 2 · La pasada de análisis (T-24) — **déjala por la noche**

Es lo que hace que el volumen deje de saltar entre canciones y que las facetas de energía
signifiquen algo. Son ~2.300 ficheros y ~19 GB: **tarda horas**.

```powershell
# primero una prueba corta, para ver que funciona
.venv\Scripts\python.exe scripts\analisis_completo.py --limit 20

# si va bien, la pasada completa (déjala toda la noche)
.venv\Scripts\python.exe scripts\analisis_completo.py
```

**Al terminar, comprueba:**

```powershell
.venv\Scripts\python.exe -c "import sqlite3;c=sqlite3.connect('data/radiov.db');print('rms:',c.execute('select count(*) from tracks where rms is not null').fetchone()[0]);print('gain_db:',c.execute('select count(*) from tracks where gain_db is not null').fetchone()[0]);print('energy=1.0:',c.execute('select count(*) from tracks where energy>=1.0').fetchone()[0]);print('total:',c.execute('select count(*) from tracks').fetchone()[0])"
```

- `rms` y `gain_db` deben acercarse al total.
- **`energy=1.0` debe caer de ~1.300 a casi 0.** Eso es la señal de que el percentil funcionó.

---

## PASO 3 · Mover la basura en cuarentena (D1) — 1 minuto

```powershell
.venv\Scripts\python.exe scripts\mover_cuarentena.py            # en seco, enseña qué movería
.venv\Scripts\python.exe scripts\mover_cuarentena.py --apply
```

Los ficheros van a `E:\Musica\_cuarentena\`. **No se borra nada.** Si en una semana no echas nada
de menos, borras esa carpeta tú.

---

## PASO 4 · Sincronizar el catálogo con la app

```powershell
$env:PYTHONPATH = "F:\EspacioCodigo\RadioPV\backend"
.venv\Scripts\python.exe -m migrate_sqlite
```

Debe decir `nuevas=… actualizadas=… retiradas=…`. Es **no destructiva**: no toca tus me-gusta ni tus
playlists. Puedes ejecutarla las veces que quieras.

---

## PASO 5 · Arrancar el backend

```powershell
# desde la RAÍZ del repo. --host 0.0.0.0 hace falta para entrar desde el móvil
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

Comprueba en el navegador: **http://127.0.0.1:8000/health** → `{"status":"ok", "tracks": …}`

Déjalo abierto. **En otra ventana**, el worker (radio, mixes, mantenimiento):

```powershell
cd F:\EspacioCodigo\RadioPV
$env:PYTHONPATH = "F:\EspacioCodigo\RadioPV\backend"
.venv\Scripts\python.exe -m app.workers
```

---

## PASO 6 · Arrancar la web

**En una tercera ventana:**

```powershell
cd F:\EspacioCodigo\RadioPV\frontend
yarn install                                       # solo la primera vez
yarn dev
```

Abre lo que diga la consola (normalmente **http://localhost:5173**).

### Lo que tienes que probar, en este orden

| # | Qué | Qué debe pasar |
|---|---|---|
| 1 | Registrarte | entras y ves la portada con tus canciones |
| 2 | **Dar al play** | **suena** |
| 3 | **Arrastrar la barra** | salta al instante y sigue sonando |
| 4 | Dejar que acabe la canción | **encadena sola** con la siguiente |
| 5 | Comparar volumen entre dos canciones distintas | **parecido** (si hiciste el paso 2) |
| 6 | Buscar "bad bunny" | resultados con pestañas |
| 7 | 👍 en tres canciones y recargar la portada | "Para ti" cambia |
| 8 | Ajustes → ocultar contenido explícito | desaparecen las marcadas |

Si algo de esto falla, **abre la consola del navegador (F12)** y guarda los tres primeros errores:
con eso el agente lo arregla en una ronda.

---

## PASO 7 · Ponerlo en el móvil (esto es "la app")

1. Instala **Tailscale** en el PC y en el móvil, con la misma cuenta.
2. En el PC: `tailscale ip -4` → apunta la IP (algo como `100.x.y.z`).
3. En `frontend\.env`, pon esa IP:
   ```
   VITE_API_URL=http://100.x.y.z:8000
   ```
4. Reconstruye y sirve la web:
   ```powershell
   cd F:\EspacioCodigo\RadioPV\frontend
   yarn build
   yarn preview --host 0.0.0.0 --port 3000
   ```
5. En el móvil (con Tailscale conectado), abre `http://100.x.y.z:3000`.
6. Menú del navegador → **"Añadir a pantalla de inicio"**. Ya tienes el icono.

**Compruébalo**: bloquea el móvil con la música sonando. Deben salir los controles y la carátula en
la pantalla de bloqueo. Eso es lo que hace que parezca una app nativa.

> ⚠️ El `yarn preview` no hace *fallback* de SPA: si entras directo a una URL interna te dará 404.
> Para uso diario está bien (navegas desde la portada); para el despliegue de verdad está el
> `Caddyfile` de [`13_DEPLOY_SPEC.md`](13_DEPLOY_SPEC.md), que sí lo hace.

---

## PASO 8 · Reanudar el recolector

Cuando el análisis del paso 2 haya terminado, vuelve a lanzar el recolector como siempre. A partir de
ahora el worker se encarga solo de analizar lo que vaya entrando.

---

## Sobre Flutter (la app nativa)

**No hace falta.** Lo del paso 7 ya es la app en tu móvil.

Si algún día la quieres nativa: el problema del agente es que su entorno no puede descargar el SDK.
Tú sí puedes, porque es tu ordenador y tiene internet normal. Sería:

```powershell
C:\flutter\flutter\bin\flutter.bat --version    # descarga el SDK la primera vez, tarda un rato
C:\flutter\flutter\bin\flutter.bat doctor
```

Con `C:\flutter\bin\cache` ya poblado, el agente puede ejecutar `flutter analyze` sin red. Pero es
trabajo de decenas de ficheros para llegar a algo que ya tienes con la PWA. **Mi recomendación:
déjalo aplazado.**

---

## Nota · por qué se renombró `app.py`

`python -m app.workers` fallaba con `ModuleNotFoundError: __path__ attribute not found on 'app'`.
La causa: el `app.py` de la raíz (la UI antigua de Streamlit) **tapaba** al paquete `backend/app/`,
porque Python mira el directorio actual antes que el `PYTHONPATH`. Por eso además salían decenas de
avisos de Streamlit: estaba importando la app vieja.

Renombrado a **`app_streamlit_legacy.py`**. Ya no tapa nada y el worker arranca. Si algún día quieres
la UI antigua: `.venv\Scripts\python.exe -m streamlit run app_streamlit_legacy.py`.

---

## Si algo se rompe

| Síntoma | Causa casi segura |
|---|---|
| `/health` no responde | el backend no arrancó: mira los errores en su ventana |
| La web carga pero sale vacía | el backend no está arriba, o `VITE_API_URL` apunta mal |
| Suena pero no se puede arrastrar la barra | hay un proxy delante que se come el `Range` |
| La barra avanza y **no se oye** | error de CORS en `/stream`: mira la consola (F12) |
| Deja de sonar tras una pausa larga | el token de streaming caducó; se recupera solo, si no, recarga |
| El volumen salta mucho entre canciones | el paso 2 no ha terminado (`gain_db` vacío) |
| Entrar por "reggaeton" enseña rap | pendiente T-27, reclasificar géneros |

---

**Limpieza**: puedes borrar `F:\EspacioCodigo\RadioPV\_tmp\` (son los .tgz y la copia de la BD que
usó Claude para verificar en el navegador).
