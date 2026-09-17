from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .config import ALLOWED_ORIGINS, MEDIA_ROOT
from .database import Base, engine, ensure_schema
from . import models  # noqa: F401  (registra las tablas)
from .routers import auth, tracks, artists, library, playlists, recommend, stream, facets, wrapped, follows, stats, admin

Base.metadata.create_all(bind=engine)
ensure_schema()          # añade columnas nuevas (mixes.explicacion) a BD antiguas

app = FastAPI(title="RadioNano API", version="0.1")
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

for r in (auth.router, tracks.router, artists.router, library.router, playlists.router, recommend.router, stream.router, facets.router, wrapped.router, follows.router, stats.router, admin.router):
    app.include_router(r)

# Carátulas y fotos de artista: la BD aporta el NOMBRE, la raíz la monta el servidor.
for sub in ("covers", "artists"):
    d = MEDIA_ROOT / sub
    d.mkdir(parents=True, exist_ok=True)
    app.mount(f"/media/{sub}", StaticFiles(directory=str(d)), name=f"media_{sub}")


@app.get("/health")
def health():
    """Health/readiness: BD accesible + contadores de catálogo (y si el worker corrió rebuild_similar)."""
    from sqlalchemy import func, text
    from .database import SessionLocal
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))                      # la BD responde
        tracks = db.query(models.Track).filter(models.Track.status == "descargada").count()
        artists = db.query(models.Artist).count()
        similar = db.query(models.Similar).count()
        users = db.query(models.User).count()
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "detail": str(e)}
    finally:
        db.close()
    return {"status": "ok", "tracks": tracks, "artists": artists,
            "similar": similar, "users": users}
