"""Qué hay en la carpeta de descargas del PC que NO está en el catálogo: basura o música perdida.

POR QUÉ EXISTE
--------------
El recolector guarda dos copias de cada canción: la «en bruto» (`descargas/`) y la catalogada
(`catalogada/`, que es la que se manda al servidor). Cuando una descarga termina bien, la ficha
apunta a `catalogada/…` y la copia en bruto se queda como archivo.

Pero el 19/09/2026, mientras el recolector moría en cada vuelta (el `UNIQUE constraint failed` de la
siembra), pasaron dos cosas: se descargaban canciones y **la ficha no llegaba a crearse** (el programa
se caía antes). Resultado medido: **216 ficheros y 11 GB en `descargas/` que ninguna ficha menciona**,
todos de ese día. Ni se oyen, ni se mandan, ni los limpia nadie.

Este guion los clasifica en dos montones:

  · **REDUNDANTES**: su canción YA está en el catálogo (con su fichero). Es una copia de más: se
    puede borrar sin perder nada.
  · **RECUPERABLES**: su canción NO está en el catálogo. Es música que se descargó y se perdió por el
    camino: en vez de borrarla, se puede meter en el catálogo (el audio ya está bajado).

Uso (en el PC):
    .venv\\Scripts\\python.exe scripts\\limpiar_descargas_pc.py
    .venv\\Scripts\\python.exe scripts\\limpiar_descargas_pc.py --borrar-redundantes
    .venv\\Scripts\\python.exe scripts\\limpiar_descargas_pc.py --importar-recuperables
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import time
import unicodedata
from pathlib import Path

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROYECTO))

for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

ap = argparse.ArgumentParser()
ap.add_argument("--borrar-redundantes", action="store_true",
                help="borra las copias en bruto cuya canción ya está en el catálogo")
ap.add_argument("--importar-recuperables", action="store_true",
                help="mete en el catálogo las que no están (el audio ya está bajado)")
ap.add_argument("--limite", type=int, default=15, help="cuántas enseñar de cada montón")
args = ap.parse_args()

os.environ.setdefault("RADIOPV_DATA_DIR", str(RAIZ_PROYECTO / "_pc_data"))
from radiov import db as rdb  # noqa: E402
from radiov.config import load_settings  # noqa: E402

rdb.init_db()
cfg = load_settings()
carpeta = Path(cfg["download_dir"])

# El catálogo entero (la base del PC conoce TODAS las canciones, también las que están en el
# servidor: las fichas sembradas lo apuntan). Interesa si la canción existe, no dónde está su fichero.
con = rdb.get_conn()
con.row_factory = __import__("sqlite3").Row
catalogo: dict[str, str] = {}
for r in con.execute("SELECT artist, title, status FROM tracks WHERE status != 'retirada'"):
    catalogo[rdb.clave_cancion(r["artist"] or "", r["title"] or "")] = r["status"]
con.close()


def norm(texto: str) -> str:
    t = unicodedata.normalize("NFD", (texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


# Y las claves normalizadas solas (sin artista), para reconocer «Amyy - TIKTOK MASHUP 💕» cuando en el
# catálogo está con otro nombre de artista.
solo_titulo = {clave.split("|", 1)[1] for clave in catalogo if "|" in clave}

ficheros = [p for p in carpeta.rglob("*.mp3")
            if "_descartadas" not in str(p) and "_tmp" not in str(p)]
redundantes: list[tuple[Path, int]] = []
recuperables: list[tuple[Path, int]] = []

for p in ficheros:
    partes = p.stem.split(" - ", 1)
    artista, titulo = (partes[0], partes[1]) if len(partes) == 2 else ("", partes[0])
    clave = rdb.clave_cancion(artista, titulo)
    en_catalogo = clave in catalogo or (titulo and norm(titulo) in solo_titulo)
    try:
        tam = p.stat().st_size
    except OSError:
        continue
    (redundantes if en_catalogo else recuperables).append((p, tam))

print(f"ficheros en {carpeta}: {len(ficheros)} "
      f"({sum(s for _p, s in ficheros and [(p, p.stat().st_size) for p in ficheros]) / 1048576:.1f} MB)")
print(f"\nREDUNDANTES (su canción ya está en el catálogo): {len(redundantes)} "
      f"({sum(s for _p, s in redundantes) / 1048576:.1f} MB)")
for p, s in sorted(redundantes, key=lambda x: -x[1])[:args.limite]:
    print(f"   {s / 1048576:7.1f} MB  {p.name}"[:110])

print(f"\nRECUPERABLES (no están en el catálogo, el audio ya está bajado): {len(recuperables)} "
      f"({sum(s for _p, s in recuperables) / 1048576:.1f} MB)")
for p, s in sorted(recuperables, key=lambda x: -x[1])[:args.limite]:
    print(f"   {s / 1048576:7.1f} MB  {p.name}"[:110])

if args.borrar_redundantes and redundantes:
    liberado = 0
    borrados = 0
    for p, s in redundantes:
        try:
            p.unlink()
            borrados += 1
            liberado += s
        except OSError as e:
            print(f"   no se pudo borrar {p.name}: {e}")
    print(f"\n[OK] {borrados} copias redundantes borradas ({liberado / 1048576:.1f} MB liberados)")
elif redundantes:
    print("\n[..] añade --borrar-redundantes para liberar ese espacio")

if args.importar_recuperables and recuperables:
    # Se importan con el MISMO camino que usa el recolector, para que queden igual que las demás:
    # organizadas en `catalogada/`, con su ficha, y luego el recolector las mandará al servidor.
    #
    # PERO CON DOS FILTROS, porque aquí no se ha pasado por la puerta de calidad (esto no es una
    # descarga, es una recuperación):
    #   1. **duración**: muchas de estas son mezclas de horas (hay ficheros de 400 MB). La puerta de
    #      calidad acepta sesiones de hasta 3 horas; lo que pase de ahí no es una sesión, es una
    #      compilación, y meterlo sería llenar el catálogo de cosas que luego hay que limpiar.
    #   2. **duplicados**: en el montón hay la misma mezcla tres veces. Se mira la clave normalizada
    #      contra el catálogo y contra lo ya importado en esta pasada.
    from mutagen import File as MutagenFile

    from radiov import catalog as _C
    from radiov import quality as _Q

    ya_vistas = set(catalogo)
    metidas = 0
    rechazadas: list[tuple[str, str]] = []
    for p, _s in recuperables:
        partes = p.stem.split(" - ", 1)
        artista, titulo = (partes[0], partes[1]) if len(partes) == 2 else ("", partes[0])
        if not titulo:
            continue
        clave = rdb.clave_cancion(artista, titulo)
        if clave in ya_vistas:
            rechazadas.append((p.name, "ya está (o repetida en el montón)"))
            continue
        try:
            duracion = float(getattr(MutagenFile(str(p)), "info", None).length or 0)
        except Exception:  # noqa: BLE001
            duracion = 0.0
        ok, motivo = _Q.revisar({"title": titulo, "artist": artista, "duration": duracion})
        if not ok:
            rechazadas.append((p.name, f"{motivo} · {int(duracion // 60)} min"))
            continue
        try:
            rec = {
                "title": titulo, "artist": artista, "file_path": str(p),
                "file_size": p.stat().st_size, "source": "recuperada", "duration": duracion,
            }
            destino = _C.organize_track(rec)
            if destino:
                rec["file_path"] = destino
            # 'incompleta': le faltan ganancia, energía y carátula. El recolector las completa y las
            # manda al servidor en las siguientes vueltas (no se publican a medias).
            tid = rdb.add_track({**rec, "status": "incompleta"})
            if tid:
                metidas += 1
                ya_vistas.add(clave)
        except Exception as e:  # noqa: BLE001
            print(f"   no se pudo recuperar {p.name}: {type(e).__name__}: {str(e)[:60]}")

    print(f"\n[OK] {metidas} canciones metidas en el catálogo (el recolector las completará y enviará)")
    if rechazadas:
        print(f"[i] {len(rechazadas)} NO se han metido (no pasan la puerta de calidad o están repetidas):")
        for nombre, motivo in rechazadas[:args.limite]:
            print(f"      {nombre}"[:80])
            print(f"         → {motivo}")
elif recuperables:
    print("\n[..] añade --importar-recuperables para no perder esa música")
