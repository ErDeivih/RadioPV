"""Prepara una copia de las BD para desplegar en Linux, normalizando rutas.

No toca las BD originales: escribe copias en el directorio de destino.

  tracks.file_path          E:\\Musica\\catalogada\\A\\x.mp3   ->  catalogada/A/x.mp3
  tracks.cover_path         F:\\...\\data\\covers\\1.jpg       ->  covers/1.jpg
  tracks.artist_image_path  ...\\data\\artists\\1.jpg          ->  artists/1.jpg
  artists.image_path        ...\\data\\artists\\1.jpg          ->  artists/1.jpg

Uso:
    python scripts/preparar_despliegue.py --out _deploy
"""

from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import radiov.config as C  # noqa: E402

# (db origen, tabla, columna, ancla)
TARGETS = [
    ("tracks", "file_path", C.BASE_MUSIC),
    ("tracks", "cover_path", C.DATA_DIR),
    ("tracks", "artist_image_path", C.DATA_DIR),
    ("artists", "image_path", C.DATA_DIR),
]
DBS = ("radiov.db", "backend.db")

DRIVE_RE = re.compile(r"^[A-Za-z]:[/\\]")


def to_relative(value: str, anchor: Path) -> str | None:
    """Devuelve la ruta relativa POSIX si 'value' cuelga del ancla; None si no aplica."""
    if not value or not value.strip():
        return None
    v = value.strip().replace("\\", "/")
    a = str(anchor).replace("\\", "/").rstrip("/")
    if v.lower() == a.lower():
        return None
    if v.lower().startswith(a.lower() + "/"):
        return v[len(a) + 1:]
    return None


def normalizar(db_path: Path, ruta_rel: str) -> tuple[int, list[tuple[str, str]]]:
    conn = sqlite3.connect(str(db_path))
    cambios = 0
    muestras: list[tuple[str, str]] = []
    try:
        for tabla, col, ancla in TARGETS:
            try:
                filas = conn.execute(
                    f"SELECT rowid, {col} FROM {tabla} "
                    f"WHERE {col} IS NOT NULL AND {col}!=''"
                ).fetchall()
            except sqlite3.OperationalError:
                continue  # tabla/columna inexistente en esta BD
            for rid, val in filas:
                rel = to_relative(val, ancla)
                if rel is None:
                    continue
                cambios += 1
                if len(muestras) < 4:
                    muestras.append((val, rel))
                conn.execute(
                    f"UPDATE {tabla} SET {col}=? WHERE rowid=?", (rel, rid)
                )
            if filas:
                print(f"    {tabla}.{col}: {len(filas)} filas revisadas")
        conn.commit()
        # Informe de rutas absolutas que hayan podido quedar sin normalizar
        restos: list[str] = []
        for tabla, col, _ in TARGETS:
            try:
                for (val,) in conn.execute(
                    f"SELECT {col} FROM {tabla} "
                    f"WHERE {col} IS NOT NULL AND {col}!='' AND ({col} LIKE '%:%\\%' "
                    f"OR {col} LIKE '%:/%') LIMIT 5"
                ).fetchall():
                    restos.append(f"{tabla}.{col} = {val}")
            except sqlite3.OperationalError:
                continue
        if restos:
            print("    [!] quedan rutas absolutas:")
            for r in restos[:5]:
                print("        ", r)
    finally:
        conn.close()
    return cambios, muestras


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="_deploy", help="directorio destino de las copias")
    args = ap.parse_args()

    out = (ROOT / args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    print(f"[i] BASE_MUSIC = {C.BASE_MUSIC}")
    print(f"[i] DATA_DIR   = {C.DATA_DIR}")
    print(f"[i] destino    = {out}\n")

    total = 0
    for nombre in DBS:
        src = C.DATA_DIR / nombre
        if not src.exists():
            print(f"  {nombre}: no existe, se omite")
            continue
        dst = out / nombre
        shutil.copy2(src, dst)
        print(f"  === {nombre}  ({src.stat().st_size/1e6:.1f} MB copiado)")
        cambios, muestras = normalizar(dst, nombre)
        total += cambios
        print(f"    filas normalizadas: {cambios}")
        for antes, despues in muestras:
            print(f"      {antes}\n        -> {despues}")
        print()

    # Volcado de la tabla users para poder revisar/promocionar admins despues
    bdb = out / "backend.db"
    if bdb.exists():
        conn = sqlite3.connect(str(bdb))
        try:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
            print(f"  users columnas: {cols}")
            for fila in conn.execute("SELECT * FROM users").fetchall():
                print("   ", fila)
        finally:
            conn.close()

    print(f"\n[OK] total filas normalizadas: {total}")
    print(f"[OK] copias listas en {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
