"""Comprueba que una lista NUEVA sólo tiene las canciones que se le añaden.

POR QUÉ EXISTE
--------------
Se detectó que una lista recién creada aparecía con más canciones de las añadidas (3 añadidas,
8 y hasta 16 en pantalla), y las de más eran las ÚLTIMAS que había importado el recolector. Eso
significa que canciones nuevas están cayendo en una lista de un usuario cualquiera.

Esta prueba crea un usuario, crea una lista, le añade 3 canciones y vuelve a leerla. Sin navegador
de por medio: si aquí salen más de 3, el culpable está en el servidor; si salen 3, está en la web.

Uso:
    python scripts/probar_lista_nueva.py
    python scripts/probar_lista_nueva.py --base http://servidor:8090/api
"""
import argparse
import json
import sys
import time

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://servidor:8090/api")
    ap.add_argument("--cuantas", type=int, default=3)
    args = ap.parse_args()

    s = requests.Session()
    correo = f"listanueva-{int(time.time())}@radiopv-test.com"
    r = s.post(f"{args.base}/auth/register", json={
        "email": correo, "password": "clave-de-pruebas-larga-123", "name": "ListaNueva",
    }, timeout=30)
    print(f"registro: HTTP {r.status_code}")
    if r.status_code >= 400:
        print(r.text[:300])
        return 1
    # El token viene en el cuerpo: se usa como Bearer (igual que hace la web con localStorage).
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})

    pl = s.post(f"{args.base}/playlists", json={"name": "Sonda de lista nueva"}, timeout=30)
    lista = pl.json()
    print(f"lista creada: {json.dumps(lista)[:120]}")

    def cuantas() -> int:
        return len(s.get(f"{args.base}/playlists/{lista['id']}/tracks", timeout=60).json())

    def trocear(etiqueta: str, esperado: int) -> None:
        print(f"   tras {etiqueta}: {cuantas()} canciones (esperado {esperado})")

    trocear("crear la lista", 0)

    pistas = s.get(f"{args.base}/tracks", params={"limit": args.cuantas}, timeout=60).json()
    print(f"   /tracks?limit={args.cuantas} devolvió {len(pistas)} canciones")
    trocear("pedir el catálogo", 0)

    puestas = 0
    for t in pistas:
        rr = s.post(f"{args.base}/playlists/{lista['id']}/tracks/{t['id']}", timeout=30)
        if rr.ok:
            puestas += 1
        trocear(f"añadir {t['id']}", puestas)
    print(f"añadidas: {puestas}")

    dentro = s.get(f"{args.base}/playlists/{lista['id']}/tracks", timeout=60).json()
    print(f"\nla lista tiene {len(dentro)} canciones (se esperaban {args.cuantas}):")
    for t in dentro:
        print(f"   id={t['id']:<6} {t.get('artist') or t.get('artists')} - {t.get('title') or t.get('name')}"[:110])

    # Y también lo que dice el contador de la propia lista.
    ficha = s.get(f"{args.base}/playlists/{lista['id']}", timeout=30).json()
    print(f"n_tracks según la ficha de la lista: {ficha.get('n_tracks')}")

    de_mas = len(dentro) - args.cuantas
    print("\n" + ("OK: exactamente las añadidas" if de_mas == 0 else
                  f"PROBLEMA: hay {de_mas} canciones DE MÁS en una lista nueva"))
    return 0 if de_mas == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
