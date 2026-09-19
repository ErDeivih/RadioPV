"""Fuerza AHORA la sincronización del catálogo (radiov.db → la base de la aplicación).

POR QUÉ
-------
La música descargada vive en `radiov.db` (la biblioteca del recolector) y la aplicación sirve
`backend.db`. La sincronización va **cada 30 minutos**, así que después de que el PC mande canciones
nuevas hay un rato en el que la aplicación todavía no las ve. Cuando eso se nota («acabo de bajar
esto y no aparece»), esto lo resuelve al momento.

Uso (dentro del contenedor del API):
    docker exec radiopv-api python /app/scripts/sincronizar_catalogo.py
"""
import os
import sqlite3
import sys

sys.path.insert(0, "/app" if os.path.isdir("/app") else ".")

DIR = os.environ.get("RADIOPV_DATA_DIR", "/app/data")


def cuantas(base: str) -> int:
    ruta = f"{DIR}/{base}"
    if not os.path.exists(ruta):
        return -1
    con = sqlite3.connect(ruta)
    try:
        return con.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
    finally:
        con.close()


antes_rec, antes_app = cuantas("radiov.db"), cuantas("backend.db")
print(f"antes:  recolector={antes_rec}  aplicación={antes_app}  (diferencia {antes_app - antes_rec:+d})")

from app.database import SessionLocal  # noqa: E402
from app.workers import sync_catalogo  # noqa: E402

db = SessionLocal()
try:
    total = sync_catalogo(db)
finally:
    db.close()

despues_rec, despues_app = cuantas("radiov.db"), cuantas("backend.db")
print(f"después: recolector={despues_rec}  aplicación={despues_app}  (total en la app: {total})")
print(f"canciones nuevas traídas a la aplicación: {despues_app - antes_app}")
if despues_app < despues_rec:
    print(f"[!] la aplicación sigue con {despues_rec - despues_app} canciones menos que el recolector")
    print("    Si no baja en la siguiente pasada, mira el registro del worker: puede haber una")
    print("    canción que falla al insertar y corta la sincronización.")
else:
    print("[OK] la aplicación tiene todo lo del recolector")
