"""¿Por que 279 pistas se quedan 'incompleta'? ¿Que campo falta exactamente y desde cuando?"""
import os
import sqlite3

DB = os.environ.get("RADIOPV_DATA_DIR", "/app/data") + "/radiov.db"
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

CAMPOS = ("year", "genre", "language", "bpm", "energy", "gain_db", "duration", "cover_url")

inc = con.execute("SELECT * FROM tracks WHERE status='incompleta'").fetchall()
print(f"incompletas: {len(inc)}")
falta = {c: 0 for c in CAMPOS}
for r in inc:
    d = dict(r)
    for c in CAMPOS:
        if not d.get(c):
            falta[c] += 1
print("campo que falta -> cuantas:")
for c, n in sorted(falta.items(), key=lambda x: -x[1]):
    print(f"   {c:12s} {n:5d}")

print("\ncombinaciones mas frecuentes:")
from collections import Counter
combos = Counter()
for r in inc:
    d = dict(r)
    combos[",".join(c for c in CAMPOS if not d.get(c))] += 1
for combo, n in combos.most_common(8):
    print(f"   {n:5d}  faltan: {combo}")

print("\n¿tienen fichero en el disco?")
con_fich = sum(1 for r in inc if r["file_path"])
print(f"   con file_path: {con_fich} de {len(inc)}")

print("\n¿solo una tanda? altas por dia de las incompletas:")
for fila in con.execute(
        "SELECT substr(added_at,1,10) dia, COUNT(*) n FROM tracks WHERE status='incompleta' "
        "GROUP BY dia ORDER BY dia DESC LIMIT 10"):
    print(f"   {fila['dia']}  {fila['n']:5d}")

print("\ncomparacion con las publicadas (mismo periodo):")
for fila in con.execute(
        "SELECT status, COUNT(*) n, SUM(CASE WHEN gain_db IS NULL THEN 1 ELSE 0 END) sin_gain, "
        "SUM(CASE WHEN cover_url IS NULL THEN 1 ELSE 0 END) sin_cover FROM tracks GROUP BY status"):
    print(f"   {str(fila['status']):12s} n={fila['n']:5d} sin_gain_db={fila['sin_gain']:5d} "
          f"sin_cover={fila['sin_cover']:5d}")

print("\nultimos eventos que mencionen problemas de analisis:")
for fila in con.execute(
        "SELECT ts, substr(message,1,120) m FROM events WHERE message LIKE '%gain%' "
        "OR message LIKE '%loudnorm%' OR message LIKE '%caratula%' OR message LIKE '%carátula%' "
        "ORDER BY id DESC LIMIT 10"):
    print(f"   {fila['ts']} {fila['m']}")

con.close()
