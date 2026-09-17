"""Coloca en su sitio los ficheros enviados sueltos (los que tar no puede manejar).

Se ejecuta DENTRO del contenedor, con /work y /dst montados:

    docker run --rm -v /tmp/radiopv-especiales:/work \
                    -v /srv/data/media/music:/dst \
                    radiopv-api python /work/colocar.py

Lee /work/manifiesto.txt, donde cada linea es:

    <nombre_temporal_en_/work>\t<ruta_relativa_destino>

y mueve cada fichero a /dst/<ruta_relativa>, creando los directorios que hagan falta.

Se hace asi (en vez de un `scp` directo a su ruta final) por dos motivos:
  · los directorios de destino son de root y scp entra como david, sin permiso;
  · asi ninguna ruta con acentos, espacios o comillas pasa por el interprete de shell.
Python lee el manifiesto tal cual, en UTF-8, sin comillas de por medio.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

WORK = Path("/work")
DST = Path("/dst")


def main() -> int:
    manifiesto = WORK / "manifiesto.txt"
    if not manifiesto.exists():
        print("no hay manifiesto; nada que hacer")
        return 0

    lineas = [l for l in manifiesto.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"  manifiesto con {len(lineas)} ficheros")

    colocados = 0
    fallos = 0
    for linea in lineas:
        partes = linea.split("\t", 1)
        if len(partes) != 2:
            print(f"  [X] linea mal formada: {linea[:80]!r}")
            fallos += 1
            continue
        temp_nombre, rel = partes
        origen = WORK / temp_nombre
        destino = DST / rel

        if not origen.exists():
            print(f"  [X] no llego el fichero temporal {temp_nombre}")
            fallos += 1
            continue
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(origen), str(destino))
            colocados += 1
        except Exception as e:  # noqa: BLE001
            print(f"  [X] {rel}: {e}")
            fallos += 1

    print(f"  colocados: {colocados} · fallos: {fallos}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
