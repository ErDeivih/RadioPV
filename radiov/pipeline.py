from __future__ import annotations

import datetime
import json
import random
import re
from pathlib import Path
from typing import Optional

from . import db
from . import models as M
from . import catalog as C
from . import deezer
from . import youtube
from . import quality
from .config import load_settings


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def parse_text(text: str) -> tuple[str, str]:
    """Divide una petición en (artista, título). Acepta 'Artista - Título' y 'Título by Artista'."""
    text = (text or "").strip()
    if not text:
        return "", ""
    m = re.split(r"\s+(?:-|by)\s+", text, maxsplit=1, flags=re.I)
    if len(m) == 2:
        a, t = m[0].strip(), m[1].strip()
        # Si parecía 'titulo - artista', intenta detectar
        return a, t
    return "", text


def _resolve_genre_lang(artist: str, title: str, genre: Optional[str], language: Optional[str]):
    genre = genre or C.guess_genre(title, artist)
    language = language or C.detect_language(title, artist)
    return genre, language


def _persist_yt(yt: dict, *, genre: str, language: str, source: str, meta: Optional[dict] = None) -> Optional[int]:
    """Guarda en la BD el resultado de una descarga ya hecha y lo cataloga."""
    meta = meta or {}
    rec = {
        "title": yt.get("title") or meta.get("title", ""),
        "artist": yt.get("artist") or meta.get("artist", ""),
        "album": meta.get("album"),
        "release_date": meta.get("release_date"),
        # El año y la carátula pueden venir del propio vídeo de YouTube (ver `youtube._download_by_id`).
        # Es lo único que hay para el contenido que no está en las tiendas de música, y sin ello la
        # ficha se quedaba «incompleta» para siempre (la puerta de metadatos los exige) y la canción
        # no llegaba nunca a la aplicación.
        "year": meta.get("year") or yt.get("year"),
        "cover_url": meta.get("cover_url") or yt.get("cover_url") or yt.get("thumbnail"),
        "genre": genre,
        "language": language,
        "duration": yt.get("duration") or meta.get("duration"),
        "deezer_id": meta.get("deezer_id"),
        "rank": meta.get("rank"),
        "source": source,
        "status": M.STATUS_DOWNLOADED,
        "youtube_id": yt.get("youtube_id"),
        "youtube_url": yt.get("youtube_url"),
        "file_path": yt.get("file_path"),
        "file_size": yt.get("file_size"),
        "match_score": yt.get("match_score"),
        "added_at": _now(),
    }
    rec = C.catalog_track(rec)
    # Clasificar por el género del ÁLBUM de Deezer (fuente de verdad); si no se puede, 'other'.
    # Sustituye al género del seed (que producía 'pop' a tope). Respeta el override manual.
    album_id = rec.get("album_id") or meta.get("album_id")
    if album_id:
        g = C.guess_genre(rec.get("title", ""), rec.get("artist", ""), album_id)
        if g != "other":
            rec["genre"] = g
        else:
            rec["genre"] = "other"      # regla: no inventar, nunca 'pop' por defecto
    # Organizar en la carpeta catalogada y actualizar la ruta/ficha
    try:
        from .catalog import organize_track
        new_path = organize_track(rec)
        if new_path:
            rec["file_path"] = C._rel_music(new_path)
            rec["file_size"] = Path(new_path).stat().st_size if Path(new_path).exists() else 0
    except Exception as e:  # noqa: BLE001
        db.log_event(f"Organizar: {e}", "warning")
    # Puerta de calidad: si no pasa, entra en cuarentena (nunca se descarta en silencio).
    ok, motivo = quality.revisar(rec)
    if not ok:
        rec["status"] = M.STATUS_QUARANTINE
        db.log_event(f"🚧 Cuarentena: {rec['artist']} - {rec['title']} → {motivo}", "warning")
    else:
        # C4 · metadatos completos: si falta algo obligatorio, no se publica aún (lo completa el
        # análisis → revisor antes de 'descargada').
        #
        # La regla de qué es obligatorio de verdad vive en `radiov.catalog.campos_que_faltan`, y es la
        # MISMA que usa el republicador: estaba escrita dos veces con excepciones distintas y una de
        # ellas se quedó sin poner (las canciones recuperadas del disco, sin año ni carátula posibles,
        # se quedaban 'incompleta' para siempre sin llegar nunca a la aplicación).
        if load_settings().get("metadata_strict", True):
            faltan = C.campos_que_faltan(rec)
            if faltan:
                rec["status"] = "incompleta"
                db.log_event(f"⏳ Incompleta ({','.join(faltan)}): {rec['artist']} - {rec['title']}", "info")
    tid = db.add_track(rec, youtube_id=rec.get("youtube_id"))
    db.log_event(f"⬇️ Descargada: {rec['artist']} - {rec['title']} (BPM {rec.get('bpm')})", "info")
    return tid


