"""P · Estadísticas y tendencias de popularidad del catálogo (listas, recopilaciones, datos)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from .. import popularidad as POP

router = APIRouter(tags=["stats"])


@router.get("/stats/popularidad")
def stats_popularidad(dias: int = Query(7, ge=1, le=90), db: Session = Depends(get_db)):
    """Estado de popularidad: tendencias (subiendo/bajando/nuevas), tops por visitas y por score,
    y agregado por género. Se refresca solo con el worker (cada 6h)."""
    return {
        "dias": dias,
        "tendencias": POP.tendencias(db, dias=dias),
        "estadisticas": POP.estadisticas(db),
    }


@router.get("/stats/recopilaciones")
def stats_recopilaciones(db: Session = Depends(get_db)):
    """Recopilaciones por pico de popularidad: éxitos por época y por género según el máximo
    histórico de visitas ('cuándo fue más popular'). Se alimenta de popularity_history."""
    return POP.recopilaciones(db)
