"""Reparte el trabajo: el PC descarga y el servidor deja de hacerlo.

POR QUE
-------
El recolector (buscar, descargar, analizar) es lo que mas pesa en el servidor: un portatil de
4 GB sin swap, que ademas tiene que servir la aplicacion. El PC de casa esta encendido igualmente
y le sobra maquina, asi que a partir de ahora descarga el y manda la musica.

Este guion APAGA el interruptor de ingesta del servidor y lo deja comprobado. Es reversible: con
`--encender` vuelve a ponerlo como estaba (util si el PC se queda sin conexion una temporada).

Uso (dentro del contenedor del API):
    docker exec radiopv-api python /app/scripts/ingesta_en_el_pc.py            # apagar
    docker exec radiopv-api python /app/scripts/ingesta_en_el_pc.py --encender # volver atras
"""
import json
import sys
import urllib.request

sys.path.insert(0, "/app")

from app.database import SessionLocal  # noqa: E402
from app import models  # noqa: E402
from app.security import create_access_token  # noqa: E402

BASE = "http://127.0.0.1:8000"
encender = "--encender" in sys.argv
deseado = bool(encender)

db = SessionLocal()
u = db.query(models.User).filter(models.User.is_admin.is_(True)).first()
if u is None:
    sys.exit("No hay ninguna cuenta de administrador en la base.")
token = create_access_token(u.id, u.token_version)
print(f"cuenta de administracion: {u.email}")
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
    except Exception as e:  # noqa: BLE001
        return getattr(e, "code", "?"), str(e)[:130]


print("antes :", peticion("GET", "/admin/ingest"))
print(f"{'encender' if deseado else 'apagar'}:", peticion("PUT", "/admin/ingest", {"enabled": deseado}))
print("ahora :", peticion("GET", "/admin/ingest"))
print()
if deseado:
    print("El servidor vuelve a descargar por su cuenta.")
else:
    print("El servidor ya NO descarga. Ahora recolecta el PC (pc/recolector_pc.py) y manda la")
    print("musica aqui. Si el PC se queda apagado mucho tiempo, esto se puede volver a encender.")
