import json
from collections import Counter
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models, schemas
from ..security import get_current_user

router = APIRouter(tags=["wrapped"])


@router.get("/wrapped")
def wrapped(period: str = Query("week", pattern="^(week|year)$"), db: Session = Depends(get_db),
            user: models.User = Depends(get_current_user)):
    """Resumen de escucha del periodo (top artistas/géneros, minutos, redescubrimientos)."""
    since = datetime.utcnow() - (timedelta(days=7) if period == "week" else timedelta(days=365))
    plays = (db.query(models.Play).filter(models.Play.user_id == user.id,
                                          models.Play.played_at >= since).all())
    tids = {p.track_id for p in plays}
    tracks = {t.id: t for t in db.query(models.Track).filter(models.Track.id.in_(tids))} if tids else {}
    artists = Counter()
    genres = Counter()
    minutos = 0.0
    for p in plays:
        t = tracks.get(p.track_id)
        if not t:
            continue
        if t.artist:
            artists[t.artist] += 1
        if t.genre:
            genres[t.genre] += 1
        minutos += (p.seconds_listened or (t.duration or 0)) / 60.0
    top_tracks = [{"id": t.id, "title": t.title, "artist": t.artist, "plays": n}
                  for t, n in Counter(
                      (tracks[p.track_id], 1) for p in plays if p.track_id in tracks
                  ).items()]
    top_tracks = sorted(top_tracks, key=lambda x: -x["plays"])[:10]
    return {
        "period": period,
        "top_artists": [{"name": a, "count": c} for a, c in artists.most_common(10)],
        "top_genres": [{"name": g, "count": c} for g, c in genres.most_common(10)],
        "minutes": round(minutos, 1),
        "top_tracks": top_tracks,
    }


@router.get("/requests/buscar")
def buscar_para_pedir(q: str = Query(..., min_length=2), db: Session = Depends(get_db),
                      user: models.User = Depends(get_current_user)):
    """Busca una canción para pedirla: primero en casa, y si no está, en YouTube.

    POR QUÉ ASÍ
    -----------
    La página de pedir canciones era una caja de texto: escribías «Artista - Título» y a esperar.
    El problema es que **no sabías si ya la tenías** (y pedir algo que ya está es trabajo perdido
    para el recolector) ni **cuál de las versiones** se iba a bajar: de un mismo tema hay el
    original, el remix, el directo y veinte subidas distintas, y el buscador por texto bajaba la
    que le parecía. Muchas veces no era la que el usuario quería.

    Ahora se devuelven tres cosas:
      · `en_biblioteca` — lo que YA está en el catálogo (con su id, para poder oírlo ahora mismo);
      · `en_youtube`   — resultados REALES de YouTube con su duración y su id de vídeo, para elegir
                         la versión exacta; se marca cuáles están ya en el catálogo;
      · `en_cola`      — lo que ya se ha pedido y sigue pendiente (para no pedirlo dos veces).
    """
    texto = (q or "").strip()
    if len(texto) < 2:
        raise HTTPException(400, "Escribe al menos dos letras")

    # --- 1) ¿está ya en casa? Se busca por título y por artista, sin acentos (como escribe la gente).
    from ..database import HAY_SIN_ACENTOS, normalizar_busqueda
    consulta = db.query(models.Track).filter(models.Track.status == "descargada")
    if HAY_SIN_ACENTOS:
        from sqlalchemy import text as sqltext
        consulta = consulta.filter(sqltext(
            "sin_acentos(tracks.title) LIKE :q OR sin_acentos(tracks.artist) LIKE :q"
        ).bindparams(q=f"%{normalizar_busqueda(texto)}%"))
    else:
        consulta = consulta.filter(models.Track.title.ilike(f"%{texto}%")
                                   | models.Track.artist.ilike(f"%{texto}%"))
    biblioteca = consulta.order_by(models.Track.rank.desc().nullslast()).limit(15).all()

    # --- 2) lo que ya está pedido y pendiente (para no pedirlo dos veces)
    like = f"%{texto}%"
    en_cola = [{"id": r.id, "text": r.text} for r in
               db.query(models.Request)
               .filter(models.Request.status == "pendiente")
               .filter(models.Request.text.ilike(like)).limit(10).all()]

    # --- 3) YouTube: qué versiones hay de verdad, con su duración, para elegir la buena
    resultados: list[dict] = []
    aviso = None
    try:
        from radiov import youtube as Y
        ids_dentro = {r[0] for r in db.query(models.Track.youtube_id)
                      .filter(models.Track.youtube_id.isnot(None)).all()}
        for cand in Y.search_videos(texto, 12):
            vid = cand.get("id")
            if not vid:
                continue
            resultados.append({
                "video_id": vid,
                "titulo": cand.get("title") or "",
                "canal": cand.get("uploader") or cand.get("channel") or "",
                "duracion": cand.get("duration"),
                "en_catalogo": vid in ids_dentro,
            })
    except Exception as e:  # noqa: BLE001
        # Que YouTube no conteste (o tarde) no puede dejar la página inservible: sin resultados se
        # sigue pudiendo pedir escribiendo el texto a mano. Se avisa en vez de mentir con una lista
        # vacía, que parecería «no existe esa canción».
        aviso = f"No se pudo preguntar a YouTube ({type(e).__name__}). Puedes pedirla escribiéndola."
        resultados = []

    return {
        "consulta": texto,
        "aviso": aviso,
        "en_biblioteca": [
            {"id": t.id, "titulo": t.title, "artista": t.artist, "duracion": t.duration}
            for t in biblioteca
        ],
        "en_youtube": resultados,
        "en_cola": en_cola,
    }


