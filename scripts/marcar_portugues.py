"""Busca en el catálogo las canciones que están en PORTUGUÉS (no deben estar).

POR QUÉ
-------
La norma del catálogo es: español (España y Latinoamérica), inglés y, de siempre, italiano y
francés. Portugués no. Pero entraba por dos caminos:

  · las semillas de sesiones de DJ tipo «set dj» devuelven **funk brasileño** en YouTube, y como la
    semilla declaraba `language: "es"`, en la ficha quedaba español y nadie lo detectaba;
  · las semillas portuguesas antiguas (listas de Brasil, barridos por décadas, exploración de
    Anitta/Roberto Carlos) dejaron fichas marcadas `pt` «porque venían de una semilla portuguesa»,
    aunque la canción fuese española: hay salsa de Tito Nieves y Luis Enrique marcada como
    portuguesa. Eso es peor que no marcar nada, porque el panel filtra por idioma y el usuario
    borraría música que sí quiere.

Ahora `radiov.quality.parece_portugues` lo detecta al entrar (y lo manda a cuarentena). Este script
es para lo que YA está dentro.

LAS DOS BASES
-------------
Trabaja sobre **las dos**: `radiov.db` (la biblioteca del recolector, que es la que gestiona el panel
de administración y la que da el recuento del atajo «En portugués») y `backend.db` (la que sirve la
aplicación). Si sólo se marcara una, el recuento del panel y lo que se borra no cuadrarían.

Uso (dentro del contenedor del API):
    docker exec radiopv-api python /app/scripts/marcar_portugues.py
    docker exec radiopv-api python /app/scripts/marcar_portugues.py --cuarentena
    docker exec radiopv-api python /app/scripts/marcar_portugues.py --revertir   # mira antes la lista
"""
import argparse
import os
import sqlite3
import sys

DIR = os.environ.get("RADIOPV_DATA_DIR", "/app/data")
BASES = ("radiov.db", "backend.db")

ap = argparse.ArgumentParser()
ap.add_argument("--cuarentena", action="store_true",
                help="saca de circulación las encontradas (estado cuarentena)")
ap.add_argument("--revertir", action="store_true",
                help="devuelve a su idioma real las fichas que dicen 'pt' sin serlo (míralas antes)")
ap.add_argument("--limite", type=int, default=40, help="cuántas enseñar")
args = ap.parse_args()

sys.path.insert(0, "/app" if os.path.isdir("/app") else ".")
from radiov.catalog import detect_language  # noqa: E402
from radiov.quality import parece_portugues  # noqa: E402

resumen: dict[str, dict] = {}

for nombre in BASES:
    ruta = f"{DIR}/{nombre}"
    if not os.path.exists(ruta):
        print(f"=== {nombre}: no existe, se salta ===")
        continue
    con = sqlite3.connect(ruta)
    con.row_factory = sqlite3.Row
    print(f"\n{'=' * 70}\n=== {nombre}")

    filas = con.execute(
        "SELECT id, title, artist, status, language, file_path, duration FROM tracks").fetchall()
    sospechosas = [f for f in filas if parece_portugues(f["title"] or "", f["artist"] or "")]
    con_fichero = sum(1 for f in sospechosas if f["file_path"])

    print(f"   canciones: {len(filas)} · en portugués: {len(sospechosas)} (con fichero: {con_fichero})")
    por_estado: dict[str, int] = {}
    for f in sospechosas:
        por_estado[f["status"] or "(vacío)"] = por_estado.get(f["status"] or "(vacío)", 0) + 1
    print(f"   por estado: {por_estado or 'ninguna'}")
    print(f"   muestra (hasta {min(args.limite, 8)}):")
    for f in sospechosas[:min(args.limite, 8)]:
        print(f"      id={f['id']:<6} [{str(f['status'])[:10]:<10}] {f['artist']} - {f['title']}"[:110])
    resumen[nombre] = {"total": len(filas), "pt": len(sospechosas)}

    # El idioma se corrige SIEMPRE, aunque no se toque el estado: así el panel de administración
    # puede filtrarlas por idioma (`language = 'pt'`), que es como el usuario hace la limpieza.
    ids = [f["id"] for f in sospechosas if (f["language"] or "") != "pt"]
    if ids:
        q = ",".join("?" * len(ids))
        con.execute(f"UPDATE tracks SET language='pt' WHERE id IN ({q})", ids)
        con.commit()
        print(f"   [OK] {len(ids)} fichas marcadas con idioma 'pt' (filtrables en el panel)")

    if args.cuarentena:
        ids_c = [f["id"] for f in sospechosas if (f["status"] or "") != "cuarentena"]
        if ids_c:
            q = ",".join("?" * len(ids_c))
            con.execute(f"UPDATE tracks SET status='cuarentena' WHERE id IN ({q})", ids_c)
            con.commit()
            print(f"   [OK] {len(ids_c)} sacadas de circulación (cuarentena, reversible)")

    # Y AL REVÉS: fichas que dicen 'pt' y que el detector NO reconoce. Va con `--revertir` a
    # propósito: la lista de marcas es ESTRECHA (para no tirar español), así que hay canciones en
    # portugués que no reconoce y ponerles `other` las perdería de la limpieza. Se enseña y se decide.
    ids_sospechosas = {f["id"] for f in sospechosas}
    dudosas = [f for f in con.execute(
        "SELECT id, title, artist FROM tracks WHERE language='pt'").fetchall()
        if f["id"] not in ids_sospechosas]
    if dudosas:
        print(f"   fichas que dicen 'pt' y el detector NO reconoce: {len(dudosas)}")
        for f in dudosas[:min(args.limite, 6)]:
            print(f"      id={f['id']:<6} {f['artist']} - {f['title']}"[:95]
                  + f"   (serían {detect_language(f['title'] or '', f['artist'] or '')})")
        if args.revertir:
            for f in dudosas:
                con.execute("UPDATE tracks SET language=? WHERE id=?",
                            (detect_language(f["title"] or "", f["artist"] or ""), f["id"]))
            con.commit()
            print(f"   [OK] {len(dudosas)} devueltas a su idioma real")
        else:
            print("   [..] para cambiarlas: --revertir (míralas antes: el detector es estrecho)")

    con.close()

print(f"\n=== resumen: {resumen} ===")
print("Recuerda: el panel de administración enseña el recuento de `radiov.db`, que es la base que")
print("gestiona. El borrado limpia ahora las dos (ver docs/35 en ProyectoServidor).")
