"""Veta (lista negra) las canciones del catálogo cuyo fichero de audio no existe.

Por qué hace falta
------------------
El catálogo tiene más canciones que ficheros. La mayoría de las que faltan son simplemente
copias que aún no se han hecho (`copiar-musica.py` va por trozos), así que **no** se pueden
vetar: llegarán. Pero hay un puñado cuyo fichero **no existe ni en el PC de origen**: son
basura de un raspado, con nombres como `meta charset=utf - 8.mp3` o
`it - left17px;positionrelative}.c-s.mp3`. Esos nunca van a sonar: aparecen en las listas, el
reproductor los intenta y los salta, y ensucian todo.

Qué hace
--------
1. Lee `_deploy/radiov.db` (copia local de la base del servidor).
2. Marca las canciones cuyo `file_path` **no está en `E:\\Musica`** (el origen): esas no llegarán.
3. Con `--aplicar`, las veta en el servidor usando el mismo camino que el botón "vetar" del
   panel: `radiov.blacklist.blacklist_song_only`, ejecutado dentro del contenedor `radiopv-api`.

Vetar NO borra nada: sólo hace que no se listen ni se vuelvan a descargar. Se puede deshacer
desde el panel de administración.

Uso:
    python scripts/vetar_sin_fichero.py             # sólo informa
    python scripts/vetar_sin_fichero.py --aplicar   # veta en el servidor
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

RAIZ = Path(__file__).resolve().parent.parent
DB = RAIZ / "_deploy" / "radiov.db"
MUSICA_LOCAL = Path(r"E:\Musica")
SERVIDOR = "david@servidor.local"
CONTENEDOR = "radiopv-api"

# El script que se ejecuta DENTRO del contenedor: allí están la base y la biblioteca `radiov`.
DENTRO = r"""
import json, sys
from radiov import blacklist as rbl
ids = json.loads(sys.argv[1])
vetadas = sum(1 for tid in ids if rbl.blacklist_song_only(tid))
print(json.dumps({"vetadas": vetadas, "solicitadas": len(ids)}))
"""


def sin_fichero_origen() -> list[tuple[int, str]]:
    """(id, file_path) de las canciones cuyo fichero no existe ni en el PC de origen."""
    conn = sqlite3.connect(str(DB))
    try:
        filas = list(conn.execute(
            "SELECT id, file_path FROM tracks WHERE file_path IS NOT NULL AND file_path != ''"))
    finally:
        conn.close()

    fuera: list[tuple[int, str]] = []
    for tid, rel in filas:
        local = MUSICA_LOCAL / Path(str(rel).replace("/", "\\"))
        if not local.is_file():
            fuera.append((int(tid), str(rel)))
    return fuera


def es_basura(rel: str) -> bool:
    """True si el nombre es un fragmento de HTML/CSS, no el de una canción.

    Son restos de un raspado que cogió trozos de la página en vez del título: llevan llaves,
    puntos y coma, almohadillas o «meta charset». Un nombre así no puede ser una canción de
    verdad, de modo que vetarlo no pierde nada.

    En cambio, las que parecen canciones reales NO se vetán solas: puede que su carpeta se
    moviera de sitio y el fichero siga estando en el disco, y vetarlas impediría volver a
    descargarlas.
    """
    señales = ('{', '}', ';', '#', 'charset', 'px)', '}.c', ' - h-p', ' - pub', ' - 8.mp3')
    return any(s in rel for s in señales)


def buscar_en_disco(nombres: list[str]) -> dict[str, list[str]]:
    """Busca por nombre de fichero en todo el árbol de origen.

    Si una canción cuyo `file_path` apunta a un sitio que ya no existe aparece en otro lugar,
    lo más probable es que se moviera de carpeta: entonces se puede ARREGLAR la ruta en vez de
    tirar la canción. Devuelve {nombre: [rutas relativas encontradas]}.
    """
    objetivos = {n.lower() for n in nombres}
    encontrados: dict[str, list[str]] = {}
    for p in MUSICA_LOCAL.rglob("*"):
        if not p.is_file():
            continue
        clave = p.name.lower()
        if clave in objetivos:
            try:
                rel = p.relative_to(MUSICA_LOCAL).as_posix()
            except ValueError:
                rel = str(p)
            encontrados.setdefault(clave, []).append(rel)
    return encontrados


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--aplicar", action="store_true", help="vetar en el servidor (si no, sólo informa)")
    ap.add_argument("--todas", action="store_true",
                    help="vetar también las que parecen canciones reales (¡revisa antes la lista!)")
    ap.add_argument("--buscar", action="store_true",
                    help="buscar las que faltan por nombre en todo el disco de origen")
    args = ap.parse_args()

    print(f"[i] catálogo: {DB}")
    print(f"[i] origen  : {MUSICA_LOCAL}")
    fuera = sin_fichero_origen()
    basura = [(t, r) for t, r in fuera if es_basura(r)]
    dudosas = [(t, r) for t, r in fuera if not es_basura(r)]

    print(f"\n[i] sin fichero en el origen: {len(fuera)}")
    print(f"[i]   · nombres imposibles (fragmentos de HTML/CSS): {len(basura)}")
    for tid, rel in basura:
        print(f"        {tid:6d}  {rel}")
    print(f"[i]   · parecen canciones reales, REVISAR: {len(dudosas)}")
    for tid, rel in dudosas:
        print(f"        {tid:6d}  {rel}")
    if dudosas and not args.todas:
        print("\n      Estas no se vetán: puede que su carpeta se moviera y el fichero siga en el")
        print("      disco. Míralas antes; si de verdad no las quieres, usa --todas.")

    if args.buscar and dudosas:
        print(f"\n[i] buscando por nombre en {MUSICA_LOCAL} (puede tardar)...")
        encontrados = buscar_en_disco([Path(r).name for _, r in dudosas])
        recuperables = 0
        for tid, rel in dudosas:
            nombre = Path(rel).name.lower()
            sitios = encontrados.get(nombre, [])
            if sitios:
                recuperables += 1
                print(f"      {tid:6d}  {Path(rel).name}")
                for s in sitios:
                    print(f"                -> {s}")
        print(f"[i] se podrían ARREGLAR (el fichero está en otro sitio): {recuperables} de {len(dudosas)}")
        if not recuperables:
            print("      ninguna aparece en el disco: su carpeta se borró de verdad")

    ids = [tid for tid, _ in (fuera if args.todas else basura)]

    if not ids:
        print("\n[OK] no hay nada que vetar")
        return 0

    if not args.aplicar:
        print(f"\n[i] sólo información: añade --aplicar para vetar estas {len(ids)} en el servidor")
        return 0

    print(f"\n[i] vetando {len(ids)} canciones en {SERVIDOR} (contenedor {CONTENEDOR})...")
    # El código va en un fichero temporal del servidor y se copia dentro del contenedor: pasar
    # un guion largo por `ssh` rompe con las comillas.
    remoto = "/tmp/vetar_radiopv.py"
    local = RAIZ / "_deploy" / "_vetar_tmp.py"
    local.write_text(DENTRO, encoding="utf-8")
    try:
        subprocess.run(["scp", "-q", str(local), f"{SERVIDOR}:{remoto}"], check=True)
        subprocess.run(
            ["ssh", "-o", "BatchMode=yes", SERVIDOR, f"docker cp {remoto} {CONTENEDOR}:/tmp/v.py"],
            check=True,
        )
        r = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", SERVIDOR,
             f"docker exec {CONTENEDOR} python3 /tmp/v.py '{json.dumps(ids)}'"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
        )
        print("[OK] " + (r.stdout.strip() or "(sin salida)"))
    finally:
        local.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
