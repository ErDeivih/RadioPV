# 🧪 RadioNano · Auditoría final + orden de cierre

> Auditoría del **2026-08-30**, hecha ejecutando el backend real con una copia de `backend.db`,
> `pytest`, `vite build` y **Chromium con Playwright** sobre las 8 rutas de la app. No es una
> lectura de código: los números de abajo salen de correrlo.
>
> Incluye el **renombrado a RadioNano** y la batería de pruebas que falta antes de dar el proyecto
> por bueno.

---

## 0. Resultado de la auditoría

| Comprobación | Resultado |
|---|---|
| `pytest` (backend) | ✅ **36 pasan** (los 4 de `test_quality` necesitan `radiov/`, no se pudieron correr en el contenedor) |
| `vite build` | ✅ compila en 9,3 s |
| Home · Browse · Búsqueda · Genre · Artist · Liked · Ajustes · 404 | ✅ **las 8 renderizan, sin 4xx, sin errores de JS** |
| Llamadas a Spotify | ✅ **ninguna** |
| Móvil 390 px | ✅ `scrollWidth = 390` → **no se sale horizontalmente** |
| `console.log` / `debugger` sueltos | ⚠️ 2 reales (ver A3) |
| `TODO` / `FIXME` | ✅ ninguno |

**La app está sana.** Lo que queda son acabados, un fallo de sesión caducada, y la ausencia total de
pruebas de interfaz.

---

## 1. 🔴 El único fallo de comportamiento encontrado

### A1 · Con la sesión caducada, la app se queda EN BLANCO

Reproducido: con un token de más de 24 h, `GET /auth/me` devuelve 401 y la portada se queda en
**538 bytes de DOM** — pantalla vacía, sin mensaje, sin formulario de acceso. Con token válido son
38.392 bytes.

**Esto le va a pasar a David mañana**, porque el token dura 24 h.

**Qué hacer**: ante un 401 en `/auth/me` (o en cualquier petición), limpiar el token y **abrir el
modal de acceso**, no dejar la pantalla muerta. `axios.ts` ya limpia el token en el 401; falta que
el estado de la aplicación reaccione y muestre el login. Añadir un test que lo fije.

---

## 2. 🟠 Renombrado a **RadioNano**

**Regla de oro: se renombra lo que ve el usuario, NO los identificadores internos.** Cambiar claves
técnicas rompe sesiones guardadas, cachés y rutas de datos sin ganar nada.

### SÍ se renombra (lo visible)

| Dónde | Qué |
|---|---|
| `frontend/index.html` | `<title>` |
| `frontend/public/manifest.json` | `name`, `short_name`, `description` |
| `frontend/.env` | `VITE_APP_NAME` |
| `frontend/src/i18n/**` | todos los textos: "Inicia sesión en RadioPV" → RadioNano, etc. |
| `frontend/src/**` | cualquier "RadioPV" en un literal que se pinte en pantalla |
| `backend/app/main.py` | `FastAPI(title=...)` |
| `README.md` y `docs/*.md` | prosa y títulos |
| `package.json` | `name` (hoy es `spotify-client`) |

### NO se renombra (interno; romperlo cuesta y no aporta)

```
radiopv_hide_explicit · radiopv_volume · radiopv_repeat   (claves de localStorage: se perderían los ajustes)
radiopv:track: · radiopv:artist: · radiopv:album: · radiopv:playlist: · radiopv:user:   (URIs internas)
RADIOPV_ENV   (variable de entorno; cambiarla rompe los arranques y el docker-compose)
radiopv.worker  (nombre del logger)
radiov/  ·  data/radiov.db  ·  data/backend.db   (paquete y ficheros de datos)
F:\EspacioCodigo\RadioPV   (la carpeta del proyecto: NO moverla)
```

Si algún día se quieren renombrar las claves de `localStorage`, se hace **con migración**: leer la
clave vieja, escribir la nueva, borrar la vieja. No en este cambio.

