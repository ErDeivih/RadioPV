import sqlite3, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
for nombre in ("backend.db", "radiov.db"):
    con = sqlite3.connect("/app/data/" + nombre)
    print(f"=== {nombre} ===")
    for r in con.execute("SELECT COALESCE(language,'(vacio)') l, COUNT(*) n FROM tracks GROUP BY l ORDER BY n DESC"):
        print(f"   {r[0]:<8} {r[1]}")
    con.close()
