"""Letras de las canciones (`/tracks/{id}/lyrics`).

POR QUÉ
-------
En la barra de reproducción hay un botón de **«Letra»** (el micrófono) que abría… el **selector de
idioma**. Es el mismo tipo de fallo que el botón de «elegir foto» de las listas: un control que
promete algo y hace otra cosa. Mirar la letra es una de las cosas que más se usan en Spotify, así
que en vez de quitar el botón se implementa.

CÓMO
----
Se pregunta a `lyrics.ovh`, que es público y no pide clave. Comprobado desde el servidor: responde
(incluso con canciones en español).

Dos detalles que importan para que acierte:

  · **El título se limpia.** En este catálogo los títulos vienen de YouTube y llevan coletillas que
    no están en ninguna base de letras: «(Official Video)», «[HD]», «(feat. Fulano)»,
    «- Remastered 2011», «(Lyric Video)»… Buscar «Yellow (Official Video)» no encuentra nada;
    buscar «Yellow», sí.
  · **Se guarda en caché.** Las letras no cambian. Sin caché, cada vez que se abre el panel se
    vuelve a pedir a un servicio externo, que es lento y ajeno (y puede acabar pidiendo cuota).

Si no hay letra, se dice **que no hay letra** (no un error): es lo normal con música poco conocida.
"""
import re
import time
import urllib.parse
import urllib.request
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models

router = APIRouter(prefix="/tracks", tags=["lyrics"])

FUENTE = "https://api.lyrics.ovh/v1/{artista}/{titulo}"
TTL_SEGUNDOS = 7 * 24 * 3600
_cache: dict[tuple[str, str], tuple[Optional[str], float]] = {}


def limpiar_titulo(titulo: str) -> str:
    """Quita del título lo que no forma parte del nombre de la canción.

    Todo esto sale del catálogo real, que se llena desde YouTube: «Yellow (Official Video)»,
    «Levitating [HD]», «DESPECHÁ - Remastered», «Song (Audio)», «Song (Lyric Video)»…
    """
    t = titulo or ""
    t = re.sub(r"[\(\[\{][^\)\]\}]*[\)\]\}]", " ", t)          # (lo que sea), [lo que sea]
    t = re.sub(r"\s-\s*(remaster(ed)?|official|audio|video|lyric|hd|4k|mv)\b.*$", " ", t, flags=re.I)
    t = re.sub(r"\b(official|lyric|music)\s+(video|audio)\b", " ", t, flags=re.I)
    t = re.sub(r"\s+", " ", t)
    return t.strip(" -–—|") or (titulo or "").strip()


def limpiar_artista(artista: str) -> str:
    """Igual con el artista: «Coldplay - Topic», «Rosalía feat. X» y «XVEVO» no existen allí."""
    a = artista or ""
    a = re.split(r"\s(?:feat\.?|ft\.?|with|con)\s", a, flags=re.I)[0]
    a = re.sub(r"\s*-\s*topic$", "", a, flags=re.I)
    a = re.sub(r"vevo$", "", a, flags=re.I)
    return a.strip(" -–—|") or (artista or "").strip()


def _pedir_letra(artista: str, titulo: str, timeout: int = 12) -> Optional[str]:
    """Pregunta a la fuente externa. Devuelve None si no la tiene (no lanza)."""
    import json

    url = FUENTE.format(artista=urllib.parse.quote(artista), titulo=urllib.parse.quote(titulo))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RadioPV/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            datos = json.loads(r.read().decode("utf-8", "replace"))
        letra = (datos.get("lyrics") or "").strip()
        return letra or None
    except Exception:  # noqa: BLE001  (sin letra no pasa nada: es lo normal)
        return None


def buscar_letra(artista: str, titulo: str) -> Optional[str]:
    """Con caché. Se guarda también el «no la tengo»: si no se guardara, cada visita volvería a
    preguntar por una canción que ya sabemos que no está."""
    clave = (limpiar_artista(artista).lower(), limpiar_titulo(titulo).lower())
    guardado = _cache.get(clave)
    if guardado and (time.time() - guardado[1]) < TTL_SEGUNDOS:
        return guardado[0]

    letra = _pedir_letra(limpiar_artista(artista), limpiar_titulo(titulo))
    if letra is None:
        # Segundo intento sin limpiar: hay títulos cuyo paréntesis SÍ forma parte del nombre
        # («Song (Reprise)»), y así no se pierden.
        letra = _pedir_letra(artista, titulo)
    _cache[clave] = (letra, time.time())
    return letra


@router.get("/{track_id}/lyrics", summary="Letra de la canción")
def lyrics(track_id: int, db: Session = Depends(get_db)) -> dict:
    """Devuelve `{letra, encontrada, fuente, titulo_buscado}`.

    Nunca es un error que no haya letra: `encontrada: false` y ya. El reproductor enseña
    «no hay letra para esta canción», que es lo que de verdad pasa con la mitad del catálogo.
    """
    t = db.query(models.Track).filter(models.Track.id == track_id).first()
    if not t:
        raise HTTPException(404, "Canción no encontrada")
    letra = buscar_letra(t.artist or "", t.title or "")
    return {
        "letra": letra,
        "encontrada": letra is not None,
        "fuente": "lyrics.ovh",
        "titulo_buscado": limpiar_titulo(t.title or ""),
        "artista_buscado": limpiar_artista(t.artist or ""),
    }
