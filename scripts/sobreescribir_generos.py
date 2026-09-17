#!/usr/bin/env python
"""Sobrescribe el género de ARTISTAS concretos que Deezer etiqueta mal (p. ej. 'Pop' para metal).

Es la única forma de fijar los casos obvios sin adivinar el resto: un diccionario curado
artista→género. NOTA: pisa el género de Deezer para esos artistas a propósito.

Uso:
    python scripts/sobreescribir_generos.py            # --dry-run: tabla
    python scripts/sobreescribir_generos.py --apply    # escribe artists.genre (luego reclasificar_generos)
"""
import argparse
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
DB_DEFAULT = _ROOT / "data" / "radiov.db"

# Curado (a mano, por alguien que conoce el catálogo): correcciones obvias de la etiqueta de Deezer.
SOBRESCRIBIR = {
    "Metallica": "rock",
    "Loquillo": "rock",
    "Loquillo Y Los Trogloditas": "rock",
    "Apocalyptica": "rock",
    "Karamelo Santo": "rock",
    "Apollo 3": "rock",
    "El Fary": "flamenco",
    "Estopa": "flamenco",
    "Camela": "flamenco",
    "Los Chichos": "flamenco",
}


def main() -> int:
    ap = argparse.ArgumentParser(description="Sobrescribe el género de artistas mal etiquetados.")
    ap.add_argument("--db", default=str(DB_DEFAULT))
    ap.add_argument("--dry-run", dest="apply", action="store_false", help="no escribir (por defecto)")
    ap.add_argument("--apply", dest="apply", action="store_true", help="escribir artists.genre")
    ap.set_defaults(apply=False)
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    cambios = {}
    for name, g in SOBRESCRIBIR.items():
        row = con.execute("SELECT genre FROM artists WHERE name=?", (name,)).fetchone()
        if row and (row[0] or "other") != g:
            cambios[name] = g
    print(f"{'ARTISTA':<28} {'GÉNERO':<12}")
    for name, g in sorted(cambios.items()):
        print(f"{name:<28} {g:<12}")
    print(f"\nCambiarían {len(cambios)} artistas.")
    if args.apply:
        con.executemany("UPDATE artists SET genre=? WHERE name=?", [(g, n) for n, g in cambios.items()])
        con.commit()
        print("\nAplicado. Luego: python scripts/reclasificar_generos.py --apply")
    else:
        print("\n(--dry-run · añade --apply)")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
