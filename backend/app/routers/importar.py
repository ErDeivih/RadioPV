"""Importar una lista de Spotify a RadioPV.

POR QUÉ
-------
Lo pidió el usuario así: *«me gustaría una opción en donde pasara un playlist de spotify y se me
creara igual en mi aplicación»*.

CÓMO FUNCIONA (sin cuenta ni clave de Spotify)
----------------------------------------------
Spotify no deja leer listas por API sin una clave y sin que el dueño autorice la aplicación. Pero
una lista **pública** sí se puede leer del endpoint que usa su propio reproductor incrustado:
`open.spotify.com/embed/playlist/<id>` devuelve el nombre de la lista y sus canciones (título y
artistas) dentro de un JSON en el HTML. Comprobado desde el servidor el 22/09/2026 con «Top 50:
España»: 50 canciones.

Lo que NO hace: no baja música de Spotify. Busca cada canción **en la biblioteca de RadioPV** por
título y artista (ignorando tildes, mayúsculas, paréntesis y el «- Remix» del final). Las que no
están se dicen claramente, y si el usuario quiere se **piden al recolector** para que las baje (el
mismo camino que «Pedir una canción»), así que la lista se va completando sola.
"""
import json
import re
import unicodedata
import urllib.error
import urllib.request

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas
from ..security import get_current_user

router = APIRouter(prefix="/importar", tags=["importar"],
                   dependencies=[Depends(get_current_user)])

# El navegador que se presenta a Spotify: con el de Python (urllib) la página puede contestar otra
# cosa. Es el mismo truco que usa cualquier lector de listas públicas.
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")

# Lo que devuelve la vista incrustada: hasta 100 canciones de la lista (es su límite, no el nuestro).
MAX_INCRUSTADO = 100


def id_de_lista(url: str) -> str:
    """Saca el id de una lista de Spotify de cualquiera de sus formas.

    Se aceptan las que la gente pega de verdad: el enlace de la aplicación
    (`open.spotify.com/playlist/<id>?si=...`), el enlace de incrustar
    (`open.spotify.com/embed/playlist/<id>`), el URI (`spotify:playlist:<id>`) y el id a secas.
    """
    texto = (url or "").strip()
    if not texto:
        raise HTTPException(400, "Pega el enlace de una lista de Spotify.")
    m = re.search(r"(?:playlist[:/])([A-Za-z0-9]{10,})", texto)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9]{10,}", texto):
        return texto
    raise HTTPException(400, "Eso no parece un enlace de una lista de Spotify.")


def _leer_spotify(playlist_id: str) -> tuple[str, list[dict]]:
    """Lee una lista PÚBLICA de Spotify. Devuelve (nombre, [{title, artist}, …]).

    Devuelve una lista vacía de canciones si la lista existe pero no se deja ver (privada), con su
    nombre, para poder decirlo en vez de fallar con un error raro.
    """
    url = f"https://open.spotify.com/embed/playlist/{playlist_id}"
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                              "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            html = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise HTTPException(404, "Esa lista no existe (o el enlace está mal).") from e
        raise HTTPException(502, f"Spotify ha contestado {e.code}.") from e
    except Exception as e:                                     # noqa: BLE001
        raise HTTPException(502, f"No se ha podido preguntar a Spotify: {e}") from e

    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        raise HTTPException(502, "Spotify no ha devuelto los datos de la lista.")
    try:
        datos = json.loads(m.group(1))
        entidad = (datos.get("props", {}).get("pageProps", {})
                   .get("state", {}).get("data", {}).get("entity", {}))
    except (ValueError, AttributeError) as e:
        raise HTTPException(502, "No se han podido leer los datos de la lista.") from e

    nombre = (entidad.get("name") or "").strip() or "Lista de Spotify"
    canciones = []
    for t in (entidad.get("trackList") or [])[:MAX_INCRUSTADO]:
        titulo = (t.get("title") or "").strip()
        artista = (t.get("subtitle") or "").strip()
        if titulo:
            canciones.append({"title": titulo, "artist": artista})
    return nombre, canciones