### Iconos y logo — **ya hechos por Claude**, no rehacerlos
`frontend/public/`: `icon-192.png`, `icon-512.png`, `favicon-64.png`, `logo.png` (cara + "RadioNano")
y `avatar-default.png`. Ya están enganchados en `index.html`, `manifest.json`, `constants/spotify.ts`
(avatar y portada por defecto) y `LoginModal`.

### Comprobación de que el renombrado está completo
```powershell
findstr /S /I /M "RadioPV" frontend\src frontend\index.html frontend\public\manifest.json README.md
```
Solo deben quedar los identificadores internos de la lista de arriba.

---

## 3. 🟠 Lo que falta de pruebas (esto es el grueso del trabajo)

Hoy hay **40 pruebas de backend y CERO de interfaz**. Toda la web se ha validado a mano.

### B1 · Pruebas de extremo a extremo con Playwright
`npm i -D @playwright/test` en `frontend/`, carpeta `frontend/e2e/`. Un `webServer` en la
configuración que levante `vite preview`; el backend se asume corriendo en `VITE_API_URL`.

Casos mínimos, uno por fichero:
1. **acceso.spec.ts** — registro con código de invitación · acceso · el token persiste al recargar ·
   **sesión caducada → sale el formulario de acceso, no una pantalla en blanco** (fija A1).
2. **reproduccion.spec.ts** — clic en una canción → `currentTime` avanza · arrastrar la barra emite
   una petición con `Range` y responde 206 · al acabar encadena la siguiente · el `GainNode` aplica
   `gain_db`.
3. **navegacion.spec.ts** — las 8 rutas renderizan, **cero peticiones 4xx** y cero errores de JS
   (assertion sobre `page.on('pageerror')`).
4. **biblioteca.spec.ts** — me gusta → aparece en "Canciones guardadas" · crear playlist, añadir,
   reordenar, quitar y borrar.
5. **familiar.spec.ts** — con el filtro activo, **ninguna** canción explícita en ninguna lista.
6. **movil.spec.ts** — a 390 px `scrollWidth === 390` en las 8 rutas (nada se sale de la pantalla).

### B2 · Pruebas de componente (Vitest)
`adapt.ts` (que `toTrack` produzca la forma que espera la UI), `token.ts`, el barajado con separación
de artista, y el cálculo de ganancia `10^(gain_db/20)`.

### B3 · Backend: los huecos que quedan
- `/stream`: petición de rango **inválido** → 416; `Range: bytes=100-` (abierto por la derecha).
- `migrate_sqlite`: test que ejecute la migración **dos veces** y afirme que los `id` no cambian y
  que las reacciones siguen (hoy se comprueba a mano; es el fallo más caro del proyecto).
- El filtro `explicit` en **todos** los endpoints de listas, no solo en `/tracks`.
- Un usuario **no puede** leer ni modificar la playlist de otro (404, no 403).

### B4 · Accesibilidad
`npm i -D @axe-core/playwright` y una comprobación de axe en las 8 rutas. Fallar el test con
cualquier violación *serious* o *critical*.

### B5 · Humo de despliegue
`scripts\humo.ps1` ya existe: ampliarlo con `/stream` con `Range` (esperando 206), `/media/...` y
`/facets`, y que devuelva código de salida distinto de 0 si algo falla.

---

## 4. 🟡 Acabados

| | Qué | Dónde |
|---|---|---|
| A2 | `Query.get()` está obsoleto en SQLAlchemy 2.0 → `db.get(Model, id)` | `security.py:68` y donde quede |
| A3 | `console.log(error)` sueltos → usar el toast de error de F5 | `store/slices/home.ts:149`, `playlist.ts:136` |
| A4 | `class Config` de Pydantic v1 → `model_config = ConfigDict(...)` | `schemas.py` |
| A5 | `.gitignore` no cubre `frontend/.env`, `_tmp/`, `frontend/build/`, `mobile/build/` | `.gitignore` |
| A6 | Vaciar `frontend/_to_delete/` y el código muerto de C2 (`episodes`, `categories`, `devices`) | `frontend/src` |
| A7 | Ficheros `.env` escritos desde PowerShell salen con **BOM** y vite no lee la variable. Documentarlo en el README con `Set-Content -Encoding utf8NoBOM` | `README.md` |
| A8 | El icono de la pestaña y el manifiesto ya son los nuevos: **no regenerarlos** | — |

