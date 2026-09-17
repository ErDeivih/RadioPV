"""¿Cuántas canciones de la aplicación NO se pueden sonar?

Es la medición que dice si las playlists se siguen saltando canciones: la aplicación sólo publica
las que están en estado 'descargada', y de esas hay que ver cuántas tienen fichero de verdad en el
disco. Cada una que falte es una canción que el reproductor intentará, recibirá un 410 y saltará.

Se ejecuta DENTRO del contenedor del API (es donde están la base y el disco de música):

    scp scripts/estado_musica.py david@servidor.local:/tmp/e.py
    ssh david@servidor.local "docker cp /tmp/e.py radiopv-api:/tmp/e.py && \
        docker exec radiopv-api python3 /tmp/e.py"

Sin argumentos informa del catálogo entero; con --playlist N revisa además los primeros temas de
una lista concreta (que es exactamente lo que ocurre al pulsar su botón de reproducir).
"""
from __future__ import annotations

import argparse
import sqlite3
import sys

sys.path.insert(0, "/app")

from app.paths import resolve_music  # noqa: E402

DB = "/app/data/backend.db"


def _tiene_fichero(fp: str | None) -> bool:
    if not fp:
        return False
    try:
        return resolve_music(fp).exists()
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--playlist", type=int, default=None, help="revisar una lista concreta")
    ap.add_argument("--muestra", type=int, default=0, help="revisar sólo N canciones (rápido)")
    args = ap.parse_args()

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    por_estado = dict(con.execute("SELECT status, COUNT(*) FROM tracks GROUP BY status").fetchall())
    print("canciones por estado:")
    for estado, n in sorted(por_estado.items(), key=lambda x: -x[1]):
        print(f"   {estado:12s} {n:6d}")

    publicadas = con.execute(
        "SELECT COUNT(*) FROM tracks WHERE status='descargada'").fetchone()[0]
    print(f"\npublicadas (las que ve la aplicación): {publicadas}")

    limite = f" LIMIT {args.muestra}" if args.muestra else ""
    filas = con.execute(
        f"SELECT id, artist, title, file_path FROM tracks WHERE status='descargada'{limite}").fetchall()
    con_fichero = sum(1 for f in filas if _tiene_fichero(f["file_path"]))
    sin = [f for f in filas if not _tiene_fichero(f["file_path"])]

    print(f"revisadas                             : {len(filas)}")
    print(f"   con fichero (se pueden sonar)      : {con_fichero}")
    print(f"   SIN fichero (el reproductor salta)  : {len(sin)}")
    if filas:
        pct = 100.0 * con_fichero / len(filas)
        print(f"   => se puede escuchar el {pct:.1f} %")

    if sin:
        print("\nprimeras que faltan:")
        for f in sin[:8]:
            print(f"   {f['id']:6d}  {f['artist']} - {f['title']}")

    if args.playlist:
        print(f"\n=== lista {args.playlist}: lo que pasa al pulsar reproducir ===")
        temas = con.execute(
            "SELECT t.id, t.artist, t.title, t.file_path FROM playlist_tracks pt "
            "JOIN tracks t ON t.id = pt.track_id WHERE pt.playlist_id=? "
            "ORDER BY pt.position", (args.playlist,)).fetchall()
        print(f"canciones en la lista: {len(temas)}")
        saltos = 0
        for i, t in enumerate(temas):
            hay = _tiene_fichero(t["file_path"])
            if not hay:
                saltos += 1
            # Se enseñan las seis primeras (para ver por dónde empieza) y todas las que fallan.
            if i < 6 or not hay:
                marca = "suena" if hay else "SE SALTA"
                print(f"   [{i + 1:3d}] {marca:9s} {t['artist']} - {t['title']}")
        print(f"\n=> si se pulsa reproducir, se saltarían {saltos} de las {len(temas)} canciones")

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
