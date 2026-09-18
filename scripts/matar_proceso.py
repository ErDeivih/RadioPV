"""Mata un proceso por el nombre de su línea de comandos (no hay `ps` ni `pkill` en la imagen).

Uso:  python matar_proceso.py analisis_completo
"""
import os
import signal
import sys

objetivo = sys.argv[1] if len(sys.argv) > 1 else "analisis_completo"
muertos = []

for pid in os.listdir("/proc"):
    if not pid.isdigit() or int(pid) == os.getpid():
        continue
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            linea = f.read().replace(b"\x00", b" ").decode("utf-8", "replace")
    except OSError:
        continue
    if objetivo in linea:
        try:
            os.kill(int(pid), signal.SIGTERM)
            muertos.append((pid, linea.strip()[:100]))
        except OSError as e:
            print(f"no se pudo matar {pid}: {e}")

if muertos:
    for pid, linea in muertos:
        print(f"terminado {pid}: {linea}")
else:
    print(f"no había ningún proceso con «{objetivo}» en su línea de comandos")
