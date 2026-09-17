"""Marca como cuarentena las pistas que no pasan la puerta de calidad y lista sus MP3.

Uso:
    .venv\\Scripts\\python.exe scripts\\limpiar_catalogo.py            # dry-run: lista lo que marcaría
    .venv\\Scripts\\python.exe scripts\\limpiar_catalogo.py --apply    # marca status='cuarentena' (no borra nada)
    .venv\\Scripts\\python.exe scripts\\limpiar_catalogo.py --delete-files  # borra los MP3 listados (¡confirmación!)

El borrado de ficheros de E:\\Musica se hace SÓLO con --delete-files, tras revisar la lista impresa.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from radiov.config import DATA_DIR, resolve_music

import radiov.quality as Q

DB = DATA_DIR / "radiov.db"


def main() -> int:
    apply = "--apply" in sys.argv
    delete = "--delete-files" in sys.argv
    if delete and not apply:
        apply = True  # borrar implica aplicar el marcado

    conn = sqlite3.connect(str(DB), timeout=60)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM tracks WHERE status != 'cuarentena'").fetchall()

    malas: list[dict] = []
    for r in rows:
        rec = dict(r)
        ok, motivo = Q.revisar(rec)
        if not ok:
            rec["_motivo"] = motivo
            malas.append(rec)

    print(f"[INFO] {len(malas)} pista(s) NO pasan la puerta de calidad:")
    total_bytes = 0
    files = []
    for t in malas:
        sz = t.get("file_size") or 0
        total_bytes += sz
        fp = t.get("file_path") or ""
        if fp:
            files.append(fp)
        print(f"  · {t.get('artist')} - {t.get('title')} | {t.get('duration') or 0:.0f}s | "
              f"{sz/1e6:.1f} MB | {t['_motivo']}")
    print(f"\n[INFO] Ficheros asociados: {len(files)} · tamaño total: ~{total_bytes/1e6/1024:.2f} GB")

    if not apply:
        print("\n[..] Dry-run. Con --apply marca status='cuarentena' (no borra nada).")
        return 0

    # marcar cuarentena
    for t in malas:
        conn.execute("UPDATE tracks SET status='cuarentena' WHERE id=?", (t["id"],))
    conn.commit()
    print(f"\n[OK] {len(malas)} pista(s) marcadas como 'cuarentena'.")

    if not delete:
        print("[..] No se ha borrado ningún fichero. Para borrar los MP3 listados usa --delete-files.")
        return 0

    # borrar ficheros (solo con --delete-files)
    for fp in files:
        p = resolve_music(fp)
        try:
            p.unlink(missing_ok=True)
        except OSError as e:  # noqa: BLE001
            print(f"    [warn] no se pudo borrar {fp}: {e}")
    print(f"[OK] Borrados {len(files)} ficheros de E:\\Musica.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
