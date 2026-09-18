"""Publica las 'incompleta' que ya están completas y dice cuántas quedan en cada estado."""
import os
import sqlite3
import sys

sys.path.insert(0, "/app")
from radiov import catalog as C  # noqa: E402

DB = os.environ.get("RADIOPV_DATA_DIR", "/app/data") + "/radiov.db"


def cuenta(etiqueta):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    filas = {r["status"]: r["n"] for r in
             con.execute("SELECT status, COUNT(*) n FROM tracks GROUP BY status")}
    con.close()
    print(f"   {etiqueta}: " + ", ".join(f"{k}={v}" for k, v in sorted(filas.items())))
    return filas


print("antes de republicar:")
cuenta("estados")
n = C.republicar_completas()
print(f"republicar_completas() → {n} publicadas")
print("después:")
cuenta("estados")
