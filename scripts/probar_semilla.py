#!/usr/bin/env python
"""Prueba UNA semilla concreta y dice qué ha traído, sin esperar a que le toque al recolector.

PARA QUÉ
--------
Cuando se añaden semillas nuevas (un género, una escena, unos artistas) no hay forma de saber si
sirven hasta que el recolector les da el turno, y con 178 semillas eso puede ser muchas horas. Esto
lanza una semilla suelta por el MISMO camino que usa el recolector (`process_youtube_seed`: búsqueda,
filtros de calidad y de portugués, deduplicación, ficha) y enseña el resultado.

Es la herramienta con la que se descubrió que las semillas de tech house no bajaban nada: primero
porque cada semilla sólo traía una canción, y después porque el recolector siempre empezaba por las
primeras de la lista y nunca llegaba a las del final.

Uso (en el PC, con su carpeta de datos):
    .venv\\Scripts\\python.exe scripts\\probar_semilla.py "Toolroom tech house"
    .venv\\Scripts\\python.exe scripts\\probar_semilla.py --lista          # lista las semillas
    .venv\\Scripts\\python.exe scripts\\probar_semilla.py "CamelPhat set" --cuantas 3
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

from radiov.config import load_settings, DATA_DIR  # noqa: E402


def semillas() -> list[dict]:
    return load_settings().get("agent_seeds", [])


def main() -> int:
    ap = argparse.ArgumentParser(description="Prueba una semilla del recolector y enseña qué trae.")
    ap.add_argument("texto", nargs="?", help="trozo del texto de la semilla")
    ap.add_argument("--cuantas", type=int, default=2, help="cuántas canciones bajar como máximo")
    ap.add_argument("--lista", action="store_true", help="enseñar las semillas y salir")
    args = ap.parse_args()

    todas = semillas()
    if args.lista or not args.texto:
        print(f"semillas: {len(todas)}")
        for i, s in enumerate(todas, 1):
            print(f"  {i:>3}. [{s.get('genre', '?'):9}] {s.get('query', '')}")
        return 0

    objetivo = args.texto.lower()
    coincide = [s for s in todas if objetivo in (s.get("query") or "").lower()]
    if not coincide:
        sys.exit(f"ninguna semilla contiene «{args.texto}» (mira --lista)")
    seed = coincide[0]
    print(f"semilla: «{seed['query']}» · género {seed.get('genre')} · idioma {seed.get('language')}")

    # El candado del recolector: si hay una vuelta en marcha, no se lanza nada (dos procesos
    # escribiendo en la misma base y bajando lo mismo es justo lo que evita ese candado).
    datos = Path(os.environ.get("RADIOPV_DATA_DIR") or DATA_DIR)
    candado = datos / "recolector_pc.lock"
    if candado.exists():
        sys.exit(f"hay una vuelta del recolector en marcha ({candado}); espera a que termine")

    from radiov import pipeline  # noqa: E402

    con = sqlite3.connect(str(datos / "radiov.db"))
    antes = con.execute("SELECT max(id) FROM tracks").fetchone()[0] or 0
    con.close()

    añadidas = pipeline.process_youtube_seed(seed, max_downloads=args.cuantas)
    print(f"\nañadidas: {añadidas}")

    con = sqlite3.connect(str(datos / "radiov.db"))
    con.row_factory = sqlite3.Row
    print("=== fichas nuevas ===")
    for r in con.execute("SELECT id, title, artist, genre, language, duration, status FROM tracks"
                         " WHERE id > ? ORDER BY id", (antes,)):
        print(f"  {r['id']:>5} [{(r['genre'] or '-'):10}] {r['status']:11} {(r['language'] or '-'):5} "
              f"{int(r['duration'] or 0):>5}s  {(r['artist'] or '')[:22]:22} {(r['title'] or '')[:46]}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
