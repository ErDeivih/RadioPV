#!/usr/bin/env python
"""Publica AHORA lo que ya está completo, sin esperar al worker (que lo hace cada 30 minutos).

Para qué: cuando se arregla algo de los metadatos (o se rellena la carátula que faltaba), las
canciones siguen en 'incompleta' hasta que le toca al worker. Esto lo hace al momento y dice qué ha
pasado, que es lo que hace falta para comprobar un arreglo en el sitio en vez de esperar media hora.

Hace las dos cosas que desbloquean la publicación:
  1. pone la carátula del propio vídeo de YouTube a lo que no tiene ninguna (es determinista y no
     gasta red) y la baja al disco, que es lo que sirve la aplicación;
  2. republica: pasa a 'descargada' lo que ya tiene todos los metadatos obligatorios.

Uso (en el PC con su carpeta de datos, o dentro del contenedor del API):
    RADIOPV_DATA_DIR=F:/EspacioCodigo/RadioPV/_pc_data python scripts/republicar_ahora.py
    docker exec radiopv-api python /app/scripts/republicar_ahora.py
"""
import os
import sys

for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

RAIZ = "/app" if os.path.isdir("/app") else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from radiov import catalog as CAT  # noqa: E402
from radiov import db as RDB       # noqa: E402


def _incompletas() -> int:
    con = RDB.get_conn()
    try:
        return con.execute("SELECT COUNT(*) FROM tracks WHERE status='incompleta'").fetchone()[0]
    finally:
        con.close()


antes = _incompletas()
print(f"incompletas antes: {antes}")

puestas = CAT.caratulas_desde_youtube(limit=500)
if puestas:
    bajadas = CAT.fetch_media(limit=max(50, puestas))
    print(f"carátulas puestas desde el vídeo de YouTube: {puestas} (bajadas al disco: {bajadas})")

publicadas = CAT.republicar_completas(limit=2000)
print(f"publicadas ahora: {publicadas}")

despues = _incompletas()
print(f"incompletas después: {despues}")

if despues:
    # Lo que sigue esperando y por qué: sin esto el «quedan 13» no dice nada útil.
    con = RDB.get_conn()
    try:
        filas = con.execute("SELECT id, artist, title, year, cover_url, cover_path, gain_db "
                            "FROM tracks WHERE status='incompleta' ORDER BY id LIMIT 20").fetchall()
    finally:
        con.close()
    print("\nlas que siguen esperando:")
    for f in filas:
        faltan = [c for c, v in (("year", f["year"]), ("cover_url", f["cover_url"] or f["cover_path"]),
                                 ("gain_db", f["gain_db"])) if not v]
        print(f"   id={f['id']:<6} le falta: {','.join(faltan) or 'NADA'}   "
              f"{(f['artist'] or '')[:22]} - {(f['title'] or '')[:44]}")
