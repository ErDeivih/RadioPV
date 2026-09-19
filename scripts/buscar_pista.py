"""Busca una canción por texto y enseña su ficha COMPLETA en las DOS bases.

POR QUÉ
-------
Cuando algo no cuadra («la pedí y no aparece», «dice que se publicó y no suena»), hace falta ver de
un tirón: si está en la base del recolector, si está en la de la aplicación, con qué estado, si su
fichero existe y qué le falta de metadatos. Hacerlo a mano son cinco consultas y dos bases, y es
justo cuando uno está con prisa.

Uso (dentro del contenedor del API, o en el PC con RADIOPV_DATA_DIR apuntando a `_pc_data`):
    docker exec radiopv-api python /app/scripts/buscar_pista.py "reggaeton viejo"
    docker exec radiopv-api python /app/scripts/buscar_pista.py "tiktok mashup"
"""
import os
import sqlite3
import sys
from pathlib import Path

for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

DIR = os.environ.get("RADIOPV_DATA_DIR", "/app/data")
RAIZ = Path(os.environ.get("RADIOPV_BASE_MUSIC") or os.environ.get("MUSIC_ROOT") or "/music")
BUSCAR = sys.argv[1] if len(sys.argv) > 1 else ""
if not BUSCAR:
    print("uso: buscar_pista.py \"texto a buscar\"")
    raise SystemExit(1)

CAMPOS = ("status", "language", "year", "genre", "bpm", "energy", "gain_db", "duration",
          "cover_url", "cover_path", "youtube_id", "deezer_id", "source")

for base in ("radiov.db", "backend.db"):
    ruta = f"{DIR}/{base}"
    if not os.path.exists(ruta):
        print(f"\n=== {base}: no existe")
        continue
    con = sqlite3.connect(ruta)
    con.row_factory = sqlite3.Row
    disponibles = {c[1] for c in con.execute("PRAGMA table_info(tracks)")}
    cols = [c for c in CAMPOS if c in disponibles]
    filas = con.execute(
        f"SELECT id, title, artist, file_path, {', '.join(cols)} FROM tracks"
        " WHERE title LIKE ? OR artist LIKE ? ORDER BY id DESC LIMIT 15",
        (f"%{BUSCAR}%", f"%{BUSCAR}%")).fetchall()

    print(f"\n=== {base}: {len(filas)} coincidencias con «{BUSCAR}» ===")
    for f in filas:
        fp = f["file_path"] or ""
        existe = (RAIZ / fp).exists() if fp else False
        print(f"\n   id={f['id']}  {f['artist']} - {f['title']}"[:120])
        print(f"      estado={f['status']}  fichero={'SÍ' if existe else 'NO'}"
              + ("" if not fp else f"  ({fp})" if len(fp) < 90 else f"  (…{fp[-70:]})"))
        faltan = [c for c in ("year", "genre", "language", "bpm", "energy", "gain_db",
                              "duration", "cover_url") if c in disponibles and not f[c]]
        if faltan:
            print(f"      LE FALTA: {', '.join(faltan)}  ← con esto no se publica")
        if f["youtube_id"] if "youtube_id" in disponibles else False:
            print(f"      youtube_id={f['youtube_id']}")
    con.close()
