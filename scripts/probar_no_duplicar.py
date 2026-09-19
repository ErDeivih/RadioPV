"""Comprueba, contra el catálogo de verdad, que importar una canción que YA está no la duplica.

POR QUÉ
-------
El PC comprueba antes de bajar, pero la última defensa está en el servidor: si por lo que sea llega
una ficha de algo que ya tenemos (otro vídeo del mismo tema, el nombre con «(Official Video)», etc.),
el servidor **no puede** crear una ficha nueva. Antes sí la creaba: se comparaba sólo «artista +
título» exactos, y así la biblioteca acabó con dos, tres y hasta cuatro fichas del mismo tema; una de
ellas sin fichero, que es la canción que aparece en la aplicación y no suena.

Este guion coge una canción real del catálogo, le inventa el nombre «sucio» que usaría YouTube y la
manda como si viniera del PC. Lo que tiene que pasar:
  · el número de canciones NO sube,
  · la respuesta dice `repetidas: 1`,
  · y sólo se rellenan huecos vacíos, sin pisar lo que ya había.

Uso (dentro del contenedor del API):
    docker exec radiopv-api python /app/scripts/probar_no_duplicar.py
"""


import os
import sqlite3
import sys

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

DB = os.environ.get("RADIOPV_DATA_DIR", "/app/data") + "/radiov.db"


def cuantas() -> int:
    con = sqlite3.connect(DB)
    try:
        return con.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
    finally:
        con.close()


def una_cancion_real() -> dict:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        r = con.execute(
            "SELECT * FROM tracks WHERE title IS NOT NULL AND title <> ''"
            " AND artist IS NOT NULL AND artist <> '' AND youtube_id IS NOT NULL"
            " ORDER BY id DESC LIMIT 1").fetchone()
        return dict(r)
    finally:
        con.close()


from app.routers.collector import ImportarIn, Rec, importar  # noqa: E402

base = una_cancion_real()
print(f"canción de partida: {base['artist']} - {base['title']}  (id {base['id']})")

antes = cuantas()
print(f"canciones antes: {antes}")

# El mismo tema con OTRO vídeo y el nombre como lo pondría YouTube: es el caso que se duplicaba.
sucio = {
    "title": f"{base['title']} (Official Video)",
    "artist": (base["artist"] or "").upper(),
    "youtube_id": "VIDEODISTINTO123",
    "duration": base.get("duration"),
    "status": "descargada",
    "source": "prueba",
    "file_path": "catalogada/prueba/no-debe-crearse.mp3",
    "album": "Álbum de prueba",
}

respuesta = importar(ImportarIn(pistas=[Rec(**sucio)], origen="prueba"))
despues = cuantas()

print(f"\nrespuesta del servidor: {respuesta}")
print(f"canciones después: {despues}")

ok_no_duplica = despues == antes
ok_lo_dice = respuesta.get("repetidas") == 1 and respuesta.get("nuevas") == 0
print(f"\n  {'OK  ' if ok_no_duplica else 'FALLO'}  no se ha creado una ficha nueva "
      f"({antes} → {despues})")
print(f"  {'OK  ' if ok_lo_dice else 'FALLO'}  el servidor dice que ya la tenía: "
      f"nuevas={respuesta.get('nuevas')} repetidas={respuesta.get('repetidas')}")

# Y lo que se rellenó: sólo huecos, nunca datos que ya estaban.
detalle = (respuesta.get("repetidas_detalle") or [{}])[0]
print(f"  [i]  campos rellenados: {detalle.get('rellenos') or 'ninguno'}")

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
try:
    fila = con.execute("SELECT * FROM tracks WHERE id=?", (base["id"],)).fetchone()
    print(f"  [i]  la ficha original sigue con youtube_id={fila['youtube_id']} "
          f"y su fichero {fila['file_path']}  (no se ha creado otra ficha)")
    print(f"  [i]  álbum tras la importación: {fila['album']!r} "
          f"(sólo se rellenó porque estaba vacío; nunca se pisa lo que ya hay)")

    # LIMPIEZA: la prueba rellena huecos vacíos de una canción REAL (es justo lo que se quiere
    # comprobar), así que hay que devolver esos huecos a como estaban. Sin esto, cada pasada de la
    # prueba dejaría un álbum inventado en una canción del catálogo.
    rellenos = detalle.get("rellenos") or []
    if rellenos:
        sets = ", ".join(f"{c}=?" for c in rellenos if c in fila.keys())
        valores = [base.get(c) for c in rellenos if c in fila.keys()]
        if sets:
            con.execute(f"UPDATE tracks SET {sets} WHERE id=?", valores + [base["id"]])
            con.commit()
            print(f"  [OK] devueltos a vacío los campos que la prueba rellenó: {rellenos}")
finally:
    con.close()

raise SystemExit(0 if (ok_no_duplica and ok_lo_dice) else 1)
