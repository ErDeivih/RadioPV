"""Une las canciones repetidas que quedaron de antes: una ficha por canción.

QUÉ ES ESTO
-----------
Antes de arreglar la comprobación de duplicados, el PC bajaba y enviaba la misma canción varias veces
(otro vídeo del mismo tema, o el nombre con «(Official Video)»). Quedaron **35 vídeos con más de una
ficha**, y como cada ficha tiene su propio fichero, eso son varias copias del mismo audio en el disco
y la misma canción saliendo dos o tres veces en la aplicación.

Es CUIDADOSO A PROPÓSITO:
  · Agrupa sólo lo que es **seguro** que es lo mismo: mismo `youtube_id` (es el mismo vídeo, luego la
    misma grabación) y, aparte, misma clave normalizada de artista+título.
  · De cada grupo **se queda una**: la que suena (estado `descargada`) y tiene fichero, y si hay
    varias, la que tiene más datos (año, carátula, ganancia, popularidad).
  · Las demás se marcan **`retirada`** (desaparecen de la aplicación y se pueden recuperar: no se
    borra nada de la base).
  · Los ficheros de las retiradas **sólo se borran si se pide** (`--borrar-ficheros`) y **nunca** si
    ninguna ficha del grupo tiene audio: en ese caso no se toca el grupo entero.
  · Sin `--aplicar` no escribe nada: enseña lo que haría.

Uso (dentro del contenedor del API):
    docker exec radiopv-api python /app/scripts/unificar_duplicadas.py
    docker exec radiopv-api python /app/scripts/unificar_duplicadas.py --aplicar
    docker exec radiopv-api python /app/scripts/unificar_duplicadas.py --aplicar --borrar-ficheros
"""


import argparse
import os
import re
import sqlite3
import sys
from pathlib import Path

# La consola de Windows usa cp1252: un título con emoji o acentos mata el guion justo al imprimir
# (pasó con «Tiktok Mashup 💗2025💗»). Todo lo que se imprime va en UTF-8 y, si algo no se puede
# representar, se sustituye en vez de reventar: un informe a medias es peor que uno con un carácter
# raro.
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

sys.path.insert(0, "/app" if os.path.isdir("/app") else ".")

DIR = os.environ.get("RADIOPV_DATA_DIR", "/app/data")
RAIZ = Path(os.environ.get("RADIOPV_BASE_MUSIC") or os.environ.get("MUSIC_ROOT") or "/music")

ap = argparse.ArgumentParser()
ap.add_argument("--aplicar", action="store_true", help="escribe los cambios (sin esto sólo informa)")
ap.add_argument("--borrar-ficheros", action="store_true",
                help="borra también el audio de las fichas retiradas (libera disco)")
ap.add_argument("--base", default="radiov.db", choices=("radiov.db", "backend.db"))
ap.add_argument("--limite", type=int, default=10, help="cuántos grupos enseñar")
ap.add_argument("--huerfanos", action="store_true",
                help="sólo borra el audio que no usa NADIE (ni esta base ni la otra)")
ap.add_argument("--sin-ficha", action="store_true",
                help="sólo mira los ficheros de música que NO tienen ninguna ficha que los apunte")
args = ap.parse_args()

from radiov import db as rdb  # noqa: E402

