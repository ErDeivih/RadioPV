"""Crea dos canciones FALSAS para poder probar el borrado del panel sin tocar música de verdad.

Crea el fichero de audio (un mp3 vacío, da igual el contenido) dentro de la carpeta de música, en
una carpeta propia `_pruebas/`, y su ficha en la base. Así se puede comprobar que el borrado en
masa del panel quita la fila Y el fichero, sin arriesgar ni una canción real.

Uso (en el contenedor del API):
    docker exec radiopv-api python /app/scripts/prueba_borrado_crear.py
    docker exec radiopv-api python /app/scripts/prueba_borrado_crear.py --borrar
"""
import os
import sqlite3
import sys
from pathlib import Path

DIR_DATOS = os.environ.get("RADIOPV_DATA_DIR", "/app/data")
RAIZ_MUSICA = Path(os.environ.get("RADIOPV_BASE_MUSIC") or os.environ.get("MUSIC_ROOT") or "/music")
DB = DIR_DATOS + "/radiov.db"

TITULOS = ["PRUEBA BORRAR UNO", "PRUEBA BORRAR DOS"]
accion = sys.argv[1] if len(sys.argv) > 1 else "crear"

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

if accion == "--comprobar":
    # ¿Queda algo de las fichas de prueba? Ni en la base ni en el disco.
    print("=== comprobacion del borrado ===")
    for t in TITULOS:
        filas = con.execute("SELECT id, file_path FROM tracks WHERE title=?", (t,)).fetchall()
        print(f"   {t}: {len(filas)} fichas en la base")
        for r in filas:
            print(f"      id={r['id']} file_path={r['file_path']}")
    carpeta = RAIZ_MUSICA / "_pruebas"
    if carpeta.exists():
        restos = [p.name for p in carpeta.iterdir()]
        print(f"   ficheros que quedan en _pruebas: {restos or 'ninguno'}")
    else:
        print("   la carpeta _pruebas ya no existe")
    con.close()
    raise SystemExit(0)

if accion == "--borrar":
    for t in TITULOS:
        filas = con.execute("SELECT id, file_path FROM tracks WHERE title=?", (t,)).fetchall()
        for r in filas:
            if r["file_path"]:
                f = RAIZ_MUSICA / r["file_path"]
                if f.exists():
                    f.unlink()
            con.execute("DELETE FROM tracks WHERE id=?", (r["id"],))
            print(f"borrada ficha {r['id']} ({t})")
    con.commit()
    con.close()
    raise SystemExit(0)

# Crear
carpeta = RAIZ_MUSICA / "_pruebas"
carpeta.mkdir(parents=True, exist_ok=True)
for i, titulo in enumerate(TITULOS, 1):
    existe = con.execute("SELECT id FROM tracks WHERE title=?", (titulo,)).fetchone()
    if existe:
        print(f"ya estaba: {titulo} (id={existe['id']})")
        continue
    rel = f"_pruebas/prueba-borrar-{i}.mp3"
    fichero = RAIZ_MUSICA / rel
    # Un mp3 mínimo válido (silencio): sirve para que /stream no reviente si alguien lo abre.
    fichero.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 4096)
    con.execute(
        "INSERT INTO tracks(title, artist, album, year, genre, language, bpm, energy, gain_db,"
        " duration, status, source, file_path, file_size, rank, cover_url)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,'prueba',?,?,?,?)",
        (titulo, "PruebaBorrado", "Pruebas", 2026, "other", "other", 120.0, 0.5, -6.0,
         180.0, "descargada", rel, fichero.stat().st_size, 500000, "http://example.com/c.jpg"))
    print(f"creada: {titulo} -> {rel}")
con.commit()
con.close()
print("(estas fichas NO son música real: se crean sólo para probar el borrado)")