@router.post("/requests")
def create_request(data: dict, db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)):
    """Encola una canción pedida desde la app ("estado vacío" de una búsqueda)."""
    text = (data.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text es obligatorio")
    if len(text) > 200:
        raise HTTPException(400, "El texto es demasiado largo")
    # Si ya se pidió y sigue pendiente, no se duplica: la página se refresca y parece que no ha
    # hecho nada, y encima el recolector trabajaría dos veces por lo mismo.
    ya = (db.query(models.Request)
          .filter_by(user_id=user.id, text=text)
          .filter(models.Request.status == "pendiente").first())
    if ya:
        return {"ok": True, "text": text, "repetida": True}
    # El vídeo exacto, si el usuario lo ha elegido en la lista de resultados. Con esto el
    # recolector baja ESA versión y no la que le parezca al buscador.
    video = (data.get("youtube_id") or "").strip() or None
    duracion = data.get("duration")
    db.add(models.Request(user_id=user.id, text=text, status="pendiente",
                          youtube_id=video,
                          duration=float(duracion) if duracion else None))
    db.commit()
    return {"ok": True, "text": text, "youtube_id": video}


@router.get("/requests")
def my_requests(db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    """Mis peticiones, con su estado, para la página de pedir canciones.

    Estados: `pendiente` (en cola), `descargada` (ya está en el catálogo) y `fallida` (se buscó y
    no se encontró). Se devuelven las últimas primero.
    """
    filas = (db.query(models.Request).filter_by(user_id=user.id)
             .order_by(models.Request.created_at.desc()).limit(100).all())
    return [
        {"id": r.id, "text": r.text, "status": r.status or "pendiente",
         "created_at": r.created_at.isoformat(timespec="seconds") if r.created_at else None}
        for r in filas
    ]


@router.delete("/requests/{request_id}")
def borrar_request(request_id: int, db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)):
    """Quita una petición de mi lista (sólo si es mía)."""
    r = db.query(models.Request).filter_by(id=request_id, user_id=user.id).first()
    if not r:
        raise HTTPException(404, "Petición no encontrada")
    db.delete(r)
    db.commit()
    return {"ok": True}


def _ids_del_mix(mix: models.Mix) -> list[int]:
    """Los ids de las canciones de un mix, en su orden.

    Se guardan como JSON en una columna de texto (`tracks_json`), así que hay que tolerar que
    venga vacío o mal formado: un mix a medio generar no puede tumbar la portada entera.
    """
    try:
        datos = json.loads(mix.tracks_json or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(datos, list):
        return []
    return [int(x) for x in datos if isinstance(x, int)]


def _canciones_del_mix(db: Session, mix: models.Mix) -> list[models.Track]:
    """Las canciones del mix, EN EL ORDEN del mix (no en el que las devuelva la base)."""
    ids = _ids_del_mix(mix)
    if not ids:
        return []
    filas = {t.id: t for t in db.query(models.Track).filter(models.Track.id.in_(ids))}
    return [filas[i] for i in ids if i in filas]


def _mix_out(db: Session, mix: models.Mix) -> schemas.MixOut:
    """Serializador único de un mix (igual que `_out` en las listas): así `/mixes` y cualquier
    otra ruta que devuelva mixes no se olvidan de la portada ni del número de canciones."""
    canciones = _canciones_del_mix(db, mix)
    # Sólo se usan las carátulas LOCALES (`/media/covers/…`): son las que la interfaz sabe pedir a
    # la API. Las `cover_url` son enlaces externos (Deezer, YouTube) y la interfaz les antepone la
    # base de la API, así que acabarían en una URL inventada que no carga.
    collage = [t.cover for t in canciones if t.cover][:4]
    return schemas.MixOut(id=mix.id, kind=mix.kind, seed=mix.seed, tracks_json=mix.tracks_json,
                          explicacion=mix.explicacion, created_at=mix.created_at,
                          uri=f"radiopv:mix:{mix.kind}", n_tracks=len(canciones),
                          collage=collage)


@router.get("/mixes", response_model=list[schemas.MixOut])
def my_mixes(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """U2 · los mixes del usuario (kind, explicacion, tracks_json) para la fila "Hecho para ti".
    Si el usuario aún no tiene mezclas (recién registrado), se generan en frío al momento."""
    mix = (db.query(models.Mix).filter_by(user_id=user.id)
           .order_by(models.Mix.created_at.desc()).all())
    if not mix:
        from ..workers import _generar_mixes_usuario
        _generar_mixes_usuario(db, user)
        mix = (db.query(models.Mix).filter_by(user_id=user.id)
               .order_by(models.Mix.created_at.desc()).all())
    return [_mix_out(db, m) for m in mix]


@router.get("/mixes/{kind}/tracks", response_model=list[schemas.TrackOut])
def tracks_of_mix(kind: str, user: models.User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Las canciones de un mix, para que «Hecho para ti» SUENE.

    POR QUÉ EXISTE
    --------------
    Las tarjetas de «Hecho para ti» llevaban a `/search`, que no busca nada: se pulsara lo que se
    pulsara, la música no sonaba. Los ids de cada mix ya estaban en la base (`tracks_json`), pero no
    había ninguna ruta que los convirtiera en canciones, así que la interfaz no tenía forma de
    reproducir un mix ni de enseñar su lista."""
    mix = (db.query(models.Mix).filter_by(user_id=user.id, kind=kind)
           .order_by(models.Mix.created_at.desc()).first())
    if not mix:
        # Sin mix de ese tipo se generan todos (es lo mismo que hace `/mixes`) y se reintenta
        # una vez: un usuario recién registrado no tiene ninguno todavía.
        from ..workers import _generar_mixes_usuario
        _generar_mixes_usuario(db, user)
        mix = (db.query(models.Mix).filter_by(user_id=user.id, kind=kind)
               .order_by(models.Mix.created_at.desc()).first())
    if not mix:
        raise HTTPException(404, "Ese mix no existe")
    return _canciones_del_mix(db, mix)
