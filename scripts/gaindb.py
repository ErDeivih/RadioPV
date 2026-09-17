"""Calcula gain_db (normalización de volumen a -14 LUFS) para las canciones.

Usa ffmpeg loudnorm sobre cada MP3 y guarda gain_db = -14.0 - input_i (objetivo Spotify).
Es lento (lee cada fichero) → tarea de worker por lotes, no interactiva.

Uso:
    .venv\\Scripts\\python.exe scripts\\gaindb.py            # dry-run (muestra cuántas faltan)
    .venv\\Scripts\\python.exe scripts\\gaindb.py --apply    # calcula y escribe gain_db
    .venv\\Scripts\\python.exe scripts\\gaindb.py --apply --limit 50   # lote de 50
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radiov.catalog as C

TARGET_LUFS = -14.0
DB = "data/radiov.db"


def measure(path: Path) -> float | None:
    """Devuelve el LUFS integral (input_i) medido por ffmpeg, o None si falla."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-i", str(path), "-af", "loudnorm=I=-14:print_format=json", "-f", "null", "-"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    try:
        js = json.loads(r.stderr[r.stderr.rfind("{"): r.stderr.rfind("}") + 1])
        return float(js.get("input_i"))
    except (ValueError, AttributeError, KeyError):
        return None


def main() -> int:
    apply = "--apply" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        i = sys.argv.index("--limit")
        if i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])

    conn = sqlite3.connect(DB, timeout=60)
    conn.row_factory = sqlite3.Row
    sql = "SELECT id, file_path FROM tracks WHERE gain_db IS NULL"
    rows = conn.execute(sql).fetchall()
    if limit:
        rows = rows[:limit]
    print(f"[INFO] {len(rows)} canción(es) sin gain_db.")
    if not apply:
        print("[..] Dry-run (usa --apply para calcular y escribir).")
        conn.close()
        return 0

    done = 0
    for r in rows:
        t = dict(r)
        if not t.get("file_path"):
            continue
        p = C.resolve_music(t["file_path"])
        if not p.exists():
            continue
        i = measure(p)
        if i is not None:
            gain = round(TARGET_LUFS - i, 2)
            conn.execute("UPDATE tracks SET gain_db=? WHERE id=?", (gain, t["id"]))
            done += 1
            if done % 10 == 0:
                conn.commit()
    conn.commit()
    print(f"[OK] gain_db calculado para {done} canción(es).")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
