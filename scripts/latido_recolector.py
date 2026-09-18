"""Latido del recolector: ¿esta descargando de verdad o solo lo intenta?

Cuenta las altas de las ultimas 24 h y 7 dias, y enseña los ultimos eventos, para poder
distinguir "no descarga nada porque YouTube devuelve 403" de "no hay nada que descargar".
"""
import os
import sqlite3

DB = os.environ.get("RADIOPV_DATA_DIR", "/app/data") + "/radiov.db"
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row


def uno(sql, args=()):
    try:
        return con.execute(sql, args).fetchone()
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


print("=== catalogo (unico DB del recolector) ===")
for fila in con.execute("SELECT status, COUNT(*) n FROM tracks GROUP BY status ORDER BY n DESC"):
    print(f"   {str(fila['status']):14s} {fila['n']:6d}")

print("\n=== altas por dia (ultimos 7) ===")
for fila in con.execute(
        "SELECT substr(added_at,1,10) dia, COUNT(*) n FROM tracks "
        "WHERE added_at IS NOT NULL GROUP BY dia ORDER BY dia DESC LIMIT 7"):
    print(f"   {fila['dia']}  {fila['n']:5d}")

print("\n=== ultimos eventos del recolector ===")
try:
    for fila in con.execute(
            "SELECT ts, level, substr(message,1,110) m FROM events ORDER BY id DESC LIMIT 12"):
        print(f"   {fila['ts']} [{fila['level']}] {fila['m']}")
except Exception as e:  # noqa: BLE001
    print("   (sin tabla events:", e, ")")

print("\n=== cola / pendientes ===")
for fila in con.execute(
        "SELECT status, COUNT(*) n, MIN(added_at) mas_vieja FROM tracks "
        "WHERE status <> 'descargada' GROUP BY status"):
    print(f"   {str(fila['status']):14s} {fila['n']:6d}  desde {fila['mas_vieja']}")

con.close()
