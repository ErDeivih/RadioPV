# Panel de administración de la biblioteca — especificación de la UI

> **Objetivo:** poder borrar **rápido y en masa** lo que no interesa (idiomas, géneros,
> artistas), gestionar la lista negra y encender/apagar la ingesta **sin salir de RadioPV**.
> La interfaz Streamlit antigua (`app_streamlit_legacy.py`) queda como referencia y no se usa.

La API ya está implementada: `backend/app/routers/admin.py` (prefijo `/admin`, requiere `is_admin`).

---

## 1. Endpoints disponibles

| Método | Ruta | Para qué |
|---|---|---|
| `GET` | `/admin/status` | Totales, por estado, GB de biblioteca, espacio libre, rutas, estado de ingesta |
| `GET` | `/admin/events?limit=100` | Últimos eventos del recolector (el "diario") |
| `GET` | `/admin/tracks` | **Tabla de gestión**: filtros + paginación + ordenación |
| `GET` | `/admin/facets` | Valores para los desplegables, **con recuento** |
| `POST` | `/admin/tracks/delete` | **Borrado masivo** `{ids:[], veto:true}` |
| `POST` | `/admin/tracks/blacklist` | Vetar sin borrar `{ids:[]}` |
| `POST` | `/admin/artists/veto` | Vetar artista `{name, delete_tracks}` |
| `POST` | `/admin/purge` | Borrar del disco todo lo vetado |
| `GET` | `/admin/blacklist?kind=` | Lista negra |
| `POST` | `/admin/blacklist` | Añadir `{kind:"artist"|"song", value, reason}` |
| `DELETE` | `/admin/blacklist/{id}` | Retirar un veto |
| `GET` | `/admin/ingest` | Estado del interruptor |
| `PUT` | `/admin/ingest` | `{enabled: bool}` |

### Filtros de `/admin/tracks`

`q` (busca en título/artista/álbum) · `artist` · `album` · `genre` · `language` · `status`
· `year_min` · `year_max` · `sort` (`artist|title|album|year|genre|language|added_at|file_size`)
· `order` (`asc|desc`) · `limit` (1-500) · `offset`

Devuelve `{total, limit, offset, items[]}`.

---

## 2. La página: `frontend/src/pages/Admin/`

```
Admin/
├── index.tsx            ← contenedor con pestañas
├── Library.tsx          ← la tabla de gestión (lo importante)
├── Blacklist.tsx        ← lista negra
├── Ingest.tsx           ← interruptor + diario de eventos
└── api.ts               ← llamadas a /admin (o extender src/api/adapt.ts)
```

Añadir la ruta en `App.tsx` como `/admin` y el enlace **solo si `user.is_admin`**.

---

## 3. `Library.tsx` — la tabla de gestión (el corazón)

### Lo que tiene que permitir, en este orden de importancia

1. **Selección múltiple** con checkbox por fila y *"seleccionar todo lo filtrado"*
2. **Botonera de acciones en masa**: `Borrar seleccionadas` · `Vetar sin borrar` ·
   `Vetar artista de las seleccionadas`
3. **Confirmación clara** antes de borrar: *"Se van a borrar 348 canciones (1,2 GB). ¿Añadirlas
   también a la lista negra para que no se vuelvan a descargar?"* → [Vetar y borrar] [Solo borrar] [Cancelar]
4. **Filtros rápidos arriba** (esto es lo que hace el borrado *rápido*):
   - **Idioma** (desplegable con recuento) ← *"borrar todo lo que no sea español"*
   - **Género** (desplegable con recuento)
   - **Artista** (autocompletar)
   - **Rango de años**
   - **Estado** (descargada / cuarentena / fallida)
   - **Buscar** por texto
5. **Atajos de selección masiva** — botones de un clic muy útiles:
   | Botón | Qué hace |
   |---|---|
   | *Seleccionar todo lo filtrado* | Marca los N resultados del filtro actual (no solo la página) |
   | *Seleccionar idioma ≠ español* | Filtra y marca todo lo que no sea `es` |
   | *Seleccionar todo un artista* | Un clic sobre el nombre del artista |
   | *Invertir selección* | — |
6. **Paginación** de 100 en 100, con el total visible
7. **Ordenación** por columnas
8. Pie con **resumen de la selección**: nº de pistas y MB

### Columnas

`[ ]` · Título · Artista (clic = filtrar por él) · Álbum · Año · Género · Idioma · BPM ·
Duración · MB · Estado · Acciones (`🗑️ Borrar` · `🚫 Vetar`)

### Comportamiento

- **Borrado optimista**: al confirmar, quita las filas de la tabla y muestra el número borrado.
- Si una fila tiene `file_path` vacío, avisar (huérfana).
- Objetivo de rendimiento: **borrar 500 canciones de una vez sin bloquear la interfaz**.

---

## 4. `Blacklist.tsx`

- Dos pestañas: **Canciones** y **Artistas**
- Tabla con `value`, `reason`, `created_at` y botón **Retirar** por fila
- Buscador
- Botón **"Purgar ahora"** → `POST /admin/purge` con confirmación
- Explicación en pantalla: *"Lo que está aquí no se volverá a descargar."*

---

## 5. `Ingest.tsx`

- **Interruptor grande** 🔛 con el estado actual (`GET /admin/ingest`)
- Texto: *"Cuando está apagada, el recolector deja de buscar y descargar música nueva."*
- Muestra `updated_at` y `updated_by`
- Debajo, **el diario de eventos** (`GET /admin/events`) que se refresca cada 10 s
- Los contadores de `/admin/status` en tarjetas: pistas, GB, espacio libre

---

## 6. Consideraciones de despliegue

| Punto | Detalle |
|---|---|
| **`is_admin`** | El campo ya existe en `models.User`. Hay que marcar tu usuario como admin: `UPDATE users SET is_admin=1 WHERE username='david';` |
| **CORS** | La web (8090) llama a la API (8000): `RADIOPV_ALLOWED_ORIGINS` debe incluirlas |
| **Token** | El `access_token` ya se usa en el resto de la app; el router `/admin` usa `get_current_user` |
| **Móvil** | Con Tailscale la web funciona desde cualquier sitio; el borrado masivo es usable también en móvil, pero está pensado para el PC |
| **Rendimiento** | `limit` máximo 500. Para borrados de miles, trocear en lotes desde el cliente |

---

## 7. Estado

| Pieza | Estado |
|---|---|
| `radiov/blacklist.py` (lógica) | ✅ existía |
| `radiov/ingest_control.py` | ✅ **creado** |
| `run_collector.py` (obedece al interruptor) | ✅ **creado** |
| `backend/app/routers/admin.py` (API) | ✅ **creado** |
| `main.py` registra el router | ✅ **parcheado** |
| `Library.tsx`, `Blacklist.tsx`, `Ingest.tsx` | ⬜ **pendiente** |
| Enlace en `App.tsx` y en la barra de navegación | ⬜ pendiente |
| Marcar tu usuario como `is_admin` | ⬜ pendiente |