# ---------------------------------------------------------------------------------------------
# MODO «SIN FICHA»: ficheros de audio que ninguna ficha del catálogo apunta
# ---------------------------------------------------------------------------------------------
# POR QUÉ PUEDE HABER FICHEROS ASÍ
# --------------------------------
# El recolector subía el audio ANTES de mandar la ficha. Si la canción ya estaba en el servidor, el
# servidor rechazaba la ficha (bien: no se duplica) pero **el audio ya se había subido**: 5-10 MB por
# canción que se quedaban en `/music` sin que ninguna fila los mencionara. Ocupan disco y no hay
# forma de verlos desde la aplicación ni desde el panel. Ahora el orden es el contrario (ficha
# primero), así que esto limpia lo que quedó de antes.
#
# CUIDADO CON LO QUE NO ES BASURA: se excluyen las carpetas que empiezan por `_` (pruebas, descartes)
# y se comprueba contra LAS DOS bases: si el fichero lo usa cualquier ficha, no se toca.
if args.sin_ficha:
    referenciados: set[str] = set()
    for base in ("radiov.db", "backend.db"):
        ruta = f"{DIR}/{base}"
        if not os.path.exists(ruta):
            continue
        c = sqlite3.connect(ruta)
        try:
            for r in c.execute("SELECT file_path FROM tracks WHERE file_path IS NOT NULL"
                               " AND file_path <> ''"):
                referenciados.add(str(r[0]).replace("\\", "/").lstrip("/"))
        finally:
            c.close()

    sueltos: list[tuple[Path, int]] = []
    for f in RAIZ.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in (".mp3", ".m4a", ".opus", ".flac", ".wav"):
            continue
        rel = str(f.relative_to(RAIZ)).replace("\\", "/")
        if rel.split("/")[0].startswith("_"):
            continue
        if rel not in referenciados:
            try:
                sueltos.append((f, f.stat().st_size))
            except OSError:
                pass

    # NO TODO LO QUE NO TIENE FICHA ES BASURA. Antes de proponer borrar un fichero se comprueba que
    # LA MISMA CANCIÓN siga en el catálogo con su fichero: si no se puede asegurar, se deja quieto y
    # se avisa. Borrar es irreversible; liberar menos espacio no le hace daño a nadie.
    con = sqlite3.connect(f"{DIR}/radiov.db")
    con.row_factory = sqlite3.Row
    activas: dict[str, str] = {}          # clave normalizada → ruta en el catálogo
    try:
        for r in con.execute("SELECT artist, title, file_path FROM tracks"
                             " WHERE file_path IS NOT NULL AND file_path <> ''"
                             " AND status != 'retirada'"):
            activas[rdb.clave_cancion(r["artist"] or "", r["title"] or "")] = r["file_path"]
    finally:
        con.close()

    seguros: list[tuple[Path, int]] = []
    dudosos: list[tuple[Path, int]] = []
    for f, s in sueltos:
        # «Artista - Título (3).mp3» → sin el número de copia ni la extensión
        nombre = re.sub(r"\s*\(\d+\)$", "", f.stem)
        partes = nombre.split(" - ", 1)
        artista, titulo = (partes[0], partes[1]) if len(partes) == 2 else ("", partes[0])
        ruta_catalogo = activas.get(rdb.clave_cancion(artista, titulo))
        hay_copia = bool(ruta_catalogo) and (RAIZ / str(ruta_catalogo)).exists()
        (seguros if hay_copia else dudosos).append((f, s))

    total_todos = sum(s for _f, s in sueltos)
    print(f"ficheros de música SIN ficha que los apunte: {len(sueltos)} ({total_todos / 1048576:.1f} MB)")
    print(f"   con copia segura en el catálogo (borrables): {len(seguros)} "
          f"({sum(s for _f, s in seguros) / 1048576:.1f} MB)")
    print(f"   sin poder asegurarlo (NO se tocan): {len(dudosos)} "
          f"({sum(s for _f, s in dudosos) / 1048576:.1f} MB)")
    for f, s in sorted(seguros, key=lambda x: -x[1])[:12]:
        print(f"      {s / 1048576:7.1f} MB  {f.relative_to(RAIZ)}")
    if dudosos:
        print("   los dudosos, para mirarlos a mano:")
        for f, s in sorted(dudosos, key=lambda x: -x[1])[:8]:
            print(f"      {s / 1048576:7.1f} MB  {f.relative_to(RAIZ)}")

    if args.aplicar and seguros:
        borrados = liberado = 0
        for f, s in seguros:
            try:
                f.unlink()
                borrados += 1
                liberado += s
            except OSError as e:
                print(f"   no se pudo borrar {f}: {e}")
        print(f"\n[OK] {borrados} ficheros borrados ({liberado / 1048576:.1f} MB liberados)")
    elif seguros:
        print("\n[..] añade --aplicar para borrar los que tienen copia segura")
    raise SystemExit(0)

# ---------------------------------------------------------------------------------------------
# MODO «HUÉRFANOS»: borrar audio que no usa ninguna ficha ACTIVA de ninguna de las dos bases
# ---------------------------------------------------------------------------------------------
# POR QUÉ ASÍ Y NO «--borrar-ficheros» A SECAS
# --------------------------------------------
# Las dos bases pueden haber elegido copias DISTINTAS como buena (sus ids no tienen nada que ver).
# Si se borrara el fichero de la copia retirada en una base, se podría estar borrando justo la copia
# que la OTRA base conserva, y la canción se quedaría sin audio. La regla segura es más simple: un
# fichero se borra sólo si **ninguna ficha en estado visible, en ninguna de las dos bases, lo usa**.
# Así nunca se borra la única copia; en el peor caso no se libera todo, y eso es aceptable.
ACTIVAS = ("descargada", "incompleta", "cuarentena", "pendiente", "perdida")

