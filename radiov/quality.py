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

# --- portugués: NO entra ---
# Norma del dueño del catálogo: español (España y Latinoamérica), inglés y, de siempre, italiano y
# francés. **Portugués no.** Y entraba: por la vía de YouTube las semillas de «set dj»/«dj nene»
# traían funk brasileño, y como la semilla declaraba `language: "es"`, ni se detectaba. Se veía en
# el catálogo real: «Mc GP - Ela Vem (SET DJ NENE)», «Henrique & Juliano - Última Saudade (Ao Vivo)»,
# «JC no beat - Eu Vou Machucar Só um Pouquinho X Catucando Gostosinho».
#
# Se reconocen marcas que el español NO usa, para no tirar canciones en español:
#   · terminaciones en «-ção» y palabras con «ã» (não, então, coração): en español serían «-ción»
#     (canción, corazón) y «á»;
#   · «você/vocês», «ao vivo», «muito», «saudade», «obrigado», «beijo», «cê», «só», «comigo»;
#   · el diminutivo en «-inho/-inha» SÓLO detrás de artículo o posesivo («um pouquinho», «meu
#     beijinho»): en español el diminutivo es «-ito/-iño», así que «nh» delata al portugués. A
#     propósito NO vale un «-inho» suelto: «Ninho» es un rapero francés y lo mandaba a cuarentena;
#   · géneros que sólo existen en Brasil: sertanejo, piseiro, forró, pagode, axé, arrocha,
#     vaquejada, sofrência, brega, funk carioca, baile funk.
# OJO con tres cosas que se probaron y se quitaron por imprecisas:
#   · «música» se escribe igual en español y en portugués (media lista española fuera);
#   · «axé» SIN tilde coincide con «axe» inglés («Small Axe», de UB40): tiene que llevar el tilde;
#   · «tá» y «tô» se escriben igual en el español coloquial («tá bien»), así que no sirven de marca.
# Y «mc N…» se mira SÓLO en el artista (ver `parece_portugues`): en una colaboración de rap francés
# aparecen «MC YOSHI» y compañía, y eso no es funk brasileño.
_PORTUGUES_RE = re.compile(
    r"\b\w+ç(ão|ões)\b|\bnão\b|\bentão\b|\btambém\b|\bvocês?\b|\bao\s+vivo\b|\bmuito\b|"
    r"\bsaudade\b|\bobrigad[oa]\b|\bbeijo\b|\bcê\b|\bsó\b|\bpra\s+mim\b|\bcomigo\b|"
    r"\b(?:um|uma|do|da|no|na|meu|minha|seu|sua|esse|essa)\s+\w+inh[ao]\b|"
    r"\bsertanej\w+|\bpiseiro\b|\bforr[óo]\b|\bpagode\b|\baxé\b|\barrocha\b|\bvaquejada\b|"
    r"\bsofrência\b|\bbrega\b|\bfunk\s+carioca\b|\bbaile\s+funk\b|"
    # «trava» es jerga brasileña del funk (medido: en el catálogo cae UNA pista, y es exactamente la
    # que se estaba colando: «SET DJ YURI PEDRADA - TRAVA CHIP», funk con MC Meno K y MC Ryan SP).
    # En español sería «traba», así que no puede llevarse nada en español.
    r"\btrava\b",
    re.I)

# Artistas brasileños de funk: se llaman «Mc» + nombre («Mc GP», «MC LUUKY»). Se comprueba sólo al
# PRINCIPIO del nombre del artista.
_ARTISTA_MC_RE = re.compile(r"^\s*mc[\s.]", re.I)


