"""Copia de seguridad de data/radiov.db y data/backend.db a data/backup/<ts>/.
No toca datos. Restauración: parar API/worker, copiar de vuelta el fichero correspondiente.
Uso:  .venv\\Scripts\\python.exe scripts\\backup.py
"""
from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BACKUP = DATA / "backup" / datetime.now().strftime("%Y%m%d-%H%M%S")


def _check_db(path: Path) -> bool:
    try:
        con = sqlite3.connect(path)
        con.execute("SELECT 1")
        con.close()
        return True
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    BACKUP.mkdir(parents=True, exist_ok=True)
    for name in ("radiov.db", "backend.db"):
        src = DATA / name
        if not src.exists():
            print(f"[..] {name} no existe, se omite")
            continue
        ok = _check_db(src)
        dst = BACKUP / name
        shutil.copy2(src, dst)
        print(f"[OK] {name} -> {dst} ({'válida' if ok else 'OJO: no pasa chequeo'})")
    print(f"[OK] Copia en {BACKUP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
