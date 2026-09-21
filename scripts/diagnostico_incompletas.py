"""¿Por que 279 pistas se quedan 'incompleta'? ¿Que campo falta exactamente y desde cuando?"""
import os
import sqlite3
import sys

# La consola de Windows (cp1252) revienta con algunos caracteres: un evento con emoji mataba el
# informe justo al imprimirlo (pasó con «⏳ Incompleta …»). Se imprime en UTF-8 y, si algo no se puede
# representar, se sustituye.
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

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

# Muestra con la ficha a la vista: sin esto sólo se ven recuentos y no se puede decidir NADA (¿tiene
# vídeo del que sacar el año?, ¿tiene la carátula ya descargada?, ¿es una recuperada del disco?).
LIMITE = int(os.environ.get("MUESTRA", "12"))
print(f"\nmuestra (hasta {LIMITE}):")
for r in con.execute("SELECT * FROM tracks WHERE status='incompleta' ORDER BY id LIMIT ?",
                     (LIMITE,)):
    faltan = [c for c in CAMPOS if not r[c]]
    tiene = ("yt" if r["youtube_id"] else "--") + " " + ("dz" if r["deezer_id"] else "--") + \
            " " + ("caratula-fichero" if r["cover_path"] else "sin-caratula")
    print(f"   id={r['id']:<6} [{(r['source'] or '?'):10}] falta={','.join(faltan) or 'NADA':28} "
          f"[{tiene:26}] {(r['artist'] or '')[:20]} - {(r['title'] or '')[:34]}")

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