# El diminutivo FEMENINO «-inha» en el TÍTULO. Es la otra mitad de lo que se estaba escapando:
# «Motinha», «Adivinha o quê» (Lulu Santos), «Recife Minha Cidade» (Reginaldo Rossi), «Fazendinha
# Sessions». Medido contra el catálogo (5.216 pistas, 20/09/2026): caen 5 pistas y las 5 son
# brasileñas. Se veía en las listas del usuario: los sets de funk brasileño se colaban en «Sesiones
# de DJ» y en «Mashups y remixes» (DJ Renato B - MOTINHA MIX…).
#
# POR QUÉ FEMENINO Y POR QUÉ SÓLO EL TÍTULO:
#   · El masculino «-inho» NO se puede añadir: cae «Ninho», un rapero francés (3 pistas), y ya se
#     quitó una vez justo por eso. La forma femenina no tiene ese problema.
#   · Sólo el título, no el artista: «Martinha» es una cantante brasileña con una canción en español
#     («Hoy Daría Yo la Vida») y marcarla por el nombre del artista sería un falso positivo; en el
#     título, «-inha» es la palabra portuguesa.
_PORTUGUES_TITULO_RE = re.compile(r"\b\w+inha\b", re.I)


def parece_portugues(titulo: str = "", artista: str = "") -> bool:
    """¿Esto es portugués? Se mira el título y el artista (en Brasil el «artista» suele ser el
    cantante del canal: «Mc GP», «Henrique & Juliano»)."""
    if _PORTUGUES_RE.search(f"{titulo or ''} {artista or ''}"):
        return True
    if _PORTUGUES_TITULO_RE.search(titulo or ""):
        return True
    return bool(_ARTISTA_MC_RE.match(artista or ""))


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
    # Compilaciones: «200 Mejores Canciones De TikTok», «Las Mejores Canciones De…». Es el mismo
    # caso que «Top 100» pero en castellano, y se colaba: apareció recuperando descargas del 19/09.
    r"\b\d{2,3}\s+mejores\s+canciones\b|\bmejores\s+canciones\b|\bmejores\s+exitos\b|"
    r"\b\d{2,3}\s+best\s+songs\b|\bbest\s+songs\b|"
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
    r"\bmezcla\s+continua\b|\bmix\s+continuo\b",
    re.I)
# «Session», «sesión», «Vol. N», «DJ», «mezcla» y «mix» a secas: puede ser una sesión de DJ o una
# canción que se llama así. Estas marcas sólo cuentan si además el track dura como una sesión.
#
# El «mix» suelto está aquí y no arriba a propósito: «(Original Mix)», «(Rock Mix)», «(Donk Mix)»
# son versiones de UNA canción, no sesiones, y con la palabra suelta se colaban en la lista de
# sesiones de DJ canciones de tres minutos. («Megamix» sí es una mezcla de verdad, y por eso está
# arriba.) Bizarrap titula «Bzrp Music Sessions, Vol. 0/66» y son canciones de dos minutos.
_SESION_DUDA_RE = re.compile(
    r"\bsesion(es)?\b|\bsession(s)?\b|\bvol\.?\s*\d+\b|\bdj\b|\bmezcla\b|(?<!re)\bmix\b",
    re.I)
# Un MASHUP cruza dos o más canciones: «A x B», «A vs B», «mashup», «megamix», «blend».
# «Medley» también: es literalmente varias canciones seguidas en una sola pista (lo comprobamos
# contra el catálogo: «Los Del Río - Medley», «Claude Barzotti - Medley»).
# El cruce se comprueba aparte (`_es_cruce_de_verdad`) porque hay títulos que llevan una «x» sin
# ser un mashup: «ROSALÍA - Yo x Ti, Tu x Mi» es una canción, no un cruce de dos.
_MASHUP_RE = re.compile(r"\bmash[\s-]?up\b|\bmegamix\b|\bblend\b|\bmedley\b", re.I)
_SEPARADOR_RE = re.compile(r"\s(?:[xX]|vs\.?|versus)\s", re.I)
# Trozos en los que NO se busca el cruce: dentro de un paréntesis hay créditos, no cruces, y una
# coma separa partes de un mismo título.
_TROCEAR_RE = re.compile(r"[,()\[\]/|]")