if args.huerfanos:
    en_uso: set[str] = set()
    for base in ("radiov.db", "backend.db"):
        ruta = f"{DIR}/{base}"
        if not os.path.exists(ruta):
            continue
        c = sqlite3.connect(ruta)
        try:
            q = ",".join("?" * len(ACTIVAS))
            for r in c.execute(f"SELECT file_path FROM tracks WHERE file_path IS NOT NULL"
                               f" AND file_path <> '' AND status IN ({q})", ACTIVAS):
                en_uso.add(str(r[0]).replace("\\", "/").lstrip("/"))
        finally:
            c.close()

    candidatos: list[Path] = []
    for base in ("radiov.db", "backend.db"):
        ruta = f"{DIR}/{base}"
        if not os.path.exists(ruta):
            continue
        c = sqlite3.connect(ruta)
        try:
            for r in c.execute("SELECT file_path FROM tracks WHERE file_path IS NOT NULL"
                               " AND file_path <> '' AND status = 'retirada'"):
                rel = str(r[0]).replace("\\", "/").lstrip("/")
                if rel not in en_uso:
                    candidatos.append(RAIZ / rel)
        finally:
            c.close()

    unicos = sorted({p for p in candidatos})
    pesan = [(p, p.stat().st_size) for p in unicos if p.exists()]
    total = sum(s for _p, s in pesan)
    print(f"ficheros de canciones retiradas que NO usa ninguna ficha visible: {len(pesan)}")
    print(f"espacio que ocupan: {total / 1048576:.1f} MB")
    for p, s in sorted(pesan, key=lambda x: -x[1])[:10]:
        print(f"   {s / 1048576:7.1f} MB  {p.relative_to(RAIZ)}")
    if args.aplicar:
        borrados = liberado = 0
        for p, s in pesan:
            try:
                p.unlink()
                borrados += 1
                liberado += s
            except OSError as e:
                print(f"   no se pudo borrar {p}: {e}")
        print(f"\n[OK] {borrados} ficheros borrados ({liberado / 1048576:.1f} MB liberados)")
    else:
        print("\n[..] añade --aplicar para borrarlos")
    raise SystemExit(0)

con = sqlite3.connect(f"{DIR}/{args.base}")
con.row_factory = sqlite3.Row


def tiene_fichero(f) -> bool:
    fp = f["file_path"] or ""
    return bool(fp) and (RAIZ / fp).exists()


def puntuacion(f) -> tuple:
    """Cuanto más alto, mejor candidata a quedarse."""
    return (
        1 if (f["status"] or "") == "descargada" else 0,
        1 if tiene_fichero(f) else 0,
        sum(1 for c in ("year", "cover_url", "cover_path", "gain_db", "energy", "bpm", "duration",
                        "youtube_id", "deezer_id") if f[c] if c in f.keys()),
        f["rank"] or 0,
        f["id"],
    )


filas = con.execute("SELECT * FROM tracks").fetchall()
columnas = set(filas[0].keys()) if filas else set()

# --- grupos: por vídeo (seguro) y por clave normalizada (probable) ---
grupos: list[tuple[str, list]] = []
por_video: dict[str, list] = {}
for f in filas:
    yt = (f["youtube_id"] or "").strip() if "youtube_id" in columnas else ""
    if yt:
        por_video.setdefault(yt, []).append(f)
for yt, fs in por_video.items():
    if len(fs) > 1:
        grupos.append((f"mismo vídeo {yt}", fs))

ids_ya = {f["id"] for _m, fs in grupos for f in fs}
por_clave: dict[str, list] = {}
for f in filas:
    if f["id"] in ids_ya:
        continue
    por_clave.setdefault(rdb.clave_cancion(f["artist"] or "", f["title"] or ""), []).append(f)
for clave, fs in por_clave.items():
    if len(fs) > 1 and clave.strip("|"):
        grupos.append((f"misma canción «{clave}»", fs))

print(f"=== {args.base}: {len(grupos)} grupos de canciones repetidas "
      f"({sum(len(fs) - 1 for _m, fs in grupos)} fichas de más) ===\n")

