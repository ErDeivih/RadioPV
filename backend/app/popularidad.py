"""P · Capa de popularidad del catálogo: visitas de YouTube, rank de Deezer, histórico temporal y
un score normalizado. Alimenta listas (tops del momento, tendencias/viral), recopilaciones y
estadísticas.

Fuentes:
  - youtube  → visitas reales (count) vía yt-dlp (tenemos youtube_id). La mejor señal disponible.
  - deezer   → `rank` (ya está en el catálogo; score 0..~1.000.000).
  - spotify  → enchufable: hoy la API pública requiere credenciales OAuth. El almacén (source='spotify')
               y el esquema ya lo soportan; cuando haya credenciales se rellena `plays`.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from . import models

# Tope de popularidad de referencia (log). Log10 de 100.000.000 ≈ 8.0.
_LOG10_REF = 8.0
# Pesos del score compuesto (visitas dominan, rank matiza).
W_VIEWS = 0.7
W_RANK = 0.3


def _score(yt_views: Optional[int], rank: Optional[int]) -> float:
    """Score de popularidad normalizado 0-1: visitas (escala log) + rank de Deezer."""
    s = 0.0
    if yt_views:
        s += min(1.0, math.log10(max(1, yt_views)) / _LOG10_REF) * W_VIEWS
    if rank:
        s += min(1.0, rank / 1_000_000.0) * W_RANK
    return round(s, 4)


def yt_metrics(youtube_id: str | None) -> tuple[int, int]:
    """Visitas y likes reales de un vídeo de YouTube. (views, likes). Sin youtube_id → (0,0)."""
    if not youtube_id:
        return 0, 0
    try:
        import yt_dlp
        url = f"https://www.youtube.com/watch?v={youtube_id}"
        with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True, "noplaylist": True}) as ydl:
            info = ydl.extract_info(url, download=False)
        views = int(info.get("view_count") or 0)
        likes = int(info.get("like_count") or 0)
        return views, likes
    except Exception:  # noqa: BLE001  (vídeo caído, bloqueo, red...) → sin señal
        return 0, 0


def _historial(id_, db, source, metric, valor):
    db.add(models.PopularitySample(track_id=id_, source=source, metric=metric,
                                   valor=float(valor), sampled_at=datetime.utcnow()))


def refrescar(db: Session, limit: int = 40) -> int:
    """Refresca la popularidad de un lote de pistas (las más relevantes por rank/popularidad o las
    recién añadidas sin señal). Escribe columnas actuales + una muestra en el histórico.

    Devuelve cuántas pistas se refrescaron.
    """
    # Prioridad: pistas sin youtube_id no sirven → las que ya tienen señal se refrescan por rank;
    # las nuevas (sin yt_views) se cogen primero para poblar el histórico cuanto antes.
    nuevas = (db.query(models.Track)
              .filter(models.Track.status == "descargada", models.Track.youtube_id.isnot(None),
                      models.Track.yt_views.is_(None))
              .order_by(models.Track.rank.desc()).limit(limit).all())
    if len(nuevas) < limit:
        restantes = limit - len(nuevas)
        ya = [t.id for t in nuevas]
        rep = (db.query(models.Track)
               .filter(models.Track.status == "descargada", models.Track.youtube_id.isnot(None),
                       models.Track.yt_views.isnot(None))
               .order_by(models.Track.popularidad.desc(), models.Track.rank.desc())
               .limit(restantes).all())
        nuevas += [t for t in rep if t.id not in ya]

    n = 0
    for t in nuevas:
        views, likes = yt_metrics(t.youtube_id)
        if not views and (t.yt_views or 0):
            continue                            # sin datos esta vez; conserva el valor previo
        t.yt_views = views
        t.yt_likes = likes
        t.popularidad = _score(views, t.rank)
        _historial(t.id, db, "youtube", "views", views)
        if t.rank:
            _historial(t.id, db, "deezer", "rank", t.rank)
        n += 1
    if n:
        db.commit()
    return n


def tendencias(db: Session, dias: int = 7, n: int = 20) -> dict:
    """Detecta subidas/bajadas comparando la media de visitas de los últimos `dias` con el periodo
    anterior. Devuelve {subiendo: [...], bajando: [...], nuevas: [...]} con mínimo histórico.

    Si aún no hay histórico suficiente, cae a las más vistas (para que la lista 'viral' no vacíe).
    """
    since = datetime.utcnow() - timedelta(days=dias)
    previo = datetime.utcnow() - timedelta(days=2 * dias)
    q = (db.query(models.PopularitySample.track_id, models.Track.title, models.Track.artist,
                  models.Track.genre, models.Track.popularidad, models.Track.yt_views,
                  func.avg(models.PopularitySample.valor).label("media"))
         .join(models.Track, models.Track.id == models.PopularitySample.track_id)
         .filter(models.PopularitySample.source == "youtube",
                 models.PopularitySample.metric == "views",
                 models.PopularitySample.sampled_at >= previo)
         .group_by(models.PopularitySample.track_id))

    filas = []
    for r in q.all():
        # media del periodo reciente vs el anterior
        medio_reciente = (db.query(func.avg(models.PopularitySample.valor))
                          .filter(models.PopularitySample.track_id == r.track_id,
                                  models.PopularitySample.source == "youtube",
                                  models.PopularitySample.metric == "views",
                                  models.PopularitySample.sampled_at >= since)
                          .scalar())
        medio_anterior = (db.query(func.avg(models.PopularitySample.valor))
                          .filter(models.PopularitySample.track_id == r.track_id,
                                  models.PopularitySample.source == "youtube",
                                  models.PopularitySample.metric == "views",
                                  models.PopularitySample.sampled_at < since,
                                  models.PopularitySample.sampled_at >= previo)
                          .scalar())
        if medio_reciente is None:
            continue
        variacion = None
        if medio_anterior:
            variacion = (float(medio_reciente) - float(medio_anterior)) / float(medio_anterior)
        filas.append({
            "track_id": r.track_id, "title": r.title, "artist": r.artist,
            "genre": r.genre, "views": int(r.yt_views or 0),
            "popularidad": r.popularidad, "variacion": variacion,
        })

    subiendo = [f for f in filas if f["variacion"] is not None and f["variacion"] > 0.08]
    bajando = [f for f in filas if f["variacion"] is not None and f["variacion"] < -0.08]
    subiendo.sort(key=lambda f: -(f["variacion"] or 0))
    bajando.sort(key=lambda f: (f["variacion"] or 0))
    # 'nuevas': sin variación (no hay periodo anterior) → candidatas recién pobladas, por visitas
    nuevas = [f for f in filas if f["variacion"] is None]
    nuevas.sort(key=lambda f: -(f["views"] or 0))

    if not (subiendo or nuevas):
        # sin histórico: devolver las más vistas del momento
        nuevas = ([{"track_id": t.id, "title": t.title, "artist": t.artist, "genre": t.genre,
                    "views": int(t.yt_views or 0), "popularidad": t.popularidad, "variacion": None}
                   for t in db.query(models.Track)
                   .filter(models.Track.status == "descargada")
                   .order_by(models.Track.yt_views.desc()).limit(n).all()])

    return {
        "subiendo": subiendo[:n],
        "bajando": bajando[:n],
        "nuevas": nuevas[:n],
    }


def recopilaciones(db: Session, n: int = 15) -> dict:
    """Recopilaciones por pico de popularidad: para cada época y cada género, las pistas con el
    MÁXIMO histórico de visitas (el 'momento' en que fue más popular). Sirve para hacer
    recopilaciones tipo 'Éxitos de los 2000' o 'Lo mejor del rock' por pico real, no por lista estática."""
    pico = (db.query(models.PopularitySample.track_id,
                     func.max(models.PopularitySample.valor).label("pico"))
            .filter(models.PopularitySample.source == "youtube",
                    models.PopularitySample.metric == "views")
            .group_by(models.PopularitySample.track_id).all())
    pico_por = {pid: (float(p) if p is not None else 0.0) for pid, p in pico}

    tracks = db.query(models.Track).filter(models.Track.status == "descargada").all()

    def agrupar(campo):
        grupos: dict[str, list] = {}
        for t in tracks:
            p = pico_por.get(t.id)
            if not p:
                continue
            k = (getattr(t, campo) or "s/época") if campo == "era" else (t.genre or "s/género")
            grupos.setdefault(k, []).append({
                "id": t.id, "title": t.title, "artist": t.artist,
                "genre": t.genre, "era": t.era, "pico": int(round(p)),
                "views": int(t.yt_views or 0),
            })
        return {k: sorted(v, key=lambda x: -x["pico"])[:n] for k, v in grupos.items()}

    return {"por_era": agrupar("era"), "por_genero": agrupar("genre")}


def estadisticas(db: Session) -> dict:
    """Agregados de popularidad por género/época + los temas más vistos y mayor score."""
    def top(orden, n=15):
        return [{"id": t.id, "title": t.title, "artist": t.artist, "genre": t.genre,
                 "views": int(t.yt_views or 0), "popularidad": t.popularidad}
                for t in db.query(models.Track)
                .filter(models.Track.status == "descargada", models.Track.yt_views.isnot(None))
                .order_by(orden).limit(n).all()]

    por_genero = [{"genero": g, "n": n} for g, n in db.query(models.Track.genre, func.count(models.Track.id))
                  .filter(models.Track.status == "descargada", models.Track.popularidad.isnot(None))
                  .group_by(models.Track.genre).all()]
    # media de popularidad por género
    medias_gen = [{"genero": g, "media_pop": round(float(m), 3), "n": c}
                  for g, m, c in db.query(models.Track.genre,
                                          func.avg(models.Track.popularidad),
                                          func.count(models.Track.id))
                  .filter(models.Track.status == "descargada", models.Track.popularidad.isnot(None))
                  .group_by(models.Track.genre).all()]
    medias_gen.sort(key=lambda x: -(x["media_pop"] or 0))

    return {
        "top_views": top(models.Track.yt_views.desc()),
        "top_score": top(models.Track.popularidad.desc()),
        "por_genero": medias_gen,
        "total_popular": db.query(models.Track)
        .filter(models.Track.status == "descargada", models.Track.popularidad > 0).count(),
    }
