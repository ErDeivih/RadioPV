"""Corrector del catálogo.

Revisa las canciones **una a una** y comprueba dos cosas distintas, que conviene no
confundir:

  1. ¿Los DATOS están bien?  artista(s), título, álbum, año, versión (remix/live/cover)…
  2. ¿El FICHERO es la canción correcta?  No basta con que exista y dure lo mismo: una
     *cover* de la misma duración pasaría ese filtro. Hay que escuchar el audio.

Por qué hacía falta, si ya había un revisor
-------------------------------------------
`catalog.review_metadata()` ya releía Deezer y corregía año/álbum/feat, pero **confiaba en
el `deezer_id` guardado**. Si ese id pertenecía a otra canción (cosa que pasa cuando la
búsqueda original eligió mal), el revisor no lo detectaba: "corregía" todos los datos hacia
la canción equivocada, con lo que el error se volvía más difícil de ver.

Y `scripts/verificar_match.py` solo comparaba **duración**. Una versión cover, un directo o
un "sped up" de la misma duración pasaban como correctos.

Las cinco comprobaciones
------------------------
| # | Comprobación | Qué aporta |
|---|---|---|
| 1 | El fichero    | existe, se lee, no es silencio, duración real |
| 2 | Sus etiquetas | los ID3 del propio MP3: un testigo **independiente** de la BD |
| 3 | Deezer        | ¿el `deezer_id` guardado es de ESTA canción? + búsqueda nueva |
| 4 | El audio      | comparación con el *preview* de 30 s de Deezer |
| 5 | YouTube       | canal oficial, duración y marcas de versión en el título |

La comprobación 4 es la importante y la que no existía. Se comparan dos cosas a la vez:

  · **croma** (armonía): dice si es la MISMA COMPOSICIÓN. Un cover la conserva.
  · **MFCC** (timbre): dice si es la MISMA GRABACIÓN. Un cover NO la conserva.

De ahí salen los tres casos que importan:

    croma alto + mfcc alto   -> la grabación correcta
    croma alto + mfcc bajo   -> misma canción, OTRA VERSIÓN (cover, directo, remaster…)
    croma bajo               -> OTRA CANCIÓN

Uso
---
    from radiov import corrector
    a = corrector.analizar(track)          # no toca nada
    corrector.aplicar(a)                   # escribe las correcciones de metadatos

    # o en lote, que es como se usa de verdad:
    corrector.revisar_lote(limit=50, aplicar=False)
"""

from __future__ import annotations

import contextlib
import dataclasses
import difflib
import io
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Optional

from . import db
from .config import load_settings, resolve_music

# ---------------------------------------------------------------------------
# Veredictos posibles
# ---------------------------------------------------------------------------
CORRECTA = "correcta"                    # todo cuadra
METADATOS = "metadatos"                  # el audio está bien, los datos no
OTRA_VERSION = "otra_version"            # misma canción, grabación/versión distinta
OTRA_CANCION = "otra_cancion"            # el fichero no es esa canción
FICHERO_MAL = "fichero_mal"              # ausente, ilegible, silencio o duración disparada
SIN_DATOS = "sin_datos"                  # no se pudo comprobar contra internet

VEREDICTOS = (CORRECTA, METADATOS, OTRA_VERSION, OTRA_CANCION, FICHERO_MAL, SIN_DATOS)

# Los que se pueden arreglar solos (solo tocan la ficha, no el fichero)
AUTOARRGLABLES = (CORRECTA, METADATOS)
# Los que necesitan volver a descargar la canción
NECESITAN_DESCARGA = (OTRA_VERSION, OTRA_CANCION, FICHERO_MAL)

# Umbrales.
#
# ESTÁN MEDIDOS, no inventados. Con `scripts/calibrar_corrector.py` se compara cada canción
# contra su propio preview (positivo) y contra el preview de otras canciones (negativo):
#
#                     croma (composición)      mfcc (grabación)
#   su propia canción   0.974 – 0.995            0.588 – 0.887
#   otra canción        0.573 – 0.931            0.044 – 0.225
#
# La separación es limpia en las dos, así que los umbrales van en medio del hueco. Ojo:
# la primera versión de esto usaba 0.78 y 0.80, que eran inservibles — una canción
# completamente distinta daba 0.931 (habría pasado por buena) y una grabación correcta con
# 0.588 se habría marcado como «otra versión».
UMBRAL_CROMA_MISMA = 0.95      # a partir de aquí, misma composición
UMBRAL_CROMA_DUDOSA = 0.88     # por debajo, canción distinta sin duda
UMBRAL_MFCC_MISMA = 0.40       # a partir de aquí, misma grabación
UMBRAL_DURACION = 0.08         # 8% de desviación entre el fichero y Deezer
UMBRAL_SILENCIO_RMS = 0.0015


