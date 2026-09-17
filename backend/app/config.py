"""Configuración central del backend. Todo lo que dependa del entorno se lee aquí."""
import os
from pathlib import Path

ENV = os.environ.get("RADIOPV_ENV", "dev").lower()        # dev | prod

_DEV_SECRET = "solo-para-desarrollo-no-usar-en-produccion"
SECRET_KEY = os.environ.get("SECRET_KEY") or (_DEV_SECRET if ENV == "dev" else "")
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY es obligatoria con RADIOPV_ENV=prod. "
        "Genérala con: python -c \"import secrets;print(secrets.token_urlsafe(48))\""
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
STREAM_TOKEN_EXPIRE_MINUTES = int(os.environ.get("STREAM_TOKEN_EXPIRE_MINUTES", "30"))

_PROJECT_ROOT = Path(__file__).resolve().parents[2]        # F:\EspacioCodigo\RadioPV

# Raíces de ficheros. En Docker/Linux se sobrescriben por variable de entorno.
MUSIC_ROOT = Path(os.environ.get("MUSIC_ROOT", r"E:\Musica"))
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", str(_PROJECT_ROOT / "data")))

# Orígenes permitidos (CORS). Por defecto local + Tailscale (red privada, sin internet).
# Añade la IP/dominio de tu tailnet en la env ALLOWED_ORIGINS (p. ej. "http://100.64.0.10:3000").
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000"
).split(",") if o.strip()]

# Registro solo por invitación (vacío = registro abierto, solo aceptable en dev)
INVITE_CODE = os.environ.get("INVITE_CODE", "")
