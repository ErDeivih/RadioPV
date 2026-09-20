#!/usr/bin/env python
"""Arregla fichas cuya ruta quedó ABSOLUTA (del PC) y deja el fichero donde la biblioteca lo busca.

POR QUÉ EXISTE (fallo real, 20/09/2026)
---------------------------------------
En el PC la ficha guarda la ruta absoluta (`E:\\MusicaRadioPV\\catalogada\\…`) hasta que el organizador
la pasa a relativa, en la fase de mantenimiento de la vuelta. Tres canciones de tech house se
publicaron antes de esa fase y llegaron al servidor así. Dos consecuencias, las dos silenciosas:

  · la canción **aparecía en la aplicación y no sonaba** (en el servidor `/music/E:/…` no existe);
  · su audio se subió con esa ruta como nombre, así que el fichero cayó en `/music/MusicaRadioPV/…`
    en vez de en `/music/catalogada/…`, donde está el resto de la biblioteca.

La causa está arreglada en los dos lados (`radiov.config.a_ruta_relativa_musica`: el PC antes de
mandar y el servidor al recibir). Este guion es para lo que YA entró mal: reescribe la ruta en las
DOS bases y trae el fichero a su sitio si lo encuentra por el nombre.

Uso (dentro del contenedor del API):
    docker exec radiopv-api python /app/scripts/reparar_rutas.py            # dry-run: qué haría
    docker exec radiopv-api python /app/scripts/reparar_rutas.py --apply
"""
import argparse
import os
import shutil
import sqlite3
import sys
from pathlib import Path

for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

DIR = os.environ.get("RADIOPV_DATA_DIR", "/app/data")
RAIZ = Path(os.environ.get("RADIOPV_BASE_MUSIC") or os.environ.get("MUSIC_ROOT") or "/music")
BASES = ("radiov.db", "backend.db")

sys.path.insert(0, "/app" if os.path.isdir("/app") else ".")
from radiov.config import a_ruta_relativa_musica  # noqa: E402


def _es_absoluta(ruta: str) -> bool:
    p = (ruta or "").replace("\\", "/")
    return bool(p) and (p.startswith("/") or (len(p) > 1 and p[1] == ":") or p.lower().startswith("musicaradiopv/"))


def _indice_por_nombre() -> dict[str, list[Path]]:
    """Todos los ficheros de música por nombre, de UNA pasada (son ~6.000)."""
    indice: dict[str, list[Path]] = {}
    for p in RAIZ.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".mp3", ".m4a", ".flac", ".opus", ".wav"):
            indice.setdefault(p.name.lower(), []).append(p)
    return indice


def main() -> int:
    ap = argparse.ArgumentParser(description="Arregla rutas absolutas de fichas del recolector.")
    ap.add_argument("--apply", action="store_true", help="escribir los cambios (sin esto, dry-run)")
    args = ap.parse_args()

    malas: dict[str, str] = {}          # ruta_mala -> ruta_buena (relativa)
    filas_por_base: dict[str, list[tuple[int, str]]] = {}
    for base in BASES:
        ruta = f"{DIR}/{base}"
        if not os.path.exists(ruta):
            print(f"=== {base}: no existe, se salta")
            continue
        con = sqlite3.connect(ruta)
        filas = [(i, fp) for i, fp in con.execute("SELECT id, file_path FROM tracks")
                 if fp and _es_absoluta(fp)]
        con.close()
        filas_por_base[base] = filas
        print(f"=== {base}: {len(filas)} fichas con ruta absoluta")
        for i, fp in filas:
            buena = a_ruta_relativa_musica(fp, RAIZ)
            malas[fp] = buena
            print(f"   id={i:<6} {fp[:70]}")
            print(f"           → {buena}")

    if not malas:
        print("\nNada que arreglar: ninguna ruta absoluta. (Es lo normal desde el arreglo del 20/09.)")
        return 0

    indice = _indice_por_nombre()
    movidos = 0
    for mala, buena in malas.items():
        destino = RAIZ / buena
        if destino.exists():
            print(f"\n   ya está en su sitio: {buena}")
            continue
        candidatos = indice.get(Path(buena).name.lower(), [])
        if len(candidatos) != 1:
            print(f"\n   AVISO: no sé de dónde traer «{Path(buena).name}» "
                  f"({len(candidatos)} candidatos): la ficha se arregla, el fichero no")
            continue
        origen = candidatos[0]
        print(f"\n   mover: {origen} → {destino}")
        if args.apply:
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(origen), str(destino))
            movidos += 1

    if args.apply:
        for base, filas in filas_por_base.items():
            con = sqlite3.connect(f"{DIR}/{base}")
            for i, fp in filas:
                con.execute("UPDATE tracks SET file_path=? WHERE id=?",
                            (a_ruta_relativa_musica(fp, RAIZ), i))
            con.commit()
            con.close()
            print(f"   {base}: {len(filas)} rutas reescritas")
        print(f"\nAplicado. Ficheros movidos: {movidos}.")
        print("Recuerda: el worker `sync_catalogo` propaga radiov.db → backend.db cada 30 min.")
    else:
        print(f"\n(--dry-run · movería {len([m for m in malas if not (RAIZ / malas[m]).exists()])} "
              f"ficheros · añade --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
