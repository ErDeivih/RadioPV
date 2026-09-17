"""Verifica a posteriori las pistas con match_score "sin verificar" (NULL) o pésimo (0).

Para cada una compara la duración REAL del fichero (catalog.real_duration) con la esperada
(de Deezer, campo `duration`). match = max(0, 1 - |real-esperada|/esperada). Se escribe el
match_score y, si queda < 0.6, la pista pasa a status='revisar' (cola de reparación).

Uso:
    .venv\\Scripts\\python.exe scripts\\verificar_match.py            # dry-run
    .venv\\Scripts\\python.exe scripts\\verificar_match.py --apply    # escribe match_score y 'revisar'
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radiov.catalog as C

UMBRAL = 0.6
DB = "data/radiov.db"


def main() -> int:
    apply = "--apply" in sys.argv
    conn = sqlite3.connect(DB, timeout=60)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, title, artist, duration, file_path, match_score, status "
        "FROM tracks WHERE (match_score IS NULL OR match_score = 0) AND status != 'revisar'").fetchall()

    print(f"[INFO] {len(rows)} fila(s) con match_score sin verificar (NULL) o 0:")
    revisar = actualizados = 0
    for r in rows:
        t = dict(r)
        if not t.get("file_path"):
            continue
        real = C.real_duration(t["file_path"])
        esperada = t.get("duration")
        if not real or not esperada:
            continue
        match = max(0.0, 1.0 - abs(real - esperada) / max(esperada, 1))
        flag = "REVISAR" if match < UMBRAL else "sin_desajuste"
        print(f"  · {t['artist']} - {t['title']} | real={real:.0f}s esperada={esperada:.0f}s "
              f"| match={match:.2f} {flag}")
        # Solo es un desajuste REAL cuando la duración guardada era la esperada y difiere.
        # Si real≈guardada es autoreferencial (sin duración esperada) → no escribir 1.0 (no está verificado).
        if apply and match < UMBRAL:
            conn.execute("UPDATE tracks SET match_score=?, status='revisar' WHERE id=?",
                         (round(match, 3), t["id"]))
            actualizados += 1
            revisar += 1
    if apply:
        conn.commit()
        print(f"\n[OK] {actualizados} marcadas 'revisar' (<{UMBRAL}). Las demás quedan sin tocar.")
    else:
        print("\n[..] Dry-run. Con --apply marca 'revisar' solo donde hay desajuste real.")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
