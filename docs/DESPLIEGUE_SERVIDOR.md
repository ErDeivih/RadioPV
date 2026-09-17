# RadioPV en el servidor — comandos completos

Guía de **configuración, despliegue y uso**. Todos los comandos, en orden, para tu PC y para el servidor.

---

## 0. Antes de empezar: qué hay ya implementado

RadioPV **ya trae** el comportamiento tipo Spotify que buscabas. No hay que construirlo:

| Función | Dónde | Cómo se usa |
|---|---|---|
| **Mixes automáticos por usuario** (`daily_1/2/3`, `discover`, `on_repeat`, `radar`, `time_capsule`) | Worker diario a las 05:00 | `GET /mixes` → fila *"Hecho para ti"* en la Home |
| **Listas de tendencias** (`Trending`, `Top España`, `Los 2000`…) | Worker | `GET /playlists/system` |
| **Tops por usuario** (`Top {usuario}`, `Lo más escuchado de la casa`, `Rescatadas`) | Worker | `GET /playlists/system` |
| **Novedades** | Worker | `GET /playlists/system` |
| **Radio por similitud** | Tabla `similar` precomputada | `GET /recommend/radio?seed_track=ID` |
| **Recomendaciones personalizadas** | Perfil + señales implícitas + diversidad | `GET /recommend`, `/recommend/daily` |
| **Playlists propias de cada usuario** | CRUD completo | `GET/POST /playlists`, `POST /playlists/{id}/tracks/{track_id}` |
| **Wrapped** (resumen anual) | — | `GET /wrapped` |

Cada mix incluye una **`explicacion`** (por qué se generó). Y hay **filtro explícito por perfil familiar**.

**Para regenerar todo a mano:** se reinicia el worker, que hace una pasada inicial completa
(`git pull` + `docker compose restart worker`).

---

## 1. En tu PC — preparar y subir

### 1.1 Subir el código

```
cd F:\EspacioCodigo\RadioPV
```
```
git add -A
```
```
git commit -m "lo que hayas cambiado"
```
```
git push
```

### 1.2 Copiar el catálogo (bases de datos y carátulas)

Las `.db` están en `.gitignore` (correcto: los datos no van a Git). Se copian aparte.

```
robocopy F:\EspacioCodigo\RadioPV\data \\servidor.local\stacks\radiopv\data /E /Z /R:2 /W:2 /MT:16 /NP /TEE /LOG:C:\radiopv-datos.log
```

### 1.3 Copiar la música catalogada

⚠️ **Solo `catalogada`** — `descargas` es la copia en bruto y no se lleva al servidor
(en el servidor la nutrirán las ingestas nuevas).

```
robocopy E:\Musica\catalogada \\servidor.local\data\media\music /E /Z /R:2 /W:2 /MT:16 /NP /TEE /LOG:C:\radiopv-musica.log
```

> `/Z` = reanudable: si se corta, lo relanzas y continúa donde iba.

### 1.4 (Opcional) Compilar el frontend en tu PC

Solo si el servidor no puede (tiene poca RAM). **Necesita WSL o Git Bash**, porque el script
usa `cp`:

```
wsl
cd /mnt/f/EspacioCodigo/RadioPV/frontend
yarn install --immutable
yarn build
exit
```

Y luego copias el resultado:
```
robocopy F:\EspacioCodigo\RadioPV\frontend\build \\servidor.local\stacks\radiopv\frontend\build /E /Z
```

---

## 2. En el servidor — instalación

### 2.1 Clonar el repositorio

```
sudo apt install -y git
```
```
sudo git clone https://github.com/ErDeivih/RadioPV.git /opt/stacks/radiopv
```
```
cd /opt/stacks/radiopv
sudo chmod +x deploy.sh
```

### 2.2 Primer despliegue (genera el `.env` con la SECRET_KEY)

```
./deploy.sh --first
```

### 2.3 Compilar el frontend

```
./deploy.sh --build-web
```

⚠️ Con 4 GB de RAM el build va justo. Si falla por memoria:
```
NODE_OPTIONS=--max-old-space-size=2048 ./deploy.sh --build-web
```
Y si aun así no puede, compílalo en tu PC (paso 1.4) y copia `frontend/build`.

### 2.4 Copiar el catálogo y la música

Desde tu PC (pasos 1.2 y 1.3). O comprobar en el servidor:
```
ls -la /opt/stacks/radiopv/data/
ls /srv/data/media/music | head
```

### 2.5 Darte permisos de administrador

```
sudo apt install -y sqlite3
```
```
sudo sqlite3 /opt/stacks/radiopv/data/backend.db "UPDATE users SET is_admin=1;"
```
```
sudo sqlite3 /opt/stacks/radiopv/data/backend.db "SELECT id, username, is_admin FROM users;"
```

### 2.6 Ajustes de la música (importante para no duplicar espacio)

Edita los ajustes del recolector:
```
sudo nano /opt/stacks/radiopv/data/settings.json
```
Cambia **`"keep_raw_copy": true` → `false`**, para que las ingestas **muevan** en vez de copiar.
Así no se acumulan dos copias de cada canción.

Ajustes que conviene revisar de paso:

| Ajuste | Valor sugerido | Por qué |
|---|---|---|
| `keep_raw_copy` | `false` | No duplicar ficheros |
| `disk_cap_gb` | el que quieras (p. ej. `300`) | El recolector para al llegar al techo |
| `downloads_per_day` | `150` | Ritmo sostenido, no una ráfaga |
| `agent_enabled_by_default` | `false` | Controlarlo desde el panel, no al arrancar |

### 2.7 Comprobar que todo está arriba

