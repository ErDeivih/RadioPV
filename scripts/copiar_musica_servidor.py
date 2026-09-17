"""Copia la musica del catalogo al servidor. Reanudable y con dos vias de envio.

Por que dos vias:
  · Solo se copian los ficheros que el catalogo REFERENCIA (file_path), no toda la
    carpeta E:\\Musica\\catalogada (que tiene ~40 GB de ficheros sin catalogar).
  · tar es rapido (un flujo por trozo) pero bsdtar en Windows convierte los argumentos
    de UTF-16 a la codepage ANSI local: cualquier nombre con caracteres fuera de cp1252
    (cirilico, japones, tildes combinantes) hace que bsdtar busque una ruta vacia y
    falle. De ahi que esos ficheros se aparten y vayan por scp, que es UTF-8 de punta
    a punta, con un manifiesto para colocarlos en su sitio sin pasar por el shell.
  · Cada trozo lleva un marcador .done en el servidor: si el proceso se corta, al
    relanzarlo se salta lo ya hecho.

Uso:
    python scripts/copiar_musica_servidor.py                # copia (reanudable)
    python scripts/copiar_musica_servidor.py --simular      # solo cuenta y planifica
    python scripts/copiar_musica_servidor.py --estado       # cuantos trozos hay hechos
    python scripts/copiar_musica_servidor.py --especiales   # solo los ficheros "dificiles"

Antes de usarlo hace falta la copia normalizada de las BD:
    python scripts/preparar_despliegue.py --out _deploy
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

RAIZ = Path(__file__).resolve().parent.parent
DB = RAIZ / "_deploy" / "radiov.db"
MUSICA_LOCAL = Path(r"E:\Musica")
SERVIDOR = "david@servidor.local"
REMOTO_BASE = "/srv/data/media/music"
REMOTO_TMP = "/tmp/radiopv-musica"
ESP_TMP = "/tmp/radiopv-especiales"
IMAGEN = "radiopv-api"
TMP_LOCAL = RAIZ / "_deploy" / "_trozos"
COLOCADOR = RAIZ / "scripts" / "colocar_despliegue.py"

TAMANO_TROZO_MB = 400
# bsdtar en Windows falla con muchos argumentos por un limite interno de longitud.
MAX_FICHEROS_TROZO = 40


def sh(cmd: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def apto_para_tar(rel: str) -> bool:
    """True si bsdtar podra leer el nombre: todo el texto debe caber en cp1252."""
    try:
        rel.encode("cp1252")
        return True
    except UnicodeEncodeError:
        return False


def listar() -> tuple[list[tuple[str, Path, int]], list[str], list[tuple[str, Path, int]]]:
    conn = sqlite3.connect(str(DB))
    try:
        filas = [r[0] for r in conn.execute(
            "SELECT file_path FROM tracks WHERE file_path IS NOT NULL AND file_path!=''")]
    finally:
        conn.close()

    aptos: list[tuple[str, Path, int]] = []
    especiales: list[tuple[str, Path, int]] = []
    ausentes: list[str] = []
    for rel in filas:
        local = MUSICA_LOCAL / Path(rel.replace("/", "\\"))
        if not local.is_file():
            ausentes.append(rel)
            continue
        (aptos if apto_para_tar(rel) else especiales).append((rel, local, local.stat().st_size))
    return aptos, ausentes, especiales


def trocear(items: list[tuple[str, Path, int]]) -> list[list[tuple[str, Path, int]]]:
    trozos: list[list[tuple[str, Path, int]]] = []
    actual: list[tuple[str, Path, int]] = []
    peso = 0
    for it in items:
        mb = it[2] / 1e6
        if actual and (peso + mb > TAMANO_TROZO_MB or len(actual) >= MAX_FICHEROS_TROZO):
            trozos.append(actual)
            actual, peso = [], 0
        actual.append(it)
        peso += mb
    if actual:
        trozos.append(actual)
    return trozos


def existe_marcador(ruta: str) -> bool:
    r = sh(["ssh", "-4", "-o", "BatchMode=yes", SERVIDOR, f"test -f {ruta} && echo si"])
    return "si" in r.stdout


def enviar_trozo(i: int, trozo: list[tuple[str, Path, int]]) -> tuple[bool, str, float]:
    """Devuelve (ok, motivo, segundos_de_envio)."""
    tar_local = TMP_LOCAL / f"chunk_{i:03d}.tar"
    tar_local.unlink(missing_ok=True)
    args_tar = ["tar", "-cf", str(tar_local), "-C", str(MUSICA_LOCAL)]
    args_tar += [rel for rel, _, _ in trozo]

    r = sh(args_tar, timeout=1800)
    if r.returncode != 0:
        return False, f"tar: {(r.stderr or '').strip()[:150]}", 0.0

    t0 = time.time()
    r = sh(["scp", "-4", "-o", "BatchMode=yes", str(tar_local),
            f"{SERVIDOR}:{REMOTO_TMP}/chunk_{i:03d}.tar"], timeout=10800)
    if r.returncode != 0:
        return False, f"scp: {(r.stderr or '').strip()[:150]}", time.time() - t0
    t_scp = time.time() - t0

    cmd = (f"docker run --rm -v {REMOTO_TMP}:/src:ro -v {REMOTO_BASE}:/dst {IMAGEN} "
           f"tar -xf /src/chunk_{i:03d}.tar -C /dst && "
           f"rm -f {REMOTO_TMP}/chunk_{i:03d}.tar && touch {REMOTO_TMP}/chunk_{i:03d}.done")
    r = sh(["ssh", "-4", "-o", "BatchMode=yes", SERVIDOR, cmd], timeout=3600)
    if r.returncode != 0:
        return False, f"extraccion: {(r.stderr or '').strip()[:150]}", t_scp

    tar_local.unlink(missing_ok=True)
    return True, "", t_scp


def enviar_especiales(especiales: list[tuple[str, Path, int]], trozo: int = 0) -> int:
    """Envia los ficheros que tar no puede manejar: scp suelto + manifiesto + colocador."""
    if not especiales:
        return 0

    print(f"  [especiales] {len(especiales)} ficheros por la via scp+manifiesto")
    sh(["ssh", "-4", "-o", "BatchMode=yes", SERVIDOR,
        f"rm -rf {ESP_TMP} && mkdir -p {ESP_TMP}"])

    manifiesto: list[str] = []
    enviados = 0
    t0 = time.time()
    for i, (rel, local, _size) in enumerate(especiales):
        temp = f"e{trozo:02d}{i:04d}.mp3"
        r = sh(["scp", "-4", "-o", "BatchMode=yes", str(local), f"{SERVIDOR}:{ESP_TMP}/{temp}"],
               timeout=3600)
        if r.returncode != 0:
            print(f"      [X] scp fallo para {rel}: {(r.stderr or '').strip()[:120]}")
            continue
        manifiesto.append(f"{temp}\t{rel}")
        enviados += 1
        if enviados % 10 == 0:
            print(f"      ... {enviados}/{len(especiales)} "
                  f"({time.time()-t0:.0f}s)", flush=True)

    if not manifiesto:
        print("      [X] no se envio ninguno")
        return 0

    local_man = TMP_LOCAL / f"manifiesto_{trozo:02d}.txt"
    local_man.parent.mkdir(parents=True, exist_ok=True)
    local_man.write_text("\n".join(manifiesto) + "\n", encoding="utf-8", newline="\n")

    sh(["scp", "-4", "-o", "BatchMode=yes", str(local_man), f"{SERVIDOR}:{ESP_TMP}/manifiesto.txt"])
    sh(["scp", "-4", "-o", "BatchMode=yes", str(COLOCADOR),
        f"{SERVIDOR}:{ESP_TMP}/colocar.py"])

    cmd = (f"docker run --rm -v {ESP_TMP}:/work -v {REMOTO_BASE}:/dst {IMAGEN} "
           f"python /work/colocar.py")
    r = sh(["ssh", "-4", "-o", "BatchMode=yes", SERVIDOR, cmd], timeout=3600)
    print("      " + (r.stdout or "").strip().replace("\n", "\n      "))
    if r.returncode != 0:
        print(f"      [X] el colocador fallo: {(r.stderr or '').strip()[:200]}")
        return 0

    sh(["ssh", "-4", "-o", "BatchMode=yes", SERVIDOR, f"rm -rf {ESP_TMP}"])
    sh(["ssh", "-4", "-o", "BatchMode=yes", SERVIDOR,
        f"touch {REMOTO_TMP}/especiales_{trozo:02d}.done"])
    return enviados


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--simular", action="store_true")
    ap.add_argument("--estado", action="store_true")
    ap.add_argument("--especiales", action="store_true",
                    help="envia solo los ficheros que tar no puede manejar")
    ap.add_argument("--rehacer", action="store_true", help="ignora los marcadores .done")
    ap.add_argument("--max-trozos", type=int, default=0, help="0 = todos")
    args = ap.parse_args()

    TMP_LOCAL.mkdir(parents=True, exist_ok=True)

    print(f"[i] leyendo el catalogo {DB}")
    aptos, ausentes, especiales = listar()
    total = sum(p[2] for p in aptos) + sum(p[2] for p in especiales)
    print(f"[i] aptos para tar (todo cp1252)      : {len(aptos)}")
    print(f"[i] con caracteres fuera de cp1252    : {len(especiales)}  (van por scp)")
    print(f"[i] referenciadas SIN fichero en disco: {len(ausentes)}")
    print(f"[i] peso total a copiar               : {total/1e9:.2f} GB")
    if ausentes:
        print("      primeras ausentes:")
        for a in ausentes[:6]:
            print(f"        {a}")

    trozos = trocear(aptos)
    print(f"[i] trozos de tar: {len(trozos)} "
          f"(max {TAMANO_TROZO_MB} MB / {MAX_FICHEROS_TROZO} ficheros)")

    if args.estado or args.simular:
        hechos = sum(1 for i in range(len(trozos)) if existe_marcador(f"{REMOTO_TMP}/chunk_{i:03d}.done"))
        esp = existe_marcador(f"{REMOTO_TMP}/especiales_00.done")
        print(f"[i] trozos hechos en el servidor: {hechos}/{len(trozos)}")
        print(f"[i] especiales enviados: {'si' if esp else 'no'}")
        if args.simular:
            for i, t in enumerate(trozos[:3]):
                print(f"    trozo {i}: {len(t)} ficheros, {sum(x[2] for x in t)/1e6:.0f} MB")
            if especiales:
                print("    especiales (ejemplos):")
                for rel, _, _ in especiales[:6]:
                    print(f"      {rel}")
        return 0

    sh(["ssh", "-4", "-o", "BatchMode=yes", SERVIDOR,
        f"mkdir -p {REMOTO_TMP} {REMOTO_BASE}/catalogada"])

    if args.especiales:
        n = enviar_especiales(especiales)
        print(f"[OK] especiales enviados: {n}")
        return 0

    t_inicio = time.time()
    copiados = saltados = fallos = 0
    a_especiales: list[tuple[str, Path, int]] = []

    for i, trozo in enumerate(trozos):
        if args.max_trozos and copiados + saltados >= args.max_trozos:
            print(f"  [i] tope de --max-trozos ({args.max_trozos}) alcanzado")
            break
        if not args.rehacer and existe_marcador(f"{REMOTO_TMP}/chunk_{i:03d}.done"):
            saltados += 1
            print(f"  [{i:03d}/{len(trozos)}] ya hecho, se salta")
            continue

        peso_mb = sum(x[2] for x in trozo) / 1e6
        print(f"  [{i:03d}/{len(trozos)}] {len(trozo)} ficheros · {peso_mb:.0f} MB · "
              f"empezando...", flush=True)
        ok, motivo, t_scp = enviar_trozo(i, trozo)
        if not ok:
            print(f"      [!] fallo ({motivo}) -> sus ficheros pasan a la via scp")
            a_especiales.extend(trozo)
            fallos += 1
            continue

        copiados += 1
        hecho_gb = sum(sum(x[2] for x in t) for t in trozos[:i + 1]) / 1e9
        vel = peso_mb / t_scp if t_scp > 0 else 0
        eta_h = ((total / 1e6 - hecho_gb * 1000) / vel / 3600) if vel > 0 else 0
        print(f"      OK · envio {t_scp/60:.1f} min ({vel*8:.1f} Mbit/s) · "
              f"llevamos {hecho_gb:.1f} GB · faltan ~{eta_h:.1f} h", flush=True)

    if a_especiales:
        print(f"\n  [i] {len(a_especiales)} ficheros que fallaron con tar pasan a scp")
        añadidos = enviar_especiales(a_especiales, trozo=99)

    if especiales:
        print()
        enviar_especiales(especiales, trozo=0)

    dur = (time.time() - t_inicio) / 3600
    print()
    print(f"[OK] trozos copiados: {copiados} · saltados: {saltados} · fallos de tar: {fallos}")
    print(f"[OK] tiempo total: {dur:.2f} h")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
