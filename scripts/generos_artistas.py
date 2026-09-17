#!/usr/bin/env python
"""D1 · Rellena `artists.genre` desde Deezer para los artistas que no tienen género (o 'other').

Lo ejecuta David (necesita red a api.deezer.com). El agente lo prueba con fixtures (lookup falso).
Regla: género más frecuente del artista en Deezer; si ninguno, se deja como está (no se inventa).

Uso:
    python scripts/generos_artistas.py            # --dry-run: tabla artista -> género nuevo
    python scripts/generos_artistas.py --apply    # escribe artists.genre
"""
import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Callable, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

DB_DEFAULT = _ROOT / "data" / "radiov.db"

# Lookup de género por (nombre de artista, album_ids de Deezer de ese artista en nuestra BD).
# El real usa /album/{id} (donde viven genres.data); el test inyecta uno falso con esa forma.
Lookup = Callable[[str, list[str]], Optional[str]]

# Normalización a nuestro vocabulario de géneros (los de Deezer pueden venir en plural/otro nombre).
NORMALIZA = {
    "metal": "rock", "heavy metal": "rock", "hard rock": "rock", "classic rock": "rock",
    "rock": "rock", "pop rock": "rock", "punk rock": "rock", "arena rock": "rock",
    "reggaeton": "reggaeton", "latin": "latin", "latin pop": "latin", "pop": "pop",
    "flamenco": "flamenco", "copla": "flamenco", "flamenco fusion": "flamenco",
    "rumba": "latin", "r&b": "r&b", "soul": "soul", "rap": "rap", "hip hop": "rap",
    "salsa": "salsa", "bachata": "bachata", "merengue": "merengue", "cumbia": "cumbia",
    "corridos": "corridos", "dance": "dance", "edm": "dance", "house": "house",
    "electro": "electro", "disco": "disco", "ballad": "ballad", "classical": "classical",
    "instrumental": "instrumental", "reggae": "reggae",
}

# Nuestro vocabulario (los valores de NORMALIZA). Solo estos géneros se aceptan; el resto → 'other'.
KNOWN = {"rock", "reggaeton", "latin", "pop", "flamenco", "r&b", "soul", "rap", "salsa",
         "bachata", "merengue", "cumbia", "corridos", "dance", "house", "electro",
         "disco", "ballad", "classical", "instrumental", "reggae"}


def deezer_lookup(name: str, album_ids: list[str]) -> Optional[str]:
    """Género más frecuente y CONOCIDO del artista a partir de sus álbumes. Si ningún género de
    Deezer entra en nuestro vocabulario → 'other' (regla: no inventar)."""
    from radiov.deezer import DeezerClient
    client = DeezerClient()
    cont = Counter()
    for aid in album_ids[:3]:                      # 2-3 álbumes distintos bastan
        try:
            alb = client.album_detail(aid)
        except Exception:  # noqa: BLE001
            continue
        for g in (alb.get("genres") or {}).get("data", []) or []:
            nm = (g.get("name") or "").strip().lower()
            if not nm:
                continue
            norm = NORMALIZA.get(nm, nm)
            if norm in KNOWN:                      # solo géneros que sabemos clasificar
                cont[norm] += 1
    if not cont:
        return "other"                             # sin género fiable → other, no inventar
    return cont.most_common(1)[0][0]


def clasificar(db_path: str, lookup: Lookup) -> dict[str, str]:
    """Solo artistas en 'other'/sin género: les saca el género de sus álbumes (mapa + fallback 'other').
    Rápido (pocos artistas). Los 'pop' mal etiquetados los arregla sobreescribir_generos.py."""
    con = sqlite3.connect(db_path)
    artistas = con.execute(
        "SELECT DISTINCT artist FROM tracks WHERE genre IS NULL OR genre='' OR lower(genre)='other'"
    ).fetchall()
    cambio = {}
    for (artist,) in artistas:
        album_ids = [r[0] for r in con.execute(
            "SELECT album_id FROM tracks WHERE lower(artist)=? AND album_id IS NOT NULL",
            (artist.lower(),))]
        if not album_ids:
            continue
        g = lookup(artist, album_ids) or "other"
        if g in KNOWN and g != "other":
            cambio[artist] = g
    con.close()
    return cambio


def main() -> int:
    ap = argparse.ArgumentParser(description="Rellena artists.genre desde Deezer.")
    ap.add_argument("--db", default=str(DB_DEFAULT))
    ap.add_argument("--dry-run", dest="apply", action="store_false", help="no escribir (por defecto)")
    ap.add_argument("--apply", dest="apply", action="store_true", help="escribir artists.genre")
    ap.set_defaults(apply=False)
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    cambio = clasificar(args.db, deezer_lookup)

    print(f"{'ARTISTA':<32} {'GÉNERO NUEVO':<20}")
    for name, g in sorted(cambio.items(), key=lambda x: -1):
        print(f"{name:<32} {g:<20}")
    print(f"\nCambiarían {len(cambio)} artistas.")

    if args.apply:
        con.executemany("UPDATE artists SET genre=? WHERE name=?", [(g, n) for n, g in cambio.items()])
        con.commit()
        print("\nAplicado. Vuelve a pasar: python scripts/reclasificar_generos.py --apply")
    else:
        print("\n(--dry-run · añade --apply; revisa antes)")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
