#!/usr/bin/env python
"""Sobrescribe el género de ARTISTAS concretos que Deezer etiqueta mal (p. ej. 'Pop' para metal).

Es la única forma de fijar los casos obvios sin adivinar el resto: un diccionario curado
artista→género. NOTA: pisa el género de Deezer para esos artistas a propósito.

LA TABLA ES UNA SOLA
--------------------
Antes este script tenía su **propia copia** de la tabla y la del clasificador (`radiov/catalog.py`)
era otra. Ya se habían separado: la del clasificador tenía 17 artistas más (Drake, Eminem, Hans
Zimmer, Celia Cruz…) que este script no conocía, así que `--apply` **no arreglaba en `artists.genre`
lo mismo que la aplicación usaba al clasificar**: el panel y la app podían decir géneros distintos de
la misma canción. Ahora importa la tabla del clasificador, así que no pueden discrepar por diseño
(hay una prueba que lo comprueba).

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

# La tabla buena, la del clasificador. Claves en minúsculas.
from radiov.catalog import SOBRESCRIBIR, _deaccent  # noqa: E402


def _clave(nombre: str) -> str:
    """La misma clave que usa el clasificador: sin tildes, en minúsculas y sin espacios de sobra."""
    return _deaccent((nombre or "").strip().lower())


def _filas(ruta: str) -> dict:
    """Artistas de la base que hay que corregir: {nombre_tal_como_está_en_la_base: género}.

    Se compara **sin distinguir mayúsculas ni tildes**, que es exactamente como compara el
    clasificador: la base guarda «Metallica» y la tabla dice «metallica», y con una comparación
    exacta el arreglo no se aplicaba nunca.
    """
    con = sqlite3.connect(ruta)
    out = {}
    for (nombre, genero) in con.execute("SELECT name, genre FROM artists"):
        objetivo = SOBRESCRIBIR.get(_clave(nombre))
        if objetivo and (genero or "other") != objetivo:
            out[nombre] = objetivo
    con.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Sobrescribe el género de artistas mal etiquetados.")
    ap.add_argument("--db", default=str(DB_DEFAULT))
    ap.add_argument("--dry-run", dest="apply", action="store_false", help="no escribir (por defecto)")
    ap.add_argument("--apply", dest="apply", action="store_true", help="escribir artists.genre")
    ap.set_defaults(apply=False)
    args = ap.parse_args()

    cambios = _filas(args.db)
    print(f"{'ARTISTA':<32} {'GÉNERO':<12}")
    for name, g in sorted(cambios.items()):
        print(f"{name:<32} {g:<12}")
    print(f"\nCambiarían {len(cambios)} artistas (de {len(SOBRESCRIBIR)} en la tabla curada).")
    if args.apply:
        con = sqlite3.connect(args.db)
        con.executemany("UPDATE artists SET genre=? WHERE name=?", [(g, n) for n, g in cambios.items()])
        con.commit()
        con.close()
        print("\nAplicado. Luego: python scripts/reclasificar_generos.py --apply")
    else:
        print("\n(--dry-run · añade --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
