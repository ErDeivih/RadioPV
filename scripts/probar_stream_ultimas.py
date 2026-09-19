"""Prueba /stream en las ultimas pistas publicadas: ¿suenan de verdad?

Tener el fichero no basta: puede estar a medias (copia interrumpida) o no ser audio valido. Esta
comprobacion pide el mismo trozo que pide el reproductor y mira el codigo de respuesta.
"""
import json
import os
import sqlite3
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
ids = [t.id for t in db.query(models.Track.id).filter(models.Track.status == "descargada")
       .order_by(models.Track.id.desc()).limit(15)]
db.close()

cab = {"Authorization": "Bearer " + token}
req = urllib.request.Request(BASE + "/auth/stream-token", data=b"", headers=cab, method="POST")
with urllib.request.urlopen(req, timeout=30) as r:
    stream_token = json.loads(r.read().decode())["token"]

print("=== /stream de las 15 ultimas publicadas ===")
malas = 0
for tid in ids:
    url = f"{BASE}/stream/{tid}?t={stream_token}"
    peticion = urllib.request.Request(url, headers={"Range": "bytes=0-1023"})
    try:
        with urllib.request.urlopen(peticion, timeout=30) as r:
            trozo = r.read()
            print(f"   {tid:>5}  HTTP {r.status}  {len(trozo)} bytes  {'OK' if len(trozo) > 100 else 'VACIO'}")
            if len(trozo) <= 100:
                malas += 1
    except Exception as e:  # noqa: BLE001
        malas += 1
        print(f"   {tid:>5}  FALLO: {str(e)[:70]}")

print(f"\n  de 15, no suenan: {malas}")
