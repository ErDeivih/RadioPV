"""Canciones publicadas cuyo fichero NO está en el disco (aparecen en la app pero no suenan).

POR QUÉ ES EL FALLO A VIGILAR
-----------------------------
Con el recolector en el PC la ficha y el fichero llegan por caminos distintos: la ficha por la API,
el audio por `tar`+`ssh`. Si algo falla en medio, la canción queda en la biblioteca **sin su
fichero**: se ve en la aplicación, se le da al play y no suena (el reproductor la salta). Es
exactamente el tipo de fallo que el usuario nota y no sabe explicar.

Comprueba **las dos bases**: `backend.db` (la que sirve la aplicación: lo que el usuario ve) y
`radiov.db` (la biblioteca del recolector, que es la que gestiona el panel).

Uso (dentro del contenedor del API):
    docker exec radiopv-api python /app/scripts/publicadas_sin_fichero.py
    docker exec radiopv-api python /app/scripts/publicadas_sin_fichero.py --marcar
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path

DIR = os.environ.get("RADIOPV_DATA_DIR", "/app/data")
RAIZ = Path(os.environ.get("RADIOPV_BASE_MUSIC") or os.environ.get("MUSIC_ROOT") or "/music")

ap = argparse.ArgumentParser()
ap.add_argument("--marcar", action="store_true",
                help="marca como 'perdida' las publicadas sin fichero (la app deja de ofrecerlas)")
ap.add_argument("--limite", type=int, default=15)
args = ap.parse_args()

for base in ("backend.db", "radiov.db"):
    ruta = f"{DIR}/{base}"
    if not os.path.exists(ruta):
        continue
    con = sqlite3.connect(ruta)
    con.row_factory = sqlite3.Row

    filas = con.execute(
        "SELECT id, title, artist, file_path, duration, status FROM tracks"
        " WHERE file_path IS NOT NULL AND file_path <> ''").fetchall()
    sin_fichero = [f for f in filas if not (RAIZ / f["file_path"]).exists()]
    publicadas = [f for f in sin_fichero if (f["status"] or "") == "descargada"]

    print(f"\n=== {base} ===")
    print(f"   fichas con ruta: {len(filas)} · SIN fichero: {len(sin_fichero)}"
          f" · de ellas PUBLICADAS (se ven en la app): {len(publicadas)}")
    por_estado: dict[str, int] = {}
    for f in sin_fichero:
        por_estado[f["status"] or "(vacío)"] = por_estado.get(f["status"] or "(vacío)", 0) + 1
    if por_estado:
        print(f"   por estado: {por_estado}")

    for f in sin_fichero[:args.limite]:
        print(f"      id={f['id']:<6} [{str(f['status'])[:10]:<10}] {f['artist']} - {f['title']}"[:112])

    if args.marcar and publicadas:
        ids = [f["id"] for f in publicadas]
        q = ",".join("?" * len(ids))
        con.execute(f"UPDATE tracks SET status='perdida' WHERE id IN ({q})", ids)
        con.commit()
        print(f"   [OK] {len(ids)} marcadas como 'perdida' (dejan de ofrecerse y se pueden volver a bajar)")
    elif publicadas:
        print("   [..] añade --marcar para sacarlas de la aplicación (es reversible: se vuelven a bajar)")

    con.close()

print("\nPara volver a bajarlas, el agente del recolector las recupera solo (`recuperar_perdidas`).")
