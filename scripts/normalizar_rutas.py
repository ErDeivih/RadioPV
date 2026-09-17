"""Normaliza las rutas de la BD (radiov.db y backend.db) a relativas.

Solo reescribe cadenas: NO mueve ni renombra ficheros. Convierte:

  tracks.file_path       E:\\Musica\\catalogada\\A\\[2025] X\\y.mp3  ->  catalogada\\A\\[2025] X\\y.mp3
  tracks.cover_path      F:\\...\\data\\covers\\693008911.jpg       ->  covers\\693008911.jpg
  tracks.artist_image_path / artists.image_path  ...\\data\\artists\\123.jpg ->  artists\\123.jpg

Uso:
    .venv\\Scripts\\python.exe scripts\\normalizar_rutas.py             # dry-run (muestra)
    .venv\\Scripts\\python.exe scripts\\normalizar_rutas.py --apply     # escribe
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# Asegurar que el paquete radiov es importable al ejecutar scripts/normalizar_rutas.py
if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radiov.config as C

# (db relativo, tabla, columna, ancla). El ancla es la raíz; lo que cuelgue de ella se vuelve relativo.
TARGETS = [
    ("data/radiov.db", "tracks", "file_path", C.BASE_MUSIC),
    ("data/radiov.db", "tracks", "cover_path", C.DATA_DIR),
    ("data/radiov.db", "tracks", "artist_image_path", C.DATA_DIR),
    ("data/radiov.db", "artists", "image_path", C.DATA_DIR),
    ("data/backend.db", "tracks", "file_path", C.BASE_MUSIC),
    ("data/backend.db", "tracks", "cover_path", C.DATA_DIR),
    ("data/backend.db", "tracks", "artist_image_path", C.DATA_DIR),
    ("data/backend.db", "artists", "image_path", C.DATA_DIR),
]


def _to_relative(value: str, anchor: Path) -> str | None:
    """Convierte una ruta absoluta bajo 'anchor' a relativa. None si ya es relativa o no cuelga del ancla."""
    if not value or value.strip() == "":
        return None
    p = Path(value)
    anchor = Path(anchor)
    # Si es absoluta y está bajo el ancla -> relativa
    try:
        if p.is_absolute() and p.is_relative_to(anchor):
            return p.relative_to(anchor).as_posix()
    except ValueError:
        pass
    # Si ya es relativa (sin unidad): la dejamos tal cual (ya normalizada)
    if not p.is_absolute():
        return None
    return None


def process_db(db_path: str, table: str, column: str, anchor: Path, apply: bool) -> tuple[int, int]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    changed = 0
    samples: list[tuple[str, str]] = []
    try:
        cur = conn.execute(f"SELECT id, {column} AS val FROM {table} WHERE {column} IS NOT NULL AND {column}!=''")
        for row in cur.fetchall():
            rel = _to_relative(row["val"], anchor)
            if rel is not None:
                changed += 1
                if len(samples) < 5:
                    samples.append((row["val"], rel))
                if apply:
                    conn.execute(f"UPDATE {table} SET {column}=? WHERE id=?", (rel, row["id"]))
        if apply:
            conn.commit()
    finally:
        conn.close()
    if samples:
        print(f"  [{db_path}] {table}.{column}  cambiaria={changed}  (ancla={anchor})")
        for before, after in samples:
            print(f"      {before}  ->  {after}")
    else:
        print(f"  [{db_path}] {table}.{column}  cambiaria=0")
    return changed, len(samples)


def main() -> int:
    apply = "--apply" in sys.argv
    # --db backend | radiov | all (por defecto all)
    only = "all"
    if "--db" in sys.argv:
        i = sys.argv.index("--db")
        if i + 1 < len(sys.argv):
            only = sys.argv[i + 1].lower()
    if only not in ("all", "backend", "radiov"):
        print("--db debe ser backend | radiov | all")
        return 2
    print("[INFO] " + ("Aplicando..." if apply else "Dry-run (usa --apply para escribir)")
          + f" · db={only}")
    total = 0
    for db, table, col, anchor in TARGETS:
        target = "backend" if "backend" in db else "radiov"
        if only != "all" and only != target:
            continue
        p = Path(db)
        if not p.exists():
            print(f"  [{db}] no existe, se omite")
            continue
        c, _ = process_db(str(p), table, col, anchor, apply)
        total += c
    print(f"\n[OK] Filas afectadas: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
