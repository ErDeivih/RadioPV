"""Prueba la busqueda de mashups y sesiones EN YOUTUBE (la que faltaba).

Las semillas de mashup pedian candidatos a Deezer, y Deezer no tiene ese contenido: por eso el
catalogo tenia 40 pistas de ese tipo. Esto comprueba que la busqueda en YouTube encuentra y
descarga de verdad.

Uso:
    .venv\\Scripts\\python.exe pc\\probar_busqueda_youtube.py "mashup reggaeton" 2
    .venv\\Scripts\\python.exe pc\\probar_busqueda_youtube.py "sesion de reggaeton viejo" 1
"""
from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    from pc.recolector_pc import cargar_config, preparar_entorno

    cfg = cargar_config()
    preparar_entorno(cfg)

    from radiov import db, pipeline, quality, youtube as Y

    consulta = sys.argv[1] if len(sys.argv) > 1 else "mashup reggaeton"
    cuantos = int(sys.argv[2]) if len(sys.argv) > 2 else 2

    db.init_db()
    print(f"Buscando en YouTube: «{consulta}» (a mirar 8, a descargar {cuantos})\n")

    candidatos = Y.search_videos(consulta, 8)
    print(f"resultados encontrados: {len(candidatos)}")
    for c in candidatos:
        artista, titulo = pipeline._partir_titulo(c)
        tipo = quality.clasificar(titulo, artista, c.get("duration"))
        ya = " (ya está)" if db.track_exists(c.get("id")) else ""
        print(f"   [{str(tipo):7}] {int((c.get('duration') or 0) // 60):>3} min  "
              f"{(c.get('channel') or '')[:22]:22} | {(c.get('title') or '')[:52]}{ya}")

    print(f"\nDescargando hasta {cuantos}…")
    t0 = time.time()
    nuevos = pipeline.process_youtube_seed(
        {"mode": "youtube", "query": consulta, "genre": "reggaeton", "language": "es"},
        max_downloads=cuantos)
    print(f"  añadidas: {nuevos}  ({time.time() - t0:.0f} s)")

    con = db.get_conn()
    con.row_factory = sqlite3.Row
    for r in con.execute(
            "SELECT title, artist, duration, status, is_remix, file_path FROM tracks "
            "ORDER BY id DESC LIMIT ?", (max(nuevos, 1),)):
        tipo = quality.clasificar(r["title"] or "", r["artist"] or "", r["duration"])
        ruta = Path(cfg["musica_local"]) / str(r["file_path"] or "")
        print(f"   [{r['status']:10}] [{str(tipo):7}] {int((r['duration'] or 0) // 60):>3} min  "
              f"{(r['artist'] or '')[:20]} - {(r['title'] or '')[:40]}"
              f"  {'FICHERO OK' if ruta.exists() else 'SIN FICHERO'}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
