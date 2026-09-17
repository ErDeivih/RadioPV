from collections import Counter
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models

router = APIRouter(tags=["facets"])


@router.get("/facets")
def facets(db: Session = Depends(get_db)):
    """Valores reales (con conteo) para que la UI no los lleve escritos a fuego."""
    genres = Counter(r[0] for r in db.query(models.Track.genre)
                     .filter(models.Track.status == "descargada"))
    eras = Counter(r[0] for r in db.query(models.Track.era)
                   .filter(models.Track.status == "descargada"))
    langs = Counter(r[0] for r in db.query(models.Track.language)
                    .filter(models.Track.status == "descargada"))
    years = Counter(r[0] for r in db.query(models.Track.year)
                    .filter(models.Track.status == "descargada"))
    # moods: se extraen de la columna tags (formato csv)
    moods = Counter()
    for (tags,) in db.query(models.Track.tags).filter(models.Track.status == "descargada"):
        for m in (tags or "").split(","):
            m = m.strip()
            if m:
                moods[m] += 1

    def series(counter):
        return [{"value": v, "count": n} for v, n in sorted(counter.items(), key=lambda x: -x[1])]

    return {
        "genres": series(genres),
        "eras": series(eras),
        "languages": series(langs),
        "years": series(years),
        "moods": series(moods),
    }
