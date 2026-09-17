"""Prueba de codificacion: tar + scp + extraccion con nombres acentuados y corchetes.

Crea una estructura local con nombres identicos a los reales del catalogo, la empaqueta
con bsdtar, la envia al servidor y comprueba que los nombres llegan intactos.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(r"F:\EspacioCodigo\RadioPV\_deploy\_prueba-tar")
SERVER = "david@servidor.local"
REMOTO_TAR = "/tmp/_prueba-nombres.tar"
REMOTO_DIR = "/tmp/_prueba-nombres"

NOMBRES = [
    "ADÉLA/[2026] PRIMA/ADÉLA - Nicole Kidman.mp3",
    "Bad Bunny/[2025] DeBí TiRAR MáS FOToS/Bad Bunny - NUEVAYoL.mp3",
    "Jhené Aiko/[2026] Westside Whimsy/Jhené Aiko - So Good (feat. Kendrick Lamar).mp3",
    "KAROL G/[2026] NO ME ARREPIENTO DE SENTIR TANTO/KAROL G - BbY WOW.mp3",
    "_suelto/Canción ñoña — guión y ¡signos!.mp3",
]


def sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", **kw)


def main() -> int:
    if BASE.exists():
        shutil.rmtree(BASE)
    BASE.mkdir(parents=True)

    # 1. Crear los ficheros de prueba
    for nombre in NOMBRES:
        destino = BASE / Path(nombre)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(f"contenido de {nombre}", encoding="utf-8")
    print(f"  [1] creados {len(NOMBRES)} ficheros de prueba")

    # 2. Lista en UTF-8 sin BOM
    lista = BASE / "_lista.txt"
    lista.write_text("\n".join(NOMBRES) + "\n", encoding="utf-8", newline="\n")
    print(f"  [2] lista escrita ({lista.stat().st_size} bytes)")

    # 3. tar con bsdtar
    tar = BASE / "_prueba.tar"
    r = sh(["tar", "-cf", str(tar), "-C", str(BASE), "-T", str(lista)])
    if r.returncode != 0:
        print("  [X] tar fallo:", r.stderr.strip()[:400])
        return 1
    print(f"  [3] tar creado: {tar.stat().st_size} bytes")

    # 4. Ver el contenido que grabo el tar
    r = sh(["tar", "-tf", str(tar)])
    dentro = [l for l in r.stdout.splitlines() if l.strip()]
    print(f"  [4] el tar contiene {len(dentro)} entradas:")
    for l in dentro:
        print(f"        {l}")
    if len(dentro) != len(NOMBRES):
        print(f"  [X] se esperaban {len(NOMBRES)} entradas")
        return 1

    # 5. Enviar
    r = sh(["scp", "-4", "-o", "BatchMode=yes", str(tar), f"{SERVER}:{REMOTO_TAR}"])
    if r.returncode != 0:
        print("  [X] scp fallo:", r.stderr.strip()[:400])
        return 1
    print("  [5] enviado al servidor")

    # 6. Extraer alli
    cmd = (f"rm -rf {REMOTO_DIR} && mkdir -p {REMOTO_DIR} && "
           f"tar -xf {REMOTO_TAR} -C {REMOTO_DIR} && find {REMOTO_DIR} -type f | sort")
    r = sh(["ssh", "-4", "-o", "BatchMode=yes", SERVER, cmd])
    if r.returncode != 0:
        print("  [X] extraccion fallo:", r.stderr.strip()[:400])
        return 1
    remotos = sorted(l.replace(REMOTO_DIR + "/", "")
                     for l in r.stdout.splitlines() if l.strip())
    print(f"  [6] extraidos {len(remotos)} ficheros en el servidor:")
    for l in remotos:
        print(f"        {l}")

    # 7. Comparar
    esperados = sorted(NOMBRES)
    print()
    if remotos == esperados:
        print("  [OK] los nombres llegan IDENTICOS (acentos y corchetes intactos)")
        ok = True
    else:
        print("  [X] los nombres NO coinciden:")
        for a, b in zip(esperados, remotos):
            marca = "  " if a == b else ">>"
            print(f"      {marca} local={a!r}")
            if a != b:
                print(f"         remoto={b!r}")
        ok = False

    # 8. Limpieza
    sh(["ssh", "-4", "-o", "BatchMode=yes", SERVER,
        f"rm -rf {REMOTO_DIR} {REMOTO_TAR}"])
    print("  [8] limpieza hecha en el servidor")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