def fulfill_track(
    artist: str,
    title: str,
    *,
    expected_duration: Optional[float] = None,
    genre: Optional[str] = None,
    language: Optional[str] = None,
    source: str = M.SOURCE_ONDEMAND,
    meta: Optional[dict] = None,
) -> Optional[int]:
    """Descarga una canción desde YouTube, la cataloga y la guarda en la BD. Devuelve el id o None."""
    artist = (artist or "").strip()
    title = (title or "").strip()
    if not title:
        return None
    # Evitar duplicados: si ya está en la biblioteca, no volver a descargar. Se comprueba con la
    # clave normalizada (no con el texto exacto), porque la misma canción aparece como «(Official
    # Video)», «(feat. …)» o subida en otro vídeo, y eso antes colaba como canción nueva.
    existing = db.pista_existente(artist=artist, title=title)
    if existing:
        db.log_event(f"⏩ Ya estaba en la biblioteca: {artist} - {title}", "info")
        return existing
    genre, language = _resolve_genre_lang(artist, title, genre, language)
    meta = dict(meta) if meta else {}
    if meta.get("deezer_id"):
        meta = deezer.enrich_meta(meta)
    else:
        # candidato sin id (éxitos/Apple): intenta obtener año/álbum desde Deezer
        enriched = deezer.metadata_for(artist, title)
        if enriched:
            enriched.update(meta)
            meta = enriched

    yt = youtube.search_and_download(
        artist, title,
        expected_duration=expected_duration,
        genre=genre, language=language, source=source,
    )
    if not yt or yt.get("skipped"):
        return None
    return _persist_yt(yt, genre=genre, language=language, source=source, meta=meta)


def process_text(text: str, source: str = M.SOURCE_ONDEMAND) -> Optional[int]:
    """Añade una canción pedida por texto (artista - título o título)."""
    artist, title = parse_text(text)
    tid = fulfill_track(artist, title, source=source)
    if tid is None:
        db.log_event(f"No se pudo descargar: {text}", "warning")
    return tid


def process_playlist(url: str, source: str = M.SOURCE_ONDEMAND) -> int:
    """Descarga una playlist de YouTube entera y persiste cada canción. Devuelve cuántas añadió."""
    count = 0
    for res in youtube.download_playlist(url, source=source):
        genre = res.get("genre") or C.guess_genre(res.get("title", ""), res.get("artist", ""))
        language = res.get("language") or C.detect_language(res.get("title", ""), res.get("artist", ""))
        tid = _persist_yt(res, genre=genre, language=language, source=source)
        if tid is not None:
            count += 1
    db.log_event(f"Playlist: {count} canciones añadidas", "info")
    return count


def is_youtube_url(text: str) -> bool:
    return bool(re.search(r"youtube\.com/(?:playlist|watch|shorts|@)|youtu\.be", text or "", re.I))


def _known_artist(client: deezer.DeezerClient, artist_obj: dict, min_rank: int) -> bool:
    """Un artista 'real' tiene muchos álbumes o un tema top con cierto ranking."""
    if (artist_obj.get("nb_album") or 0) >= 10:
        return True
    try:
        top = client.artist_top(artist_obj.get("id"), limit=1)
        if top and (top[0].get("rank") or 0) >= min_rank:
            return True
    except deezer.DeezerError:
        pass
    return False


def _famous_artist(client: deezer.DeezerClient, artist_obj: dict, min_rank: int) -> bool:
    """Solo un artista realmente popular (tema top con alto ranking)."""
    try:
        top = client.artist_top(artist_obj.get("id"), limit=1)
        return bool(top and (top[0].get("rank") or 0) >= min_rank)
    except deezer.DeezerError:
        return False


