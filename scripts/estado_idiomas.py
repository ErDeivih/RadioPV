"""Cómo está repartido el catálogo entre las DOS bases, y qué se diferencian.

POR QUÉ HACE FALTA
------------------
RadioPV guarda la música en dos bases SQLite y no son la misma cosa:

  · `radiov.db`  — la biblioteca del recolector (la que gestiona el panel de administración).
  · `backend.db` — la que sirve la aplicación (listas, portada, reproductor): la que ve el usuario.

Esa separación ya causó un fallo serio: el borrado del panel limpiaba `radiov.db` y el disco, y
dejaba la canción en `backend.db` (o sea, en la aplicación, y sin fichero). Este script enseña de un
vistazo si las dos bases cuentan lo mismo, que es la comprobación que hay que hacer después de
cualquier limpieza.

Uso (dentro del contenedor del API):
    docker exec radiopv-api python /app/scripts/estado_idiomas.py
"""
import os
import sqlite3

DIR = os.environ.get("RADIOPV_DATA_DIR", "/app/data")
BASES = ("radiov.db", "backend.db")


def abrir(nombre: str) -> sqlite3.Connection:
    con = sqlite3.connect(f"{DIR}/{nombre}")
    con.row_factory = sqlite3.Row
    return con


def idiomas(con: sqlite3.Connection) -> dict:
    return {r["l"] or "(vacío)": r["n"] for r in con.execute(
        "SELECT COALESCE(language,'') l, COUNT(*) n FROM tracks GROUP BY l ORDER BY n DESC")}


datos = {}
for nombre in BASES:
    con = abrir(nombre)
    datos[nombre] = {
        "total": con.execute("SELECT COUNT(*) FROM tracks").fetchone()[0],
        "idiomas": idiomas(con),
        "sin_fichero": con.execute(
            "SELECT COUNT(*) FROM tracks WHERE file_path IS NULL OR file_path=''").fetchone()[0],
        "por_estado": {r["s"]: r["n"] for r in con.execute(
            "SELECT COALESCE(status,'') s, COUNT(*) n FROM tracks GROUP BY s ORDER BY n DESC")},
    }
    con.close()

print("=== resumen ===")
for nombre in BASES:
    d = datos[nombre]
    print(f"   {nombre:<12} {d['total']:>6} canciones · sin fichero: {d['sin_fichero']} · "
          f"{len(d['por_estado'])} estados")

print("\n=== por idioma (y la diferencia entre las dos) ===")
claves = sorted(set(datos[BASES[0]]["idiomas"]) | set(datos[BASES[1]]["idiomas"]))
print(f"   {'idioma':<10} {'recolector':>11} {'aplicación':>11}   diferencia")
for k in claves:
    a = datos["radiov.db"]["idiomas"].get(k, 0)
    b = datos["backend.db"]["idiomas"].get(k, 0)
    aviso = "" if a == b else f"   <-- {b - a:+d}"
    print(f"   {k:<10} {a:>11} {b:>11}{aviso}")

print("\n=== por estado ===")
claves = sorted(set(datos["radiov.db"]["por_estado"]) | set(datos["backend.db"]["por_estado"]))
print(f"   {'estado':<14} {'recolector':>11} {'aplicación':>11}")
for k in claves:
    a = datos["radiov.db"]["por_estado"].get(k, 0)
    b = datos["backend.db"]["por_estado"].get(k, 0)
    print(f"   {k or '(vacío)':<14} {a:>11} {b:>11}")

dif = datos["backend.db"]["total"] - datos["radiov.db"]["total"]
print(f"\n[{'i' if dif == 0 else '!'}] la aplicación tiene {dif:+d} canciones respecto al recolector")
if dif:
    print("    Si la diferencia crece después de una limpieza, es que se está borrando en una base")
    print("    y no en la otra: canciones que siguen en la aplicación y ya no tienen fichero.")
