"""Que vocabulario de mashups/remixes/sesiones encuentra canciones DE VERDAD en el catalogo.

Sirve para ampliar la deteccion con datos y no a ojo: para cada patron candidato dice cuantas
pistas coinciden, cuantas de ellas NO las detecta ya el clasificador actual, y tres ejemplos. Asi
se ve si merece la pena anadirlo y si traeria basura.

Uso (en el servidor):
    docker exec radiopv-api python /tmp/vocabulario_remixes.py
"""
import os
import re
import sqlite3
import sys

sys.path.insert(0, "/app")
from radiov.quality import clasificar  # noqa: E402

DB = os.environ.get("RADIOPV_DATA_DIR", "/app/data") + "/radiov.db"

# Patrones candidatos: (nombre, expresion, tipo que se le asignaria)
CANDIDATOS = [
    # --- mashups y cruces ---
    ("mash up (con espacio)", r"\bmash\s?up\b", "mashup"),
    ("mashup abreviado (mshp)", r"\bmshp\b", "mashup"),
    ("medley", r"\bmedley\b", "mashup"),
    ("potpourri", r"\bpotpourri\b", "mashup"),
    ("crossover", r"\bcrossover\b", "mashup"),
    ("cruce con x minuscula", r"\sx\s", "mashup"),
    ("cruce con ×", r"\s[×✕]\s", "mashup"),
    ("cruce con +", r"\s\+\s", "mashup"),
    ("cruce con &", r"\s&\s", "mashup"),
    ("vs", r"\bvs\.?\b", "mashup"),
    ("versus", r"\bversus\b", "mashup"),
    ("mashup de tiktok", r"tiktok", "mashup"),
    # --- remixes ---
    ("remix (ya esta)", r"\bremix\b", "remix"),
    ("rmx", r"\brmx\b", "remix"),
    ("bootleg", r"\bbootleg\b", "remix"),
    ("flip", r"\bflip\b", "remix"),
    ("rework", r"\brework\b", "remix"),
    ("refix", r"\brefix\b", "remix"),
    ("vip mix", r"\bvip\s?mix\b", "remix"),
    ("club mix", r"\bclub\s?mix\b", "remix"),
    ("extended", r"\bextended\b", "remix"),
    ("sped up / slowed", r"sped\s?up|slowed", "remix"),
    # --- sesiones y mezclas ---
    ("dj set (ya esta)", r"\bdj\s?set\b", "sesion"),
    ("set dj (ya esta)", r"\bset\s?dj\b", "sesion"),
    ("mixed by", r"\bmixed\s+by\b", "sesion"),
    ("continuous mix", r"\bcontinuous\s+mix\b", "sesion"),
    ("essential mix", r"\bessential\s+mix\b", "sesion"),
    ("guest mix", r"\bguest\s+mix\b", "sesion"),
    ("live at / live from", r"\blive\s+(at|from)\b", "sesion"),
    ("en directo / en vivo", r"\ben\s+(directo|vivo)\b", "sesion"),
    ("b2b / back to back", r"\bb2b\b|\bback\s?2\s?back\b", "sesion"),
    ("all night", r"\ball\s+night\b", "sesion"),
    ("afterparty", r"\bafter\s?party\b", "sesion"),
    ("warm up", r"\bwarm\s?up\b", "sesion"),
    ("mixtape (ya esta)", r"\bmixtape\b", "sesion"),
    ("nonstop / non-stop", r"\bnon[\s-]?stop\b", "sesion"),
    ("sesion (ya esta)", r"\bsesi[oó]n(es)?\b", "sesion"),
    ("session (ya esta)", r"\bsessions?\b", "sesion"),
    ("mezcla", r"\bmezcla\b", "sesion"),
    ("mix suelto", r"(?<!re)\bmix\b", "sesion"),
    ("perreo / guaracha (set latino)", r"\bperreo\b|\bguaracha\b", "sesion"),
    ("set de", r"\bset\s+de\b", "sesion"),
    ("vol. N", r"\bvol\.?\s*\d+\b", "sesion"),
    ("part N / pt. N", r"\b(part|pt)\.?\s*\d+\b", "sesion"),
    ("hora / horas", r"\b\d+\s*(h|horas)\b", "sesion"),
]

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
filas = con.execute("SELECT title, artist, duration, is_remix FROM tracks").fetchall()
con.close()

print(f"catalogo: {len(filas)} pistas\n")
print(f"{'patron':34} {'tipo':7} {'coincide':>8} {'nuevas':>7}  ejemplos")
print("-" * 118)

for nombre, patron, tipo in CANDIDATOS:
    rx = re.compile(patron, re.I)
    coincide = 0
    nuevas = []
    for r in filas:
        t = r["title"] or ""
        if not rx.search(t):
            continue
        coincide += 1
        actual = clasificar(t, r["artist"] or "", r["duration"])
        if actual is None:
            nuevas.append(f"{r['artist']} - {t[:40]}")
    ejemplos = " | ".join(nuevas[:2]) if nuevas else ""
    print(f"{nombre:34} {tipo:7} {coincide:>8} {len(nuevas):>7}  {ejemplos[:56]}")
