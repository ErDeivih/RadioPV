"""Verifica que las transferencias PC -> servidor llegan BIEN (no sólo que lleguen).

Se ejecuta en los dos lados y compara **tamaño y sha1 de los primeros 1 MB**. Eso es lo que de
verdad demuestra que el fichero llegó entero: un tamaño igual no basta, porque una copia cortada
puede rellenarse con ceros y pesar exactamente lo mismo.

    # 1) En el PC: escribe la lista de lo que ha enviado (el guion escribe el fichero él mismo;
    #    NO se usa `>` de PowerShell, que lo guardaría en UTF-16 y lo estropearía)
    .venv\\Scripts\\python.exe pc\\verificar_transferencias.py --lado pc --salida _pc_data\\transferencias_pc.txt

    # 2) Se copia esa lista al servidor y se mete en el contenedor
    scp _pc_data\\transferencias_pc.txt david@servidor.local:/tmp/
    ssh david@servidor.local "docker cp /tmp/transferencias_pc.txt radiopv-api:/tmp/"

    # 3) En el servidor: comprueba SUS ficheros para esas mismas claves
    docker exec radiopv-api python /tmp/verificar.py --lado servidor --claves /tmp/transferencias_pc.txt

    # 4) Y se comparan los dos ficheros
    .venv\\Scripts\\python.exe pc\\comparar_transferencias.py

OJO al buscar en el servidor: hay que buscar **exactamente** las pistas enviadas. No vale «las N
últimas publicadas», porque una pista enviada por el PC puede haber ACTUALIZADO una fila que ya
existía (el alta casa por id de YouTube, id de Deezer o artista+título), así que conserva su id
antiguo y se queda fuera de cualquier lista «por id descendente». Esa fue la razón de que la
primera medición dijera «16 no están en el servidor» cuando estaban todas.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/backend")

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

TROZO = 1024 * 1024          # 1 MB


def sha1_trozo(ruta: Path) -> str:
    h = hashlib.sha1()
    with open(ruta, "rb") as f:
        h.update(f.read(TROZO))
    return h.hexdigest()[:12]


def linea_de(titulo, artista, yt, ruta: Path | None) -> str:
    """titulo|artista|youtube_id|bytes|sha1|fecha"""
    if ruta is None or not ruta.exists():
        return f"{titulo}|{artista}|{yt or ''}|FALTA|FALTA|FALTA"
    import datetime

    fecha = datetime.datetime.fromtimestamp(ruta.stat().st_mtime).isoformat(timespec="seconds")
    return f"{titulo}|{artista}|{yt or ''}|{ruta.stat().st_size}|{sha1_trozo(ruta)}|{fecha}"


def main() -> int:
    # La consola de Windows usa cp1252: sin esto, un título con acentos mata el guion al imprimir.
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--lado", choices=["pc", "servidor"], required=True)
    ap.add_argument("--salida", help="fichero donde escribir el manifiesto (UTF-8)")
    ap.add_argument("--claves", help="manifiesto del PC: qué claves comprobar en el servidor")
    args = ap.parse_args()

    from radiov.config import resolve_music

    db = os.environ.get("RADIOPV_DATA_DIR", "/app/data") + "/radiov.db"
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row

    if args.lado == "pc":
        filas = con.execute(
            """SELECT t.title, t.artist, t.file_path, t.youtube_id FROM pc_enviadas e
               JOIN tracks t ON t.id = e.track_id ORDER BY t.id""").fetchall()
        con.close()
        lineas = [f"# lado=pc pistas={len(filas)}"]
        for r in filas:
            ruta = Path(resolve_music(r["file_path"])) if r["file_path"] else None
            lineas.append(linea_de(r["title"], r["artist"], r["youtube_id"], ruta))
        texto = "\n".join(lineas) + "\n"
        if args.salida:
            Path(args.salida).write_text(texto, encoding="utf-8")
            print(f"manifiesto del PC escrito en {args.salida} ({len(filas)} pistas)")
        else:
            print(texto, end="")
        return 0

    # --- servidor: se comprueban SÓLO las pistas del manifiesto del PC ---
    #
    # Se casa por **id de YouTube**, que es único, y no por «artista + título»: en este catálogo
    # hay canciones repetidas con el mismo nombre (un single y el álbum entero subido como una
    # sola pista, por ejemplo), así que buscar por título encontraba «otra» fila y decía que el
    # fichero era distinto cuando en realidad el enviado estaba perfecto.
    if not args.claves:
        sys.exit("Falta --claves (el manifiesto que ha escrito el PC)")
    por_yt: dict[str, tuple[str, str]] = {}
    por_titulo: set[tuple[str, str]] = set()
    for linea in Path(args.claves).read_text(encoding="utf-8", errors="replace").splitlines():
        if linea.startswith("#") or "|" not in linea:
            continue
        partes = linea.split("|")
        if len(partes) < 3:
            continue
        titulo, artista, yt = partes[0].strip(), partes[1].strip(), partes[2].strip()
        if yt:
            por_yt[yt] = (titulo, artista)
        else:
            por_titulo.add((titulo.lower(), artista.lower()))

    filas = con.execute("SELECT title, artist, file_path, youtube_id FROM tracks").fetchall()
    con.close()

    lineas = [f"# lado=servidor por_youtube_id={len(por_yt)} por_titulo={len(por_titulo)}"]
    vistas: set[str] = set()
    vistas_titulo: set[tuple[str, str]] = set()
    for r in filas:
        yt = (r["youtube_id"] or "").strip()
        clave_titulo = ((r["title"] or "").strip().lower(), (r["artist"] or "").strip().lower())
        if yt and yt in por_yt:
            vistas.add(yt)
        elif not por_yt and clave_titulo in por_titulo:
            vistas_titulo.add(clave_titulo)
        else:
            continue
        ruta = Path(resolve_music(r["file_path"])) if r["file_path"] else None
        lineas.append(linea_de(r["title"], r["artist"], yt, ruta))

    faltan_base = set(por_yt) - vistas
    for yt in sorted(faltan_base):
        titulo, artista = por_yt[yt]
        lineas.append(f"{titulo}|{artista}|{yt}|NO-ESTA|NO-ESTA")
    lineas.append(f"# pistas del PC que no estan en la base del servidor: {len(faltan_base)}")

    texto = "\n".join(lineas) + "\n"
    if args.salida:
        Path(args.salida).write_text(texto, encoding="utf-8")
        print(f"manifiesto del servidor escrito en {args.salida}")
    else:
        print(texto, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
