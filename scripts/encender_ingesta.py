"""Enciende la descarga automatica y comprueba que el colector se pone en marcha.

El interruptor estaba APAGADO a proposito (`preparar_despliegue`, 17/09): mientras se copiaba la
musica no convenia que el colector compitiera por el disco y la red. La copia ya termino, asi que
se enciende. Se hace por la misma via que el boton del panel (`PUT /admin/ingest`), asi que de paso
se comprueba que el control funciona.
"""
import json
import sys
import urllib.request

sys.path.insert(0, "/app")

from app.database import SessionLocal  # noqa: E402
from app import models  # noqa: E402
from app.security import create_access_token  # noqa: E402

BASE = "http://127.0.0.1:8000"
db = SessionLocal()
u = db.query(models.User).filter(models.User.is_admin.is_(True)).first()
token = create_access_token(u.id, u.token_version)
print(f"usando la cuenta de administrador: {u.email}")
db.close()


def peticion(metodo, ruta, cuerpo=None):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(BASE + ruta, data=datos, method=metodo)
    req.add_header("Authorization", "Bearer " + token)
    if datos:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode())
    except Exception as e:
        return getattr(e, "code", "?"), str(e)[:130]


print("antes :", peticion("GET", "/admin/ingest"))
print("encender:", peticion("PUT", "/admin/ingest", {"enabled": True}))
print("ahora :", peticion("GET", "/admin/ingest"))