def interpret_priority_line(line: str) -> Optional[dict]:
    """Interpreta una línea de la caja de prioridades: artista, álbum o canción.

    Prefijos para forzar el tipo: 'artista: X', 'album: X', 'cancion: X' (o a:/al:/s:).
    Sin prefijo el sistema lo deduce (artista conocido → álbum convincente → canción).
    """
    line = (line or "").strip()
    if not line:
        return None
    deacc = lambda s: C._deaccent(s or "").lower().strip()
    client = deezer.DeezerClient()
    genre = C.guess_genre(line)
    language = C.detect_language(line)

    low = line.lower()
    force = None
    if low.startswith("artista:") or low.startswith("a:"):
        force, line = "artist", line.split(":", 1)[1].strip()
    elif low.startswith("album:") or low.startswith("al:"):
        force, line = "album", line.split(":", 1)[1].strip()
    elif low.startswith("cancion:") or low.startswith("canción:") or low.startswith("s:"):
        force, line = "song", line.split(":", 1)[1].strip()
    if not line:
        return None

    min_rank = int(load_settings().get("min_rank", 200000))

    # 1) artista
    if force in (None, "artist"):
        for a in client.search_artists(line, limit=8):
            if deacc(a.get("name")) == deacc(line):
                if force == "artist" or _known_artist(client, a, min_rank):
                    return {"kind": "artist", "value": line, "genre": genre,
                            "language": language, "deezer_id": a.get("id")}
                # coincidencia de nombre pero no conocido: seguir probando otros
        if force == "artist":
            return {"kind": "artist", "value": line, "genre": genre, "language": language}
    # 2) álbum (convincente: artista conocido o bastantes pistas)
    if force in (None, "album"):
        for a in client.search_albums(line, limit=10):
            if deacc(a.get("title")) != deacc(line):
                continue
            artist = a.get("artist", {}).get("name", "") if isinstance(a.get("artist"), dict) else ""
            nb = int(a.get("nb_tracks") or 0)
            known_artist = False
            if artist:
                for ar in client.search_artists(artist, limit=3):
                    if deacc(ar.get("name")) == deacc(artist) and _famous_artist(client, ar, min_rank):
                        known_artist = True
                        break
            if force == "album" or (known_artist and nb >= 5):
                return {"kind": "album", "value": line, "genre": genre, "language": language,
                        "album_artist": artist, "album_id": a.get("id"),
                        "album_title": a.get("title"),
                        "album_id_or_name": a.get("id") or line}
        if force == "album":
            return {"kind": "album", "value": line, "genre": genre, "language": language}
    # 3) canción
    artist, title = parse_text(line)
    return {"kind": "song", "value": line, "genre": genre, "language": language,
            "artist": artist, "title": title or line}


def _clean_phrase(text: str) -> str:
    words = ["más", "mas", "quiero", "quierese", "pon", "ponme", "poned", "busca", "descarga",
             "añade", "agrega", "agregar", "añadir", "algo", "de", "del", "por", "favor", "la",
             "el", "los", "las", "un", "una", "musica", "música", "cancion", "canciones", "canción"]
    parts = text.strip().split()
    out = [p for p in parts if p.lower() not in words]
    cleaned = " ".join(out)
    return cleaned or text.strip()


def interpret_natural(text: str) -> list[dict]:
    """Interpreta una frase en lenguaje natural y la convierte en peticiones (año, género, artista…)."""
    text = (text or "").strip()
    items: list[dict] = []
    if not text:
        return items
    # ¿pide un año? ('más canciones de 2015', '2015')
    m = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    if m:
        items.append({"kind": "year", "year": int(m.group(1)), "value": m.group(1)})
        return items
    # ¿pide un género?
    g = C.guess_genre(text)
    if g != "other":
        items.append({"kind": "genre", "genre": g, "value": g, "language": C.detect_language(text)})
        return items
    # resto → artista/álbum/canción
    it = interpret_priority_line(_clean_phrase(text))
    if it:
        items.append(it)
    return items


def _seeds_for_genre(genre: str) -> list[str]:
    for seed in load_settings().get("agent_seeds", []):
        if seed.get("genre") == genre and seed.get("mode") in ("explore", "genre_artists"):
            return list(seed.get("seeds") or [])
    return []


