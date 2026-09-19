"""Rellena el AÑO y la CARÁTULA de las canciones que vinieron de YouTube y se quedaron a medias.

POR QUÉ
-------
La puerta de metadatos exige, para publicar una canción, que tenga año, género, idioma, BPM,
energía, ganancia, duración y carátula. Para el contenido que **sólo existe en YouTube** (mashups,
remixes caseros, sesiones de DJ) no había de dónde sacar el año ni la carátula —Deezer no tiene
ficha de esas canciones—, así que se quedaban en estado `incompleta` **para siempre** y no llegaban
nunca a la aplicación. Se veía así en el registro del recolector:

    aviso: 15 descargadas aún sin completar; se mandarán cuando lo estén

Y ahí se quedaban, incluida la sesión de DJ que el usuario había pedido a mano.

Ya está arreglado de origen (`youtube._download_by_id` devuelve el año de subida del vídeo y su
miniatura). Este guion es para **las que se quedaron atascadas antes**: a cada una le pone el año
(consultando el vídeo) y la carátula (su miniatura, sin consultar nada).

Uso (dentro del contenedor del API, que es donde vive la base del recolector):
    docker exec radiopv-api python /app/scripts/completar_desde_youtube.py
    docker exec radiopv-api python /app/scripts/completar_desde_youtube.py --aplicar
    docker exec radiopv-api python /app/scripts/completar_desde_youtube.py --aplicar --limite 40
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, "/app" if os.path.isdir("/app") else ".")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# La consola de Windows usa cp1252 y revienta con emojis y acentos (pasó: un título con 🔥 mató el
# resumen justo al informar). Todo lo que se imprime va en UTF-8.
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

DIR = os.environ.get("RADIOPV_DATA_DIR", "/app/data")

ap = argparse.ArgumentParser()
ap.add_argument("--aplicar", action="store_true", help="escribe los datos (sin esto sólo informa)")
ap.add_argument("--limite", type=int, default=20, help="cuántas consultar a YouTube por pasada")
ap.add_argument("--base", default="radiov.db", choices=("radiov.db", "backend.db"))
args = ap.parse_args()

con = sqlite3.connect(f"{DIR}/{args.base}")
con.row_factory = sqlite3.Row

filas = con.execute(
    "SELECT id, title, artist, year, cover_url, youtube_id, status FROM tracks"
    " WHERE youtube_id IS NOT NULL AND youtube_id <> ''"
    "   AND (year IS NULL OR cover_url IS NULL)"
    " ORDER BY (year IS NULL) DESC, id DESC").fetchall()

print(f"=== {args.base}: con vídeo de YouTube y sin año o sin carátula: {len(filas)} ===")
if not filas:
    print("   nada que hacer")
    raise SystemExit(0)

por_estado: dict[str, int] = {}
for f in filas:
    por_estado[f["status"] or "(vacío)"] = por_estado.get(f["status"] or "(vacío)", 0) + 1
print(f"   por estado: {por_estado}")

cambios = []
for f in filas[:args.limite]:
    nuevo: dict = {}
    # La carátula se puede deducir sin preguntar a nadie: es la miniatura del vídeo.
    if not f["cover_url"]:
        nuevo["cover_url"] = f"https://i.ytimg.com/vi/{f['youtube_id']}/hqdefault.jpg"
    # El año, por este orden:
    #   1. lo que diga el propio vídeo (fecha de subida);
    #   2. el año que aparece EN EL TÍTULO, que en este contenido es lo normal («Tiktok Mashup
    #      December 2025», «Best of Arijit Singh Mashup 2024», «The Best Party Mix 2025»);
    #   3. y si no se sabe, se deja vacío: la canción se publica igual (el año ya no bloquea a lo
    #      que sólo existe en YouTube). Mejor un mashup que suena sin fecha que una fecha perfecta
    #      que no suena.
    if not f["year"]:
        import re
        en_titulo = re.search(r"\b(19[5-9]\d|20[0-4]\d)\b", f["title"] or "")
        if en_titulo:
            nuevo["year"] = int(en_titulo.group(1))
        else:
            try:
                import yt_dlp
                # MISMAS cabeceras que la descarga. Sin el User-Agent de un navegador, YouTube
                # contesta «Sign in to confirm you're not a bot» a la consulta de metadatos.
                from radiov.youtube import UA, _ano_de_upload
                opts = {"quiet": True, "no_warnings": True, "skip_download": True,
                        "socket_timeout": 20, "retries": 2,
                        "http_headers": {"User-Agent": UA,
                                         "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"}}
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(
                        f"https://www.youtube.com/watch?v={f['youtube_id']}", download=False)
                ano = _ano_de_upload(info or {})
                if ano:
                    nuevo["year"] = ano
            except Exception as e:  # noqa: BLE001
                print(f"   aviso: no se pudo preguntar por {f['youtube_id']}: {str(e)[:60]}")
    if nuevo:
        cambios.append((f, nuevo))
        print(f"   id={f['id']:<6} {f['artist']} - {f['title']}"[:95])
        print(f"        {nuevo}")

if args.aplicar and cambios:
    for f, nuevo in cambios:
        sets = ", ".join(f"{k}=?" for k in nuevo)
        con.execute(f"UPDATE tracks SET {sets} WHERE id=?", tuple(nuevo.values()) + (f["id"],))
    con.commit()
    print(f"\n[OK] {len(cambios)} fichas completadas. Ahora el recolector las analizará y publicará.")
elif cambios:
    print(f"\n[..] {len(cambios)} fichas se pueden completar: añade --aplicar")
else:
    print("\n[i] no se pudo completar ninguna")

con.close()