retirar: list = []
redirigir: list[tuple[int, int]] = []      # (ficha_que_sobra, ficha_que_se_queda)
ficheros: list[Path] = []
mb = 0.0
saltados = 0
for motivo, fs in grupos[:args.limite]:
    orden = sorted(fs, key=puntuacion, reverse=True)
    se_queda, sobran = orden[0], orden[1:]
    if not tiene_fichero(se_queda):
        # Ninguna del grupo tiene audio: no se toca (podrían ser dos canciones distintas con el
        # mismo nombre y sin fichero, y retirarlas no arreglaría nada).
        saltados += 1
        continue
    print(f"   [{motivo}]")
    print(f"      SE QUEDA  id={se_queda['id']:<6} [{se_queda['status']}] "
          f"{se_queda['artist']} - {se_queda['title']}"[:115])
    for f in sobran:
        pesa = (RAIZ / (f["file_path"] or "")).stat().st_size if tiene_fichero(f) else 0
        mb += pesa / 1048576
        retirar.append(f["id"])
        redirigir.append((f["id"], se_queda["id"]))
        if tiene_fichero(f):
            ficheros.append(RAIZ / f["file_path"])
        print(f"      se retira id={f['id']:<6} [{f['status']}] {f['title']}"[:100]
              + (f"  ({pesa / 1048576:.1f} MB)" if pesa else ""))

# ¿Está alguna de las que se retiran en una lista del usuario o en sus «me gusta»? Entonces hay que
# APUNTAR ESAS REFERENCIAS A LA QUE SE QUEDA: si no, la canción desaparecería de su lista (la lista
# sigue apuntando a una ficha retirada, que ya no suena) y perdería el «me gusta».
en_listas = 0
en_gustos = 0
for sobra, queda in redirigir:
    en_listas += con.execute("SELECT COUNT(*) FROM playlist_tracks WHERE track_id=?",
                             (sobra,)).fetchone()[0]
    en_gustos += con.execute("SELECT COUNT(*) FROM reactions WHERE track_id=?",
                             (sobra,)).fetchone()[0]

print(f"\n   fichas a retirar: {len(retirar)}")
print(f"   audio redundante: {mb:.1f} MB")
print(f"   referencias en listas que se reapuntarán: {en_listas}")
print(f"   «me gusta» que se reapuntarán: {en_gustos}")
if saltados:
    print(f"   grupos saltados (ninguna con fichero): {saltados}")

if args.aplicar and retirar:
    # 1) Reapuntar listas y «me gusta» a la ficha que se queda, ANTES de retirar nada: así la canción
    #    no desaparece de las listas del usuario ni pierde sus corazones.
    for sobra, queda in redirigir:
        con.execute("UPDATE OR IGNORE playlist_tracks SET track_id=? WHERE track_id=?",
                    (queda, sobra))
        con.execute("DELETE FROM playlist_tracks WHERE track_id=?", (sobra,))
        con.execute("UPDATE OR IGNORE reactions SET track_id=? WHERE track_id=?", (queda, sobra))
        con.execute("DELETE FROM reactions WHERE track_id=?", (sobra,))
    con.commit()

    # 2) Retirar las fichas de más (reversible: siguen en la base, sólo salen de la aplicación).
    q = ",".join("?" * len(retirar))
    con.execute(f"UPDATE tracks SET status='retirada' WHERE id IN ({q})", retirar)
    con.commit()
    print(f"\n[OK] {len(retirar)} fichas marcadas como 'retirada' (reversible: siguen en la base)")
    print(f"[OK] {en_listas} referencias de listas y {en_gustos} «me gusta» reapuntados a la copia "
          f"que se queda")

    if args.borrar_ficheros:
        # Sólo se borra audio si la copia que se queda TIENE fichero (se comprobó al agrupar), así que
        # nunca se queda el catálogo sin la canción.
        borrados = 0
        liberado = 0
        for ruta in ficheros:
            try:
                liberado += ruta.stat().st_size
                ruta.unlink()
                borrados += 1
            except OSError as e:
                print(f"   no se pudo borrar {ruta}: {e}")
        print(f"[OK] {borrados} ficheros redundantes borrados ({liberado / 1048576:.1f} MB liberados)")
    else:
        print("[i] el audio redundante sigue en el disco (añade --borrar-ficheros para liberarlo)")
elif not args.aplicar:
    print("\n[..] sólo información: añade --aplicar (y --borrar-ficheros si quieres liberar el audio)")

con.close()
