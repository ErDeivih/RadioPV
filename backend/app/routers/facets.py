"""`/facets` con una sola pasada y con caché.

Antes: cinco recorridos de la tabla (genre, era, language, year y tags por separado) más un bucle
en Python sobre TODAS las etiquetas, en **cada** petición — y el endpoint es público, así que
cualquiera podía pedirlo en bucle. El catálogo sólo cambia cuando corre la sincronización (cada
30 minutos), así que recalcularlo decenas de veces por minuto es trabajo tirado.
"""
import time
from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models

router = APIRouter(tags=["facets"])

# Cuánto se puede reutilizar el resultado. El catálogo cambia cada 30 minutos (sync_catalogo), así
# que 5 minutos es margen de sobra y quita casi todo el trabajo repetido.
TTL_SEGUNDOS = 300

_cache: tuple[float, dict] | None = None


def _contar(db: Session) -> dict:
    """Cuenta géneros, épocas, idiomas, años y estados de ánimo en UNA sola pasada."""
    genres: Counter = Counter()
    eras: Counter = Counter()
    langs: Counter = Counter()
    years: Counter = Counter()
    moods: Counter = Counter()

    # Una consulta con las cinco columnas en vez de cinco consultas de una columna.
    filas = db.query(
        models.Track.genre, models.Track.era, models.Track.language,
        models.Track.year, models.Track.tags,
    ).filter(models.Track.status == "descargada")

    for genre, era, language, year, tags in filas:
        genres[genre] += 1
        eras[era] += 1
        langs[language] += 1
        years[year] += 1
        for m in (tags or "").split(","):
            m = m.strip()
            if m:
                moods[m] += 1

    def series(counter: Counter) -> list[dict]:
        return [{"value": v, "count": n}
                for v, n in sorted(counter.items(), key=lambda x: -x[1])]

    return {
        "genres": series(genres),
        "eras": series(eras),
        "languages": series(langs),
        "years": series(years),
        "moods": series(moods),
    }


def invalidar() -> None:
    """Tira la caché. Lo usa la sincronización del catálogo para no servir datos viejos."""
    global _cache
    _cache = None


@router.get("/facets")
def facets(db: Session = Depends(get_db)):
    """Valores reales (con conteo) para que la UI no los lleve escritos a fuego."""
    global _cache
    ahora = time.time()
    if _cache is not None:
        momento, datos = _cache
        if ahora - momento < TTL_SEGUNDOS:
            return datos
    datos = _contar(db)
    _cache = (ahora, datos)
    return datos