---

## 5. 🟡 Datos (esto es de David, no del agente)

**T-27 · Reclasificar géneros.** Sigue igual: `/tracks?genre=reggaeton` devuelve *Tory Lanez – Hurts
Me* y *Nobu Woods – ISSUES*. Hay 144 canciones en `other`. La pantalla Genre es correcta; lo que
enseña, no. Mientras no se arregle, navegar por géneros da mala impresión.

---

## 6. Orden de trabajo sugerido

```
1. A1  · sesión caducada → formulario de acceso        (es el único fallo de verdad)
2. §2  · renombrado a RadioNano                         (mecánico, con la lista de exclusiones)
3. B1  · pruebas de extremo a extremo con Playwright    (el grueso; 6 ficheros)
4. B3  · huecos del backend + B2 componentes
5. B4  · accesibilidad · B5 humo
6. §4  · acabados A2-A7
```

**Criterio de cierre**: `pytest` verde, `npx playwright test` verde, `npx vitest run` verde,
`vite build` sin errores, y `findstr /S /I "RadioPV"` sin resultados fuera de la lista de
identificadores internos.

---

# ✅ ADENDA (2026-08-30, tarde) · Claude montó y EJECUTÓ la batería de pruebas

El agente no podía instalar ni correr el tooling en su entorno. Claude lo hizo en el suyo, con el
backend real y Chromium, y deja la suite **ya verificada** en el repo.

## Qué hay ahora en `frontend/`

```
playwright.config.ts      · dos proyectos: escritorio y móvil (Pixel 5)
vitest.config.ts          · unitarias con jsdom
e2e/utils.ts              · alta/acceso, sesión iniciada, cazador de errores, las 7 rutas
e2e/acceso.spec.ts        · sesión persistente · REGRESIÓN A1 · ámbitos de token
e2e/navegacion.spec.ts    · 7 rutas sin 4xx ni errores de JS · nada hacia Spotify · ruta inexistente
e2e/reproduccion.spec.ts  · el audio SUENA (currentTime avanza) · seek · 200/206/416/404 · señal de escucha
e2e/biblioteca.spec.ts    · me gusta · ciclo completo de playlist · playlist ajena → 404
e2e/familiar.spec.ts      · ninguna explícita en 5 listas distintas
e2e/movil.spec.ts         · 7 rutas sin desbordar a lo ancho
e2e/accesibilidad.spec.ts · axe-core, sin violaciones serias ni críticas
src/__tests__/adapt.test.ts · 11 unitarias del adaptador y de la ganancia
```

`package.json`: `npm test` (unitarias), `npm run test:e2e` (extremo a extremo), `npm run test:todo`.

## Resultado real de la ejecución

| | |
|---|---|
| Unitarias (vitest) | ✅ **11 de 11** |
| Extremo a extremo (Playwright) | ✅ **39 pasan** · ❌ **7 fallan**, todas la misma causa (abajo) |
| Backend (pytest) | ✅ 42 |

**Comprobado de paso: el arreglo A1 funciona.** La prueba de regresión de sesión caducada pasa: ya no
se queda en blanco.

## 🔴 Hallazgo NUEVO que encontró la prueba: la app seguía llamando a Spotify

`src/styles/App.scss` tenía cinco `@font-face` apuntando a **`https://encore.scdn.co`** (las
tipografías de Spotify). C5 dio por bueno "cero llamadas a Spotify" porque miró los *scripts*, no el
CSS. Consecuencias: una petición a Spotify en cada carga, y en la red de Tailscale —sin internet— las
fuentes fallan y **la tipografía de toda la app cambia**.

**Corregido por Claude**: fuera los `@font-face` y las familias pasan a la pila del sistema. Verificado:
0 referencias en el CSS del build y la prueba "ninguna petición sale hacia Spotify" ahora pasa.

## 🟠 Lo único que queda en rojo: 9 botones sin nombre accesible

