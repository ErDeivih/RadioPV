"""Compara lo que el PC dice haber enviado con lo que el servidor tiene de verdad.

Se ejecuta en LOS DOS sitios (mismo guion): en el PC lee su base local y `pc_enviadas`, y en el
servidor lee la suya. Comparar las dos listas es la forma de ver si un envio se quedo a medias,
que es el fallo mas facil de que pase desapercibido en este reparto.
"""
import os
import sqlite3
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/backend")

# En el PC la base esta en la carpeta de datos local; en el servidor, en /app/data.
DB = os.environ.get("RADIOPV_DATA_DIR", "/app/data") + "/radiov.db"
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

tiene_enviadas = con.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name='pc_enviadas'").fetchone()

if tiene_enviadas:
    print("=== EN EL PC: lo que dice haber enviado ===")
    filas = con.execute(
        """SELECT t.id, t.title, t.artist, t.status, t.gain_db, t.cover_path, e.enviada_en
           FROM pc_enviadas e JOIN tracks t ON t.id = e.track_id ORDER BY e.enviada_en DESC
           LIMIT 12""").fetchall()
    for r in filas:
        print(f"   {r['enviada_en']}  [{r['status']:10}] gain={str(r['gain_db'])[:6]:6} "
              f"{(r['artist'] or '')[:20]} - {(r['title'] or '')[:34]}")
    print(f"   (total enviadas: {con.execute('SELECT COUNT(*) FROM pc_enviadas').fetchone()[0]})")
else:
    print("=== EN EL SERVIDOR: esas mismas pistas ===")

print("\n=== pistas con caratula descargada hoy ===")
for r in con.execute(
        "SELECT id, title, artist, status, gain_db, cover_path FROM tracks "
        "WHERE cover_path IS NOT NULL AND cover_path != '' ORDER BY id DESC LIMIT 12"):
    print(f"   {r['id']:>5} [{r['status']:10}] gain={str(r['gain_db'])[:6]:6} "
          f"{(r['artist'] or '')[:20]} - {(r['title'] or '')[:34]}")

print("\n=== importaciones registradas ===")
for r in con.execute("SELECT ts, message FROM events WHERE message LIKE '%importadas%' "
                     "ORDER BY id DESC LIMIT 5"):
    print(f"   {r['ts']} {r['message'][:60]}")

con.close()
