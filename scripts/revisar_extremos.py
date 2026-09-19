"""Revisa los EXTREMOS de las canciones: intros habladas, diálogos, colas y silencios.

QUÉ BUSCA
---------
Los vídeos de YouTube (sobre todo los «oficiales») traen cosas que no son la canción: la intro
hablada del presentador, un diálogo, un anuncio, unos segundos de silencio, la despedida del final.
En la aplicación eso se nota mucho: le das a la canción y los primeros 20 segundos es alguien
hablando.

Lo mide `radiov/extremos.py`: mira el SONIDO (no transcribe nada) y saca **en qué segundo empieza la
música de verdad** y en cuál acaba. Con eso se distingue:
  · **silencio** al principio o al final → se puede recortar sin más;
  · **sonido que no es la canción** (voz, ambiente) → lo que se busca es OTRA VERSIÓN.

DÓNDE SE EJECUTA
----------------
En el PC, que es donde está el audio (el servidor es un portátil de 4 GB y no tiene por qué analizar
6.000 ficheros). Se guarda el resultado en la base del PC; el recolector lo manda al servidor con la
ficha, y allí se ve en el panel de administración.

Uso (en el PC):
    .venv\\Scripts\\python.exe scripts\\revisar_extremos.py --limite 40
    .venv\\Scripts\\python.exe scripts\\revisar_extremos.py --limite 40 --buscar-otra
    .venv\\Scripts\\python.exe scripts\\revisar_extremos.py --solo-youtube --limite 100
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROYECTO))

for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

ap = argparse.ArgumentParser()
ap.add_argument("--limite", type=int, default=40, help="cuántas canciones revisar en esta pasada")
ap.add_argument("--solo-youtube", action="store_true",
                help="sólo las que se bajaron de YouTube (son las que traen intros)")
ap.add_argument("--buscar-otra", action="store_true",
                help="para las que tengan voz/diálogo: buscar otra versión y cambiarla")
ap.add_argument("--minutos", type=float, default=0, help="parar pasados estos minutos (0 = sin tope)")
ap.add_argument("--listar", action="store_true", help="sólo enseñar lo ya revisado, no analizar")
args = ap.parse_args()

os.environ.setdefault("RADIOPV_DATA_DIR", str(RAIZ_PROYECTO / "_pc_data"))
DIR_DATOS = Path(os.environ["RADIOPV_DATA_DIR"])

from radiov import catalog as C  # noqa: E402
from radiov import db as rdb  # noqa: E402
from radiov.extremos import analizar  # noqa: E402
from radiov.config import resolve_music  # noqa: E402

# Crea la base si no está y, sobre todo, **añade las columnas nuevas** a una base que ya existía
# (intros/cola). Sin esto, la primera vez el guion falla con «no such column: extremos_revisado».
rdb.init_db()

con = rdb.get_conn()
con.row_factory = sqlite3.Row

if args.listar:
    filas = con.execute(
        "SELECT id, artist, title, intro_seg, cola_seg, version_limpia FROM tracks"
        " WHERE extremos_revisado IS NOT NULL AND (COALESCE(intro_seg,0) > 0"
        " OR COALESCE(cola_seg,0) > 0) ORDER BY COALESCE(intro_seg,0) DESC LIMIT ?",
        (args.limite,)).fetchall()
    print(f"canciones con algo en los extremos: {len(filas)} (de las ya revisadas)")
    for f in filas:
        marca = " [versión limpia puesta]" if f["version_limpia"] else ""
        print(f"   id={f['id']:<6} intro={f['intro_seg'] or 0:>5}s cola={f['cola_seg'] or 0:>5}s "
              f"{f['artist']} - {f['title']}"[:110] + marca)
    con.close()
    raise SystemExit(0)

print(f"por revisar: hasta {args.limite}")
t0 = time.time()
revisadas, con_algo, cambiadas = C.revisar_extremos_lote(
    limit=args.limite, buscar_otra=(5 if args.buscar_otra else 0), log=print)
print(f"\nrevisadas: {revisadas} · con algo en los extremos: {con_algo} · "
      f"cambiadas por otra versión: {cambiadas} · en {(time.time()-t0)/60:.1f} min")
if not args.buscar_otra and con_algo:
    print("\n[i] para intentar cambiarlas por otra versión: añade --buscar-otra")
