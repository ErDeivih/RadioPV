"""Diagnóstico de una lista: qué filas tiene de verdad en `playlist_tracks`.

Existe por un hallazgo real: una lista recién creada por un usuario aparecía con MÁS canciones
de las que se le habían añadido (3 añadidas, 8 y hasta 16 en la pantalla). Hay que saber si el
problema está en los datos (filas de más) o en la consulta que las lee.

Uso (dentro del contenedor del API):
    docker exec radiopv-api python /app/scripts/diagnostico_lista.py            # listas recientes
    docker exec radiopv-api python /app/scripts/diagnostico_lista.py 81         # una lista concreta
"""

# La consola de Windows usa cp1252: un título con emoji o acentos mata el guion justo al imprimir
# (pasó con «Tiktok Mashup 💗2025💗»). Todo lo que se imprime va en UTF-8 y, si algo no se puede
# representar, se sustituye en vez de reventar: un informe a medias es peor que uno con un carácter
# raro.
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

import os
import sqlite3
import sys

DB = os.environ.get("RADIOPV_DATA_DIR", "/app/data") + "/backend.db"

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

objetivo = sys.argv[1] if len(sys.argv) > 1 else None

if objetivo == "--huerfanos":
    # Filas de playlist_tracks cuya lista YA NO EXISTE. Si hay muchas, el problema está claro:
    # al borrar una lista (o un usuario de prueba) se quedan sus filas, y como los ids de las
    # listas se reutilizan, la siguiente lista que se cree HEREDA esas canciones.
    n = con.execute("SELECT COUNT(*) FROM playlist_tracks WHERE playlist_id NOT IN"
                    " (SELECT id FROM playlists)").fetchone()[0]
    print(f"filas huérfanas (su lista no existe): {n}")
    print("\npor lista desaparecida:")
    for r in con.execute(
        "SELECT pt.playlist_id, COUNT(*) n FROM playlist_tracks pt WHERE pt.playlist_id NOT IN"
        " (SELECT id FROM playlists) GROUP BY pt.playlist_id ORDER BY n DESC LIMIT 20"
    ).fetchall():
        print(f"   lista {r['playlist_id']:<6} {r['n']} filas")
    print("\nvacías (listas sin ninguna canción):")
    for r in con.execute(
        "SELECT p.id, p.name, p.type, p.user_id FROM playlists p WHERE NOT EXISTS"
        " (SELECT 1 FROM playlist_tracks pt WHERE pt.playlist_id=p.id) ORDER BY p.id DESC LIMIT 10"
    ).fetchall():
        print(f"   id={r['id']:<6} type={str(r['type']):<8} user={r['user_id']} {r['name']!r}")
    con.close()
    raise SystemExit(0)

if objetivo:
    pid = int(objetivo)
    p = con.execute("SELECT * FROM playlists WHERE id=?", (pid,)).fetchone()
    if not p:
        print(f"no existe la lista {pid}")
        raise SystemExit(1)
    print(f"lista {pid}: {p['name']!r}  user_id={p['user_id']}  type={p['type']!r}")
    filas = con.execute(
        "SELECT pt.id AS fila, pt.track_id, pt.position, t.title, t.artist"
        " FROM playlist_tracks pt LEFT JOIN tracks t ON t.id = pt.track_id"
        " WHERE pt.playlist_id=? ORDER BY pt.position, pt.id",
        (pid,),
    ).fetchall()
    print(f"filas en playlist_tracks: {len(filas)}")
    for f in filas:
        print(f"   fila={f['fila']:<6} pos={f['position']:<4} track={f['track_id']:<7} "
              f"{(f['artist'] or '?')} - {(f['title'] or '?')}"[:120])
    ids = [f["track_id"] for f in filas]
    repetidos = {i: ids.count(i) for i in set(ids) if ids.count(i) > 1}
    print(f"canciones repetidas: {repetidos or 'ninguna'}")
    pos = [f["position"] for f in filas]
    print(f"posiciones repetidas: {sorted({x for x in pos if pos.count(x) > 1}) or 'ninguna'}")
else:
    print("=== últimas 12 listas creadas ===")
    for p in con.execute(
        "SELECT p.id, p.name, p.type, p.user_id, p.created_at,"
        " (SELECT COUNT(*) FROM playlist_tracks pt WHERE pt.playlist_id = p.id) AS n"
        " FROM playlists p ORDER BY p.id DESC LIMIT 12"
    ).fetchall():
        print(f"   id={p['id']:<6} n={p['n']:<5} type={str(p['type']):<8} user={p['user_id']} "
              f"{p['created_at']}  {p['name']!r}")

con.close()
