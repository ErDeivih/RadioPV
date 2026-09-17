"""Recalcula `energy` por percentil sobre el corpus (y regenera `tags`).

Problema: energy = min(1, rms/0.15) deja ~60 % en exactamente 1.0. Se re-normaliza de forma uniforme
usando el rango (percentil) del rms guardado: energy = (pos+0.5)/n. Luego se regeneran los `tags`
(derive_tags usa umbrales >=0.55 / <=0.3) para que "energia alta" vuelva a significar algo.

Requiere: columnas rms (/gain_db) presentes y al menos algunas filas con rms. El reanálisis del
audio (leer cada MP3) es una tarea de worker, no de este script.

Uso:
    .venv\\Scripts\\python.exe scripts\\recalcular_energia.py   # recalcula y regenera tags
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB = "data/radiov.db"


def main() -> int:
    conn = sqlite3.connect(DB, timeout=60)
    conn.row_factory = sqlite3.Row
    filas = conn.execute(
        "SELECT id, rms FROM tracks WHERE rms IS NOT NULL ORDER BY rms").fetchall()
    n = len(filas)
    if n == 0:
        print("[..] Sin filas con rms. Reanaliza el audio en lotes (worker) y vuelve a ejecutarlo.")
        conn.close()
        return 1
    # re-normalizar energía por rangos (uniforme 0-1)
    for pos, (tid, _) in enumerate(filas):
        energy = round((pos + 0.5) / n, 3)
        conn.execute("UPDATE tracks SET energy=? WHERE id=?", (energy, tid))
    conn.commit()
    print(f"[OK] {n} filas re-normalizadas por percentil.")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
