"""Prueba de borrado con las DOS bases: ¿limpia el panel lo que el usuario ve?

POR QUÉ HACE FALTA ESTO
-----------------------
RadioPV guarda la música en **dos bases SQLite distintas**:

  · `radiov.db`  — la biblioteca del recolector (la que gestiona el panel de administración, con
                   `radiov.blacklist`). Es la que tiene los ficheros y los estados de descarga.
  · `backend.db` — la que sirve la aplicación (listas, portadas, reproductor). Es la que ve el
                   usuario al abrir RadioPV.

El panel de administración borra en `radiov.db`. La pregunta que importa es si el borrado llega
TAMBIÉN a `backend.db`: si no llegara, el usuario borraría canciones en el panel y **seguirían
apareciendo en la aplicación**, sin fichero, o sea rotas. Una herramienta de limpieza que deja
fantasmas es peor que no tenerla.

Las pruebas anteriores usaban fichas creadas SÓLO en `radiov.db`, así que no podían detectar eso.
Esta crea la misma ficha falsa en LAS DOS bases (como una canción de verdad), para que el borrado
del panel se pueda comprobar en las dos.

Uso (dentro del contenedor del API):
    docker exec radiopv-api python /app/scripts/prueba_borrado_dos_bases.py
    docker exec radiopv-api python /app/scripts/prueba_borrado_dos_bases.py --comprobar
    docker exec radiopv-api python /app/scripts/prueba_borrado_dos_bases.py --borrar
"""
import os
import sqlite3
import sys
from pathlib import Path

DIR = os.environ.get("RADIOPV_DATA_DIR", "/app/data")
RAIZ_MUSICA = Path(os.environ.get("RADIOPV_BASE_MUSIC") or os.environ.get("MUSIC_ROOT") or "/music")
BASES = ("radiov.db", "backend.db")

TITULO = "PRUEBA DOS BASES"
REL = "_pruebas/prueba-dos-bases.mp3"
accion = sys.argv[1] if len(sys.argv) > 1 else "crear"


def abrir(nombre: str) -> sqlite3.Connection:
    con = sqlite3.connect(f"{DIR}/{nombre}")
    con.row_factory = sqlite3.Row
    return con


if accion == "--comprobar":
    print("=== ¿queda algo de la ficha de prueba? ===")
    for nombre in BASES:
        con = abrir(nombre)
        filas = con.execute("SELECT id, file_path, status FROM tracks WHERE title=?",
                            (TITULO,)).fetchall()
        print(f"   {nombre}: {len(filas)} fichas")
        for f in filas:
            print(f"      id={f['id']} status={f['status']} file_path={f['file_path']}")
        con.close()
    fichero = RAIZ_MUSICA / REL
    print(f"   fichero en el disco: {'SIGUE AHÍ (mal)' if fichero.exists() else 'borrado (bien)'}")
    raise SystemExit(0)

if accion == "--borrar":
    for nombre in BASES:
        con = abrir(nombre)
        for f in con.execute("SELECT id, file_path FROM tracks WHERE title=?", (TITULO,)).fetchall():
            con.execute("DELETE FROM tracks WHERE id=?", (f["id"],))
            print(f"borrada ficha {f['id']} de {nombre}")
        con.commit()
        con.close()
    (RAIZ_MUSICA / REL).unlink(missing_ok=True)
    print("fichero de prueba borrado")
    raise SystemExit(0)

# --- crear ---
carpeta = RAIZ_MUSICA / "_pruebas"
carpeta.mkdir(parents=True, exist_ok=True)
fichero = RAIZ_MUSICA / REL
fichero.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 4096)

for nombre in BASES:
    con = abrir(nombre)
    ya = con.execute("SELECT id FROM tracks WHERE title=?", (TITULO,)).fetchone()
    if ya:
        print(f"ya estaba en {nombre}: id={ya['id']}")
        con.close()
        continue
    # Las dos bases NO tienen las mismas columnas (`backend.db` no tiene `file_size`, por ejemplo),
    # así que se insertan sólo las que existen en cada una. La ficha es la misma canción en las dos.
    valores = {
        "title": TITULO, "artist": "PruebaDosBases", "album": "Pruebas", "year": 2026,
        "genre": "other", "language": "other", "bpm": 120.0, "energy": 0.5, "gain_db": -6.0,
        "duration": 180.0, "status": "descargada", "source": "prueba", "file_path": REL,
        "file_size": fichero.stat().st_size, "rank": 500000, "cover_url": "http://x/c.jpg",
    }
    existentes = {c[1] for c in con.execute("PRAGMA table_info(tracks)")}
    cols = [c for c in valores if c in existentes]
    con.execute(
        f"INSERT INTO tracks({', '.join(cols)}) VALUES({', '.join('?' * len(cols))})",
        tuple(valores[c] for c in cols))
    con.commit()
    print(f"creada en {nombre} ({len(cols)} columnas)")
    con.close()

print("\n(ahora borra desde el panel de administración y comprueba con --comprobar)")