def _download_year(client: deezer.DeezerClient, year: int, genre: str,
                   language: str, limit: int = 15) -> int:
    """Descarga canciones populares de un año concreto (filtra por fecha de Deezer)."""
    import datetime as _dt
    added = 0
    seen: set[str] = set()
    queries = [str(year), f"{year} hits", f"canciones {year}"]
    for q in queries:
        if added >= limit:
            break
        try:
            results = client.search(q, limit=25, index=0)
        except deezer.DeezerError:
            break
        for it in results:
            if added >= limit or not it.get("id"):
                continue
            track = client.to_track(it, genre=genre, language=language, source=M.SOURCE_PRIORITY)
            key = f"{track['artist'].lower()}|{track['title'].lower()}"
            if key in seen or db.track_exists_by_artist_title(track["artist"], track["title"]):
                continue
            try:
                d = client.track_detail(str(it["id"]))
            except deezer.DeezerError:
                continue
            rel = str(d.get("release_date") or "")[:4]
            if rel != str(year):
                continue
            seen.add(key)
            track["deezer_id"] = str(it["id"])
            track["year"] = year
            track["release_date"] = d.get("release_date")
            tid = fulfill_track(track["artist"], track["title"], expected_duration=track.get("duration"),
                                genre=genre, language=language, source=M.SOURCE_PRIORITY, meta=track)
            if tid is not None:
                added += 1
    return added


def process_priority_item(item: dict) -> int:
    """Descarga las canciones más conocidas de un artista, un álbum o una canción concreta."""
    cfg = load_settings()
    client = deezer.DeezerClient()
    kind = item.get("kind")
    genre = item.get("genre") or "other"
    language = item.get("language") or M.LANG_OTHER
    added = 0

    def _dl(cand_meta: dict) -> None:
        nonlocal added
        if db.track_exists_by_artist_title(cand_meta["artist"], cand_meta["title"]):
            return
        if cand_meta.get("deezer_id") and db.track_exists_by_deezer(cand_meta["deezer_id"]):
            return
        if db.is_blacklisted(M.BLACKLIST_ARTIST, cand_meta["artist"]):
            return
        if db.is_blacklisted(M.BLACKLIST_SONG, f"{cand_meta['title']}|{cand_meta['artist']}"):
            return
        cand_meta = deezer.enrich_meta(dict(cand_meta))
        tid = fulfill_track(
            cand_meta["artist"], cand_meta["title"],
            expected_duration=cand_meta.get("duration"),
            genre=cand_meta.get("genre") or genre,
            language=cand_meta.get("language") or language,
            source=M.SOURCE_PRIORITY, meta=cand_meta,
        )
        if tid is not None:
            added += 1

    if kind == "artist":
        aid = item.get("deezer_id") or client.search_artist_id(item["value"])
        if not aid:
            db.log_event(f"No se encontró al artista: {item['value']}", "warning")
            return 0
        for t in client.artist_top(aid, limit=int(cfg.get("priority_artist_songs", 12))):
            meta = client.to_track(t, genre=genre, language=language, source=M.SOURCE_PRIORITY)
            _dl(meta)
    elif kind == "album":
        aid = item.get("album_id")
        if not aid:
            for a in client.search_albums(item.get("value", ""), limit=5):
                aid = a.get("id")
                item["album_artist"] = item.get("album_artist") or (
                    a.get("artist", {}).get("name", "") if isinstance(a.get("artist"), dict) else "")
                break
        if not aid:
            db.log_event(f"No se encontró el álbum: {item['value']}", "warning")
            return 0
        album_artist = item.get("album_artist") or ""
        cap = cfg.get("priority_album", "all")
        tracks = client.album_tracks(aid)
        if cap != "all":
            tracks = tracks[: int(cap)]
        for t in tracks:
            meta = client.to_track(t, genre=genre, language=language, source=M.SOURCE_PRIORITY)
            if album_artist and not meta["artist"]:
                meta["artist"] = album_artist
            _dl(meta)
    elif kind == "genre":
        seeds = _seeds_for_genre(item.get("genre", ""))
        seed = {"mode": "explore", "genre": item.get("genre", "other"), "language": language, "seeds": seeds}
        added = process_seed(seed, client=client,
                             max_downloads=int(cfg.get("agent_downloads_per_seed_per_pass", 3)) * 4)
    elif kind == "year":
        added = _download_year(client, int(item.get("year") or 0), genre, language,
                               limit=int(cfg.get("priority_artist_songs", 12)))
    else:  # canción
        item = dict(item)
        _dl({"artist": item.get("artist") or "", "title": item.get("title") or item["value"],
             "genre": genre, "language": language, "source": M.SOURCE_PRIORITY})
    db.log_event(f"Prioridad «{item.get('value')}»: +{added} canciones", "info")
    return added


