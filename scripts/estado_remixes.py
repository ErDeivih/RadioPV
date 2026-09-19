"""¿Cuántos mashups, remixes y sesiones de DJ hay de verdad en el catálogo?

Se mira por marca (`is_remix`), por patrón de título (cruce «x», «vs») y por duración (las
sesiones de DJ son largas). Sirve para decidir si hace falta una lista propia y con cuántas
canciones contaría.
"""
import os
import re
import sqlite3

DB = os.environ.get("RADIOPV_DATA_DIR", "/app/data") + "/radiov.db"
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

print("=== por marca is_remix ===")
for f in con.execute("SELECT is_remix, COUNT(*) n FROM tracks GROUP BY is_remix"):
    print(f"   is_remix={f['is_remix']}: {f['n']}")

print("\n=== de las marcadas, por estado ===")
for f in con.execute(
        "SELECT status, COUNT(*) n FROM tracks WHERE is_remix=1 GROUP BY status ORDER BY n DESC"):
    print(f"   {f['status']}: {f['n']}")

print("\n=== cruces en el título (mashup sin la palabra mashup) ===")
patrones = {
    "cruce con x  (A x B)": r"\S+\s+[xX]\s+\S+",
    "vs": r"\bvs\.?\b",
    "mashup/up": r"mash\s?up",
    "megamix/blend": r"megamix|blend",
    "remix": r"\bremix\b",
    "sesion/ dj set": r"\bdj\s?set\b|session|mixtape",
    "artista que empieza por dj": None,
}
for nombre, patron in patrones.items():
    if patron is None:
        n = con.execute("SELECT COUNT(*) n FROM tracks WHERE LOWER(artist) LIKE 'dj%'").fetchone()["n"]
    else:
        n = con.execute("SELECT COUNT(*) n FROM tracks WHERE title REGEXP ?", (patron,)).fetchone()["n"] \
            if False else None
        # SQLite no trae REGEXP: se filtra en Python.
        n = sum(1 for r in con.execute("SELECT title FROM tracks") if re.search(patron, r["title"] or "", re.I))
    print(f"   {nombre:28s} {n}")

print("\n=== sesiones largas (más de 15 min) ===")
largas = con.execute(
    "SELECT COUNT(*) n FROM tracks WHERE duration > 900").fetchone()["n"]
largas_remix = con.execute(
    "SELECT COUNT(*) n FROM tracks WHERE duration > 900 AND is_remix=1").fetchone()["n"]
print(f"   todas: {largas} · marcadas como remix/sesión: {largas_remix}")

print("\n=== artistas tipo DJ con más canciones ===")
for f in con.execute(
        "SELECT artist, COUNT(*) n FROM tracks WHERE LOWER(artist) LIKE 'dj%' "
        "GROUP BY artist ORDER BY n DESC LIMIT 12"):
    print(f"   {f['n']:4d}  {f['artist']}")

print("\n=== muestra de mashups por cruce (título) ===")
vistos = 0
for r in con.execute("SELECT title, artist, duration FROM tracks WHERE is_remix=1 "
                     "ORDER BY rank DESC LIMIT 12"):
    print(f"   {r['artist']} - {r['title']} ({int((r['duration'] or 0) // 60)} min)")

con.close()
