#!/usr/bin/env python
"""Ficheros de música que NO tiene ninguna ficha: ocupan disco y nadie los puede escuchar.

POR QUÉ EXISTE
--------------
El envío del PC manda primero la ficha y después el audio. Si algo se corta en medio (un envío
colgado, un corte de red, una vuelta que muere), el fichero puede llegar sin ficha o quedarse a
medias: son megas ocupados que no aparecen en ninguna lista y que no hay forma de encontrar mirando
la aplicación. También aparecen al revés (ficha sin fichero, eso lo dice `publicadas_sin_fichero.py`).

Este guion compara el DISCO con las DOS bases y enseña lo que sobra. No borra nada sin `--borrar`, y
cuando borra sólo toca ficheros de audio **con más de 6 horas** (un envío en marcha tiene un fichero
creciendo que todavía no tiene ficha: borrarlo sería romper la subida que está funcionando).

Uso (dentro del contenedor del API):
    docker exec radiopv-api python /app/scripts/ficheros_huerfanos.py
    docker exec radiopv-api python /app/scripts/ficheros_huerfanos.py --borrar
"""
import argparse
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

DIR = os.environ.get("RADIOPV_DATA_DIR", "/app/data")
RAIZ = Path(os.environ.get("RADIOPV_BASE_MUSIC") or os.environ.get("MUSIC_ROOT") or "/music")
BASES = ("radiov.db", "backend.db")
AUDIO = (".mp3", ".m4a", ".flac", ".opus", ".wav", ".aac", ".ogg")
HORAS_MINIMAS = 6


def _rutas_en_las_bases() -> set[str]:
    conocidas: set[str] = set()
    for base in BASES:
        ruta = f"{DIR}/{base}"
        if not os.path.exists(ruta):
            continue
        con = sqlite3.connect(ruta)
        try:
            for (fp,) in con.execute("SELECT file_path FROM tracks WHERE file_path IS NOT NULL"):
                p = str(fp).replace("\\", "/").strip().lstrip("/")
                conocidas.add(p.lower())
                # Los ficheros pueden estar con el prefijo de la carpeta de la música («MusicaRadioPV/…»)
                # según de dónde vinieran: se aceptan las dos formas para no borrar algo que sí tiene
                # ficha.
                partes = p.split("/", 1)
                if len(partes) == 2:
                    conocidas.add(partes[1].lower())
        finally:
            con.close()
    return conocidas


def _claves_de_canciones() -> set[str]:
    """Los TÍTULOS normalizados de todo el catálogo, para no borrar música que nadie más tiene.

    Se compara por TÍTULO y no por «artista - título» del nombre del fichero, porque los ficheros
    huérfanos llevan a menudo un artista mal puesto o inventado («Fonsi - Échame la culpa (3).mp3»
    cuando en el catálogo está como «Luis Fonsi - Échame la culpa.mp3», o «Álex y Christina - Chu
    chu.mp3» para un tema de Alejandro Fernández). Con la comparación estricta, once de los catorce
    huérfanos salían como «música única» y no lo eran: son copias de algo que la aplicación ya toca.

    Si el título NO está en el catálogo, no se borra: puede ser música que sólo existe en ese fichero.
    """
    from radiov.db import clave_cancion

    titulos: set[str] = set()
    for base in BASES:
        ruta = f"{DIR}/{base}"
        if not os.path.exists(ruta):
            continue
        con = sqlite3.connect(ruta)
        try:
            for (title,) in con.execute("SELECT title FROM tracks WHERE title IS NOT NULL"):
                # `clave_cancion` normaliza (sin tildes, sin paréntesis de ruido…): se usa sólo la
                # parte del título.
                titulos.add(clave_cancion("", title).split("|", 1)[-1])
        finally:
            con.close()
    return titulos


def _posible_clave(p: Path) -> str:
    """Título que se deduce del nombre del fichero («Artista - Tema (3).mp3» → «tema»)."""
    from radiov.db import clave_cancion

    nombre = re.sub(r"\s*\(\d+\)\s*$", "", p.stem).strip()
    titulo = nombre.split(" - ", 1)[1] if " - " in nombre else nombre
    return clave_cancion("", titulo).split("|", 1)[-1]


def main() -> int:
    ap = argparse.ArgumentParser(description="Ficheros de música sin ficha (ocupan disco para nada).")
    ap.add_argument("--borrar", action="store_true", help="bórralos (sólo si tienen más de 6 horas)")
    ap.add_argument("--horas", type=float, default=HORAS_MINIMAS,
                    help=f"antigüedad mínima para borrar (por defecto {HORAS_MINIMAS} h)")
    ap.add_argument("--limite", type=int, default=25, help="cuántos enseñar")
    args = ap.parse_args()

    conocidas = _rutas_en_las_bases()
    print(f"rutas con ficha en las dos bases: {len(conocidas)}")
    print(f"música: {RAIZ}")

    huerfanos: list[tuple[Path, float]] = []
    total_mb = 0.0
    for p in RAIZ.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in AUDIO:
            continue
        rel = str(p.relative_to(RAIZ)).replace("\\", "/").lower()
        if rel in conocidas:
            continue
        try:
            mb = p.stat().st_size / 1024 / 1024
            edad_h = (time.time() - p.stat().st_mtime) / 3600
        except OSError:
            continue
        huerfanos.append((p, mb))
        total_mb += mb
        if len(huerfanos) <= args.limite:
            print(f"   {mb:7.1f} MB  {edad_h:6.1f} h  {p.relative_to(RAIZ)}"[:140])
    print(f"\nsin ficha: {len(huerfanos)} ficheros · {total_mb:.1f} MB")

    if not huerfanos:
        print("Nada que limpiar: cada fichero del disco tiene su ficha.")
        return 0

    # Sólo se borra lo que tiene copia segura en el catálogo (misma canción, otra ficha).
    claves = _claves_de_canciones()
    con_copia = [(p, mb) for p, mb in huerfanos if _posible_clave(p) in claves]
    sin_copia = [(p, mb) for p, mb in huerfanos if _posible_clave(p) not in claves]
    print(f"   de ellos, {len(con_copia)} son copias de una canción que YA está en el catálogo "
          f"({sum(mb for _p, mb in con_copia):.1f} MB)")
    print(f"   y {len(sin_copia)} NO se corresponden con ninguna canción del catálogo "
          f"({sum(mb for _p, mb in sin_copia):.1f} MB) → no se borran solos")
    for p, mb in sin_copia[:10]:
        print(f"      {mb:7.1f} MB  {p.relative_to(RAIZ)}"[:130])

    if args.borrar:
        borrados = 0
        liberado = 0.0
        for p, mb in con_copia:
            try:
                if (time.time() - p.stat().st_mtime) / 3600 < args.horas:
                    continue          # puede ser un envío en marcha: no se toca
                p.unlink()
                borrados += 1
                liberado += mb
            except OSError:
                continue
        print(f"\nborrados {borrados} ficheros · {liberado:.1f} MB liberados")
        print("(los de menos de %.0f h se han dejado: pueden estar subiéndose ahora mismo)" % args.horas)
    else:
        print("\n(--dry-run · añade --borrar para liberar ese espacio)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