def _partir_titulo(cand: dict) -> tuple[str, str]:
    """Separa «Artista - Tema» del título de un vídeo de YouTube.

    En YouTube los mashups y las sesiones se titulan de mil maneras:
        «DJ Pino - Mashup Reggaeton 2025»
        «SET DJ YURI PEDRADA - TRAVA CHIP»
        «Reggaeton Viejo Mix (1 hora)»          → sin artista: se usa el canal
    Si no hay guion, el artista es el canal (limpiando el « - Topic» de los canales automáticos).
    """
    titulo = (cand.get("clean_title") or cand.get("title") or "").strip()
    canal = (cand.get("channel") or cand.get("artist") or "").strip()
    canal = re.sub(r"\s*-\s*topic$", "", canal, flags=re.I)

    if " - " in titulo:
        izquierda, derecha = titulo.split(" - ", 1)
        # Sólo se parte si las dos partes tienen contenido razonable: hay títulos con guiones que
        # son parte del nombre («Reggaeton - Old School - Vol. 1»).
        if len(izquierda) >= 2 and len(derecha) >= 2:
            return izquierda.strip(), derecha.strip()
    return canal, titulo


def process_youtube_seed(seed: dict, progress: Optional[dict] = None,
                         max_downloads: Optional[int] = None) -> int:
    """Busca una frase EN YOUTUBE y descarga lo que encuentre.

    POR QUÉ EXISTE
    --------------
    Las semillas de mashups, remixes y sesiones de DJ pedían candidatos a **Deezer**
    (`deezer.discover_seed`), y Deezer no tiene ese contenido: los mashups y las sesiones se
    publican en YouTube, no en las tiendas de música. Resultado medido: con 13 semillas de mashup,
    el catálogo tenía **40 pistas** de ese tipo. La búsqueda no encontraba nada porque buscaba
    donde no está.

    Aquí se busca directamente en YouTube (`ytsearch`) y se descarga cada vídeo. Lo que entra pasa
    por la misma puerta de calidad y el mismo etiquetado que todo lo demás, así que una sesión de
    dos horas se acepta como sesión y un mashup corto como mashup.
    """
    from . import youtube as Y

    cfg = load_settings()
    query = seed.get("query") or ""
    if not query:
        return 0
    cuantos = int(seed.get("n") or cfg.get("youtube_resultados_por_busqueda", 20))

    candidatos = Y.search_videos(query, cuantos)
    random.shuffle(candidatos)          # no siempre los mismos primeros resultados
    added = 0
    en_portugues = 0
    ya_estaba = 0
    # Las claves de toda la biblioteca, de UNA vez. Comprobar cada candidato con su propia consulta
    # serían 20-25 consultas por búsqueda para nada, y esto corre en un portátil de 4 GB.
    claves = db.indice_de_claves()

    for cand in candidatos:
        if max_downloads is not None and added >= max_downloads:
            break
        if progress is not None and progress.get("stop"):
            break
        vid = cand.get("id")
        if not vid or db.track_exists(vid):
            continue

        artista, titulo = _partir_titulo(cand)
        if not titulo or len(titulo) < 3:
            continue
        # Portugués fuera ANTES de descargar: en YouTube las búsquedas de «set dj» devuelven funk
        # brasileño, y bajarlo para luego ponerlo en cuarentena es gastar ancho de banda y disco
        # para nada. (La puerta de calidad lo rechaza igualmente: esto es el atajo.)
        if quality.parece_portugues(titulo, artista):
            en_portugues += 1
            continue
        # ¿La tenemos ya? Se mira por vídeo, por Deezer y por la clave normalizada de artista y
        # título: es lo que evita bajar «Feid - HAXTA EL DÍA FINAL» cuando ya está «FEID - Haxta el
        # dia final (Official Video)», o el mismo tema subido en otro vídeo. Antes sólo se comparaba
        # el texto EXACTO, así que nada de eso coincidía y la misma canción entraba dos veces.
        if db.pista_existente(youtube_id=vid, artist=artista, title=titulo, claves=claves):
            ya_estaba += 1
            continue
        if db.is_blacklisted(M.BLACKLIST_ARTIST, artista):
            continue
        if db.is_blacklisted(M.BLACKLIST_SONG, f"{titulo}|{artista}"):
            continue

        genero, idioma = _resolve_genre_lang(artista, titulo, seed.get("genre"), seed.get("language"))
        bajado = Y.download_video(vid, artist=artista, title=titulo)
        if not bajado:
            continue

        # El título que manda es el del vídeo, ya limpio; el artista, el que hayamos deducido.
        bajado["title"] = titulo
        bajado["artist"] = artista or bajado.get("artist") or ""
        bajado["duration"] = bajado.get("youtube_duration") or cand.get("duration")
        tid = _persist_yt(bajado, genre=genero, language=idioma, source=M.SOURCE_AGENT)
        if tid is not None:
            added += 1
            # La recién bajada entra en el índice de claves: si más abajo en la misma búsqueda sale
            # otro vídeo del mismo tema, no se baja dos veces.
            #
            # OJO CON EL TIPO: `indice_de_claves()` devuelve un DICCIONARIO `{clave: id}` (antes era
            # un conjunto y aquí había un `.add()`). Con el `.add()` esta línea lanzaba
            # AttributeError y **mataba la búsqueda entera en cuanto bajaba la primera canción**:
            # cada semilla de YouTube (mashups, sesiones y ahora también tech house) sólo podía traer
            # UNA canción por vuelta en vez de las 6 de su cupo, y el recolector lo apuntaba como
            # «Fallo en semilla» sin decir por qué. Lo encontró la prueba de una semilla de tech
            # house a mano (20/09/2026); hay una prueba de regresión en `test_semilla_youtube.py`.
            claves[db.clave_cancion(bajado["artist"], bajado["title"])] = tid
        if progress is not None:
            progress["last"] = f"{artista} - {titulo}"
            progress["seen"] += 1

    db.log_event(f"🔎 Búsqueda en YouTube «{query}»: +{added} canciones"
                 + (f" · {ya_estaba} ya estaban en la biblioteca" if ya_estaba else "")
                 + (f" · {en_portugues} descartadas por estar en portugués" if en_portugues else ""),
                 "info")
    return added


