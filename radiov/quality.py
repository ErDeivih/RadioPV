"""Puerta de calidad: decide si una pista puede entrar al catálogo público.

LA DURACIÓN DEPENDE DE QUÉ SEA
------------------------------
Aquí ponía un único margen (1:30 – 15:00) con el comentario «corta mezclas de DJ y ruido». El
resultado medido en el servidor: **28 pistas en cuarentena por duración**, y entre ellas cosas
que el usuario escucha a propósito —una sesión de reggaetón viejo de 22 minutos, un «Party Mix
Session», mashups de 60-90 s— mientras colaban compilaciones de 5 horas («2024 Top Hits.wav»,
289 min) y tonos de móvil.

O sea: la puerta rechazaba lo bueno y dejaba pasar lo malo, porque miraba **cuánto dura** en vez
de **qué es**. Ahora el margen se elige según el tipo:

    canción normal     1:30 – 15:00     (como antes)
    remix / mashup     0:45 – 20:00     (los mashups son cortos; algunos cruces duran 15 min)
    sesión de DJ       5:00 – 3:00:00   (una sesión dura lo que dura; hasta 3 h)

Y sigue habiendo veto para lo que no es música: compilaciones de gimnasio, tonos de móvil,
sintonías de series y «top 100» de temporada.
"""
import re

# --- márgenes por tipo ---
DUR_MIN, DUR_MAX = 90.0, 900.0                    # canción normal (1:30 – 15:00)
DUR_MIN_REMIX, DUR_MAX_REMIX = 45.0, 1200.0       # remix / mashup (0:45 – 20:00)
DUR_MIN_SESION, DUR_MAX_SESION = 300.0, 10800.0   # sesión de DJ (5:00 – 3:00:00)

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

# Lo que NO es música, aunque dure lo que una canción. Estos venían del catálogo real: canales
# de compilaciones ("2024 Hit Playlist", "Workout Music Records", "Fitness & Workout Hits"),
# tonos de móvil ("Ringtone Hits") y sintonías de series ("TV Hits", "Cartoon Opening Theme").
NO_MUSICA = re.compile(
    r"\bringtone|\btono\s+de\s+llamada|"
    r"\b(top|greatest|best)\s*(100|50|40|20|10)\b|"
    r"\btop\s+hits?\b|\bhits?\s+playlist\b|\bhit\s+playlist\b|"
    r"\bworkout\b|\baerobic\b|\bfitness\b|\bcardio\b|\bstep\s+session\b|\bgym\b|"
    r"\bcartoon\s+opening\b|\bopening\s+theme\b|\btv\s+hits?\b|"
    r"\bkaraoke\b|\bbacking\s+track\b|\bcover\s+version\s+by\b",
    re.I)

# --- cómo se reconoce cada tipo ---
# OJO CON `re.I`: sin él, «Mashup» y «Remix» (con mayúscula, que es como se escriben de verdad)
# NO coincidían. Es un fallo de una letra que deja fuera justo lo que se busca.
#
# Una SESIÓN de DJ: o lo dice claramente (dj set, set dj, mixtape, megamix, non-stop, mezcla
# continua, «vol. N»), o lleva «session/sesión» **y además dura más de una canción**. Lo segundo
# es importante: «Bzrp Music Sessions» son canciones de 2 minutos, no sesiones de DJ.
_SESION_CLARA_RE = re.compile(
    r"\bdj\s*set\b|\bset\s*dj\b|\bmixtape\b|\bmegamix\b|\bnon[\s-]?stop\b|"
    r"\bcontinuous\s+mix\b|\blive\s+set\b|\bparty\s+mix\b|"
    # En castellano, que es como se titula aquí la mitad del catálogo.
    r"\bmezcla\s+continua\b|\bmix\s+continuo\b|"
    r"(?<!re)\bmix\b",
    re.I)
# «Session», «sesión», «Vol. N», «DJ» y «mezcla» a secas: puede ser una sesión de DJ o una canción
# que se llama así. Bizarrap titula «Bzrp Music Sessions, Vol. 0/66» y son canciones de dos
# minutos, así que estas marcas sólo cuentan si además el track dura como una sesión.
_SESION_DUDA_RE = re.compile(
    r"\bsesion(es)?\b|\bsession(s)?\b|\bvol\.?\s*\d+\b|\bdj\b|\bmezcla\b|\bremix\s+set\b",
    re.I)