```
cd /opt/stacks/radiopv
sudo docker compose ps
```
```
curl -s http://127.0.0.1:8000/health
```

---

## 3. Acceso

| Qué | URL |
|---|---|
| **Web (la app)** | `http://servidor.local:8090` |
| **API** | `http://servidor.local:8000` |
| **Documentación de la API** | `http://servidor.local:8000/docs` |
| **Admin (biblioteca)** | `http://servidor.local:8090/admin` |

**Desde el móvil, en cualquier sitio:** instala Tailscale en el móvil con tu cuenta y usa
`http://servidor:8090`. Luego **"Añadir a pantalla de inicio"** en Chrome → queda como app.

---

## 4. Uso diario

### 4.1 El panel de administración (`/admin`)

| Pestaña | Para qué |
|---|---|
| **🎵 Biblioteca** | Filtrar, agrupar y **borrar/vetar en masa** |
| **🚫 Lista negra** | Ver y retirar vetos · *Purgar vetados* |
| **🎛️ Ingesta** | Interruptor de descargas + diario en vivo |

**El flujo para limpiar rápido:**

```
1. Filtro: Idioma = Inglés
2. Vista: [ Por artista ]        ← 412 artistas en vez de 3.180 canciones
3. Ocultar los que tengan menos de 3 canciones
4. Marcar los que no quieras
5. [ Vetar y borrar los seleccionados ]
6. Confirmar (te dice cuántas canciones caen)
```

**Vetar y borrar** = borra los ficheros del disco **y** los registra en la lista negra, así que
ni ocupan espacio ni se vuelven a descargar. Hay previsualización obligatoria antes de ejecutar.

### 4.2 Comandos del servidor

**Ver el estado:**
```
cd /opt/stacks/radiopv
sudo docker compose ps
sudo docker compose logs --tail 50 api
sudo docker compose logs --tail 50 collector
sudo docker compose logs --tail 50 worker
```

**Encender / apagar todo (para liberar RAM):**
```
sudo docker compose stop
sudo docker compose start
```

**Regenerar listas, mixes y tops a mano** (el worker lo hace solo cada día a las 05:00):
```
sudo docker compose restart worker
sudo docker compose logs -f worker
```

**Encender/apagar solo la ingesta** sin tocar el resto (desde el panel), o forzando:
```
sudo sqlite3 /opt/stacks/radiopv/data/radiov.db "INSERT INTO agent_state(key,value) VALUES('ingest_enabled','0') ON CONFLICT(key) DO UPDATE SET value='0';"
sudo sqlite3 /opt/stacks/radiopv/data/radiov.db "INSERT INTO agent_state(key,value) VALUES('ingest_enabled','1') ON CONFLICT(key) DO UPDATE SET value='1';"
```

**Actualizar tras un `git push` desde el PC:**
```
cd /opt/stacks/radiopv
./deploy.sh
```

### 4.3 Consultas útiles a la base de datos

**Cuántas canciones por idioma:**
```
sudo sqlite3 /opt/stacks/radiopv/data/radiov.db "SELECT language, COUNT(*) FROM tracks GROUP BY language ORDER BY 2 DESC;"
```

**Por género:**
```
sudo sqlite3 /opt/stacks/radiopv/data/radiov.db "SELECT genre, COUNT(*) FROM tracks GROUP BY genre ORDER BY 2 DESC LIMIT 20;"
```

**Los 20 artistas con más canciones:**
```
sudo sqlite3 /opt/stacks/radiopv/data/radiov.db "SELECT artist, COUNT(*) n FROM tracks GROUP BY artist ORDER BY n DESC LIMIT 20;"
```

**Cuánto ocupa la biblioteca:**
```
sudo sqlite3 /opt/stacks/radiopv/data/radiov.db "SELECT ROUND(SUM(file_size)/1073741824.0, 2) || ' GB', COUNT(*) FROM tracks;"
```

**Qué hay vetado:**
```
sudo sqlite3 /opt/stacks/radiopv/data/radiov.db "SELECT kind, value, created_at FROM blacklist WHERE active=1 ORDER BY created_at DESC LIMIT 30;"
```

**Filas huérfanas (sin fichero):**
```
sudo sqlite3 /opt/stacks/radiopv/data/radiov.db "SELECT COUNT(*) FROM tracks WHERE file_path IS NULL OR file_path='';"
```

**Espacio en disco:**
```
df -h /srv/data
du -sh /srv/data/media/music
```

---

## 5. Copias de seguridad (cuando toque)

**Volcado de las bases** (nunca copies un SQLite en caliente):
```
sudo sqlite3 /opt/stacks/radiopv/data/radiov.db ".backup '/srv/data/backups/radiov-$(date +%F).db'"
sudo sqlite3 /opt/stacks/radiopv/data/backend.db ".backup '/srv/data/backups/backend-$(date +%F).db'"
```

**Y la música** a un disco externo con `restic` (pendiente, cuando lo montemos).

---

## 6. Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| La web da 404 en `/admin` | Tu usuario no es admin | Paso 2.5 |
| La web carga pero no suena | `ALLOWED_ORIGINS` no incluye la URL | Revisa `.env` y `./deploy.sh` |
| `docker compose up` falla por `RADIOPV_SECRET_KEY` | Falta el `.env` | `./deploy.sh --first` |
| El build del frontend falla por memoria | Pocos GB de RAM | `NODE_OPTIONS=--max-old-space-size=2048` o compila en el PC |
| El recolector no descarga | Ingesta apagada | Panel → Ingesta → encender |
| Todo va lento / se matan contenedores | 4 GB de RAM | `docker compose stop` y deja solo `api` + `web` |
| El disco se llena | `keep_raw_copy: true` duplica | Paso 2.6 |
