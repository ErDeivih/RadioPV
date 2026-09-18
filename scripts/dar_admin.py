"""Devuelve el permiso de administrador al dueño de la casa y comprueba el panel.

Qué pasó: el sistema concede admin «al primero que se registre», y cuando se registró David ya
existían cuentas de prueba que ocuparon ese hueco. Al limpiar esas cuentas, la base se quedó SIN
NINGÚN administrador, así que todos los endpoints de `/admin/*` respondían 403 y el panel salía
vacío en la web.

Arreglo doble:
  1) se marca la cuenta del dueño como administradora, y
  2) se deja `RADIOPV_ADMIN_EMAILS` en el `.env` del despliegue, que es la fuente de verdad por
     configuración: así el permiso no depende del orden de registro ni de que exista otro admin.
"""
import sys

sys.path.insert(0, "/app")

from app.database import SessionLocal  # noqa: E402
from app import models  # noqa: E402

OBJETIVO = "davidpeve01@gmail.com"

db = SessionLocal()

print("=== usuarios de la base ===")
for u in db.query(models.User).all():
    print(f"   id={u.id:3d}  {u.email:32s} admin={u.is_admin}")

print("\n=== admins antes ===")
print("  ", [u.email for u in db.query(models.User).filter(models.User.is_admin.is_(True)).all()] or "NINGUNO")

u = db.query(models.User).filter(models.User.email == OBJETIVO).first()
if not u:
    print(f"\n[ERROR] no existe el usuario {OBJETIVO}")
else:
    u.is_admin = True
    db.commit()
    print(f"\n[OK] {u.email} ahora es administrador")

print("\n=== admins despues ===")
print("  ", [u.email for u in db.query(models.User).filter(models.User.is_admin.is_(True)).all()])
db.close()