def _es_cruce_de_verdad(titulo: str) -> bool:
    """¿El «A x B» / «A vs B» del título es un mashup o sólo una «x» en el nombre?

    Las dos comprobaciones salen de mirar el catálogo real, y las dos hicieron falta:

      · **Se quitan los paréntesis.** Los mashups ponen el cruce en el título; lo que va entre
        paréntesis suele ser un crédito de colaboración: «Avicii - I Could Be The One (Avicii Vs.
        Nicky Romero)» es una canción de los dos, no un cruce.
      · **El cruce se mira en su trozo, no en todo el título.** «ROSALÍA - Yo x Ti, Tu x Mi» tiene
        una «x» a cada lado de una coma: si se mira el título entero, el lado derecho parece un
        título de tres palabras y la canción acaba en la lista de mashups. Mirando cada trozo por
        separado, a cada lado del cruce sólo hay una palabra.
      · Y hace falta que **al menos un lado parezca un título** (dos palabras o más):
        «Shape of You x Despacito» sí, «Yo x Ti» no.

    Se pierden algunos mashups titulados sólo con dos nombres de artista («Eminem vs Linkin Park»).
    Es a propósito: prefiero que falte alguno a llenarle la lista de colaboraciones que no son
    mashups, que es lo que pasaba antes.
    """
    sin_parentesis = re.sub(r"\([^)]*\)", " ", titulo or "")
    for trozo in _TROCEAR_RE.split(sin_parentesis):
        partes = _SEPARADOR_RE.split(trozo)
        if len(partes) != 2:            # sin cruce, o más de uno: no se decide
            continue
        palabras = lambda t: len(re.findall(r"[^\s]+", t.strip()))  # noqa: E731
        if palabras(partes[0]) >= 2 or palabras(partes[1]) >= 2:
            return True
    return False
# Un REMIX parte de UNA canción. Aquí entran las formas que se usan de verdad en YouTube y que el
# catálogo tenía sin clasificar (contadas contra las 6.000 pistas reales):
#   «rmx» (2), «(Original Mix)»/«(Radio Mix)»/«(Club Mix)» (10), «(Extended Version)» (1),
#   «(Sped up)»/«(Slowed)» (1) y «Medley» va como mashup.
# El «mix» suelto cuenta como remix y NO como sesión: una sesión ya se ha reconocido antes por su
# duración, así que lo que llega hasta aquí es «(Donk Mix)» o «(Cumbia Wepa Mix)», que son
# versiones de una canción.
_REMIX_RE = re.compile(
    r"\bremix\b|\bre-?mix\b|\brmx\b|\bbootleg\b|\bedit\b|\bflip\b|\brework\b|\brefix\b|"
    r"\bextended\s+(mix|version)\b|\bsped\s?up\b|\bslowed\b|(?<!re)\bmix\b",
    re.I)


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
        # «Vol. 3» (que es como se numeran las sesiones de un DJ), «… Mix».
        if re.match(r"^\s*dj", a, re.I) or _SESION_DUDA_RE.search(f"{t} {a}"):
            return "sesion"
        # Y SI DURA MÁS DE 20 MINUTOS, ES UNA MEZCLA AUNQUE NO LO DIGA EL TÍTULO.
        # -------------------------------------------------------------------
        # Antes esto se decidía sólo por el nombre, y se quedaban fuera mezclas que el usuario
        # escucha: se midió al recuperar descargas del 19/09 y apareció «BRESH - REMIXES Y REGGAETON
        # OLD SCHOOL EN AMERIKA», **66 minutos**, rechazada por «duración fuera de rango» porque su
        # título no dice «sesión» ni «set dj» ni el artista empieza por «DJ». Una canción normal de
        # 20 minutos no existe: a partir de ahí, o es una mezcla o es una compilación, y las
        # compilaciones ya las caza `NO_MUSICA` («Top 100», «200 Mejores Canciones»…) antes de
        # llegar aquí. Así que el que decide es el tiempo, no el nombre.
        if d > 1200:
            return "sesion"
    if _MASHUP_RE.search(t) or _es_cruce_de_verdad(t):
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
    if parece_portugues(titulo, artista):
        return False, "portugués (el catálogo es en español/inglés, e italiano y francés de siempre)"
    if len(titulo.strip()) < 2 or len(artista.strip()) < 2:
        return False, "título o artista demasiado cortos"
    d = rec.get("duration") or 0
    if d:
        tipo = rec.get("tipo") or clasificar(titulo, artista, d)
        if not any(minimo <= d <= maximo for minimo, maximo in ventanas(tipo)):
            etiqueta = f" [{tipo}]" if tipo else ""
            return False, f"duración fuera de rango{etiqueta}: {d:.0f}s"
    return True, ""
