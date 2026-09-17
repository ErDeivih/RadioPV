#!/usr/bin/env python
"""C5 · Reclasificar géneros (T-27).

La fuente de verdad del género es el ARTISTA en Deezer (tabla `artists.genre`), no el que se
heredó del seed/tema. Regla (de menor a mayor confianza):
    género del álbum  →  (no se guarda por álbum; se usa el artista)
    género del artista →  si existe y != 'other'
    género del tema    →  si existe y != 'other'
    'other'            →  si no hay nada fiable (mejor ausente que equivocado)

Uso:
    python scripts/reclasificar_generos.py            # --dry-run: tabla viejo->nuevo + conteos
    python scripts/reclasificar_generos.py --apply    # escribe genre y guarda genre_original
"""
import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path

DB_DEFAULT = Path(__file__).resolve().parents[1] / "data" / "radiov.db"


def norm(g: str | None) -> str:
    return (g or "").strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="Reclasificar géneros por el género del artista (Deezer).")
    ap.add_argument("--db", default=str(DB_DEFAULT), help="ruta a radiov.db (no backend.db)")
    ap.add_argument("--apply", action="store_true", help="escribir los cambios (sin esto, dry-run)")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    cols = [r[1] for r in con.execute("PRAGMA table_info(tracks)")]
    if "genre_original" not in cols:
        con.execute("ALTER TABLE tracks ADD COLUMN genre_original TEXT")

    # género del artista (Deezer) normalizado: name(bajito) -> genre
    artist_genre = {}
    for name, genre in con.execute("SELECT name, genre FROM artists"):
        if genre and norm(genre).lower() != "other":
            artist_genre[(name or "").strip().lower()] = norm(genre).lower()

    rows = con.execute("SELECT id, artist, genre FROM tracks").fetchall()
    plan = []          # (id, old, new)
    for tid, artist, genre in rows:
        old = norm(genre).lower() or "other"
        ag = artist_genre.get((artist or "").strip().lower())
        if ag:
            new = ag
        elif old != "other":
            new = old
        else:
            new = "other"
        if new != old:
            plan.append((tid, old, new))

    print(f"{'GÉNERO ORIGINAL':<20} {'GÉNERO NUEVO':<20} {'#':>6}")
    for (old, new), n in sorted(Counter((o, n2) for _, o, n2 in plan).items(), key=lambda x: -x[1]):
        print(f"{old:<20} {new:<20} {n:>6}")
    print(f"\nCambiarán {len(plan)} filas de {len(rows)}.")

    # 'other' antes/después
    plan_ids = {tid for tid, _, _ in plan}
    result = {}
    for tid, artist, genre in rows:
        old = norm(genre).lower() or "other"
        # si no cambió, su 'nuevo' es su actual
        result[tid] = old
    for tid, old, new in plan:
        result[tid] = new
    other_before = sum(1 for tid, o, n2 in plan if o == 'other')
    other_before += sum(1 for tid, _, g in rows if (norm(g).lower() or 'other') == 'other' and tid not in plan_ids)
    other_after = sum(1 for ng in result.values() if ng == 'other')
    print(f"   'other' antes: {other_before} · después (estimado): {other_after}")

    if args.apply:
        con.executemany("UPDATE tracks SET genre=?, genre_original=? WHERE id=?",
                        [(new, old, tid) for tid, old, new in plan])
        con.commit()
        print("\nAplicado a radiov.db. Lanza `python -m app.workers` (sync_catalogo) para propagarlo a backend.db.")
    else:
        print("\n(--dry-run · añade --apply para escribir; revisa la tabla antes)")

    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
