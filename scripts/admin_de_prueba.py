"""Crea (o borra) un usuario de pruebas CON permisos de administracion.

Hace falta para poder mirar el panel de administracion como lo ve el usuario: las pruebas
automaticas normales entran con usuarios nuevos, y esos no son administradores.

Uso (en el contenedor del API):
    docker exec radiopv-api python /app/scripts/admin_de_prueba.py crear
    docker exec radiopv-api python /app/scripts/admin_de_prueba.py borrar
"""
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/backend")

from app.database import SessionLocal  # noqa: E402
from app import models  # noqa: E402
from app.security import hash_password  # noqa: E402

EMAIL = "admin-pruebas@radiopv-test.com"
CLAVE = "clave-de-pruebas-larga-123"
accion = sys.argv[1] if len(sys.argv) > 1 else "crear"

db = SessionLocal()
try:
    u = db.query(models.User).filter_by(email=EMAIL).first()
    if accion == "borrar":
        if not u:
            print("no existe; nada que borrar")
        else:
            # Se borran también sus datos dependientes, por introspección de las tablas con user_id.
            import sqlite3
            import os
            ruta = os.environ.get("RADIOPV_DATA_DIR", "/app/data") + "/backend.db"
            con = sqlite3.connect(ruta)
            for (tabla,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
                cols = [c[1] for c in con.execute(f"PRAGMA table_info({tabla})")]
                if "user_id" in cols:
                    con.execute(f"DELETE FROM {tabla} WHERE user_id=?", (u.id,))
            con.commit()
            con.close()
            db.delete(u)
            db.commit()
            print(f"borrado: {EMAIL}")
        raise SystemExit(0)

    if u:
        u.is_admin = True
        u.hashed_password = hash_password(CLAVE)
        db.commit()
        print(f"ya existia; ahora es admin y tiene la clave de pruebas: {EMAIL}")
    else:
        db.add(models.User(email=EMAIL, display_name="AdminPruebas",
                           hashed_password=hash_password(CLAVE), is_admin=True))
        db.commit()
        print(f"creado admin de pruebas: {EMAIL}")
    print(f"clave: {CLAVE}")
finally:
    db.close()