# ===========================================================================
# Utilidades de texto
# ===========================================================================
def clave(texto: Any) -> str:
    """Normaliza para comparar: minúsculas, sin acentos, sin puntuación, espacios simples."""
    s = unicodedata.normalize("NFKD", str(texto or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[\(\[\{].*?[\)\]\}]", " ", s)          # fuera paréntesis
    s = re.sub(r"[^a-z0-9áéíóúüñ& ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parecido(a: Any, b: Any) -> float:
    """Similitud 0..1 entre dos textos, ya normalizados."""
    return difflib.SequenceMatcher(None, clave(a), clave(b)).ratio()


# Marcas de versión que aparecen en títulos de fichero y de vídeo.
MARCAS = {
    "cover": r"\bcover\b|\bversi[oó]n de\b|\bversion by\b|\btributo a\b|\btribute\b",
    "karaoke": r"\bkaraoke\b|\bkaraoké\b|\bplayback\b|\bpista\b",
    "instrumental": r"\binstrumental\b|\bmade famous by\b|\bsin voz\b",
    "live": r"\blive\b|\ben vivo\b|\bdirecto\b|\bconcert\b|\bauditorio\b|\bunplugged\b|\bac[uú]stico\b",
    "remix": r"\bremix\b|\bre-?mix\b|\bbootleg\b|\bedit\b|\bmashup\b",
    "sped": r"\bsped\s?up\b|\bslowed\b|\br?everb\b|\bnightcore\b|\bfast\b.*\bversion\b",
    "remaster": r"\bremaster(ed)?\b|\bre-?master\b|\bremasterizad",
    "extendida": r"\bextended\b|\bextendida\b|\blong version\b|\b12\s?inch\b|\bclub mix\b",
    "demo": r"\bdemo\b|\bmaqueta\b",
    "ensayo": r"\brehearsal\b|\bsoundcheck\b|\bprueba de sonido\b",
    "letra": r"\blyrics?\b|\bletra\b|\bvideo oficial\b|\bofficial video\b|\baudio oficial\b",
}


def marcas(texto: str) -> set[str]:
    t = (texto or "").lower()
    return {nombre for nombre, patron in MARCAS.items() if re.search(patron, t)}


def _anio(valor: Any) -> Optional[int]:
    m = re.search(r"(19|20)\d{2}", str(valor or ""))
    return int(m.group(0)) if m else None


# ===========================================================================
# 1 · El fichero
# ===========================================================================
def revisar_fichero(track: dict) -> dict:
    """Mira si el fichero existe, se puede leer y suena (no es silencio ni basura)."""
    salida: dict[str, Any] = {"ok": False, "problemas": [], "duration": None, "rms": None}
    ruta_txt = track.get("file_path")
    if not ruta_txt:
        salida["problemas"].append("la ficha no tiene fichero asignado")
        salida["estado"] = "sin_ruta"
        return salida

    ruta = resolve_music(ruta_txt)
    if not ruta.exists():
        salida["problemas"].append(f"el fichero no está en disco: {ruta_txt}")
        salida["estado"] = "ausente"
        return salida
    if ruta.stat().st_size < 50_000:
        salida["problemas"].append(f"el fichero es sospechosamente pequeño ({ruta.stat().st_size} bytes)")
        salida["estado"] = "diminuto"
        return salida

    from .catalog import real_duration
    dur = real_duration(ruta_txt)
    salida["duration"] = dur
    if not dur:
        salida["problemas"].append("no se pudo leer la duración (¿fichero corrupto?)")
        salida["estado"] = "ilegible"
        return salida

    # Silencio o casi: se mira la energía media.
    try:
        import numpy as np
        import librosa
        with _sin_ruido_de_audio():
            y, sr = librosa.load(str(ruta), sr=22050, mono=True,
                                 duration=min(120.0, max(20.0, (dur or 60) / 2)))
        if y.size:
            rms = float(np.sqrt(np.mean(np.square(y))))
            salida["rms"] = round(rms, 5)
            if rms < UMBRAL_SILENCIO_RMS:
                salida["problemas"].append(f"el audio está prácticamente en silencio (rms={rms:.5f})")
                salida["estado"] = "silencio"
                return salida
    except Exception as e:  # noqa: BLE001
        salida["problemas"].append(f"no se pudo analizar el audio: {type(e).__name__}")

    guardada = track.get("duration")
    if guardada and dur:
        desvio = abs(dur - float(guardada)) / max(float(guardada), 1)
        salida["desvio_duracion"] = round(desvio, 3)
        if desvio > 0.25:
            # No es fallo por sí solo: la duración guardada puede venir del vídeo de
            # YouTube y no de la canción. Se anota para que lo juzgue el veredicto.
            salida["problemas"].append(
                f"la duración del fichero ({dur:.0f}s) no cuadra con la guardada ({guardada:.0f}s)")

    salida["ok"] = True
    salida["estado"] = "ok"
    return salida


# ===========================================================================
# 2 · Las etiquetas del propio fichero (testigo independiente)
# ===========================================================================
def leer_tags(ruta_txt: str) -> dict:
    """Lee título/artista/álbum de los ID3 del propio MP3.

    Vale como testigo independiente: si algún proceso reescribió los ficheros o se
    cruzaron al copiarlos, los ID3 lo delatan y no depende de lo que diga nuestra BD.
    """
    salida: dict[str, Any] = {"disponible": False}
    try:
        from mutagen import File as MutaFile
        ruta = resolve_music(ruta_txt)
        if not ruta.exists():
            return salida
        f = MutaFile(str(ruta), easy=True)
        if not f:
            return salida
        for campo in ("title", "artist", "album", "date", "tracknumber"):
            valor = f.get(campo)
            if valor:
                salida[campo] = str(valor[0])
        salida["disponible"] = any(k in salida for k in ("title", "artist", "album"))
    except Exception as e:  # noqa: BLE001
        salida["error"] = f"{type(e).__name__}: {e}"
    return salida


def revisar_tags(track: dict, tags: dict) -> dict:
    """Compara los ID3 con la ficha. Devuelve qué discrepa."""
    salida: dict[str, Any] = {"ok": True, "discrepancias": []}
    if not tags.get("disponible"):
        salida["ok"] = None          # no se puede juzgar
        return salida
    pares = (("title", "title", "título"), ("artist", "artist", "artista"),
             ("album", "album", "álbum"))
    for campo_tag, campo_bd, nombre in pares:
        en_tag = tags.get(campo_tag)
        en_bd = track.get(campo_bd)
        if not en_tag or not en_bd:
            continue
        p = parecido(en_tag, en_bd)
        if p < 0.75:
            salida["ok"] = False
            salida["discrepancias"].append(
                f"los ID3 dicen {nombre}={en_tag!r} y la ficha dice {en_bd!r} (parecido {p:.0%})")
    return salida


# ===========================================================================
# 3 · Deezer
# ===========================================================================
def _mejor_candidato_deezer(track: dict, candidatos: list[dict]) -> Optional[dict]:
    """Elige el candidato de Deezer que mejor encaja con la ficha (nombre + duración)."""
    if not candidatos:
        return None
    dur = track.get("duration") or 0

    def puntua(c: dict) -> float:
        p = parecido(c.get("title"), track.get("title"))
        art = c.get("artist") or {}
        art_nombre = art.get("name") if isinstance(art, dict) else str(art)
        p += parecido(art_nombre, track.get("artist"))
        cd = float(c.get("duration") or 0)
        if dur and cd:
            desvio = abs(cd - float(dur)) / max(float(dur), 1)
            p += max(0.0, 1.0 - desvio * 3)
        return p

    return sorted(candidatos, key=puntua, reverse=True)[0]


def revisar_deezer(track: dict, client=None) -> dict:
    """Dos cosas distintas, y las dos importan:

    a) ¿El `deezer_id` guardado pertenece a ESTA canción?  Si no, todos los datos que se
       "corrigieron" a partir de él están mal.
    b) ¿Qué dice una búsqueda NUEVA, hecha con el artista y título que tenemos?
    """
    from . import deezer as dz
    salida: dict[str, Any] = {"ok": None, "problemas": [], "propuestas": {}, "candidato": None}
    try:
        client = client or dz.DeezerClient()
    except Exception as e:  # noqa: BLE001
        salida["problemas"].append(f"no se pudo crear el cliente de Deezer: {e}")
        return salida

    # --- a) el id guardado ---
    did = track.get("deezer_id")
    if did:
        try:
            det = client.track_detail(str(did))
        except Exception:  # noqa: BLE001
            det = None
        if det:
            salida["guardado"] = {
                "id": str(did),
                "title": det.get("title"),
                "artist": (det.get("artist") or {}).get("name") if isinstance(det.get("artist"), dict) else None,
                "album": (det.get("album") or {}).get("title") if isinstance(det.get("album"), dict) else None,
                "duration": det.get("duration"),
                "release_date": det.get("release_date"),
                "preview": det.get("preview"),
            }
            p_tit = parecido(det.get("title"), track.get("title"))
            art = det.get("artist") or {}
            art_nombre = art.get("name") if isinstance(art, dict) else ""
            p_art = parecido(art_nombre, track.get("artist"))
            if p_tit < 0.55 or p_art < 0.55:
                salida["problemas"].append(
                    f"el deezer_id guardado ({did}) es de OTRA canción: "
                    f"Deezer dice «{art_nombre} - {det.get('title')}» "
                    f"(parecido título {p_tit:.0%}, artista {p_art:.0%})")
                salida["id_guardado_valido"] = False
            else:
                salida["id_guardado_valido"] = True
        else:
            salida["problemas"].append(f"el deezer_id guardado ({did}) ya no existe en Deezer")
            salida["id_guardado_valido"] = False
    else:
        salida["id_guardado_valido"] = None

    # --- b) búsqueda nueva ---
    consulta = f'{track.get("artist", "")} {track.get("title", "")}'.strip()
    try:
        candidatos = client.search(consulta, limit=25)
    except Exception as e:  # noqa: BLE001
        salida["problemas"].append(f"la búsqueda en Deezer falló: {e}")
        return salida
    mejor = _mejor_candidato_deezer(track, candidatos)
    if not mejor:
        salida["problemas"].append("Deezer no encuentra ninguna canción con ese artista y título")
        return salida
    # El resultado de /search no trae preview ni release_date: hace falta el detalle.
    try:
        det_nuevo = client.track_detail(str(mejor.get("id")))
    except Exception:  # noqa: BLE001
        det_nuevo = None
    if det_nuevo:
        mejor = det_nuevo
    salida["candidato"] = {
        "id": str(mejor.get("id")),
        "title": mejor.get("title"),
        "artist": (mejor.get("artist") or {}).get("name") if isinstance(mejor.get("artist"), dict) else None,
        "album": (mejor.get("album") or {}).get("title") if isinstance(mejor.get("album"), dict) else None,
        "duration": mejor.get("duration"),
        "release_date": mejor.get("release_date"),
        "preview": mejor.get("preview"),
        "rank": mejor.get("rank"),
    }

    # Propuestas de corrección de datos a partir del candidato
    prop: dict[str, Any] = {}
    cand = salida["candidato"]
    if parecido(cand["title"], track.get("title")) >= 0.72 and cand["title"]:
        if clave(cand["title"]) != clave(track.get("title")):
            prop["title"] = cand["title"]
    if cand["artist"] and clave(cand["artist"]) != clave(track.get("artist")):
        prop["artist"] = cand["artist"]
    if cand["album"] and clave(cand["album"]) != clave(track.get("album")):
        prop["album"] = cand["album"]
    if cand["id"] and str(cand["id"]) != str(track.get("deezer_id") or ""):
        prop["deezer_id"] = cand["id"]
    y = _anio(cand.get("release_date"))
    if y and y != track.get("year"):
        prop["year"] = y
    if cand.get("release_date"):
        prop["release_date"] = str(cand["release_date"])[:10]

    # Colaboraciones: `contributors` del detalle (el "feat" real)
    try:
        contribs = [c.get("name") for c in (mejor.get("contributors") or []) if c.get("name")]
        principal = (cand["artist"] or "").strip().lower()
        feat = ", ".join(n for n in contribs if n.strip().lower() != principal)
        if feat and clave(feat) != clave(track.get("feat")):
            prop["feat"] = feat
    except Exception:  # noqa: BLE001
        pass

    if mejor.get("explicit_lyrics") is not None:
        prop["explicit"] = 1 if mejor["explicit_lyrics"] else 0

    salida["propuestas"] = prop
    salida["ok"] = True
    return salida


# ===========================================================================
# 4 · El audio contra el preview de Deezer
# ===========================================================================
def _huellas(y, sr: int, hop: int = 2048):
    """Devuelve (croma, mfcc) normalizados por frame, para comparar con coseno."""
    import librosa
    import numpy as np

    croma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)
    croma = croma / np.maximum(np.linalg.norm(croma, axis=0, keepdims=True), 1e-6)

    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20, hop_length=hop)
    # Se centra cada coeficiente en su propia media y desviación: así la comparación no
    # depende de que una grabación suene más fuerte o más brillante que la otra.
    mfcc = (mfcc - mfcc.mean(axis=1, keepdims=True)) / (mfcc.std(axis=1, keepdims=True) + 1e-6)
    mfcc = mfcc / np.maximum(np.linalg.norm(mfcc, axis=0, keepdims=True), 1e-6)
    return croma, mfcc


@contextlib.contextmanager
def _sin_ruido_de_audio():
    """Calla el ruido que las bibliotecas de audio escriben directamente en el descriptor 2.

    mpg123 (el decodificador de MP3 que usa libsndfile) avisa de etiquetas ID3 raras con
    líneas del tipo «unrealistic small tag lengh», y no pasa por Python, así que
    `redirect_stderr` no lo tapa. Hay que redirigir el descriptor de fichero.
    """
    try:
        guardado = os.dup(2)
        nulo = os.open(os.devnull, os.O_WRONLY)
        os.dup2(nulo, 2)
    except OSError:
        yield
        return
    try:
        yield
    finally:
        try:
            os.dup2(guardado, 2)
        finally:
            os.close(nulo)
            os.close(guardado)


def _mejor_alineamiento(A, B, paso: int = 4) -> tuple[float, float]:
    """Desliza B (el preview) sobre A (el fichero) y devuelve la mejor similitud media."""
    import numpy as np

    Ta, Tb = A.shape[1], B.shape[1]
    if Ta < Tb or Tb < 8:
        return 0.0, 0.0
    mejor, mejor_off = -1.0, 0
    for off in range(0, Ta - Tb + 1, paso):
        seg = A[:, off:off + Tb]
        sim = float(np.mean(np.sum(seg * B, axis=0)))
        if sim > mejor:
            mejor, mejor_off = sim, off
    return mejor, float(mejor_off)


def comparar_audio(track: dict, preview_url: Optional[str], *, hop: int = 2048) -> dict:
    """Compara el fichero con el preview de 30 s de Deezer.

    Devuelve `croma` (¿misma composición?) y `mfcc` (¿misma grabación?).
    """
    import numpy as np
    import librosa
    import requests

    salida: dict[str, Any] = {"ok": False, "croma": None, "mfcc": None, "problemas": []}
    if not preview_url:
        salida["problemas"].append("Deezer no ofrece preview de esta canción")
        return salida
    if not track.get("file_path"):
        salida["problemas"].append("la ficha no tiene fichero")
        return salida

    ruta = resolve_music(track["file_path"])
    if not ruta.exists():
        salida["problemas"].append("el fichero no está en disco")
        return salida

    # --- el preview ---
    # Se guarda en un fichero temporal en vez de leerlo desde memoria: libsndfile no
    # reconoce el formato de un MP3 que le llega por un flujo sin nombre y lanza
    # LibsndfileError. Con extensión .mp3 sí lo identifica.
    import tempfile

    tmp = None
    try:
        r = requests.get(preview_url, timeout=25)
        r.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(r.content)
            tmp = f.name
        with _sin_ruido_de_audio():
            y_prev, sr_p = librosa.load(tmp, sr=22050, mono=True)
    except Exception as e:  # noqa: BLE001
        salida["problemas"].append(
            f"no se pudo descargar o leer el preview: {type(e).__name__}: {e}")
        return salida
    finally:
        if tmp:
            try:
                Path(tmp).unlink(missing_ok=True)
            except OSError:
                pass
    if y_prev.size < 22050 * 5:
        salida["problemas"].append("el preview es demasiado corto para comparar")
        return salida

    # --- el fichero ---
    try:
        with _sin_ruido_de_audio():
            y, sr = librosa.load(str(ruta), sr=22050, mono=True)
    except Exception as e:  # noqa: BLE001
        salida["problemas"].append(f"no se pudo leer el fichero: {type(e).__name__}")
        return salida
    if y.size < 22050 * 5:
        salida["problemas"].append("el fichero es demasiado corto para comparar")
        return salida

    try:
        croma_p, mfcc_p = _huellas(y_prev, sr_p, hop)
        croma_f, mfcc_f = _huellas(y, sr, hop)
        croma, off_c = _mejor_alineamiento(croma_f, croma_p)
        mfcc, off_m = _mejor_alineamiento(mfcc_f, mfcc_p)
    except Exception as e:  # noqa: BLE001
        salida["problemas"].append(f"falló el cálculo de las huellas: {type(e).__name__}: {e}")
        return salida

    salida.update({
        "ok": True,
        "croma": round(croma, 4),
        "mfcc": round(mfcc, 4),
        "segundo_fichero_croma": round(off_c * hop / 22050, 1),
        "segundo_fichero_mfcc": round(off_m * hop / 22050, 1),
        "segundos_fichero": round(float(y.size) / sr, 1),
        "segundos_preview": round(float(y_prev.size) / sr_p, 1),
        "misma_composicion": croma >= UMBRAL_CROMA_MISMA,
        "misma_grabacion": mfcc >= UMBRAL_MFCC_MISMA,
    })
    return salida


# ===========================================================================
# 5 · YouTube
# ===========================================================================
def revisar_youtube(track: dict, max_candidatos: int = 8) -> dict:
    """Busca la canción en YouTube y mira si lo que hay se corresponde.

    No descarga nada: solo busca y compara títulos y duraciones. Sirve sobre todo para
    detectar que nuestra copia es una versión rara (cover, directo, "sped up") y para
    tener una segunda fuente con la que contrastar a Deezer.
    """
    from .youtube import _search_candidates          # reutiliza la búsqueda ya existente

    salida: dict[str, Any] = {"ok": False, "problemas": [], "candidatos": []}
    consulta = f'{track.get("artist", "")} {track.get("title", "")}'.strip()
    if not consulta:
        salida["problemas"].append("sin artista ni título con los que buscar")
        return salida
    try:
        cands = _search_candidates(consulta, n=max_candidatos)
    except Exception as e:  # noqa: BLE001
        salida["problemas"].append(f"la búsqueda en YouTube falló: {type(e).__name__}")
        return salida
    if not cands:
        salida["problemas"].append("YouTube no devolvió resultados")
        return salida

    dur = float(track.get("duration") or 0)
    art = clave(track.get("artist"))
    tit = clave(track.get("title"))
    filas = []
    for c in cands:
        canal = (c.get("channel") or "").lower()
        texto = f"{c.get('title','')} {c.get('channel','')}"
        filas.append({
            "youtube_id": c.get("youtube_id") or c.get("id"),
            "title": c.get("title"),
            "channel": c.get("channel"),
            "duration": c.get("duration"),
            "es_topic": canal.endswith("- topic"),
            "es_oficial": any(x in canal for x in ("official", "vevo", "topic")),
            "marcas": sorted(marcas(texto)),
            "parecido_titulo": round(parecido(c.get("title"), track.get("title")), 3),
            "parecido_artista": round(parecido(c.get("channel"), track.get("artist")), 3),
            "desvio_duracion": (round(abs(float(c.get("duration") or 0) - dur) / dur, 3)
                                if dur and c.get("duration") else None),
        })
    salida["candidatos"] = filas
    # El que tenemos, si aparece entre los resultados
    nuestro = str(track.get("youtube_id") or "")
    salida["nuestro_en_resultados"] = any(
        f.get("youtube_id") and str(f["youtube_id"]) == nuestro for f in filas) if nuestro else None
    salida["ok"] = True

    # ¿Alguno es claramente la versión "limpia" (canal oficial y sin marcas raras)?
    limpios = [f for f in filas
               if f["es_oficial"] and not (f["marcas"] - {"letra", "remaster"})]
    salida["oficial_limpio"] = limpios[0] if limpios else None
    return salida


# ===========================================================================
# Veredicto
# ===========================================================================
@dataclasses.dataclass
class Analisis:
    """Resultado de revisar una canción. No cambia nada por sí solo."""

    track_id: int
    titulo: str
    artista: str
    veredicto: str
    problemas: list[str] = dataclasses.field(default_factory=list)
    correcciones: dict = dataclasses.field(default_factory=dict)
    detalle: dict = dataclasses.field(default_factory=dict)

    @property
    def hay_correcciones(self) -> bool:
        return bool(self.correcciones)

    def resumen(self) -> str:
        return f"[{self.veredicto}] {self.artista} - {self.titulo}"

    def a_dict(self) -> dict:
        return {
            "track_id": self.track_id, "titulo": self.titulo, "artista": self.artista,
            "veredicto": self.veredicto, "problemas": self.problemas,
            "correcciones": self.correcciones, "detalle": self.detalle,
        }


def decidir(track: dict, fichero: dict, tags: dict, tags_cmp: dict,
            dz: dict, audio: dict, yt: dict) -> tuple[str, list[str], dict]:
    """Combina las comprobaciones en un veredicto y una lista de correcciones."""
    problemas: list[str] = []
    correcciones: dict = {}

    # --- el fichero manda: si no está o no suena, no hay nada más que discutir ---
    if not fichero.get("ok"):
        return FICHERO_MAL, list(fichero.get("problemas", [])), {}

    problemas += fichero.get("problemas", [])

    # --- ¿el audio es la canción que dice ser? ---
    #
    # Se combinan los dos ejes, porque cada uno responde a una pregunta distinta:
    #   croma -> ¿es la misma COMPOSICIÓN?   (un cover la conserva)
    #   mfcc  -> ¿es la misma GRABACIÓN?     (un cover NO la conserva)
    #
    # Y el mfcc es el discriminador más fuerte según la medición: las grabaciones correctas
    # dieron 0.588–0.887 y las canciones ajenas 0.044–0.225. El croma también separa
    # (0.974–0.995 contra 0.573–0.931) pero con menos margen, así que se usa como apoyo.
    if audio.get("ok"):
        croma, mfcc = audio["croma"], audio["mfcc"]
        misma_composicion = croma >= UMBRAL_CROMA_MISMA
        misma_grabacion = mfcc >= UMBRAL_MFCC_MISMA

        if misma_composicion and misma_grabacion:
            pass                                   # el fichero es lo que dice ser
        elif misma_composicion and not misma_grabacion:
            problemas.append(
                f"misma canción pero OTRA GRABACIÓN (cover, directo u otra versión): la "
                f"composición cuadra (croma {croma:.2f}) pero el timbre no "
                f"(mfcc {mfcc:.2f}, se espera ≥{UMBRAL_MFCC_MISMA})")
            return OTRA_VERSION, problemas, {}
        elif croma < UMBRAL_CROMA_DUDOSA:
            problemas.append(
                f"el audio NO es esa canción: no cuadra ni la composición (croma {croma:.2f}, "
                f"se espera ≥{UMBRAL_CROMA_MISMA}) ni la grabación (mfcc {mfcc:.2f})")
            return OTRA_CANCION, problemas, {}
        else:
            # Composición dudosa y timbre distinto: casi siempre es otra canción, pero se
            # deja como problema en vez de veredicto para que lo mire una persona.
            problemas.append(
                f"el audio no cuadra: composición dudosa (croma {croma:.2f}, frontera "
                f"{UMBRAL_CROMA_DUDOSA}–{UMBRAL_CROMA_MISMA}) y grabación distinta "
                f"(mfcc {mfcc:.2f})")
            return OTRA_CANCION, problemas, {}

    # --- los datos ---
    if dz.get("id_guardado_valido") is False:
        problemas.append("el deezer_id guardado apunta a otra canción; sus datos no son fiables")
    correcciones.update(dz.get("propuestas") or {})

    if tags_cmp.get("ok") is False:
        problemas += tags_cmp.get("discrepancias", [])

    # --- versión según los títulos ---
    m_titulo = marcas(f"{track.get('title','')} {track.get('album','')}")
    m_yt = marcas((yt.get("oficial_limpio") or {}).get("title") or "")
    raras = {"cover", "karaoke", "instrumental", "sped", "demo", "ensayo", "letra"}
    if (m_titulo & raras) and not (m_yt & raras):
        problemas.append(f"el título lleva marcas de versión rara {sorted(m_titulo & raras)}")
        return OTRA_VERSION, problemas, {}
    if "remix" in m_titulo and not track.get("is_remix"):
        correcciones["is_remix"] = 1
    if int(track.get("is_remix") or 0) == 1 and "remix" not in m_titulo and clave(track.get("title")) == clave(
            (dz.get("candidato") or {}).get("title")):
        correcciones["is_remix"] = 0

    # --- duración contra Deezer ---
    cand = dz.get("candidato") or {}
    guardado = dz.get("guardado") or {}
    referencia = cand.get("duration") or guardado.get("duration")
    real = fichero.get("duration")
    if referencia and real:
        desvio = abs(float(real) - float(referencia)) / max(float(referencia), 1)
        if desvio > 0.25:
            problemas.append(
                f"la duración del fichero ({real:.0f}s) se aleja mucho de la de Deezer "
                f"({referencia:.0f}s, {desvio:.0%})")
            return OTRA_VERSION, problemas, {}

    # --- si no hay nada con lo que contrastar ---
    if not dz.get("ok") and not audio.get("ok") and not yt.get("ok"):
        problemas.append("no se pudo contrastar con ninguna fuente externa")
        return SIN_DATOS, problemas, {}

    if correcciones:
        return METADATOS, problemas, correcciones
    return CORRECTA, problemas, {}


# ===========================================================================
# API
# ===========================================================================
def analizar(track: dict, *, client=None, con_audio: bool = True,
             con_youtube: bool = True, con_preview: bool = True) -> Analisis:
    """Revisa una canción. No escribe nada: devuelve el análisis."""
    detalle: dict[str, Any] = {}

    fichero = revisar_fichero(track)
    detalle["fichero"] = fichero

    tags: dict = {}
    tags_cmp: dict = {}
    if track.get("file_path"):
        tags = leer_tags(track["file_path"])
        tags_cmp = revisar_tags(track, tags)
    detalle["tags"] = tags
    detalle["tags_cmp"] = tags_cmp

    dz = revisar_deezer(track, client)
    detalle["deezer"] = dz

    audio: dict = {"ok": False}
    if con_audio and con_preview and fichero.get("ok"):
        preview = None
        cand = dz.get("candidato") or {}
        guardado = dz.get("guardado") or {}
        # Se prefiere el preview de la canción a la que dice la ficha, no el del candidato
        # nuevo: así se comprueba «¿el fichero es lo que DICE ser?», que es la pregunta.
        if guardado.get("preview"):
            preview = guardado["preview"]
        elif cand.get("preview"):
            preview = cand["preview"]
        audio = comparar_audio(track, preview)
    detalle["audio"] = audio

    yt: dict = {"ok": False}
    if con_youtube:
        yt = revisar_youtube(track)
    detalle["youtube"] = yt

    veredicto, problemas, correcciones = decidir(track, fichero, tags, tags_cmp, dz, audio, yt)
    return Analisis(
        track_id=int(track["id"]), titulo=track.get("title") or "", artista=track.get("artist") or "",
        veredicto=veredicto, problemas=problemas, correcciones=correcciones, detalle=detalle)


def registrar(a: Analisis) -> None:
    """Deja constancia del veredicto SIN tocar la ficha.

    Hace falta para que una pasada de revisión avance: si no se apuntara nada, el lote
    siguiente volvería a empezar por las mismas canciones y nunca se llegaría al final del
    catálogo. Es lo que hace `--sin-aplicar` (revisar sin corregir).
    """
    db.update_track(
        a.track_id,
        verificado_at=_ahora(),
        veredicto=a.veredicto,
        veredicto_detalle=json.dumps(a.a_dict(), ensure_ascii=False)[:20000],
        audio_huella=(a.detalle.get("audio") or {}).get("croma"),
    )


def aplicar(a: Analisis, *, mover_fichero: bool = True) -> dict:
    """Escribe las correcciones de METADATOS y deja el veredicto guardado.

    No sustituye ficheros: eso es `reemplazar_fichero()`, que necesita descargar y por eso
    va aparte y con su propio permiso.
    """
    from .catalog import derive_era, derive_tags, is_remix, organize_track, write_tags

    hecho: dict[str, Any] = {"campos": {}, "fichero_movido": None}
    if a.correcciones:
        campos = dict(a.correcciones)
        # Recolocar era / remix con los datos nuevos
        merged = {**{k: v for k, v in a.detalle.get("_track", {}).items()}, **campos}
        era = derive_era(campos.get("year") or merged.get("year"))
        if era and era != merged.get("era"):
            campos["era"] = era
        rem = 1 if is_remix(campos.get("title") or merged.get("title", ""),
                            campos.get("artist") or merged.get("artist", "")) else 0
        campos["is_remix"] = rem
        campos["tags"] = ", ".join(derive_tags(
            bpm=merged.get("bpm"), energy=merged.get("energy"), genre=merged.get("genre"),
            year=campos.get("year") or merged.get("year"),
            title=campos.get("title") or merged.get("title", ""),
            artist=campos.get("artist") or merged.get("artist", ""),
            language=merged.get("language"), is_remix_flag=bool(rem)))

        db.update_track(a.track_id, **campos)
        hecho["campos"] = campos

        # Reescribir los ID3 para que el fichero deje de contradecir a la ficha
        if merged.get("file_path"):
            try:
                write_tags(merged["file_path"], {**merged, **campos})
            except Exception as e:  # noqa: BLE001
                hecho["error_tags"] = f"{type(e).__name__}: {e}"
            if mover_fichero and any(campos.get(k) for k in ("year", "album", "artist", "title")):
                try:
                    nuevo = organize_track({**merged, **campos})
                    if nuevo and nuevo != merged.get("file_path"):
                        from .catalog import _rel_music
                        p = Path(nuevo)
                        db.update_track(a.track_id,
                                        file_path=_rel_music(nuevo),
                                        file_size=p.stat().st_size if p.exists() else 0)
                        hecho["fichero_movido"] = nuevo
                except Exception as e:  # noqa: BLE001
                    hecho["error_mover"] = f"{type(e).__name__}: {e}"

    registrar(a)
    return hecho


def _ahora() -> str:
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")


# ===========================================================================
# Revisión en lote
# ===========================================================================
def pendientes(limit: int = 50, *, solo_dudosos: bool = False,
               horas: int = 0, incluir_veredictos: Iterable[str] | None = None) -> list[dict]:
    """Canciones por revisar: las nunca verificadas o las verificadas hace tiempo."""
    # Las columnas del corrector las crea init_db(); sin esto, un proceso que no sea la app
    # (un script, por ejemplo) se encontraría con «no such column: verificado_at».
    db.init_db()
    conn = db.get_conn()
    try:
        sql = ("SELECT * FROM tracks WHERE file_path IS NOT NULL AND file_path!='' ")
        args: list[Any] = []
        if incluir_veredictos:
            marcas_sql = ",".join("?" * len(list(incluir_veredictos)))
            sql += f"AND veredicto IN ({marcas_sql}) "
            args += list(incluir_veredictos)
        elif solo_dudosos:
            sql += ("AND (veredicto IS NULL OR veredicto IN "
                    "('otra_version','otra_cancion','fichero_mal','sin_datos','metadatos')) ")
        if horas > 0:
            sql += ("AND (verificado_at IS NULL OR "
                    "verificado_at < datetime('now', ?)) ")
            args.append(f"-{horas} hours")
        elif not incluir_veredictos:
            sql += "AND verificado_at IS NULL "
        sql += "ORDER BY verificado_at IS NOT NULL, id LIMIT ?"
        args.append(limit)
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def revisar_lote(limit: int = 50, *, aplicar: bool = False, con_audio: bool = True,
                 con_youtube: bool = True, progreso=None, parar_si=None) -> list[Analisis]:
    """Revisa un lote. Con `aplicar=False` (por defecto) no toca NADA."""
    from . import deezer as dz
    try:
        client = dz.DeezerClient()
    except Exception:  # noqa: BLE001
        client = None

    salida: list[Analisis] = []
    for t in pendientes(limit):
        if parar_si and parar_si():
            break
        if progreso is not None:
            progreso["actual"] = f"{t.get('artist')} - {t.get('title')}"
        try:
            a = analizar(t, client=client, con_audio=con_audio, con_youtube=con_youtube)
        except Exception as e:  # noqa: BLE001
            a = Analisis(track_id=int(t["id"]), titulo=t.get("title") or "",
                         artista=t.get("artist") or "", veredicto=SIN_DATOS,
                         problemas=[f"error inesperado: {type(e).__name__}: {e}"])
        a.detalle["_track"] = t
        if aplicar:
            a.detalle["aplicado"] = aplicar(a)
        else:
            registrar(a)
        salida.append(a)
    return salida
