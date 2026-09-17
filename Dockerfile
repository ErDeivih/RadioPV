# RadioPV · API + recolector + worker (imagen común)
#
# La música vive en un volumen del host montado en /music (ver docker-compose.yml).
# Los datos internos (backend.db, radiov.db, carátulas, fotos) en /app/data.
#
# Rutas configurables por entorno (radiov/config.py):
#   RADIOPV_BASE_MUSIC  → raíz de la música   (por defecto /music fuera de Windows)
#   RADIOPV_DATA_DIR    → datos internos      (por defecto /app/data)

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    RADIOPV_ENV=prod \
    RADIOPV_BASE_MUSIC=/music \
    MUSIC_ROOT=/music \
    RADIOPV_DATA_DIR=/app/data \
    MEDIA_ROOT=/app/data

# ffmpeg: lo usan /stream y el análisis de audio del recolector.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-backend.txt .
RUN pip install --no-cache-dir -r requirements-backend.txt \
 && pip install --no-cache-dir librosa soundfile numpy pandas yt-dlp requests

# Código
COPY backend backend
COPY radiov radiov
COPY scripts scripts
COPY run_agent.py ./

RUN mkdir -p /app/data

EXPOSE 8000

# El comando real lo pone docker-compose.yml:
#   api       → uvicorn app.main:app --app-dir backend
#   worker    → python -m app.workers
#   collector → python run_agent.py
CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
