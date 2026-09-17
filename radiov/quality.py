"""Puerta de calidad: decide si una pista puede entrar al catálogo público."""
import re

DUR_MIN, DUR_MAX = 90.0, 900.0          # 1:30 – 15:00 (conserva Thriller/Metallica; corta mezclas de DJ y ruido)
ARTISTAS_PROHIBIDOS = {"deezer", "disney", "various artists", "various", "unknown"}
# Canales automáticos de YouTube: se llaman "Artista - Topic". Es un SUFIJO.
# Ojo: "topic" a secas NO vale como veto — Topic es un DJ real ("Breaking Me").
SUFIJOS_PROHIBIDOS = (" - topic", " - tema")
BASURA = re.compile(
    r"<[a-zA-Z/][^>]*>"           # etiqueta HTML real
    r"|charset|font-weight|z-index|align-items|justify-content|display\s*:\s*block|"
    r"min[\s-]*height|background|margin\s*:|padding\s*:|position\s*:|content\s*:|"
    r"color\s*:|left\s*:|top\s*:|width\s*:|height\s*:"
    r"|&nbsp;|&#\d+;|https?://|^\s*$",
    re.I)


def revisar(rec: dict) -> tuple[bool, str]:
    """Devuelve (aceptada, motivo). Si aceptada=False, la pista va a 'cuarentena'."""
    titulo, artista = (rec.get("title") or ""), (rec.get("artist") or "")
    if BASURA.search(titulo) or BASURA.search(artista):
        return False, "texto no musical (HTML/CSS) en título o artista"
    art_l = artista.strip().lower()
    if art_l in ARTISTAS_PROHIBIDOS or art_l.endswith(SUFIJOS_PROHIBIDOS):
        return False, f"artista genérico: {artista}"
    d = rec.get("duration") or 0
    if d and not (DUR_MIN <= d <= DUR_MAX):
        return False, f"duración fuera de rango: {d:.0f}s"
    if len(titulo.strip()) < 2 or len(artista.strip()) < 2:
        return False, "título o artista demasiado cortos"
    return True, ""
