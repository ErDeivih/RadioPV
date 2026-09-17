"""Espera a que termine la copia de la música y comprueba el resultado.

POR QUÉ EXISTE
--------------
El objetivo era "terminar de copiar los ficheros de audio y comprobar que las playlists dejan de
saltarse canciones". La copia tarda horas, así que la comprobación no puede depender de que
alguien esté mirando: este vigilante espera, mide y **avisa al móvil** por ntfy cuando termina.

Qué mide, dentro del contenedor del API (que es donde están la base y el disco):
  · cuántas canciones publicadas NO tienen fichero (cada una es una canción que el reproductor
    intentará, recibirá un 410 y saltará),
  · si la primera canción de la lista "Novedades" ya suena (era el caso concreto que fallaba).

Uso:
    python _deploy/vigilar-copia.py              # espera y comprueba
    python _deploy/vigilar-copia.py --una-vez    # comprueba ya, sin esperar
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

SERVIDOR = "david@servidor.local"
TOTAL_TROZOS = 135
TOPIC = "alertas-servidor"


def ssh(cmd: str, timeout: int = 120) -> str:
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", SERVIDOR, cmd],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    return (r.stdout or "") + (r.stderr or "")


def trozos_hechos() -> int:
    salida = ssh("ls /tmp/radiopv-musica/*.done 2>/dev/null | wc -l")
    m = re.search(r"(\d+)", salida)
    return int(m.group(1)) if m else 0


def avisar(texto: str, titulo: str = "RadioPV") -> None:
    # ntfy está en el servidor; el móvil está suscrito a este tema (lo usan el vigilante y el
    # botón de encendido del PC).
    ssh(f"curl -s -H 'Title: {titulo}' -d {_citar(texto)} http://127.0.0.1:8085/{TOPIC} >/dev/null")


def _citar(texto: str) -> str:
    return "'" + texto.replace("'", "") + "'"


def medir() -> str:
    """Devuelve el informe de `scripts/estado_musica.py` ejecutado en el servidor."""
    scp = subprocess.run(["scp", "-q", "scripts/estado_musica.py", f"{SERVIDOR}:/tmp/em.py"],
                         capture_output=True, text=True, timeout=120)
    if scp.returncode != 0:
        print(f"    [aviso] no se pudo copiar el medidor: {scp.stderr.strip()[:120]}", flush=True)

    orden = ("docker cp /tmp/em.py radiopv-api:/tmp/em.py >/dev/null 2>&1; "
             "docker exec radiopv-api python3 /tmp/em.py --muestra 1200 --playlist 2 2>&1")
    salida = ssh(orden, timeout=600)
    if not salida.strip():
        # Puede coincidir con un reinicio del contenedor (el autodespliegue recrea la API).
        print("    [aviso] la medición salió vacía; reintentando en 30 s...", flush=True)
        time.sleep(30)
        salida = ssh(orden, timeout=600)
    return salida


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--una-vez", action="store_true")
    args = ap.parse_args()

    if not args.una_vez:
        print(f"[i] esperando a que la copia llegue a {TOTAL_TROZOS} trozos...", flush=True)
        visto = -1
        ultimo_cambio = time.time()
        # Un trozo que falle con tar NO deja marcador (el script lo manda por scp y sigue), así que
        # esperar sólo a los 135 marcadores puede quedarse esperando para siempre. Si el contador
        # no se mueve en 45 minutos (un trozo tarda 4), se da por detenida y se mide lo que haya.
        SIN_AVANZAR = 45 * 60
        while True:
            n = trozos_hechos()
            if n != visto:
                print(f"    trozos hechos: {n}/{TOTAL_TROZOS}", flush=True)
                visto = n
                ultimo_cambio = time.time()
            if n >= TOTAL_TROZOS:
                break
            if time.time() - ultimo_cambio > SIN_AVANZAR:
                print(f"    [aviso] la copia lleva {SIN_AVANZAR // 60} min sin avanzar en {n}"
                      f"/{TOTAL_TROZOS}: se mide lo que hay", flush=True)
                break
            time.sleep(300)
        print("[i] la copia ha terminado; midiendo el resultado...", flush=True)
        # Un margen para que el último trozo se descomprima y se coloque.
        time.sleep(60)

    informe = medir()
    print(informe)

    m = re.search(r"SIN fichero \(el reproductor salta\)\s*:\s*(\d+)", informe)
    faltan = int(m.group(1)) if m else -1
    m2 = re.search(r"se puede escuchar el ([\d.,]+) %", informe)
    pct = m2.group(1) if m2 else "?"
    saltos = re.findall(r"SE SALTA", informe)

    if faltan == 0:
        veredicto = f"LISTO: no falta ningún fichero de las canciones revisadas ({pct} % sonable)."
    elif faltan < 0:
        veredicto = "No se pudo interpretar el informe; míralo a mano."
    else:
        veredicto = (f"Faltan {faltan} ficheros de las revisadas (se puede escuchar el {pct} %). "
                     f"El reproductor se salta {len(saltos)} de la lista de prueba.")

    print("\n>>> " + veredicto)
    avisar(veredicto, "RadioPV: música copiada")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
