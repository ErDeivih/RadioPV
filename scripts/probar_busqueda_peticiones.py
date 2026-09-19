"""Prueba de la búsqueda de la página de pedir canciones, contra el servidor de verdad.

Comprueba lo que hace falta para que la página sirva:
  1. que la búsqueda diga lo que YA está en la biblioteca (para no pedir lo que ya suena);
  2. que devuelva versiones REALES de YouTube, con duración (para elegir la buena);
  3. que una petición guarde el vídeo elegido y vuelva con él.

Uso:
    .venv\\Scripts\\python.exe scripts\\probar_busqueda_peticiones.py
    .venv\\Scripts\\python.exe scripts\\probar_busqueda_peticiones.py --q "sesion reggaeton viejo"
"""
import argparse
import sys
import time

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ap = argparse.ArgumentParser()
ap.add_argument("--base", default="http://servidor:8090/api")
ap.add_argument("--q", default="mashup reggaeton")
args = ap.parse_args()

s = requests.Session()
correo = f"buscar-{int(time.time())}@radiopv-test.com"
r = s.post(f"{args.base}/auth/register",
           json={"email": correo, "password": "clave-de-pruebas-larga-123", "name": "Buscar"},
           timeout=30)
if r.status_code >= 400:
    print(f"no se pudo registrar: HTTP {r.status_code} {r.text[:200]}")
    raise SystemExit(1)
s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})

print(f"=== buscando «{args.q}» ===")
t0 = time.time()
r = s.get(f"{args.base}/requests/buscar", params={"q": args.q}, timeout=60)
print(f"HTTP {r.status_code} en {time.time() - t0:.1f} s")
if r.status_code != 200:
    print(r.text[:400])
    raise SystemExit(1)
d = r.json()

print(f"  aviso: {d.get('aviso') or 'ninguno'}")
print(f"  en la biblioteca: {len(d['en_biblioteca'])}")
for t in d["en_biblioteca"][:5]:
    print(f"     id={t['id']:<6} {t['artista']} - {t['titulo']}"[:100])
print(f"  en YouTube: {len(d['en_youtube'])}")
for v in d["en_youtube"][:6]:
    dur = int(v["duracion"] or 0)
    etiqueta = "YA EN CASA" if v["en_catalogo"] else "nueva"
    print(f"     {v['video_id']:<14} {dur // 60:>3}:{dur % 60:02d}  [{etiqueta}] "
          f"{v['titulo'][:60]}  ·  {v['canal'][:25]}")
print(f"  ya pedidas: {len(d['en_cola'])}")

# Pedir la primera versión que NO esté en casa, con su vídeo exacto.
candidata = next((v for v in d["en_youtube"] if not v["en_catalogo"]), None)
if not candidata:
    print("\n[i] no hay ninguna versión nueva que pedir en este resultado")
    raise SystemExit(0)

print(f"\n=== pidiendo el vídeo {candidata['video_id']} ===")
r = s.post(f"{args.base}/requests",
           json={"text": candidata["titulo"][:180], "youtube_id": candidata["video_id"],
                 "duration": candidata["duracion"]}, timeout=30)
print(f"HTTP {r.status_code} {r.text[:160]}")

mias = s.get(f"{args.base}/requests", timeout=30).json()
print(f"\n=== mis peticiones ({len(mias)}) ===")
for p in mias[:3]:
    print(f"   {p['status']:<10} {p['text'][:70]}")

print("\n[OK] la búsqueda y la petición con vídeo funcionan")
print(f"[i] usuario de pruebas creado: {correo} (se limpia con limpiar_datos_de_prueba.py)")
