"""Mira una pista concreta: ficha, fichero y /stream. Para el caso raro que salio en la prueba."""

# La consola de Windows usa cp1252: un título con emoji o acentos mata el guion justo al imprimir
# (pasó con «Tiktok Mashup 💗2025💗»). Todo lo que se imprime va en UTF-8 y, si algo no se puede
# representar, se sustituye en vez de reventar: un informe a medias es peor que uno con un carácter
# raro.
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

import json
import os
import sqlite3
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, "/app")
from radiov.config import BASE_MUSIC, resolve_music  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app import models  # noqa: E402
from app.security import create_access_token  # noqa: E402

BUSCAR = sys.argv[1] if len(sys.argv) > 1 else "Omar Courtz"
POR_ARTISTA = True

DB = os.environ.get("RADIOPV_DATA_DIR", "/app/data") + "/radiov.db"
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
# Se busca por artista por defecto: los titulos de este catalogo llevan acentos, y al pasar el
# guion por PowerShell los acentos se estropean y la busqueda no encuentra nada.
columna = "artist" if POR_ARTISTA else "title"
filas = con.execute(f"SELECT id, title, artist, status, file_path, duration, file_size "
                    f"FROM tracks WHERE {columna} LIKE ?", (f"%{BUSCAR}%",)).fetchall()
con.close()

print(f"pistas que coinciden con «{BUSCAR}»: {len(filas)}")
for r in filas:
    print(f"\n  id={r['id']} [{r['status']}] {r['artist']} - {r['title']}")
    print(f"    file_path={r['file_path']}")
    print(f"    duration={r['duration']} file_size={r['file_size']}")
    if r["file_path"]:
        ruta = Path(resolve_music(r["file_path"]))
        print(f"    resuelto={ruta}")
        print(f"    existe={ruta.exists()}")
        if ruta.exists():
            print(f"    tamaño real={ruta.stat().st_size} bytes")
        else:
            carpeta = ruta.parent
            print(f"    ¿existe la carpeta? {carpeta.exists()}")
            if carpeta.exists():
                print(f"    contenido: {[p.name for p in carpeta.iterdir()][:6]}")

# Y una prueba de /stream de verdad
if filas:
    db = SessionLocal()
    u = db.query(models.User).filter(models.User.is_admin.is_(True)).first()
    token = create_access_token(u.id, u.token_version)
    db.close()
    req = urllib.request.Request("http://127.0.0.1:8000/auth/stream-token", data=b"",
                                 headers={"Authorization": "Bearer " + token}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        st = json.loads(r.read().decode())["token"]
    for r in filas[:3]:
        url = f"http://127.0.0.1:8000/stream/{r['id']}?t={st}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"Range": "bytes=0-255"}), timeout=30) as resp:
                print(f"\n  /stream/{r['id']}: HTTP {resp.status}, {len(resp.read())} bytes")
        except Exception as e:  # noqa: BLE001
            print(f"\n  /stream/{r['id']}: FALLO {str(e)[:80]}")
