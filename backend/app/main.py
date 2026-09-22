from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from .config import ALLOWED_ORIGINS, MEDIA_ROOT
from .database import Base, engine, ensure_schema
from . import models  # noqa: F401  (registra las tablas)
from .routers import auth, tracks, artists, library, playlists, recommend, stream, facets, wrapped, follows, stats, admin, collector, lyrics, importar

Base.metadata.create_all(bind=engine)
ensure_schema()          # añade columnas e índices que falten en bases antiguas

app = FastAPI(title="RadioPV API", version="1.0")
# Comprimir las respuestas: `/tracks` devuelve hasta 500 canciones con ~30 campos cada una, y se
# consume sobre todo desde el móvil. nginx ya comprime el frontend, pero las respuestas de la API
# salían sin comprimir. Los ficheros de audio no se tocan (son binarios ya comprimidos y van por
# otro camino), y por debajo del mínimo no se comprime nada.
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS,
                   allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["X-Total-Count", "Content-Range", "Accept-Ranges", "Content-Length"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Cabeceras de seguridad básicas (DP-06)."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    return response

for r in (auth.router, tracks.router, artists.router, library.router, playlists.router, recommend.router, stream.router, facets.router, wrapped.router, follows.router, stats.router, admin.router, collector.router, lyrics.router, importar.router):
    app.include_router(r)

# Carátulas y fotos de artista: la BD aporta el NOMBRE, la raíz la monta el servidor.
for sub in ("covers", "artists"):
    d = MEDIA_ROOT / sub
    d.mkdir(parents=True, exist_ok=True)
    app.mount(f"/media/{sub}", StaticFiles(directory=str(d)), name=f"media_{sub}")


@app.get("/health")
def health():
    """Health/readiness: BD accesible + contadores de catálogo (y si el worker corrió rebuild_similar).

    IMPORTANTE: cuando la base de datos falla, esta ruta devolvía **200** con `{"status":"error"}`.
    El monitor (Uptime Kuma) mira el código HTTP, así que daba el servicio por bueno justo cuando
    estaba roto. Ahora devuelve **503**, que es lo que hace que salte el aviso.
    """
    from sqlalchemy import text
    from .database import SessionLocal
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))                      # la BD responde
        tracks = db.query(models.Track).filter(models.Track.status == "descargada").count()
        artists = db.query(models.Artist).count()
        similar = db.query(models.Similar).count()
        users = db.query(models.User).count()
    except Exception as e:  # noqa: BLE001
        # El detalle se queda en el registro: /health es público y no debe contar cómo es la
        # base por dentro.
        print(f"[health] la base de datos no responde: {e}", flush=True)
        return JSONResponse(status_code=503, content={"status": "error"})
    finally:
        db.close()
    return {"status": "ok", "tracks": tracks, "artists": artists,
            "similar": similar, "users": users}
