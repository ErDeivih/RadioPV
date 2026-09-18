"""Cambia la politica de descargas del colector y anade mashups/remixes.

Politica pedida: solo ESPANOL, LATINO e INGLES. Frances e italiano, solo las mas escuchadas de
siempre (nada de listas locales ni de novedades del pais). Portugues, nada.

Que se quita de las semillas (`radiov/config.py`):
  · las listas locales de Apple de Brasil (pt), Italia (it) y Francia (fr), que son las canciones
    del momento en esos paises;
  · los barridos por decadas de italiano, frances y portugues, que traen material local;
  · las semillas de exploracion en portugues.
Que se queda: la exploracion de italianos y franceses clasicos (Eros Ramazzotti, Laura Pausini,
Andrea Bocelli, Edith Piaf, Stromae...), que es "lo mas escuchado de siempre".

Y se anaden semillas de MASHUPS y REMIXES: canciones que mezclan dos o tres temas, hechas por
gente en YouTube. Se buscan por texto, que es lo que mejor encuentra ese tipo de contenido.

Uso:  python scripts/politica_descargas.py            # solo informa
      python scripts/politica_descargas.py --apply
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = RAIZ / "radiov" / "config.py"

# Lineas que se van (comparadas sin espacios sobrantes)
FUERA = [
    '{"mode": "hits_apple", "country": "br", "genre": "latin", "language": "pt", "limit": 20},',
    '{"mode": "hits_apple", "country": "it", "genre": "pop", "language": "it", "limit": 20},',
    '{"mode": "hits_apple", "country": "fr", "genre": "pop", "language": "fr", "limit": 20},',
    '{"mode": "year_sweep", "language": "it", "genre": "pop", "years": [1970, 1980, 1990, 2000, 2010, 2020]},',
    '{"mode": "year_sweep", "language": "fr", "genre": "pop", "years": [1970, 1980, 1990, 2000, 2010, 2020]},',
    '{"mode": "year_sweep", "language": "pt", "genre": "latin", "years": [1970, 1980, 1990, 2000, 2010, 2020]},',
    '{"mode": "explore", "genre": "latin", "language": "pt", "seeds": ["Anitta", "Roberto Carlos", "Caetano Veloso"]},',
]

NUEVAS = [
    "",
    "    # MASHUPS Y REMIXES: canciones que mezclan dos o tres temas, hechas por gente en YouTube.",
    "    # Se buscan por texto (es lo que mejor encuentra ese tipo de contenido).",
    '    {"mode": "query", "genre": "dance", "query": "mashup two songs", "language": "en"},',
    '    {"mode": "query", "genre": "dance", "query": "best mashup mix", "language": "en"},',
    '    {"mode": "query", "genre": "pop", "query": "mashup 3 songs", "language": "en"},',
    '    {"mode": "query", "genre": "reggaeton", "query": "mashup reggaeton", "language": "es"},',
    '    {"mode": "query", "genre": "dance", "query": "remix mashup", "language": "en"},',
]

apply = "--apply" in sys.argv
texto = CONFIG.read_text(encoding="utf-8")

print("=== semillas que se QUITAN (politica: solo es/latin/en; fr e it solo clasicos) ===")
quitadas = 0
for linea in FUERA:
    if linea in texto:
        print(f"   {linea[:88]}")
        quitadas += 1
    else:
        print(f"   [aviso] no encontrada: {linea[:70]}")

print(f"\n   total a quitar: {quitadas} de {len(FUERA)}")

if not apply:
    print("\n[..] solo informacion: anade --apply para cambiarlo")
    raise SystemExit(0)

for linea in FUERA:
    texto = texto.replace(linea + "\n", "")

# Las nuevas van justo despues de la ultima semilla de tipo "query"
m = list(re.finditer(r'(?m)^.*\{"mode": "query".*$', texto))
if m:
    ultima = m[-1]
    fin = texto.index("\n", ultima.end())
    texto = texto[:fin] + "\n" + "\n".join(NUEVAS) + texto[fin:]
else:
    print("[ERROR] no se encontro donde insertar las semillas nuevas")

CONFIG.write_text(texto, encoding="utf-8")
print(f"\n[OK] politica aplicada y {len(NUEVAS) - 3} semillas de mashup/remix anadidas")
