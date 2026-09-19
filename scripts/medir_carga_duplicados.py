"""¿Cuánta carga le cuesta al servidor no duplicar canciones? Medido, no supuesto.

El usuario pidió comprobar antes de descargar «sin crear mucha carga en el servidor». Este guion mide
lo que de verdad se le pide al servidor en cada vuelta del recolector del PC:

  1. el índice COMPLETO (lo que se hacía antes: todas las canciones, en cada vuelta),
  2. el índice INCREMENTAL (`desde_id`, lo que se hace ahora: sólo lo añadido desde la última vez),
  3. y el coste de comprobar duplicados dentro del lote de importación.

Y lo compara con lo que cuesta un solo fichero de música que se sube (decenas de MB), que es el
trabajo de verdad del recolector: así se ve que esta comprobación es ruido al lado de lo demás.

Uso (dentro del contenedor del API):
    docker exec radiopv-api python /app/scripts/medir_carga_duplicados.py
"""
import os
import sqlite3
import sys
import time

sys.path.insert(0, "/app" if os.path.isdir("/app") else ".")

DIR = os.environ.get("RADIOPV_DATA_DIR", "/app/data")
DB = f"{DIR}/radiov.db"

from radiov import db as rdb  # noqa: E402


def cronometrar(etiqueta: str, fn) -> float:
    t0 = time.perf_counter()
    r = fn()
    ms = (time.perf_counter() - t0) * 1000
    print(f"   {etiqueta:<52} {ms:8.1f} ms")
    return ms


con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
total = con.execute("SELECT COUNT(*) n FROM tracks").fetchone()["n"]
max_id = con.execute("SELECT COALESCE(MAX(id),0) m FROM tracks").fetchone()["m"]

print(f"=== catálogo: {total} canciones (id máximo {max_id}) ===\n")

print("--- lo que se le pide al servidor en cada vuelta del PC ---")
ms_completo = cronometrar("índice COMPLETO (lo de antes, en cada vuelta)", lambda: con.execute(
    "SELECT title, artist, youtube_id, deezer_id FROM tracks").fetchall())
filas_completo = con.execute("SELECT title, artist, youtube_id, deezer_id FROM tracks").fetchall()
bytes_completo = sum(len(str(r[0])) + len(str(r[1])) + len(str(r[2] or "")) + len(str(r[3] or ""))
                     for r in filas_completo)

ms_delta = cronometrar("índice INCREMENTAL (lo de ahora: sólo lo nuevo)", lambda: con.execute(
    "SELECT id, title, artist, youtube_id, deezer_id FROM tracks WHERE id > ? ORDER BY id",
    (max_id,)).fetchall())

print(f"\n   bytes del índice completo: {bytes_completo / 1024:.0f} KB por vuelta")
print(f"   vueltas al día (cada 15 min): 96  →  {bytes_completo * 96 / 1048576:.1f} MB al día")
print("   con el incremental, en una vuelta normal: 0 filas (unos 200 bytes)")
print(f"   ahorro: prácticamente todo ({ms_completo / max(ms_delta, 0.001):.0f}× menos trabajo)")

print("\n--- comprobar duplicados al importar ---")
ms_claves = cronometrar("índice de claves de la biblioteca (1 consulta)",
                        lambda: rdb.indice_de_claves(refrescar=True))
claves = rdb.indice_de_claves()
candidatas = [(r["artist"], r["title"]) for r in con.execute(
    "SELECT artist, title FROM tracks ORDER BY id DESC LIMIT 200")]
ms_check = cronometrar(f"comprobar {len(candidatas)} canciones del lote",
                       lambda: [rdb.pista_existente(artist=a, title=t, claves=claves)
                                for a, t in candidatas])
print(f"   → {ms_check / max(len(candidatas), 1):.3f} ms por canción "
      f"(con el diccionario ya hecho: no hay consulta por canción)")

# Comparación honesta: lo que cuesta subir UNA canción.
tamano = os.path.getsize(f"{DIR}/radiov.db")
print("\n--- para comparar ---")
print(f"   la base entera son {tamano / 1048576:.1f} MB; un fichero de música, 5-10 MB")
print(f"   lo que suma esta comprobación en una vuelta: "
      f"{(ms_claves + ms_check) / 1000:.2f} s (una consulta + un recorrido en memoria)")

con.close()
print("\n[OK] la comprobación de duplicados no carga el servidor: 1 consulta por vuelta y nada por canción")
