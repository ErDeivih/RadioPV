import os, sqlite3, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
con = sqlite3.connect(os.environ.get("RADIOPV_DATA_DIR", "/app/data") + "/backend.db")
print("=== idiomas en la base de la aplicacion ===")
for r in con.execute("SELECT COALESCE(language,'(vacio)') l, COUNT(*) n FROM tracks GROUP BY l ORDER BY n DESC"):
    print(f"   {r[0]:<10} {r[1]}")
con.close()