# Un MASHUP cruza dos o más canciones: lo típico es «A x B», «A vs B» o decirlo con la palabra.
_MASHUP_RE = re.compile(
    r"\bmash[\s-]?up\b|\bmegamix\b|\bblend\b|\bvs\.?\b|(?<=\S)\s[xX]\s(?=\S)", re.I)
# Un REMIX parte de UNA canción.
_REMIX_RE = re.compile(
    r"\bremix\b|\bre-?mix\b|\bbootleg\b|\bedit\b|\bflip\b|\brework\b|\brefix\b", re.I)


def clasificar(titulo: str = "", artista: str = "", duracion: float | None = None) -> str | None:
    """Devuelve 'sesion', 'mashup', 'remix' o None.

    El artista se limpia de las colaboraciones (`feat.`, `ft.`, `con`) ANTES de mirarlo: si no,
    «Basshunter - Now You're Gone (feat. DJ Mental Theo's Bazzheadz)» contaba como sesión de DJ
    por el `feat.`, que es un falso positivo que ya estaba en el catálogo.
    """
    t = titulo or ""
    a = re.split(r"\s(?:feat\.?|ft\.?|with|con)\s", artista or "", flags=re.I)[0]
    d = duracion or 0

    if _SESION_CLARA_RE.search(f"{t} {a}"):
        return "sesion"
    if d > DUR_MAX:
        # Con una duración de sesión, cualquiera de estas marcas basta: «DJ …», «session»,
        # «Vol. 3» (que es como se numeran las sesiones de un DJ).
        if re.match(r"^\s*dj", a, re.I) or _SESION_DUDA_RE.search(f"{t} {a}"):
            return "sesion"
    if _MASHUP_RE.search(t):
        return "mashup"
    if _REMIX_RE.search(t):
        return "remix"
    return None


def margenes(tipo: str | None) -> tuple[float, float]:
    """El margen de duración de un tipo concreto (para poder explicarlo en los mensajes)."""
    if tipo == "sesion":
        return DUR_MIN_SESION, DUR_MAX_SESION
    if tipo in ("remix", "mashup"):
        return DUR_MIN_REMIX, DUR_MAX_REMIX
    return DUR_MIN, DUR_MAX


def ventanas(tipo: str | None) -> list[tuple[float, float]]:
    """TODAS las ventanas que le valen a esta pista: entra si encaja en cualquiera.

    Se acepta por «cualquiera» y no por «la que le toca» a propósito, y así se resuelven los casos
    raros sin listas de excepciones:
      · «Bzrp Music Sessions, Vol. 0/66» (120 s) no es sesión, pero es una canción normal: entra.
      · «SET DJ YURI PEDRADA» (8 min) es sesión y también cabe como canción: entra igual.
      · Un mashup de 63 s no llega al mínimo de canción, pero sí al de mashup: entra.
      · Una compilación de 5 horas no cabe en ninguna: se queda fuera, que es lo que se quiere.
    """
    v = [margenes(None)]                        # el margen de canción normal siempre vale
    if tipo in ("remix", "mashup", "sesion"):
        # Las mezclas cortas («Party Mix Session 1.5», 72 s) son mezclas: si se rechazaran por no
        # llegar al mínimo de sesión, se perdería contenido que el usuario sí escucha.
        v.append(margenes("remix"))
    if tipo == "sesion":
        v.append(margenes("sesion"))
    return v


def revisar(rec: dict) -> tuple[bool, str]:
    """Devuelve (aceptada, motivo). Si aceptada=False, la pista va a 'cuarentena'."""
    titulo, artista = (rec.get("title") or ""), (rec.get("artist") or "")
    if BASURA.search(titulo) or BASURA.search(artista):
        return False, "texto no musical (HTML/CSS) en título o artista"
    art_l = artista.strip().lower()
    if art_l in ARTISTAS_PROHIBIDOS or art_l.endswith(SUFIJOS_PROHIBIDOS):
        return False, f"artista genérico: {artista}"
    if NO_MUSICA.search(titulo) or NO_MUSICA.search(artista):
        return False, "no es música (compilación, tono o sintonía)"
    if len(titulo.strip()) < 2 or len(artista.strip()) < 2:
        return False, "título o artista demasiado cortos"
    d = rec.get("duration") or 0
    if d:
        tipo = rec.get("tipo") or clasificar(titulo, artista, d)
        if not any(minimo <= d <= maximo for minimo, maximo in ventanas(tipo)):
            etiqueta = f" [{tipo}]" if tipo else ""
            return False, f"duración fuera de rango{etiqueta}: {d:.0f}s"
    return True, ""
