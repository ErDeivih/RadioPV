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

# La columna `tags` NO sólo lleva estados de ánimo: `radiov.catalog.derive_tags` mete ahí también la
# era («20s»), el idioma («es»), el género de adorno («house», «urbano») y avisos («sin bpm»,
# «remix»). Eso está bien para buscar, pero **la fila de «estados de ánimo» de la aplicación no puede
# enseñar tarjetas que digan «es» o «20s»**: es lo que estaba pasando (medido el 21/09/2026:
# moods = energia alta, fiesta, trabajo, …, es, 20s, en, house, pop es, sin bpm).
#
# Aquí se declara qué es un estado de ánimo de verdad. Cualquier etiqueta que no esté en esta lista ni
# en la de «no es un ánimo» se queda fuera, y hay una prueba que compara las dos listas con lo que
# `derive_tags` puede producir: si alguien añade una etiqueta nueva, la prueba avisa en vez de que
# aparezca una tarjeta rara en la aplicación.
MOODS_VALIDOS = frozenset({
    "meditacion", "tranquilidad", "relax", "chill", "energia baja", "energia alta",
    "concentracion", "trabajo", "romantica", "fiesta", "fiesta temprana", "fiesta puntual",
    "fiesta tardia", "perreo", "gimnasio", "correr", "cardio", "sprint", "estudio",
    "epica", "triste", "feliz", "acustico", "lofi",
})
# Y lo que sale en `tags` pero no es un ánimo (se listan para que la prueba pueda comprobar que no se
# queda nada sin clasificar).
TAGS_QUE_NO_SON_ANIMO = frozenset({
    # idiomas
    "es", "en", "it", "fr", "other",
    # épocas
    "20s", "10s", "00s", "90s", "80s", "70s", "60s", "vintage",
    # género de adorno
    "house", "disco", "urbano", "clasica", "instrumental", "soul", "indie", "folk",
    # avisos y cruces
    "sin bpm", "remix", "pop es", "pop es 2000s",
})

_cache: tuple[float, dict] | None = None


def es_animo(tag: str) -> bool:
    """¿Esta etiqueta se puede enseñar como estado de ánimo? (ver `MOODS_VALIDOS`)."""
    return (tag or "").strip().lower() in MOODS_VALIDOS


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
            if m and es_animo(m):
                moods[m] += 1

    def series(counter: Counter) -> list[dict]:
        # Los valores VACÍOS fuera: había una era sin valor ('') y la aplicación pintaba una tarjeta
        # de género/época **sin nombre**, que parece un fallo. Un dato que no está no se enseña.
        return [{"value": v, "count": n}
                for v, n in sorted(counter.items(), key=lambda x: -x[1])
                if v not in (None, "")]

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
