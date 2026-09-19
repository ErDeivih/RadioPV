"""¿Cómo va el repertorio que más le importa al usuario? Sesiones de DJ, mashups y remixes.

El usuario pidió prioridad para «sesiones, remixes, canción1 x canción2 y ese tipo de cosas», así
que hace falta poder mirar de un vistazo, sin abrir la aplicación:

  · cuántas canciones hay de cada tipo (con el MISMO clasificador que usa la puerta de calidad y
    las listas, `radiov.quality.clasificar`, para que no haya dos verdades);
  · cómo están las dos listas de sistema («Sesiones de DJ» y «Mashups y remixes»), incluido
    cuántas de sus canciones se pueden oír de verdad (fichero en disco) y cuántas están rotas;
  · qué ha entrado ÚLTIMAMENTE de cada tipo, que es la señal de que el recolector sigue trabajando;
  · qué hay pendiente: peticiones de canciones y semillas de YouTube esperando turno.

Uso (dentro del contenedor del API):
    docker exec radiopv-api python /app/scripts/estado_repertorio.py
    docker exec radiopv-api python /app/scripts/estado_repertorio.py --limite 20
"""


import argparse
import os
import sqlite3
import sys

# La consola de Windows usa cp1252: un título con emoji o acentos mata el guion justo al imprimir
# (pasó con «Tiktok Mashup 💗2025💗»). Todo lo que se imprime va en UTF-8 y, si algo no se puede
# representar, se sustituye en vez de reventar: un informe a medias es peor que uno con un carácter
# raro.
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

DB = os.environ.get("RADIOPV_DATA_DIR", "/app/data") + "/backend.db"

ap = argparse.ArgumentParser()
ap.add_argument("--limite", type=int, default=12, help="cuántas entradas recientes enseñar")
args = ap.parse_args()

sys.path.insert(0, "/app" if os.path.isdir("/app") else ".")
try:
    from radiov.quality import clasificar
except Exception as e:  # noqa: BLE001
    print(f"no se pudo cargar el clasificador: {e}")
    raise SystemExit(1)

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

# «Lo último» se mide por id: la tabla `tracks` no tiene `created_at` (se añadió después a otros
# sitios), y el id crece con cada importación, que es justo lo que se quiere ver aquí.
filas = con.execute(
    "SELECT id, title, artist, duration, status, file_path, is_remix FROM tracks"
    " WHERE status IN ('descargada', 'incompleta')").fetchall()

por_tipo = {"sesion": [], "mashup": [], "remix": [], "normal": []}
for f in filas:
    tipo = clasificar(f["title"] or "", f["artist"] or "", f["duration"]) or "normal"
    por_tipo.setdefault(tipo, []).append(f)

print(f"=== repertorio por tipo ({len(filas)} canciones descargadas o incompletas) ===")
for tipo in ("sesion", "mashup", "remix", "normal"):
    lista = por_tipo.get(tipo, [])
    con_fichero = sum(1 for f in lista if f["file_path"])
    largas = sum(1 for f in lista if (f["duration"] or 0) > 900)
    print(f"   {tipo:8s} {len(lista):5d}   con fichero: {con_fichero:5d}   de más de 15 min: {largas}")

print("\n=== lo ÚLTIMO que ha entrado de sesiones / mashups / remixes ===")
interesantes = sorted(
    por_tipo.get("sesion", []) + por_tipo.get("mashup", []) + por_tipo.get("remix", []),
    key=lambda f: f["id"], reverse=True)[:args.limite]
if not interesantes:
    print("   (nada todavía)")
for f in interesantes:
    tipo = clasificar(f["title"] or "", f["artist"] or "", f["duration"]) or "?"
    mins = int((f["duration"] or 0) // 60)
    print(f"   [{tipo:6s}] id={f['id']:<5} {mins:4d} min  {f['artist']} - {f['title']}"[:125])

print("\n=== las listas del sistema ===")
for p in con.execute(
        "SELECT id, name, type FROM playlists WHERE type='system' AND (name LIKE '%Sesion%'"
        " OR name LIKE '%Mashup%' OR name LIKE '%remix%') ORDER BY name").fetchall():
    total = con.execute("SELECT COUNT(*) FROM playlist_tracks WHERE playlist_id=?", (p["id"],)).fetchone()[0]
    rotas = con.execute(
        "SELECT COUNT(*) FROM playlist_tracks pt LEFT JOIN tracks t ON t.id=pt.track_id"
        " WHERE pt.playlist_id=? AND (t.id IS NULL OR t.file_path IS NULL OR t.status<>'descargada')",
        (p["id"],)).fetchone()[0]
    estado = "al día" if total and not rotas else ("VACÍA" if not total else f"{rotas} sin poder oírse")
    print(f"   «{p['name']}»: {total} canciones  ({estado})")

print("\n=== pendiente de descargar ===")
try:
    for est, n in con.execute("SELECT status, COUNT(*) n FROM requests GROUP BY status"):
        print(f"   peticiones {est}: {n}")
    for r in con.execute("SELECT text, status FROM requests WHERE status='pendiente'"
                         " ORDER BY id DESC LIMIT 6"):
        print(f"      · {r['text']}"[:110])
except sqlite3.OperationalError as e:
    print(f"   (sin tabla de peticiones: {e})")

con.close()
