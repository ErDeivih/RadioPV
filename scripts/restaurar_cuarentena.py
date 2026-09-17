"""Saca canciones de la cuarentena: devuelve el MP3 a su sitio y marca status='descargada'.

Uso:
    .venv\\Scripts\\python.exe scripts\\restaurar_cuarentena.py                 # lista lo que hay
    .venv\\Scripts\\python.exe scripts\\restaurar_cuarentena.py "Topic" "Albi"  # en seco
    .venv\\Scripts\\python.exe scripts\\restaurar_cuarentena.py "Topic" "Albi" --apply
"""
from __future__ import annotations
import sqlite3
import sys
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# `DATA_DIR` sale de radiov.config: es la ruta ABSOLUTA de los datos. Antes la base se abría como
# "data/radiov.db" (relativa al directorio desde el que lanzaras el script), así que desde otro
# sitio SQLite creaba una base VACÍA y el script decía "0 filas" sin avisar de nada.
from radiov.config import BASE_MUSIC, DATA_DIR  # noqa: E402

DB = DATA_DIR / "radiov.db"
CUARENTENA = Path(BASE_MUSIC) / "_cuarentena"


def listar(con) -> None:
    filas = con.execute(
        "SELECT artist, title, round(duration) FROM tracks "
        "WHERE status='cuarentena' ORDER BY artist"
    ).fetchall()
    print(f"[INFO] {len(filas)} en cuarentena:")
    for a, t, d in filas:
        print(f'    {d or 0:>6.0f}s  "{a}" "{t}"')
    print("\nPara restaurar una:  scripts\\restaurar_cuarentena.py \"Artista\" \"Título\" --apply")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    aplicar = "--apply" in sys.argv
    con = sqlite3.connect(str(DB))

    if len(args) < 2:
        listar(con)
        return

    artista, titulo = args[0], args[1]
    fila = con.execute(
        "SELECT id, file_path FROM tracks WHERE status='cuarentena' "
        "AND lower(artist)=lower(?) AND lower(title)=lower(?)",
        (artista, titulo),
    ).fetchone()
    if not fila:
        print(f'[ERROR] No hay nada en cuarentena con artista "{artista}" y título "{titulo}".')
        listar(con)
        return

    tid, rel = fila
    rel = (rel or "").replace("\\", "/")
    origen, destino = CUARENTENA / rel, Path(BASE_MUSIC) / rel
    print(f"    {origen}\n -> {destino}")

    if not aplicar:
        print("\n[SECO] Nada movido. Añade --apply para hacerlo de verdad.")
        return

    if origen.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        origen.replace(destino)
        print("[OK] Fichero devuelto a su sitio.")
    else:
        print("[AVISO] El fichero no estaba en la cuarentena; solo actualizo la base de datos.")

    con.execute("UPDATE tracks SET status='descargada' WHERE id=?", (tid,))
    con.commit()
    print(f"[OK] «{artista} - {titulo}» restaurada. Ejecuta migrate_sqlite para que la vea la app.")


if __name__ == "__main__":
    main()
