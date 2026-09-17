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
import datetime
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
    """Devuelve la ruta relativa POSIX si 'value' cuelga del ancla; None si no aplica.

    Dos casos:
      1. Absoluta bajo el ancla  -> se recorta el prefijo y se pasa a POSIX.
      2. Ya relativa pero con backslashes (normalizaciones antiguas en Windows) -> solo
         se cambian los separadores. Sin esto, en Linux un backslash es un carácter
         legal dentro de un nombre de fichero y la ruta no existiría nunca.
    """
    if not value or not value.strip():
        return None
    v = value.strip().replace("\\", "/")
    a = str(anchor).replace("\\", "/").rstrip("/")
    if v.lower() == a.lower():
        return None
    if v.lower().startswith(a.lower() + "/"):
        return v[len(a) + 1:]
    # Ya relativa: solo hay que unificar separadores si traía backslashes.
    if not DRIVE_RE.match(v) and "\\" in value:
        return v
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
        # Verificación: no debe quedar ni una ruta absoluta ni un backslash.
        problemas = 0
        for tabla, col, _ in TARGETS:
            try:
                cond = f"{col} IS NOT NULL AND {col}!=''"
                absolutas = conn.execute(
                    f"SELECT COUNT(*) FROM {tabla} WHERE {cond} AND ("
                    f"{col} LIKE '%:%\\%' OR {col} LIKE '%:/%')").fetchone()[0]
                barras = conn.execute(
                    f"SELECT COUNT(*) FROM {tabla} WHERE {cond} AND {col} LIKE '%\\%'"
                ).fetchone()[0]
                total_col = conn.execute(
                    f"SELECT COUNT(*) FROM {tabla} WHERE {cond}").fetchone()[0]
            except sqlite3.OperationalError:
                continue
            if absolutas or barras:
                problemas += absolutas + barras
                print(f"    [X] {tabla}.{col}: {absolutas} absolutas, "
                      f"{barras} con backslash (de {total_col})")
                for (val,) in conn.execute(
                    f"SELECT {col} FROM {tabla} WHERE {cond} AND ("
                    f"{col} LIKE '%:%\\%' OR {col} LIKE '%:/%' OR {col} LIKE '%\\%') LIMIT 3"
                ).fetchall():
                    print(f"        {val}")
            elif total_col:
                print(f"    [OK] {tabla}.{col}: {total_col} rutas relativas POSIX")
        if problemas:
            print(f"    [!!] {problemas} rutas sin normalizar")
    finally:
        conn.close()
    return cambios, muestras


def configurar_ingesta(db_path: Path, enabled: bool) -> None:
    """Fija el interruptor de ingesta dentro de la copia de radiov.db.

    Sin la clave `ingest_enabled`, ingest_control.is_enabled() devuelve True, así que el
    colector empezaría a descargar en cuanto arrancase. En un despliegue nuevo interesa
    que arranque APAGADO y que lo encienda el usuario desde la web, cuando la música ya
    esté en su sitio.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        existe = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_state'"
        ).fetchone()
        if not existe:
            print("    [i] no hay tabla agent_state; se omite el interruptor de ingesta")
            return
        ahora = datetime.datetime.now().isoformat(timespec="seconds")
        valores = {
            "ingest_enabled": "1" if enabled else "0",
            "ingest_updated_at": ahora,
            "ingest_updated_by": "preparar_despliegue",
        }
        for clave, valor in valores.items():
            conn.execute(
                "INSERT INTO agent_state(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (clave, valor))
        conn.commit()
        estado = dict(conn.execute(
            "SELECT key, value FROM agent_state WHERE key LIKE 'ingest%'").fetchall())
        print(f"    [OK] ingesta {'ENCENDIDA' if enabled else 'APAGADA'} en la copia: {estado}")
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="_deploy", help="directorio destino de las copias")
    ap.add_argument("--ingesta", choices=("on", "off"), default="off",
                    help="estado del interruptor de ingesta en la copia (por defecto off)")
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
        if nombre == "radiov.db":
            configurar_ingesta(dst, args.ingesta == "on")
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
