"""¿Hay de dónde sacar letras? Se prueban dos servicios publicos y sin clave.

El boton de «Letra» de la barra de reproduccion abria... el selector de idioma. Antes de
arreglarlo hay que saber si hay alguna fuente que responda desde el servidor.
"""
import json
import urllib.parse
import urllib.request

PRUEBAS = [
    ("lyrics.ovh", "https://api.lyrics.ovh/v1/{artista}/{titulo}"),
    ("lyrics.ovh (titulo con parentesis)", "https://api.lyrics.ovh/v1/{artista}/{titulo}"),
]

CASOS = [
    ("Coldplay", "Yellow"),
    ("Rosalia", "DESPECHA"),
    ("Dua Lipa", "Levitating"),
]

for nombre, plantilla in PRUEBAS[:1]:
    print(f"== {nombre} ==")
    for artista, titulo in CASOS:
        url = plantilla.format(artista=urllib.parse.quote(artista), titulo=urllib.parse.quote(titulo))
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "RadioPV/1.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                datos = json.loads(r.read().decode("utf-8", "replace"))
            letra = (datos.get("lyrics") or "").strip()
            print(f"   OK  {artista} - {titulo}: {len(letra)} caracteres")
            if letra:
                print(f"       empieza: {' '.join(letra.split())[:80]}")
        except Exception as e:  # noqa: BLE001
            print(f"   NO  {artista} - {titulo}: {str(e)[:90]}")