def buscar_version_sin_intro(artist: str, title: str, track_id: int, file_path: str, *,
                             intro_actual: float = 0.0, cola_actual: float = 0.0,
                             duracion: Optional[float] = None) -> str:
    """Busca OTRA versión de la misma canción que no traiga intro hablada ni cola, y la pone.

    POR QUÉ
    -------
    De un mismo tema hay muchas subidas: el **vídeo oficial** (que suele empezar con el presentador,
    un diálogo o una escena), el **audio oficial** del disco, el **lyric video**, y los canales
    automáticos «Artista - Topic» (que son la pista del álbum tal cual). El usuario lo pidió así:
    *«para buscar otra versión que no lo tenga»*.

    CÓMO
    ----
    1. Se buscan candidatos con sesgo hacia lo que NO trae intro: se pregunta por «audio», por
       «topic» (los canales automáticos de discográfica) y por la canción a secas.
    2. Se descarta el vídeo que ya tenemos y los que ya están en la biblioteca.
    3. Se baja el mejor candidato a una carpeta temporal, se le miden los extremos con el MISMO
       detector y sólo se cambia si **está claramente mejor** (al menos 4 s menos de intro+cola) y la
       duración se parece (si no, es otra grabación: un directo, un remix…).
    4. Si se cambia, el fichero viejo se mueve a `descargas/_descartadas/` (no se borra) y la ficha
       del PC se actualiza para que el recolector lo vuelva a enviar al servidor.

    Devuelve un texto con lo que ha pasado (se imprime en el registro del recolector).
    """
    from pathlib import Path

    from . import youtube as Y
    from .extremos import analizar

    if not title:
        return "sin título que buscar"

    # UNA MEZCLA NO SE CAMBIA POR «OTRA VERSIÓN»
    # ------------------------------------------
    # Se aprendió con un caso real (20/09/2026): se cambió la sesión que el usuario había pedido a
    # mano («Dj RuLoX - Mix REGGAETON VIEJO», 36 min) por otra subida de **otro canal** («DJ Naydee»)
    # que se llamaba casi igual y duraba parecido. Son mezclas DISTINTAS: no es «la misma canción sin
    # la intro», es otro trabajo, con otro orden, otros cortes y otras canciones dentro. Para una
    # canción normal, cambiar el vídeo oficial por el audio del disco es seguro (misma grabación);
    # para una sesión no lo es. A partir de 20 minutos **sólo se informa**: queda apuntado que tiene
    # intro para que el usuario decida, y no se le toca la música.
    from .quality import clasificar

    if clasificar(title, artist, duracion or 0) == "sesion" or (duracion or 0) > 1200:
        return ("es una mezcla: no se cambia sola por otra subida del mismo título "
                f"(tiene {intro_actual + cola_actual:.0f}s de intro/cola, queda apuntado)")

    cfg = load_settings()
    candidatos: list[dict] = []
    vistos: set[str] = set()
    # El orden importa: primero lo que estadísticamente trae menos intro.
    consultas = [f"{artist} {title} topic", f"{artist} {title} audio",
                 f"{artist} {title} lyric", f"{artist} {title}"]
    for consulta in consultas:
        try:
            for c in Y.search_videos(consulta, 6):
                vid = c.get("id")
                if not vid or vid in vistos:
                    continue
                vistos.add(vid)
                candidatos.append({**c, "_consulta": consulta})
        except Exception:  # noqa: BLE001
            continue
    if not candidatos:
        return "no se encontraron candidatos"

    def prioridad(c: dict) -> tuple:
        """Cuánto promete este candidato para NO traer intro."""
        canal = (c.get("uploader") or c.get("channel") or "").lower()
        titulo_c = (c.get("title") or "").lower()
        puntos = 0
        if canal.endswith("- topic"):
            puntos += 3          # canal automático de discográfica: es la pista del álbum
        if "audio" in titulo_c or "audio" in c["_consulta"]:
            puntos += 2
        if "lyric" in titulo_c or "letra" in titulo_c:
            puntos += 1
        if "official video" in titulo_c or "videoclip" in titulo_c:
            puntos -= 2          # el vídeo oficial es justo el que suele traer la intro
        return (-puntos, c.get("duration") or 0)

    candidatos.sort(key=prioridad)
    mejor_actual = intro_actual + cola_actual
    # Márgenes para CAMBIAR la canción (no para avisar; avisar es más barato y no rompe nada):
    #   · la nueva tiene que estar prácticamente limpia (≤ LIMPIO segundos de extremos raros), y
    #   · tiene que mejorar de verdad (≥ MEJORA segundos menos).
    # Con un solo criterio se cambiaba una intro de 21 s por otra de 14 s, y eso NO es lo que se
    # busca: el usuario quiere la canción sin intro, no «menos intro».
    LIMPIO = 8.0
    MEJORA = 6.0

    for cand in candidatos[:4]:
        vid = cand.get("id")
        if db.pista_existente(youtube_id=vid) or db.track_exists(vid):
            continue
        # La duración tiene que encajar con «la misma grabación sin el trozo de más»:
        #   · puede ser MÁS CORTA, pero no más de lo que se quiere quitar (intro+cola) más un margen
        #     de 30 s: si es mucho más corta, es otra edición (un radio edit, un corte);
        #   · y no puede ser más larga que un 10 %: eso sería una versión extendida o un directo.
        # Antes se admitía un ±25 % y por ahí cabía casi cualquier cosa con el mismo título.
        dur_cand = float(cand.get("duration") or 0)
        if duracion and dur_cand:
            margen_abajo = float(intro_actual) + float(cola_actual) + 30.0
            if dur_cand < float(duracion) - margen_abajo or dur_cand > float(duracion) * 1.10:
                continue

        bajado = Y.download_video(vid, artist=artist, title=title)
        if not bajado or not bajado.get("file_path"):
            continue
        try:
            medida = analizar(bajado["file_path"], duracion=bajado.get("youtube_duration"))
        except Exception:  # noqa: BLE001
            medida = {"ok": False}
        if not medida.get("ok"):
            Path(bajado["file_path"]).unlink(missing_ok=True)
            continue
        nuevo_total = float(medida.get("intro_seg") or 0) + float(medida.get("cola_seg") or 0)
        if nuevo_total > LIMPIO or nuevo_total > mejor_actual - MEJORA:
            # O sigue teniendo intro, o no mejora lo suficiente: se descarta lo bajado y se prueba
            # con el siguiente candidato.
            Path(bajado["file_path"]).unlink(missing_ok=True)
            continue

        # --- se cambia ---
        from . import catalog as C
        from .config import resolve_music

        # El fichero viejo NO se borra: se aparta en `descargas/_descartadas/`. Si la versión nueva
        # resultara peor por algo (un corte, un empalme raro), la original sigue ahí.
        viejo = resolve_music(file_path)
        descartadas = Path(cfg["download_dir"]) / "_descartadas"
        descartadas.mkdir(parents=True, exist_ok=True)
        try:
            if viejo.exists():
                viejo.replace(descartadas / viejo.name)
        except OSError:
            pass

        rec = {
            "title": title, "artist": artist, "youtube_id": vid,
            "youtube_url": f"https://www.youtube.com/watch?v={vid}",
            "file_path": bajado["file_path"], "file_size": bajado.get("file_size"),
            "duration": bajado.get("youtube_duration") or dur_cand,
            "cover_url": bajado.get("cover_url"), "year": bajado.get("year"),
        }
        try:
            organizado = C.organize_track(rec)
            if organizado:
                rec["file_path"] = organizado
        except Exception:  # noqa: BLE001
            pass

        # La ruta se guarda RELATIVA a la carpeta de música (cada máquina tiene la suya: en el PC es
        # `E:/MusicaRadioPV` y en el servidor `/music`), que es como la espera todo lo demás.
        rel = C._rel_music(str(rec["file_path"]))
        db.update_track(track_id, file_path=rel, youtube_id=vid,
                        youtube_url=rec["youtube_url"], file_size=rec["file_size"],
                        duration=rec["duration"], intro_seg=medida["intro_seg"],
                        cola_seg=medida["cola_seg"], version_limpia=1,
                        extremos_json=json.dumps(medida, ensure_ascii=False))
        # La ficha tiene que volver a enviarse al servidor (el fichero es otro).
        conn = db.get_conn()
        try:
            conn.execute("DELETE FROM pc_enviadas WHERE track_id=?", (track_id,))
            conn.commit()
        finally:
            conn.close()
        db.log_event(f"🎯 Otra versión sin intro para {artist} - {title}: "
                     f"intro {intro_actual}s → {medida['intro_seg']}s", "info")
        canal = cand.get("uploader") or cand.get("channel") or "canal desconocido"
        return (f"cambiada por {vid} ({canal}): "
                f"intro {intro_actual}s → {medida['intro_seg']}s, cola {cola_actual}s → "
                f"{medida['cola_seg']}s")

    return f"ninguna de las {len(candidatos)} versiones encontradas mejora lo que hay"


