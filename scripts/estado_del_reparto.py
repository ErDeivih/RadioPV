"""Estado del reparto: quien ha mandado cada cosa y quien sigue completando lo que falta.

Sirve para comprobar, despues de mover el recolector al PC, que:
  · lo que manda el PC llega COMPLETO (con gain_db y caratula), y
  · lo que se quedo a medias en el servidor antes del cambio no se abandona.
"""
import os
import sqlite3

DB = os.environ.get("RADIOPV_DATA_DIR", "/app/data") + "/radiov.db"
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

print("=== ultimas 14 pistas (con youtube_id) ===")
print(f"{'id':>6} {'estado':11} {'gain_db':>8} {'caratula':8} {'dur':>5}  artista - titulo")
for r in con.execute(
        "SELECT id, title, artist, status, duration, gain_db, cover_url, cover_path, source "
        "FROM tracks WHERE youtube_id IS NOT NULL ORDER BY id DESC LIMIT 14"):
    print(f"{r['id']:>6} {str(r['status']):11} {str(r['gain_db'])[:8]:>8} "
          f"{'si' if r['cover_path'] else 'no':8} {int((r['duration'] or 0) // 60):>4}m  "
          f"{(r['artist'] or '')[:22]} - {(r['title'] or '')[:34]}")

print("\n=== mantenimiento del agente (ultimos 4) ===")
for r in con.execute("SELECT ts, substr(message,1,70) m FROM events "
                     "WHERE message LIKE '%Mantenimiento%' ORDER BY id DESC LIMIT 4"):
    print(f"   {r['ts']} {r['m']}")

print("\n=== pistas republicadas (ultimas 4) ===")
for r in con.execute("SELECT ts, substr(message,1,70) m FROM events "
                     "WHERE message LIKE '%republicad%' ORDER BY id DESC LIMIT 4"):
    print(f"   {r['ts']} {r['m']}")

print("\n=== importaciones del PC ===")
for r in con.execute("SELECT ts, substr(message,1,70) m FROM events "
                     "WHERE message LIKE '%importadas del recolector%' ORDER BY id DESC LIMIT 4"):
    print(f"   {r['ts']} {r['m']}")

print("\n=== resumen por estado ===")
for r in con.execute("SELECT status, COUNT(*) n FROM tracks GROUP BY status ORDER BY n DESC"):
    print(f"   {str(r['status']):12} {r['n']}")

con.close()
