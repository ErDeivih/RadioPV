"""Compara los dos manifiestos de transferencia (PC y servidor) y dice si coinciden.

Comprueba por canción —casando por **id de YouTube**, que es único— tres cosas:
  1. que está en los dos lados,
  2. que el tamaño coincide, y
  3. que el **sha1 de los primeros 1 MB** coincide.

Lo tercero es lo que de verdad demuestra que el fichero llegó entero: un tamaño igual no basta,
porque una copia cortada puede rellenarse con ceros y pesar exactamente lo mismo.

Uso:
    .venv\\Scripts\\python.exe pc\\comparar_transferencias.py
"""
import sys
from pathlib import Path

# La consola de Windows usa cp1252 y revienta con ciertos caracteres (pasó: un nombre con acentos
# mataba el resumen justo al informar de un fallo).
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

RAIZ = Path(__file__).resolve().parent.parent


def leer(ruta: Path) -> dict:
    """Devuelve {clave: (tam, sha1, nombre)}. La clave es el id de YouTube si lo hay."""
    datos = {}
    for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
        if linea.startswith("#") or "|" not in linea:
            continue
        partes = linea.split("|")
        if len(partes) == 5:                       # con id de YouTube
            titulo, artista, yt, tam, sha = partes
            clave = yt.strip() or f"{titulo.strip().lower()}|{artista.strip().lower()}"
        elif len(partes) == 4:                     # formato antiguo, sin id
            titulo, artista, tam, sha = partes
            clave = f"{titulo.strip().lower()}|{artista.strip().lower()}"
        else:
            continue
        datos[clave] = (tam.strip(), sha.strip(), f"{artista.strip()} - {titulo.strip()}")
    return datos


def main() -> int:
    pc = leer(RAIZ / "_pc_data" / "transferencias_pc.txt")
    srv = leer(RAIZ / "_pc_data" / "transferencias_servidor.txt")

    print(f"en el PC:       {len(pc)} pistas enviadas")
    print(f"en el servidor: {len(srv)} pistas encontradas de esas")

    iguales, faltan, distintos, faltan_fichero = [], [], [], []
    for clave, (tam, sha, nombre) in pc.items():
        if clave not in srv:
            faltan.append(nombre)
            continue
        tam_srv, sha_srv, _ = srv[clave]
        if tam_srv in ("FALTA", "NO-ESTA"):
            faltan_fichero.append(nombre)
        elif tam == tam_srv and sha == sha_srv:
            iguales.append(nombre)
        else:
            distintos.append((nombre, tam, tam_srv, sha, sha_srv))

    print()
    print(f"  IDÉNTICAS (mismo tamaño y mismo sha1): {len(iguales)}")
    print(f"  sin fichero en el servidor:            {len(faltan_fichero)}")
    print(f"  ni siquiera están en la base:          {len(faltan)}")
    print(f"  con contenido DISTINTO:                {len(distintos)}")

    for nombre in faltan_fichero[:10]:
        print(f"     sin fichero: {nombre}")
    for nombre in faltan[:10]:
        print(f"     no está: {nombre}")
    for nombre, tam, tam_srv, sha, sha_srv in distintos[:10]:
        print(f"     distinta: {nombre}: pc={tam}/{sha} servidor={tam_srv}/{sha_srv}")

    if iguales and not (faltan or distintos or faltan_fichero):
        print("\nTRANSFERENCIAS BIEN: todo lo enviado está y es idéntico.")
        return 0
    print("\nREVISAR: hay envíos que no cuadran (ver arriba).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
