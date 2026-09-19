"""Revisa la cuarentena con la puerta de calidad de AHORA y republica lo que ya pasa.

POR QUÉ
-------
La puerta cortaba todo lo que durase más de 15 minutos y todo lo que bajase de 90 segundos, así
que las sesiones de DJ y los mashups cortos se quedaban en cuarentena al entrar. Con los márgenes
por tipo (ver `radiov/quality.py`) hay pistas que ahora sí pasan y que llevan ahí desde entonces.

Uso (dentro del contenedor del API):
    docker exec radiopv-api python /app/scripts/revisar_cuarentena.py            # solo informa
    docker exec radiopv-api python /app/scripts/revisar_cuarentena.py --apply    # republica
"""
import os
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/backend")

import sqlite3  # noqa: E402

from radiov import db as rdb  # noqa: E402
from radiov import quality as Q  # noqa: E402
from radiov.models import STATUS_DOWNLOADED, STATUS_QUARANTINE  # noqa: E402

DB = os.environ.get("RADIOPV_DATA_DIR", "/app/data") + "/radiov.db"
aplicar = "--apply" in sys.argv

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
filas = con.execute(
    "SELECT id, title, artist, duration FROM tracks WHERE status=?", (STATUS_QUARANTINE,)).fetchall()
con.close()

recuperables = []
siguen_fuera = []
for r in filas:
    ok, motivo = Q.revisar({"title": r["title"], "artist": r["artist"], "duration": r["duration"]})
    tipo = Q.clasificar(r["title"] or "", r["artist"] or "", r["duration"])
    (recuperables if ok else siguen_fuera).append((r, tipo, motivo))

print(f"en cuarentena: {len(filas)}")
print(f"  ahora SI pasan: {len(recuperables)}")
print(f"  siguen fuera:   {len(siguen_fuera)}")

if recuperables:
    print("\n--- se recuperan ---")
    for r, tipo, _ in recuperables:
        print(f"   [{str(tipo):7s}] {int((r['duration'] or 0) // 60):4d} min  "
              f"{r['artist']} - {(r['title'] or '')[:58]}")

if siguen_fuera:
    print("\n--- siguen fuera (motivo) ---")
    for r, tipo, motivo in siguen_fuera:
        print(f"   [{str(tipo):7s}] {motivo[:42]:44s} {r['artist']} - {(r['title'] or '')[:40]}")

if aplicar and recuperables:
    for r, _, _ in recuperables:
        rdb.update_track(r["id"], status=STATUS_DOWNLOADED)
    rdb.log_event(f"✅ {len(recuperables)} pistas republicadas desde cuarentena "
                  f"(margenes de duracion por tipo)", "info")
    print(f"\n[OK] {len(recuperables)} pistas vuelven a estar publicadas")
elif not aplicar:
    print("\n[..] solo informacion: anade --apply para republicarlas")
