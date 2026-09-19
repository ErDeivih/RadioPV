"""Busca en el catálogo las canciones que están en PORTUGUÉS (no deben estar).

POR QUÉ
-------
La norma del catálogo es: español (España y Latinoamérica), inglés y, de siempre, italiano y
francés. Portugués no. Pero entraba por la vía de YouTube: las semillas de sesiones de DJ tipo
«set dj» devuelven funk brasileño, y como la semilla declaraba `language: "es"`, en la ficha
quedaba español y nadie lo detectaba.

Ahora `radiov.quality.parece_portugues` lo detecta al entrar (y lo manda a cuarentena). Este script
es para lo que YA está dentro: las cuenta, y con `--cuarentena` las saca de circulación (les pone
estado `cuarentena`, que es reversible y se revisa en el panel de administración).

Uso (dentro del contenedor del API):
    docker exec radiopv-api python /app/scripts/marcar_portugues.py
    docker exec radiopv-api python /app/scripts/marcar_portugues.py --cuarentena
"""
import argparse
import os
import sqlite3
import sys

DB = os.environ.get("RADIOPV_DATA_DIR", "/app/data") + "/backend.db"

ap = argparse.ArgumentParser()
ap.add_argument("--cuarentena", action="store_true",
                help="saca de circulación las encontradas (estado cuarentena)")
ap.add_argument("--limite", type=int, default=40, help="cuántas enseñar")
args = ap.parse_args()

sys.path.insert(0, "/app" if os.path.isdir("/app") else ".")
from radiov.quality import parece_portugues  # noqa: E402

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

filas = con.execute(
    "SELECT id, title, artist, status, language, file_path, duration FROM tracks"
    " WHERE status IN ('descargada', 'incompleta', 'cuarentena')").fetchall()

sospechosas = [f for f in filas if parece_portugues(f["title"] or "", f["artist"] or "")]
publicadas = [f for f in sospechosas if f["status"] in ("descargada", "incompleta")]

print(f"=== canciones en portugués: {len(sospechosas)} de {len(filas)} revisadas ===")
print(f"    de ellas, PUBLICADAS (se pueden oír en la app): {len(publicadas)}")

print("\n=== por estado ===")
for est in sorted({f["status"] for f in sospechosas}):
    n = sum(1 for f in sospechosas if f["status"] == est)
    print(f"   {est}: {n}")

print("\n=== por idioma que tienen en la ficha (así se ve el fallo) ===")
for f in sorted({(f["language"] or "(vacío)") for f in sospechosas}):
    n = sum(1 for x in sospechosas if (x["language"] or "(vacío)") == f)
    print(f"   {f}: {n}")

print(f"\n=== muestra (hasta {args.limite}) ===")
for f in sospechosas[:args.limite]:
    print(f"   id={f['id']:<6} [{f['status']:<10}] lang={str(f['language']):<6} "
          f"{f['artist']} - {f['title']}"[:125])

if args.cuarentena:
    ids = [f["id"] for f in publicadas]
    if not ids:
        print("\n[OK] no hay nada publicado que sacar")
    else:
        q = ",".join("?" * len(ids))
        con.execute(f"UPDATE tracks SET status='cuarentena' WHERE id IN ({q})", ids)
        con.commit()
        print(f"\n[OK] {len(ids)} canciones pasadas a cuarentena (se pueden borrar desde el panel)")
else:
    print("\n[..] sólo información: añade --cuarentena para sacarlas de circulación")

con.close()
