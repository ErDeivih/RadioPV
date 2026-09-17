# 🧾 RadioPV · Orden de trabajo por bloques (para el agente)

> **Cómo se usa esta orden.** No es una lista de sugerencias: es la cola de trabajo. Se ejecuta de
> arriba abajo. **Un bloque entero es una entrega**, no un ítem. No se para entre ítems del mismo
> bloque, no se pide confirmación entre ítems, y no se reporta el estado más de una vez por bloque.
>
> Escrita el 2026-08-29, después de verificar en Chromium real que Home, Búsqueda, Artist y
> LikedSongs renderizan contra el backend con datos del catálogo. Los hallazgos de esa verificación
> están incorporados abajo y marcados con 🔎.

---

## Reglas de ejecución (leer una vez, aplicar siempre)

1. **Una entrega = un bloque completo.** Si el bloque tiene ocho ítems, se hacen los ocho y se
   reporta al final. Nada de "he hecho el ítem 1, ¿sigo?".
2. **Nunca esperar respuesta más de una ronda.** Si algo queda bloqueado, se salta ese ítem, se anota
   por qué en `PROGRESS.md`, y **se sigue con el siguiente**. Al final del bloque se listan los
   saltados.
3. **`tsc --noEmit` verde antes de cerrar cada ítem**; `pytest` verde antes de cerrar cada ítem que
   toque el backend. No hace falta reportarlo por ítem: basta una línea al cerrar el bloque.
4. **No escribir tests de endpoints que ya estaban cubiertos.** Test nuevo solo para código nuevo o
   para un fallo corregido (test de regresión).
5. **No tocar `vendor/`.** No tocar `E:\Musica`. No borrar ficheros.
6. **Al cerrar el bloque**: una tabla de ítem → estado → ficheros tocados, los saltados con su
   motivo, y **nada más**. Sin resúmenes del proyecto entero, sin repetir el estado global.
7. Si aparece una decisión de producto, dinero, datos irreversibles o exposición a terceros: parar y
   preguntar **solo esa**, y seguir con el resto del bloque mientras tanto.

---

# BLOQUE A · Terminar FE-08 (pantallas)

**Estado verificado**: Home ✅ · Búsqueda con término ✅ · Artist ✅ · LikedSongs ✅ (vacía, sin likes).

### A1 · 🔎 Browse (`/search` sin término) sale vacío
Verificado en navegador: la pantalla renderiza pero solo muestra "Browse all" y **ninguna categoría**.
Usaba las categorías de Spotify. Cablearla a **`GET /facets`**: rejilla de géneros, eras, moods e
idiomas con su conteo, cada una enlazando a `/genre/:id` o a `/tracks?genre=`.
*Aceptación*: `/search` muestra al menos los 12 géneros reales del catálogo con su número.

### A2 · Página Genre
`/genre/:genreId` → `GET /tracks?genre=` con paginación por `X-Total-Count`.
*Aceptación*: entrar desde Browse a "reggaeton" lista canciones reales y hace scroll infinito.

### A3 · Playlist
Detalle con portada, nº de canciones, reproducir, aleatorio; **añadir, quitar, reordenar
(`react-drag-listview` ya está) y borrar**, contra `DELETE /playlists/{id}`,
`DELETE /playlists/{id}/tracks/{t}`, `PATCH /playlists/{id}` y `PUT /playlists/{id}/order`.
*Aceptación*: crear una lista, añadir 3 temas, reordenarlos, quitar uno y borrarla, sin recargar.

### A4 · Album
Ya cableado a `/tracks?artist=&album=`. Repasar que la cabecera muestre año y portada y que
"reproducir álbum" encole **todas** las pistas en orden, no solo la primera.

### A5 · Discography
`/artist/:artistId/discography` → `GET /artists/{name}/albums`, agrupada por año descendente.

### A6 · Profile / User
`/users/:userId` → `GET /library/top?type=artists|tracks` y `/library/history`. Quitar lo que quede
apuntando a `/me/top/*`.

### A7 · Estado vacío útil
Cuando `/tracks?q=` no devuelve nada: botón **"pedir esta canción"** → `POST /requests`.
*Aceptación*: buscar algo inexistente ofrece el botón y el registro aparece en la tabla `requests`.

### A8 · Paginación real
Usar `X-Total-Count` en Búsqueda, Genre y Artist para el scroll infinito
(`react-infinite-scroll-component` ya está en las dependencias).

---

# BLOQUE B · Reproducción completa

### B1 · Cola de verdad
Estado de cola en Redux: lista, índice actual, siguiente/anterior, y **"añadir a continuación"**
distinto de "añadir al final". `playerController.bindEnded` ya existe: engancharlo aquí.
*Aceptación*: reproducir un álbum encadena las 12 pistas sin tocar nada.

### B2 · Flow (reproducción continua)
Al agotarse la cola: `GET /recommend/radio?seed_track={última}` y encolar.
*Aceptación*: con una cola de 1 tema, al acabar sigue sonando música parecida.

### B3 · Shuffle con separación de artista
Barajar evitando dos temas seguidos del mismo artista (algoritmo en `10_FRONTEND_SPEC.md` §4.5).

### B4 · Repetir (uno / todo / off) y volumen persistente
El volumen y el modo de repetición se recuerdan entre sesiones (`localStorage`).

### B5 · Precarga de la siguiente
Cuando queden ~20 s, `<audio>` oculto con `preload="auto"` apuntando a la siguiente.
*Aceptación*: el salto entre temas no tiene silencio perceptible.

