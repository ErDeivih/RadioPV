"""Qué dice `/admin/facets` del idioma portugués (y si coincide con la base).

Existe por una discrepancia real (19/09/2026): el panel enseñaba 202 canciones en el atajo «En
portugués» mientras la base tenía 49 filas con `language='pt'`. Hay que saber si la diferencia está
en el endpoint o en la pantalla, así que esto lo pregunta por HTTP, sin navegador.

Uso:
    .venv\\Scripts\\python.exe scripts\\probar_facetas_admin.py
"""
import argparse
import sys
import time

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ap = argparse.ArgumentParser()
ap.add_argument("--base", default="http://servidor:8090/api")
ap.add_argument("--email", default="admin-pruebas@radiopv-test.com")
ap.add_argument("--clave", default="clave-de-pruebas-larga-123")
args = ap.parse_args()

s = requests.Session()
# El login va por formulario (`username`/`password`), no por JSON: es OAuth2 password flow.
r = s.post(f"{args.base}/auth/login", data={"username": args.email, "password": args.clave},
           timeout=30)
if r.status_code >= 400:
    print(f"no se pudo entrar: HTTP {r.status_code} {r.text[:200]}")
    raise SystemExit(1)
s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})

print("=== /admin/facets · idiomas ===")
r = s.get(f"{args.base}/admin/facets", timeout=60)
print(f"HTTP {r.status_code}")
if r.status_code != 200:
    print(r.text[:300])
    raise SystemExit(1)
d = r.json()
for item in d["languages"]:
    marca = "   <-- el atajo «En portugués»" if item["valor"] == "pt" else ""
    print(f"   {item['valor']:<8} {item['n']}{marca}")

print("\n=== lo que filtra el atajo (language=pt) ===")
r = s.get(f"{args.base}/admin/tracks", params={"language": "pt", "limit": 1}, timeout=60)
if r.status_code == 200:
    print(f"   canciones con language=pt: {r.json()['total']}")
else:
    print(f"   HTTP {r.status_code} {r.text[:200]}")

print("\n=== los atajos que manda el servidor ===")
salud = d.get("salud") or {}
for k, v in salud.items():
    print(f"   {k:<16} {v.get('n')}")

# Repetido a los pocos segundos: si cambia sin tocar nada, hay caché por medio.
time.sleep(3)
d2 = s.get(f"{args.base}/admin/facets", timeout=60).json()
pt1 = next((i["n"] for i in d["languages"] if i["valor"] == "pt"), None)
pt2 = next((i["n"] for i in d2["languages"] if i["valor"] == "pt"), None)
print(f"\n[comprobación] portugués en dos llamadas seguidas: {pt1} y {pt2} "
      f"({'IGUAL' if pt1 == pt2 else 'DISTINTO: algo lo está cambiando'})")