Las 7 pruebas de accesibilidad fallan por lo mismo, en todas las pantallas:

```
critical: button-name (9) — Buttons must have discernible text
```

Son botones de sólo icono sin `aria-label`. F3 puso etiquetas en los controles del reproductor, pero
faltan otros nueve. **Es trabajo real pendiente, no una prueba mal escrita**: cuando se arreglen, las
7 pasan. Para localizarlos:

```powershell
cd frontend
npx playwright test e2e/accesibilidad.spec.ts --grep Portada
# el informe nombra cada nodo que incumple
```

## Cómo se ejecuta todo

```powershell
# 1 · backend en marcha (otra ventana)
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000

# 2 · dependencias de prueba (sólo la primera vez)
cd frontend
yarn install
npx playwright install chromium     # descarga el navegador; en un equipo con internet funciona

# 3 · las pruebas
npm test                            # unitarias
npm run build                       # el e2e usa el build
npm run test:e2e                    # extremo a extremo
```

> `playwright.config.ts` acepta `E2E_CHROMIUM=/ruta/al/chrome` para entornos que no puedan descargar
> el navegador. En un equipo normal no hace falta.


---

# 🔍 Lista exacta de lo que falla en accesibilidad (medido con axe, 2026-08-30 noche)

Tras los `aria-label` del agente, `button-name` bajó de 9 a 4 en la Portada, pero **quedan 20
elementos distintos** y han aflorado otras cuatro reglas. Esta es la lista con el HTML real, para
que no haya que adivinar. Se obtiene con `node axe_detalle.mjs` (script en `frontend/`).

## 1. CRITICAL · `button-name` — 20 elementos sin nombre accesible

| Selector | Dónde | Etiqueta sugerida |
|---|---|---|
| `button.navigation-button` (×2) | flechas atrás/adelante de la barra superior | `Atrás` / `Adelante` |
| `button.search-browse-button` | botón de explorar en el buscador | `Explorar` |
| `button.actions` (×muchos) | el `…` de cada fila de canción | `Más opciones` |
| `button[style*="justify-content: center"]` con `aria-describedby` | botón de icono dentro de tarjeta | según su icono |

> Los `.actions` son los que más suman: **un solo `aria-label` en ese componente los arregla todos**.

## 2. CRITICAL · `image-alt` — 1 elemento

```html
<img loading="lazy" src="/images/playlist.png">
```
Falta `alt`. Poner el nombre de la lista, o `alt=""` si es puramente decorativa.

## 3. SERIOUS · `nested-interactive` — 2 componentes

```html
<button class="ant-dropdown-trigger … activable-song">
```
Es una **tarjeta de canción que es un `<button>` y lleva otro botón dentro** (el de reproducir). Un
lector de pantalla no puede alcanzar el de dentro.

**Arreglo**: el contenedor deja de ser `<button>` y pasa a `<div role="button" tabIndex={0}>` con
`onKeyDown` para Enter y Espacio, dejando el botón interno como el único `<button>` real. Es el
único de la lista que toca estructura; hacerlo con cuidado.

## 4. SERIOUS · `color-contrast` — 12 elementos, todos en **Ajustes**

`<h2>Ajustes</h2>`, los `<h3>` (Idioma, Ocultar contenido explícito, Nombre visible, Temporizador de
apagado) y los `<span>` de 15/30/60 min. La pantalla se escribió sin fijar color de texto y hereda uno
oscuro sobre el fondo oscuro. **Arreglo**: color claro explícito en esa pantalla.

## 5. CRITICAL · `label` — 1 elemento

El `<Select>` de idioma en Ajustes no tiene etiqueta asociada. Añadir `aria-label="Idioma"` (el `<h3>`
de al lado no cuenta como etiqueta).

---

**Nota**: Claude añadió a `tsconfig.json` la exclusión de `e2e/`, `src/__tests__/` y los ficheros de
configuración de pruebas, para que **`tsc --noEmit` vuelva a estar limpio** sin tener que instalar
vitest ni playwright. La red de seguridad del agente funciona otra vez.