def process_seed(seed: dict, client: Optional[deezer.DeezerClient] = None,
                 progress: Optional[dict] = None, max_downloads: Optional[int] = None) -> int:
    """Descubre candidatos de una semilla y descarga los que falten. Devuelve el nº añadido."""
    client = client or deezer.DeezerClient()
    candidates = deezer.discover_seed(seed, client)
    # más aleatorio: se baraja dentro de la fuente (no siempre los primeros artistas)
    random.shuffle(candidates)
    added = 0
    for cand in candidates:
        if max_downloads is not None and added >= max_downloads:
            break
        if progress is not None and progress.get("stop"):
            break
        if db.track_exists_by_artist_title(cand["artist"], cand["title"]):
            continue
        if cand.get("deezer_id") and db.track_exists_by_deezer(cand["deezer_id"]):
            continue
        if db.is_blacklisted(M.BLACKLIST_ARTIST, cand["artist"]):
            continue
        if db.is_blacklisted(M.BLACKLIST_SONG, f"{cand['title']}|{cand['artist']}"):
            continue
        tid = fulfill_track(
            cand["artist"], cand["title"],
            expected_duration=cand.get("duration"),
            genre=cand.get("genre"), language=cand.get("language"),
            source=M.SOURCE_AGENT, meta=cand,
        )
        if tid is not None:
            added += 1
        if progress is not None:
            progress["last"] = f"{cand['artist']} - {cand['title']}"
            progress["seen"] += 1
    return added
