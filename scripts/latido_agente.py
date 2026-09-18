"""¿El mantenimiento automático del agente estaba corriendo? Se mira por sus propios eventos."""
import os
import sqlite3

DB = os.environ.get("RADIOPV_DATA_DIR", "/app/data") + "/radiov.db"
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

print("=== eventos de mantenimiento (últimos 10) ===")
for fila in con.execute(
        "SELECT ts, substr(message,1,110) m FROM events WHERE message LIKE '%Mantenimiento%' "
        "OR message LIKE '%mantenimiento%' ORDER BY id DESC LIMIT 10"):
    print(f"   {fila['ts']} {fila['m']}")

print("\n=== eventos de agente (últimos 10) ===")
for fila in con.execute(
        "SELECT ts, substr(message,1,110) m FROM events WHERE message LIKE '%Agente%' "
        "OR message LIKE '%republicad%' OR message LIKE '%review%' ORDER BY id DESC LIMIT 10"):
    print(f"   {fila['ts']} {fila['m']}")

print("\n=== reparto de eventos por día (últimos 7) ===")
for fila in con.execute(
        "SELECT substr(ts,1,10) dia, level, COUNT(*) n FROM events "
        "GROUP BY dia, level ORDER BY dia DESC LIMIT 12"):
    print(f"   {fila['dia']} [{fila['level']}] {fila['n']}")

con.close()
