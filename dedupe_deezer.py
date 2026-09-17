"""Dedupe deezer_id en radiov.db (una sola vez, tras lo cual el índice UNIQUE puede crearse).

Conserva, por cada deezer_id duplicado, la fila con mayor `match_score` (desempate: id más bajo)
y mueve las demás a `blacklist` (kind='song', value='title|artist') antes de borrarlas.

Uso:
    .venv\\Scripts\\python.exe dedupe_deezer.py            # solo listado (dry-run)
    .venv\\Scripts\\python.exe dedupe_deezer.py --apply    # aplica cambios
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("data/radiov.db")


def _norm(value: str) -> str:
    return " ".join(value.lower().split())


def find_dupes(conn: sqlite3.Connection) -> list[list[dict]]:
    """Devuelve la lista de grupos de filas con deezer_id repetido (>=2)."""
    dids = [r[0] for r in conn.execute(
        "select deezer_id from tracks where deezer_id is not null "
        "group by deezer_id having count(*)>1").fetchall()]
    groups: list[list[dict]] = []
    for did in dids:
        rows = [dict(r) for r in conn.execute(
            "select id, artist, title, match_score, added_at, status "
            "from tracks where deezer_id=? order by match_score desc, id asc", (did,))]
        groups.append(rows)
    return groups


def pick_keeper(rows: list[dict]) -> dict:
    """La fila con mayor match_score (desempate: id más bajo)."""
    return min(rows, key=lambda r: (-float(r.get("match_score") or 0.0), r["id"]))


def apply(conn: sqlite3.Connection, groups: list[list[dict]]) -> tuple[int, int]:
    kept = moved = 0
    for rows in groups:
        keeper = pick_keeper(rows)
        for r in rows:
            if r["id"] == keeper["id"]:
                continue
            value = _norm(f"{r['title']}|{r['artist']}")
            conn.execute(
                "insert into blacklist(kind,value,reason,active,created_at) values('song',?,?,1,?)",
                (value, f"dedup deezer_id {r['deezer_id'] if 'deezer_id' in r else ''}", None))
            conn.execute("delete from tracks where id=?", (r["id"],))
            moved += 1
        kept += 1
    conn.commit()
    return kept, moved


def main() -> int:
    apply_mode = "--apply" in sys.argv
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        groups = find_dupes(conn)
        if not groups:
            print("[OK] No hay deezer_id duplicados en radiov.db")
            return 0
        print(f"[INFO] {len(groups)} grupo(s) duplicado(s):")
        for rows in groups:
            keeper = pick_keeper(rows)
            print(f"  deezer_id={rows[0].get('deezer_id')}")
            for r in rows:
                tag = "KEEP" if r["id"] == keeper["id"] else "del "
                print(f"      {tag} id={r['id']:>4} ms={r.get('match_score')} {r['artist']} - {r['title']}")
        if not apply_mode:
            print("\n[..] Dry-run. Ejecuta con --apply para mover los perdedores a blacklist y borrarlos.")
            return 0
        kept, moved = apply(conn, groups)
        print(f"\n[OK] Aplicado: {kept} conservados, {moved} movidos a blacklist y borrados.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
