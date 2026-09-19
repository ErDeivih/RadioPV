import sqlite3, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
for nombre in ("radiov.db", "backend.db"):
    con = sqlite3.connect("/app/data/" + nombre)
    cols = [c[1] for c in con.execute("PRAGMA table_info(tracks)")]
    print(f"=== {nombre} ({len(cols)} columnas)")
    print("   ", ", ".join(cols))
    con.close()