### B6 · Señales completas
Confirmar que al saltar antes del 30 % se manda además `POST /library/{id}/skip`, y que `context`
va relleno (`playlist:12`, `radio:88`, `daily`, `search`, `artist`).

### B7 · Atajos de teclado
Espacio = play/pausa · flechas = ±10 s · `M` = silenciar · `L` = me gusta.

---

# BLOQUE C · Quitar lo que queda de Spotify

### C1 · 🔎 Restos visibles en la barra superior
Verificado en navegador: **todas** las pantallas muestran "Source code" y la pestaña **"Podcasts"**.
Quitar ambos. Están en `components/Layout/components/Navbar/Header.tsx` y en `i18n/en/home.ts`,
`i18n/es/home.ts`, `i18n/es/navbar.ts`.

### C2 · Servicios y tipos muertos
Borrar `services/episodes.ts`, `services/categories.ts` (o reapuntarla a `/facets`),
`utils/spotify/getDeviceIcon.tsx`, `interfaces/devices.d.ts`, `interfaces/episode.d.ts`, y el resto
de `utils/spotify/login.ts` que ya no se use. Vaciar `frontend/_to_delete/`.

### C3 · Textos e idioma
Repasar `i18n/es` para que la app hable en español de RadioPV, no de Spotify. Nombre del producto,
títulos de sección y textos de los estados vacíos.

### C4 · Marca
Favicon, `<title>` y logo. Hoy el título de la pestaña sigue siendo **"Spotify Web Player"**
(verificado). Cambiar a "RadioPV".

### C5 · Barrido final
`grep -rn "spotify\|scdn\|api\.spotify" frontend/src frontend/index.html` debe salir **vacío**
salvo comentarios explicativos.
*Aceptación*: cargar la app con la red del navegador filtrada por "spotify" no muestra ni una petición.

---

# BLOQUE D · Ajustes y perfil familiar

### D1 · Pantalla de Ajustes
Ruta nueva `/settings`: idioma, cerrar sesión, y **ocultar contenido explícito**.

### D2 · Filtro explícito de verdad
El interruptor se guarda en el perfil y se aplica a **todas** las listas: `/tracks`, `/recommend`,
`/recommend/daily`, `/radio`, playlists y búsqueda. Hay 160 temas marcados.
*Aceptación*: con el filtro puesto, ninguna canción `explicit` aparece en ninguna pantalla.

### D3 · Perfil de usuario
Nombre visible editable (`PATCH /auth/me`, añadirlo si no existe) y avatar por inicial.

### D4 · Temporizador de apagado
"Parar en 15/30/60 min o al acabar la canción".

### D5 · Estadísticas
`/wrapped` en una pantalla simple: top artistas, top géneros, minutos escuchados, descubrimientos.

---

# BLOQUE E · Móvil (F5 completo)

Seguir `12_MOBILE_SPEC.md` de principio a fin: **MB-02 a MB-08 en una sola entrega**.

- **E1** `pubspec.yaml` al día y que la app original arranque (commit aparte, antes de tocar nada).
- **E2** `url.dart` + `ApiClient` con JWT (recordar: `10.0.2.2` desde el emulador).
- **E3** Token de streaming (mismo mecanismo que la web).
- **E4** `song_model.dart` → `TrackOut`; carátula con la base delante; foto de artista vía `/artists/{name}`.
- **E5** Repositorios a nuestros endpoints (tabla en `12_MOBILE_SPEC.md` §MB-05).
- **E6** Reproductor: `/stream`, ganancia por `gain_db`, notificación, señales, offline.
- **E7** Android: permisos, `network_security_config.xml`, build de release.
- **E8** Pantallas + login con invitación + ajustes con filtro explícito.

*Aceptación del bloque*: `flutter analyze` limpio y la lista de lo que no se pudo compilar aquí, para
compilarlo fuera.

---

# BLOQUE F · Pulido y cierre

- **F1** PWA instalable (manifest + service worker con caché de la carcasa, **nunca** del audio).
- **F2** Esqueletos de carga y estados vacíos honestos en todas las pantallas.
- **F3** Accesibilidad: foco visible, `aria-label` en los controles del reproductor, contraste.
- **F4** 🔎 La búsqueda dispara **9 peticiones** por término (`limit=1,5,10` × tracks/artists/playlists).
  Reducirlo a una por tipo y recortar en cliente.
- **F5** Manejo de errores visible: un `Toast` cuando la API falla, en vez del silencio actual.
- **F6** 🔎 **El servidor de producción necesita *fallback* de SPA** (`try_files … /index.html`). Sin
  eso, entrar directo a `/artist/Bad Bunny` da 404 — comprobado. Añadirlo al `Caddyfile` de
  `13_DEPLOY_SPEC.md` y al `docker-compose`.
- **F7** Repasar `06_BUILD_GUIDE.md`, `05_UI.md` y `07_CROSS_PLATFORM_BLUEPRINT.md` para que
  describan lo que existe, no lo que se planeó.

---

## Orden y tamaño de las entregas

```
A (8 ítems)  →  B (7)  →  C (5)  →  D (5)  →  E (8)  →  F (7)
```

Cada letra es **una entrega**. Si un bloque se hace largo, se parte **por la mitad**, no en ocho
trozos. Entre bloques sí se para y se reporta.

**Lo único que sigue siendo de David**: T-24 (la pasada de análisis, que da `gain_db` y arregla
`energy`) y mover la cuarentena. No bloquean ningún ítem de esta orden.
