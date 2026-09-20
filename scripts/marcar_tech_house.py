#!/usr/bin/env python
"""C5b · Marca el género `techhouse` en las pistas que YA están en el catálogo.

POR QUÉ
-------
El usuario pidió esta música por su nombre («me gustan los tech house remix y este tipo de canciones
hechas por gente, por ejemplo estoy viendo un tal Pomata en spotify… con bass, en español o inglés o
mezcla, usando una o varias canciones originales»). El género `techhouse` se aplica solo a lo que se
descargue a partir de ahora, pero **las remezclas de tech house que ya estaban en el catálogo se
quedaron con el género viejo** («other», «dance», «house»), así que en el panel de administración no
había forma de verlas ni de filtrarlas: el género de la ficha y lo que la aplicación usa para
clasificar (`radiov.catalog.guess_genre`) decían cosas distintas.

QUÉ CAMBIA Y QUÉ NO
-------------------
Se reclasifica con **el mismo clasificador que el recolector** (título + artista; sin llamar a
Deezer), así que la ficha y la aplicación no pueden discrepar. Sólo se escribe cuando el género
resultante es `techhouse` **y** el que había era un cajón poco preciso («other», «dance», «electro»,
«house», «techno»): si la ficha tiene un género más concreto (reggaetón, pop…), se respeta y sólo se
avisa. Nunca se pisa un género por otro peor.

Uso:
    python scripts/marcar_tech_house.py --db data/radiov.db            # dry-run: cuenta y lista
    python scripts/marcar_tech_house.py --db data/radiov.db --apply
"""
import argparse
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# La consola de Windows (cp1252) revienta con algunos caracteres (medido: la flecha «→» lanzaba
# UnicodeEncodeError y el script moría a mitad de la tabla). Se escribe en UTF-8 y, si algo no se
# puede representar, se sustituye en vez de reventar.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

DB_DEFAULT = _ROOT / "data" / "radiov.db"
# Cajones poco precisos: dentro de estos, `techhouse` es más exacto (no al revés).
COARSE = {"", "other", "dance", "electro", "house", "techno"}


def main() -> int:
    ap = argparse.ArgumentParser(description="Marca el género techhouse en el catálogo ya descargado.")
    ap.add_argument("--db", default=str(DB_DEFAULT), help="ruta a la base (radiov.db o backend.db)")
    ap.add_argument("--apply", action="store_true", help="escribir los cambios (sin esto, dry-run)")
    args = ap.parse_args()

    from radiov.catalog import guess_genre

    con = sqlite3.connect(args.db)
    cols = [r[1] for r in con.execute("PRAGMA table_info(tracks)")]
    if args.apply and "genre_original" not in cols:
        con.execute("ALTER TABLE tracks ADD COLUMN genre_original TEXT")

    plan, respetadas = [], []
    for tid, title, artist, genre in con.execute("SELECT id, title, artist, genre FROM tracks"):
        if guess_genre(title or "", artist or "") != "techhouse":
            continue
        actual = (genre or "").strip().lower()
        if actual == "techhouse":
            continue
        (plan if actual in COARSE else respetadas).append((tid, title, artist, actual))

    print(f"{'#':>5}  {'TÍTULO':<52} {'ARTISTA':<22} GÉNERO")
    for tid, title, artist, actual in plan[:40]:
        print(f"{tid:>5}  {(title or '')[:52]:<52} {(artist or '')[:22]:<22} {actual or 'other'} -> techhouse")
    if len(plan) > 40:
        print(f"  … y {len(plan) - 40} más")
    print(f"\nSe marcarían {len(plan)} pistas como techhouse.")

    if respetadas:
        print(f"\nNo se tocan {len(respetadas)} que tienen un género más concreto (se respeta):")
        for tid, title, artist, actual in respetadas[:15]:
            print(f"{tid:>5}  {(title or '')[:52]:<52} {(artist or '')[:22]:<22} {actual}")
        if len(respetadas) > 15:
            print(f"  … y {len(respetadas) - 15} más")

    if args.apply:
        con.executemany("UPDATE tracks SET genre='techhouse', genre_original=COALESCE(genre_original, ?) WHERE id=?",
                        [(a or "other", tid) for tid, _t, _ar, a in plan])
        con.commit()
        print(f"\nAplicado a {args.db}.")
    else:
        print("\n(--dry-run · añade --apply para escribir)")

    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
