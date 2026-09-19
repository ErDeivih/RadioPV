import sqlite3, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
for nombre in ("radiov.db", "backend.db"):
    con = sqlite3.connect("/app/data/" + nombre)
    con.row_factory = sqlite3.Row
    n = con.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
    prueba = con.execute("SELECT id, title, status FROM tracks WHERE title LIKE '%PRUEBA BORRAR%'").fetchall()
    print(f"=== {nombre}: {n} canciones · fichas de prueba que quedan: {len(prueba)}")
    for r in prueba:
        print(f"      id={r['id']} {r['title']} ({r['status']})")
    con.close()
