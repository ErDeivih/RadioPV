# 🎬 Media-Stack — Netflix casero (Plex + Sonarr + Radarr + qBittorrent)

Pila **independiente de RadioPV** para películas y series. Un compose levanta 6 servicios en Docker.
Puertos y URLs (en tu máquina):

| Servicio | URL | Puerto | Para qué |
|---|---|---|---|
| **qBittorrent** | http://localhost:8080 | 8080 | Cliente torrent (WebUI) |
| **Prowlarr** | http://localhost:9696 | 9696 | Gestionar indexadores (fuentes) |
| **Sonarr** | http://localhost:8989 | 8989 | Series (buscar/descargar/organizar) |
| **Radarr** | http://localhost:7878 | 7878 | Películas |
| **Plex** | http://localhost:32400 | 32400 | El "Netflix": ver y organizar |
| **Overseerr** | http://localhost:5055 | 5055 | Pedir pelis/series con un clic |

## 1) Arrancar

1. **Abre Docker Desktop** (está instalado pero el motor no estaba en marcha) y deja que arranque.
2. En esta carpeta (`media-stack`):
   ```
   docker compose up -d
   ```
3. Espera ~1 min y comprueba que todos los contenedores están `Up`:
   ```
   docker compose ps
   ```

## 2) Conectar el flujo (lo haces tú, son pasos de 1 minuto cada uno)

El orden recomendado:

- **qBittorrent** (:8080). Login por defecto: **admin / adminadmin**. Ve a *Settings → Downloads* y pon la ruta de guardado en **`/media/downloads`**.
- **Prowlarr** (:9696). Aquí **añades los indexadores** (esta es la parte que no automatizo, ver abajo). Luego *Settings → Apps* y conecta **Sonarr** y **Radarr**.
- **Sonarr** (:8989) y **Radarr** (:7878):
  - *Settings → Media Management → Root Folders* → añade **`/media/tv`** (Sonarr) y **`/media/movies`** (Radarr).
  - *Settings → Download Clients* → añade **qBittorrent** (host `qbittorrent`, puerto `8080`, usuario admin, contraseña adminadmin, categoría en `/media/downloads`).
  - *Settings → Indexers* → se rellenan desde Prowlarr.
- **Plex** (:32400): haz login / reclama el servidor. Añade dos **bibliotecas**: *Movies* → `/media/movies` y *TV Shows* → `/media/tv`. Activa el agente de metadatos (TMDB).
- **Overseerr** (:5055): inicia sesión con Plex, conecta **Sonarr/Radarr** y ya puedes **pedir pelis y series** desde una web tipo Netflix.

## 3) Calidad: HD por defecto (no 4K/UHD)

En **Radarr** y **Sonarr** → *Settings → Profiles*:
- Marca como **perfil por defecto** uno que **cap en 1080p** (HD). Así, salvo que tú pidas específicamente 4K/UHD, se bajará en HD y ocupará poco.
- Para un título concreto en 4K, selecciónalo manualmente con ese perfil (o crea un perfil "4K" a mano y úsalo solo cuando lo pidas).

## 4) Qué **NO** te hago yo (y por qué)

- **El "rascado" de DonTorrent vía Brave/Tor/.onion** no lo automatizo: indexa contenido **bajo copyright** y no voy a escribir ese scraper. En **Prowlarr** añades tú los indexadores que quieras.
- **Vídeos de contenido con copyright**: el stack es agnóstico; funciona igual de bien con **dominio público, Creative Commons, tus propios rips o material autorizado**.

> ⚠️ Consejo legal honesto: descargar películas/series comerciales por torrent es, en la práctica, piratería en casi todos los países. Para uso 100% legal, el flujo es idéntico pero desde fuentes legítimas (dominio público / CC / copias propias).

## 5) Lo que dejaré ya montado (archivos)

| Archivo | Contenido |
|---|---|
| `docker-compose.yml` | Los 6 servicios con sus volúmenes, puertos y TZ `Europe/Madrid` |
| `E:/Videos/{movies,tv,downloads}` | Carpetas de biblioteca y descargas (ya creadas) |

## 6) Notas

- **Credenciales por defecto**: las de linuxserver (qbittorrent admin/adminadmin). Cámbialas por seguridad.
- **VPN/Tor**: si decides usar indexadores y quieres que las descargas salgan por una red más anónima, se hace en qBittorrent (opciones de proxy); no lo preconfiguro por defecto.
- **PLEX_CLAIM**: opcional en el compose. Si lo dejas vacío, reclamas el servidor en la web (:32400), que es lo más fácil.

Todo lo demás (metadatos, portadas, transcodificado automático, descarga bajo demanda) lo hace el propio stack una vez conectado. **Dime si quieres que ajuste algo** (puertos, carpetas, añadir `Tautulli`/`Jellyfin` en vez de Plex, o un script de arranque).
