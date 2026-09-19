"""Prueba de humo del recolector del PC: ¿puede descargar aquí de verdad?

Comprueba la cadena entera en ESTA máquina, sin depender del servidor: buscar en YouTube,
descargar, etiquetar, analizar y guardar la ficha. Es lo primero que hay que mirar si el PC deja
de recolectar, porque falla por cosas del sistema (yt-dlp viejo, ffmpeg fuera del PATH, permisos
en la carpeta de música) y no por el código.

Uso:
    .venv\\Scripts\\python.exe pc\\probar_descarga.py             # busca una que falte y la baja
    .venv\\Scripts\\python.exe pc\\probar_descarga.py --listar    # sólo dice qué falta
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

# Candidatas variadas y poco probables en el catálogo (que se hizo con éxitos y semillas).
CANDIDATAS = [
    ("Kavinsky", "Nightcall"),
    ("Chromatics", "Tick of the Clock"),
    ("Los Zigarros", "Ayer"),
    ("Rigoberta Bandini", "Ay Mama"),
    ("Vetusta Morla", "Copenhague"),
    ("Leiva", "La Llamada"),
    ("Silvia Perez Cruz", "Pequeno Vals"),
    ("C. Tangana", "Demasiadas Mujeres"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Prueba de descarga del recolector del PC")
    ap.add_argument("--listar", action="store_true", help="sólo decir cuáles faltan")
    args = ap.parse_args()

    from pc.recolector_pc import cargar_config, preparar_entorno  # noqa: PLC0415

    cfg = cargar_config()
    preparar_entorno(cfg)

    from radiov import db, pipeline

    db.init_db()
    con = db.get_conn()
    con.row_factory = sqlite3.Row
    faltan = []
    for artista, titulo in CANDIDATAS:
        ya = con.execute("SELECT id, file_path FROM tracks WHERE artist=? AND title=?",
                         (artista, titulo)).fetchone()
        if ya:
            tiene = "con fichero" if (ya["file_path"] or "").strip() else "sólo ficha sembrada"
            print(f"  YA ESTA  {artista} - {titulo}  ({tiene})")
        else:
            print(f"  FALTA    {artista} - {titulo}")
            faltan.append((artista, titulo))
    con.close()

    if args.listar or not faltan:
        if not faltan:
            print("\nNo hay ninguna candidata libre: prueba a añadir otra a la lista.")
        return 0

    artista, titulo = faltan[0]
    print(f"\nDescargando {artista} - {titulo} …")
    t0 = time.time()
    tid = pipeline.fulfill_track(artista, titulo)
    print(f"  id devuelto: {tid}  ({time.time() - t0:.1f} s)")

    con = db.get_conn()
    con.row_factory = sqlite3.Row
    f = con.execute(
        "SELECT title, artist, file_path, duration, bpm, energy, gain_db, status, cover_url, "
        "youtube_id FROM tracks WHERE id=?", (tid,)).fetchone()
    con.close()
    if not f:
        print("  FALLO: no se creó ninguna ficha")
        return 1

    for k in f.keys():
        print(f"    {k:12s} {f[k]}")

    ruta = Path(cfg["musica_local"]) / str(f["file_path"] or "")
    # Sin flechas ni simbolos raros en los mensajes: la consola de Windows usa cp1252 y revienta
    # con caracteres que no estan en esa tabla (paso con el simbolo de flecha).
    print(f"\n  fichero en disco: {ruta} -> {'EXISTE' if ruta.exists() else 'NO EXISTE'}")
    if ruta.exists():
        print(f"  tamano: {ruta.stat().st_size / 1024 / 1024:.1f} MB")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
