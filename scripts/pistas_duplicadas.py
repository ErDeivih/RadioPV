"""Canciones repetidas: la misma canción con dos fichas (y a veces con un fichero que ya no está).

POR QUÉ
-------
Salió investigando las transferencias del PC al servidor: la comprobación decía que 4 canciones
enviadas «no tenían fichero» en el servidor, y al mirarlas una a una el fichero SÍ estaba. El motivo
es que hay **dos fichas para el mismo vídeo de YouTube**, y la que se queda con el `youtube_id` es
justo la que apunta a un fichero que ya no existe. Lo mismo explica parte de los «contenido
distinto»: son copias distintas de la misma canción.

Esto importa para la limpieza: cada ficha de más ocupa sitio en la biblioteca, aparece dos veces en
las búsquedas y hace que las comprobaciones mientan.

Uso (dentro del contenedor del API):
    docker exec radiopv-api python /app/scripts/pistas_duplicadas.py
    docker exec radiopv-api python /app/scripts/pistas_duplicadas.py --limite 30
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path

DIR = os.environ.get("RADIOPV_DATA_DIR", "/app/data")
RAIZ = Path(os.environ.get("RADIOPV_BASE_MUSIC") or os.environ.get("MUSIC_ROOT") or "/music")

ap = argparse.ArgumentParser()
ap.add_argument("--limite", type=int, default=15)
ap.add_argument("--base", default="backend.db", choices=("backend.db", "radiov.db"))
args = ap.parse_args()

con = sqlite3.connect(f"{DIR}/{args.base}")
con.row_factory = sqlite3.Row

print(f"=== {args.base}: fichas repetidas ===")

# OJO CON EL ESTADO: una ficha 'retirada' es una copia de más que YA está fuera de la aplicación (la
# marcó `unificar_duplicadas.py`). Sigue en la base a propósito —es reversible— pero no molesta a
# nadie. Lo que hay que mirar es cuántas copias se pueden VER, que es lo que nota el usuario: si aquí
# salieran todas, parecería que no se ha arreglado nada.
ACTIVAS = ("descargada", "incompleta", "cuarentena", "pendiente", "perdida")

# 1) Mismo vídeo de YouTube en varias fichas (es el caso que rompía las comprobaciones)
print("\n--- por id de YouTube (varias fichas, mismo vídeo) ---")
grupos = con.execute(
    "SELECT youtube_id, COUNT(*) n FROM tracks WHERE youtube_id IS NOT NULL AND youtube_id <> ''"
    " GROUP BY youtube_id HAVING n > 1 ORDER BY n DESC").fetchall()
visibles = 0
for g in grupos:
    filas = con.execute(
        "SELECT id, title, artist, status, file_path FROM tracks WHERE youtube_id=?",
        (g["youtube_id"],)).fetchall()
    activas = [f for f in filas if (f["status"] or "") in ACTIVAS]
    if len(activas) > 1:
        visibles += 1
print(f"   vídeos con más de una ficha: {len(grupos)}")
print(f"   de esos, con MÁS DE UNA VISIBLE en la aplicación: {visibles}"
      f"{'  ← esto es lo que hay que arreglar' if visibles else '  (bien: las de más están retiradas)'}")
sin_fichero = 0
for g in grupos[:args.limite]:
    filas = con.execute(
        "SELECT id, title, artist, status, file_path FROM tracks WHERE youtube_id=?",
        (g["youtube_id"],)).fetchall()
    estados = []
    for f in filas:
        existe = bool(f["file_path"]) and (RAIZ / f["file_path"]).exists()
        if not existe and (f["status"] or "") in ACTIVAS:
            sin_fichero += 1
        estados.append(f"id={f['id']}{'✓' if existe else '✗'}")
    print(f"   {g['youtube_id']:<14} {g['n']} fichas ({', '.join(estados)})")
    for f in filas:
        print(f"        id={f['id']:<6} [{str(f['status'])[:10]:<10}] {f['artist']} - {f['title']}"[:112])
if sin_fichero:
    print(f"   [!] {sin_fichero} fichas VISIBLES apuntan a un fichero que NO existe")

# 2) Mismo artista y título en varias fichas
print("\n--- por artista y título ---")
grupos2 = con.execute(
    "SELECT artist, title, COUNT(*) n FROM tracks GROUP BY LOWER(artist), LOWER(title)"
    " HAVING n > 1 ORDER BY n DESC LIMIT ?", (args.limite,)).fetchall()
totales = con.execute(
    "SELECT COUNT(*) FROM (SELECT 1 FROM tracks GROUP BY LOWER(artist), LOWER(title)"
    " HAVING COUNT(*) > 1)").fetchone()[0]
print(f"   parejas artista+título repetidas: {totales}")
for g in grupos2:
    filas = con.execute(
        "SELECT id, status, file_path FROM tracks WHERE LOWER(artist)=LOWER(?)"
        " AND LOWER(title)=LOWER(?)", (g["artist"], g["title"])).fetchall()
    existe = sum(1 for f in filas if f["file_path"] and (RAIZ / f["file_path"]).exists())
    print(f"   {g['n']} fichas · {existe} con fichero · {g['artist']} - {g['title']}"[:112])

# 3) Fichas que apuntan a un fichero que no está (fantasmas)
print("\n--- fichas cuyo fichero no existe (lo que ve el usuario como «no suena») ---")
todas = con.execute("SELECT id, title, artist, status, file_path FROM tracks"
                    " WHERE file_path IS NOT NULL AND file_path <> ''").fetchall()
fantasmas = [f for f in todas if not (RAIZ / f["file_path"]).exists()]
print(f"   {len(fantasmas)} de {len(todas)} fichas")
for f in fantasmas[:args.limite]:
    print(f"      id={f['id']:<6} [{str(f['status'])[:10]:<10}] {f['artist']} - {f['title']}"[:110])
    print(f"          {f['file_path']}"[:110])

con.close()
