"""D1: mueve (NO borra) los ficheros de las pistas en 'cuarentena' a E:\\Musica\\_cuarentena\\
conservando la estructura de carpetas relativa a BASE_MUSIC. Las filas se quedan status='cuarentena'
(para que el recolector no las vuelva a bajar).

Requiere acceso de escritura a E:\\Musica (fuera del sandbox). Correr DESPUÉS de la pasada de análisis.

Uso:  .venv\\Scripts\\python.exe scripts\\mover_cuarentena.py          # dry-run (lista)
      .venv\\Scripts\\python.exe scripts\\mover_cuarentena.py --apply  # mueve
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radiov.config import BASE_MUSIC

DB = "data/radiov.db"
DEST_ROOT = BASE_MUSIC / "_cuarentena"


def main() -> int:
    apply = "--apply" in sys.argv
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, artist, title, file_path FROM tracks WHERE status='cuarentena' AND file_path IS NOT NULL").fetchall()
    if not rows:
        print("[..] No hay filas en cuarentena con fichero.")
        return 0
    print(f"[INFO] {len(rows)} fila(s) en cuarentena. Destino: {DEST_ROOT}")
    moved = 0
    for r in rows:
        fp = r["file_path"]
        p = Path(fp)
        if not p.exists():
            print(f"    [omitir] no existe en disco: {fp}")
            continue
        rel = p.relative_to(BASE_MUSIC) if p.is_relative_to(BASE_MUSIC) else Path(p.name)
        dest = DEST_ROOT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"    {fp}  ->  {dest}")
        if apply:
            try:
                shutil.move(str(p), str(dest))
                moved += 1
            except OSError as e:  # noqa: BLE001
                print(f"    [error] {e}")
    if apply:
        print(f"\n[OK] Movidos {moved} ficheros a E:\\Musica\\_cuarentena\\ (nada borrado).")
    else:
        print("\n[..] Dry-run (usa --apply para mover).")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
