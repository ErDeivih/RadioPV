"""¿Por qué está en cuarentena lo que está? ¿Cuánto se rechazó SOLO por la duración?

La puerta de calidad corta todo lo que dure más de 15 minutos («corta mezclas de DJ»), así que
las sesiones de DJ —justo lo que el usuario escucha— se quedaban fuera al entrar.
"""

# La consola de Windows usa cp1252: un título con emoji o acentos mata el guion justo al imprimir
# (pasó con «Tiktok Mashup 💗2025💗»). Todo lo que se imprime va en UTF-8 y, si algo no se puede
# representar, se sustituye en vez de reventar: un informe a medias es peor que uno con un carácter
# raro.
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

import os
import re
import sqlite3
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/backend")
from radiov import quality as Q  # noqa: E402

DB = os.environ.get("RADIOPV_DATA_DIR", "/app/data") + "/radiov.db"
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

print("=== cuarentena: por que ===")
motivos = {}
largas = []
cortas = []
for r in con.execute("SELECT id, title, artist, duration, status FROM tracks WHERE status='cuarentena'"):
    ok, motivo = Q.revisar({"title": r["title"], "artist": r["artist"], "duration": r["duration"]})
    clave = re.sub(r":\s*[\d.]+s", "", motivo).strip() or "aceptada (?)"
    motivos[clave] = motivos.get(clave, 0) + 1
    # Sin acentos a proposito: al pasar el guion por PowerShell los acentos se estropean y una
    # comparacion con "duracion" acentuada no coincide nunca (me paso y daba 0 rechazadas).
    if "raci" in motivo:
        d = r["duration"] or 0
        (largas if d > Q.DUR_MAX else cortas).append((d, r["artist"], r["title"]))
for k, n in sorted(motivos.items(), key=lambda x: -x[1]):
    print(f"   {k}: {n}")

print(f"\n=== rechazadas por DEMASIADO LARGAS (> {Q.DUR_MAX:.0f}s): {len(largas)} ===")
for d, a, t in sorted(largas, reverse=True)[:15]:
    print(f"   {int(d // 60):4d} min  {a} - {t[:60]}")

print(f"\n=== rechazadas por DEMASIADO CORTAS (< {Q.DUR_MIN:.0f}s): {len(cortas)} ===")
for d, a, t in sorted(cortas)[:10]:
    print(f"   {int(d):4d} s    {a} - {t[:60]}")

print("\n=== todas las que duran más de 15 min (en cualquier estado) ===")
for f in con.execute("SELECT status, COUNT(*) n FROM tracks WHERE duration > 900 GROUP BY status"):
    print(f"   {f['status']}: {f['n']}")

print("\n=== pistas de entre 10 y 15 min (candidatas a sesión corta) ===")
n = con.execute("SELECT COUNT(*) n FROM tracks WHERE duration BETWEEN 600 AND 900").fetchone()["n"]
print(f"   {n}")

print("\n=== cuántas 'descargada' se caerían si se aplicara la puerta otra vez ===")
caerian = 0
for r in con.execute("SELECT title, artist, duration FROM tracks WHERE status='descargada'"):
    ok, _ = Q.revisar({"title": r["title"], "artist": r["artist"], "duration": r["duration"]})
    if not ok:
        caerian += 1
print(f"   {caerian}")

con.close()