def _clave(texto: str) -> str:
    """Normaliza para comparar: sin tildes, sin mayúsculas, sin paréntesis ni coletillas.

    «De Lejitos - Remix (feat. X)» y «de lejitos» tienen que parecer lo mismo, porque la biblioteca
    viene de YouTube y de Deezer y los títulos no coinciden letra por letra.
    """
    s = unicodedata.normalize("NFKD", (texto or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\((?:[^()]*)\)|\[[^\]]*\]", " ", s)          # (feat. …), [Official Video]
    s = re.sub(r"\s+-\s+(?:remix|remaster(?:ed)?|live|version|edit|mix)\b.*$", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _artista_principal(artista: str) -> str:
    """El primer artista de la lista («KAROL G, Judeline, rusowsky» → «karol g»)."""
    return _clave((artista or "").split(",")[0])


def _variantes(titulo: str) -> list[str]:
    """Formas normalizadas del título con las que se busca en la biblioteca.

    Hace falta más de una porque el mismo título llega escrito de mil maneras: en Spotify
    «Quevedo - LA GRACIOSA» (el artista delante) y en la biblioteca «LA GRACIOSA» a secas. El guion
    hay que partirlo ANTES de normalizar: `_clave` quita la puntuación, así que después ya no queda
    rastro de dónde estaba.
    """
    variantes = [_clave(titulo)]
    partes = re.split(r"\s+-\s+", (titulo or "").strip())
    if len(partes) >= 2:
        variantes.append(_clave(partes[-1]))       # lo de después del guion
        variantes.append(_clave(partes[0]))        # y lo de antes, por si el guion separa un remix
    return [v for v in dict.fromkeys(variantes) if v]


def emparejar(canciones: list[dict], catalogo: list[tuple[int, str, str]]) -> tuple[list[int], list[dict]]:
    """Busca cada canción de Spotify en el catálogo. Devuelve (ids_en_orden, las_que_faltan).

    Se compara por título y artista normalizados. Si el título coincide pero el artista no, **se
    acepta igualmente** (la biblioteca puede tener la canción como «Artista A, Artista B» o con el
    nombre del canal de YouTube): es mejor que la lista salga llena y que el usuario vea la canción
    que dejar media lista vacía por un detalle del nombre.
    """
    por_titulo: dict[str, list[tuple[int, str]]] = {}
    for tid, titulo, artista in catalogo:
        por_titulo.setdefault(_clave(titulo), []).append((tid, _artista_principal(artista)))

    ids: list[int] = []
    faltan: list[dict] = []
    for c in canciones:
        candidatos: list[tuple[int, str]] = []
        for variante in _variantes(c["title"]):
            candidatos = por_titulo.get(variante) or []
            if candidatos:
                break
        if not candidatos:
            faltan.append(c)
            continue
        quiere = _artista_principal(c.get("artist", ""))
        elegido = next((tid for tid, art in candidatos if quiere and art and quiere == art), None)
        if elegido is None:
            elegido = candidatos[0][0]
        if elegido not in ids:                                 # sin repetidas dentro de la lista
            ids.append(elegido)
    return ids, faltan


@router.post("/spotify", response_model=schemas.ImportarOut)
def importar_de_spotify(data: dict, db: Session = Depends(get_db),
                        user: models.User = Depends(get_current_user)):
    """Crea una lista con las canciones de una lista pública de Spotify.

    Se puede repetir sin miedo: si esa misma lista ya se importó antes, se **rellena otra vez** en
    lugar de crear una copia (si no, dos toques por error dejarían la biblioteca con la lista
    duplicada)."""
    playlist_id = id_de_lista(data.get("url") or "")
    pedir = bool(data.get("pedir"))
    nombre, canciones = _leer_spotify(playlist_id)
    if not canciones:
        raise HTTPException(409, "Esa lista está vacía o es privada: Spotify no deja leerla.")

    url = f"https://open.spotify.com/playlist/{playlist_id}"
    catalogo = (db.query(models.Track.id, models.Track.title, models.Track.artist)
                .filter(models.Track.status == "descargada").all())
    ids, faltan = emparejar(canciones, catalogo)

    # La lista: la que ya se importó de esta misma URL, o una nueva.
    #
    # Se busca por el ID DE SPOTIFY dentro de la descripción (y no por la descripción entera): así no
    # importa cómo se escriba la marca alrededor, y una lista importada dos veces se rellena en lugar
    # de duplicarse.
    pl = (db.query(models.Playlist)
          .filter(models.Playlist.user_id == user.id,
                  models.Playlist.description.like(f"%{playlist_id}%")).first())
    marca = f"Importada de Spotify · {url}"
    if pl is None:
        pl = models.Playlist(name=nombre, description=marca, type="user", user_id=user.id,
                             public=False)
        db.add(pl)
        db.flush()
    else:
        pl.name = nombre
        pl.description = marca
        db.query(models.PlaylistTrack).filter_by(playlist_id=pl.id).delete()

    for pos, tid in enumerate(ids, start=1):
        db.add(models.PlaylistTrack(playlist_id=pl.id, track_id=tid, position=pos))

    # Si faltan canciones y el usuario quiere, se piden al recolector (mismo camino que «Pedir una
    # canción»): así la lista se completa sola en las siguientes vueltas.
    pedidas = 0
    if pedir:
        for c in faltan:
            texto = f"{c['artist']} - {c['title']}".strip(" -")[:200]
            ya = (db.query(models.Request)
                  .filter_by(user_id=user.id, text=texto)
                  .filter(models.Request.status == "pendiente").first())
            if ya:
                continue
            db.add(models.Request(user_id=user.id, text=texto, status="pendiente"))
            pedidas += 1

    db.commit()
    db.refresh(pl)

    return schemas.ImportarOut(
        playlist=schemas.PlaylistOut(id=pl.id, name=pl.name, description=pl.description,
                                    type=pl.type, n_tracks=len(ids), user_id=pl.user_id,
                                    public=bool(pl.public), cover=pl.cover),
        nombre=nombre,
        total=len(canciones),
        encontradas=len(ids),
        faltan=faltan,
        pedidas=pedidas,
        aviso=("Spotify sólo deja ver las primeras 100 canciones de una lista en su vista "
               "incrustada." if len(canciones) >= MAX_INCRUSTADO else None),
    )
