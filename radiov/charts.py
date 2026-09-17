from __future__ import annotations

import re

import requests

APPLE_TEMPLATE = "https://rss.applemarketingtools.com/api/v2/{country}/music/most-played/{limit}/songs.json"


def apple_top_songs(country: str = "es", limit: int = 50) -> list[dict]:
    """Lista de éxitos actuales de un país desde el feed RSS de Apple Music."""
    url = APPLE_TEMPLATE.format(country=country, limit=limit)
    try:
        r = requests.get(url, timeout=20)
        d = r.json()
    except Exception:  # noqa: BLE001
        return []
    return [
        {"artist": (i.get("artistName") or "").strip(), "title": (i.get("name") or "").strip()}
        for i in d.get("feed", {}).get("results", [])
        if i.get("name")
    ]


def primary_artist(name: str) -> str:
    """Deja solo el artista principal (corta 'feat.', '&', ',' etc.)."""
    if not name:
        return ""
    parts = re.split(r"\s*(?:,|&|feat\.?|ft\.?|\bx\b|\bcon\b)\s*", name, flags=re.I)
    cleaned = (parts[0] or "").strip()
    return cleaned or name.strip()


def los40_top(limit: int = 20) -> list[dict]:
    """Lista de Los 40 (España). Mejor esfuerzo: si no se puede, devuelve []. """
    try:
        import html as _html
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
        r = requests.get("https://los40.com/lista40/", headers={"User-Agent": ua}, timeout=20)
        if r.status_code != 200:
            return []
        text = r.text
    except Exception:  # noqa: BLE001
        return []
    text = _html.unescape(text)
    # Sanear el HTML antes de buscar "Artista - Título": quitar <style>/<script> y todas las
    # etiquetas. Sin esto, el regex captura CSS (`color:#1565b3;font-weight:700`...) y atributos
    # de <meta> (`charset="utf - 8"`) como si fueran títulos. Es la causa de la basura (T-18).
    text = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _html.unescape(text)
    # patrón "Artista - Título" que suele aparecer en las listas
    found = []
    for m in re.finditer(r"([^<>]{2,70})\s*-\s*([^<>]{2,70})", text):
        artist = (m.group(1) or "").strip().strip('"').strip()
        title = (m.group(2) or "").strip().strip('"').strip()
        if not artist or not title or artist == title:
            continue
        if "LISTA" in artist.upper() or len(artist) > 45 or len(title) > 60:
            continue
        key = (artist.lower(), title.lower())
        if key not in found:
            found.append(key)
        if len(found) >= limit * 2:
            break
    return [{"artist": a, "title": t} for a, t in found[:limit]]
