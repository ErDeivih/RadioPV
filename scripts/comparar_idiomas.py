"""Compara el idioma de las canciones entre las dos bases. **Diagnóstico, no fuente de verdad.**

POR QUÉ
-------
Hay dos bases con la misma música: la del recolector (`radiov.db`, la que llena el agente) y la de
la aplicación (`backend.db`, la que sirve la web). Este script enseña en qué se diferencian.

OJO: **ninguna de las dos manda.** Se comprobó contra el catálogo real (19/09/2026) y las dos se
equivocan, cada una a su manera:

| Canción | Recolector | Aplicación | La verdad |
|---|---|---|---|
| Ariana Grande - hate that i made you love me | `pt` | `en` | inglés |
| KATSEYE - Hootie Frutti | `pt` | `other` | inglés |
| Chico César - Pensar Em Você | `en` | `pt` | portugués |
| Ninho - Tout en Gucci | `fr` | `fr` | francés |

El motivo es que el idioma lo adivina un detector por palabras sueltas (`catalog.detect_language`),
y adivinar idioma así falla en títulos cortos y en inglés. Por eso el script **avisa, no arregla**:
usar el valor del recolector para sobrescribir la aplicación volvería a poner `pt` en canciones
inglesas. Para lo que sí sirve es para ver dónde están las discrepancias y cuántas hay.

Uso (dentro del contenedor del API):
    docker exec radiopv-api python /app/scripts/comparar_idiomas.py
"""
import argparse
import os
import sqlite3

DIR = os.environ.get("RADIOPV_DATA_DIR", "/app/data")

ap = argparse.ArgumentParser()
ap.add_argument("--aplicar", action="store_true", help="escribe los idiomas que falten")
ap.add_argument("--limite", type=int, default=25)
args = ap.parse_args()

app_db = sqlite3.connect(f"{DIR}/backend.db")
app_db.row_factory = sqlite3.Row
try:
    rec_db = sqlite3.connect(f"{DIR}/radiov.db")
except sqlite3.OperationalError as e:
    print(f"no se pudo abrir la base del recolector: {e}")
    raise SystemExit(1)
rec_db.row_factory = sqlite3.Row

# El idioma de cada (artista, título) según el recolector, que es quien lo calculó al descargar.
suyo = {(r["artist"], r["title"]): r["language"]
        for r in rec_db.execute("SELECT artist, title, language FROM tracks"
                                " WHERE language IS NOT NULL AND language <> ''")}

filas = app_db.execute("SELECT id, title, artist, language FROM tracks").fetchall()
iguales = distintos = faltan = 0
cambios = []
for f in filas:
    su = suyo.get((f["artist"], f["title"]))
    if su is None:
        faltan += 1
        continue
    if (f["language"] or "") == su:
        iguales += 1
    else:
        distintos += 1
        cambios.append((f["id"], f["artist"], f["title"], f["language"], su))

print(f"=== {len(filas)} canciones en la base de la aplicación ===")
print(f"    con idioma igual al del recolector: {iguales}")
print(f"    con idioma DISTINTO:                {distintos}")
print(f"    sin pareja en la base del recolector: {faltan}")

print(f"\n=== diferencias (hasta {args.limite}) ===")
for pid, artista, titulo, aqui, alli in cambios[:args.limite]:
    print(f"   id={pid:<6} {str(aqui):<6} → {str(alli):<6}  {artista} - {titulo}"[:110])

if args.aplicar:
    print("\n[!] ESTE SCRIPT YA NO ESCRIBE: se comprobó que el valor del recolector tampoco es fiable")
    print("    (pone 'pt' en canciones inglesas). Mira la tabla del docstring antes de tocar nada.")
app_db.close()
rec_db.close()
