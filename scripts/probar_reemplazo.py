"""Prueba de punta a punta del reemplazo de fichero, en un entorno AISLADO.

Es la prueba que de verdad importa del corrector: que ante un fichero que NO es la cancion
que dice ser, sea capaz de detectarlo, descargar la buena, comprobar que la nueva si cuadra
y apartar la vieja.

Se hace todo en directorios temporales propios (variables RADIOPV_DATA_DIR y
RADIOPV_BASE_MUSIC) para NO tocar la biblioteca real. Si algo sale mal, se borra la carpeta
temporal y ya esta.

    python scripts/probar_reemplazo.py
    python scripts/probar_reemplazo.py --sin-descargar    # solo la deteccion
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

# La consola de Windows usa cp1252 y revienta con los simbolos de los mensajes (≥, →).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

RAIZ = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Aislamiento: esto tiene que ir ANTES de importar radiov, porque config.py lee las
# variables de entorno al importarse.
# ---------------------------------------------------------------------------
BASE_TMP = Path(tempfile.gettempdir()) / "radiopv-prueba-reemplazo"
if BASE_TMP.exists():
    shutil.rmtree(BASE_TMP, ignore_errors=True)
MUSICA = BASE_TMP / "musica"
DATOS = BASE_TMP / "datos"
(MUSICA / "catalogada").mkdir(parents=True)
(MUSICA / "descargas").mkdir(parents=True)
DATOS.mkdir(parents=True)
os.environ["RADIOPV_BASE_MUSIC"] = str(MUSICA)
os.environ["RADIOPV_DATA_DIR"] = str(DATOS)
os.environ["RADIOPV_RAW_DIR"] = str(MUSICA / "descargas")
os.environ["RADIOPV_CATALOG_DIR"] = str(MUSICA / "catalogada")

sys.path.insert(0, str(RAIZ))

from radiov import corrector as CO, db, deezer as dz  # noqa: E402

# Una cancion real, con deezer_id, tomada del catalogo de verdad (solo lectura).
CATALOGO_REAL = RAIZ / "data" / "radiov.db"


def cancion_de_prueba() -> tuple[dict, Path]:
    """Coge una cancion real del catalogo y devuelve su ficha y un fichero suyo."""
    import sqlite3
    if not CATALOGO_REAL.exists():
        raise SystemExit(f"no encuentro el catalogo real en {CATALOGO_REAL}")
    conn = sqlite3.connect(str(CATALOGO_REAL))
    conn.row_factory = sqlite3.Row
    # Se pide una que tenga deezer_id y cuyo fichero exista de verdad.
    filas = conn.execute(
        "SELECT * FROM tracks WHERE deezer_id IS NOT NULL AND file_path IS NOT NULL "
        "AND file_path!='' ORDER BY id LIMIT 60").fetchall()
    conn.close()
    for f in filas:
        t = dict(f)
        p = CO.resolve_music(t["file_path"])
        if p.exists() and p.stat().st_size > 1_000_000:
            return t, p
    raise SystemExit("no encontre ninguna cancion con fichero en el catalogo real")


def main() -> int:
    sin_descargar = "--sin-descargar" in sys.argv
    fallos = 0

    def check(nombre: str, ok: bool, detalle: str = "") -> None:
        nonlocal fallos
        if not ok:
            fallos += 1
        print(f"  [{'OK ' if ok else 'FALLO'}] {nombre}" + (f"  ·  {detalle}" if detalle else ""))

    print("=" * 76)
    print("  PRUEBA DEL REEMPLAZO DE FICHERO (en directorios temporales)")
    print(f"  musica de prueba: {MUSICA}")
    print("=" * 76)

    real, fichero_real = cancion_de_prueba()
    print(f"\n  cancion de prueba: {real['artist']} - {real['title']}  (id real={real['id']})")
    print(f"  su fichero bueno : {fichero_real.name} ({fichero_real.stat().st_size/1e6:.1f} MB)")

    # ------------------------------------------------------------------
    # Se monta el caso: un fichero que NO es esa cancion, pero etiquetado como si lo fuera.
    # Se usa el audio de OTRA cancion distinta del catalogo.
    # ------------------------------------------------------------------
    import sqlite3
    conn = sqlite3.connect(str(CATALOGO_REAL))
    conn.row_factory = sqlite3.Row
    otra = None
    for f in conn.execute("SELECT * FROM tracks WHERE artist != ? AND file_path IS NOT NULL "
                          "ORDER BY id LIMIT 40", (real["artist"],)).fetchall():
        p = CO.resolve_music(dict(f)["file_path"])
        if p.exists() and p.stat().st_size > 1_000_000 and CO.clave(dict(f)["artist"]) != CO.clave(real["artist"]):
            otra = dict(f)
            break
    conn.close()
    if not otra:
        raise SystemExit("no encontre una segunda cancion para hacer de fichero equivocado")

    fichero_ajeno = CO.resolve_music(otra["file_path"])
    print(f"  audio que se pondrá en su lugar (a propósito): "
          f"{otra['artist']} - {otra['title']}")

    # El fichero malo, en la carpeta del bueno
    carpeta = MUSICA / "catalogada" / real["artist"] / f"[{real.get('year') or 2020}] {real.get('album') or 'Album'}"
    carpeta.mkdir(parents=True, exist_ok=True)
    destino_malo = carpeta / f"{real['artist']} - {real['title']}.mp3"
    shutil.copy2(fichero_ajeno, destino_malo)
    tamano_malo = destino_malo.stat().st_size
    print(f"  fichero colocado : {destino_malo.relative_to(MUSICA)}  "
          f"({tamano_malo/1e6:.1f} MB, es otra cancion a proposito)")

    # ------------------------------------------------------------------
    # La ficha, en la base de datos de prueba
    # ------------------------------------------------------------------
    db.init_db()
    rec = {k: real.get(k) for k in (
        "title", "artist", "album", "year", "genre", "language", "bpm", "energy", "gain_db",
        "duration", "deezer_id", "album_id", "cover_url", "rank", "source", "status")}
    rec["file_path"] = str(destino_malo.relative_to(MUSICA)).replace("\\", "/")
    rec["file_size"] = destino_malo.stat().st_size
    tid = db.add_track(rec)
    print(f"  ficha creada en la BD de prueba con id={tid}")

    t = db.get_track_by_id(tid)

    # ------------------------------------------------------------------
    # 1. ¿Lo detecta?
    # ------------------------------------------------------------------
    print("\n  --- 1. deteccion ---")
    a = CO.analizar(t, con_youtube=False)
    aud = a.detalle.get("audio") or {}
    print(f"      veredicto: {a.veredicto}   croma={aud.get('croma')}  mfcc={aud.get('mfcc')}")
    for p in a.problemas[:3]:
        print(f"      · {p}")
    check("detecta que el fichero es OTRA cancion", a.veredicto == CO.OTRA_CANCION,
          f"veredicto={a.veredicto}")

    if sin_descargar:
        print("\n  (--sin-descargar: no se prueba el reemplazo)")
        shutil.rmtree(BASE_TMP, ignore_errors=True)
        return 1 if fallos else 0

    # ------------------------------------------------------------------
    # 2. ¿Lo reemplaza?
    # ------------------------------------------------------------------
    print("\n  --- 2. reemplazo (descarga de verdad) ---")
    res = CO.reemplazar_fichero(t, a)
    for paso in res.get("pasos", []):
        print(f"      · {paso}")
    if res.get("error"):
        print(f"      [X] {res['error']}")
    check("ha reemplazado el fichero", bool(res.get("reemplazado")),
          str(res.get("error") or ""))

    if not res.get("reemplazado"):
        print("\n  (no se puede seguir sin reemplazo)")
        shutil.rmtree(BASE_TMP, ignore_errors=True)
        return 1

    # ------------------------------------------------------------------
    # 3. ¿El fichero nuevo es el bueno?
    # ------------------------------------------------------------------
    print("\n  --- 3. comprobaciones finales ---")
    t2 = db.get_track_by_id(tid)
    ruta_nueva = CO.resolve_music(t2["file_path"])
    check("el fichero nuevo existe", ruta_nueva.exists(), str(ruta_nueva))
    check("esta en la carpeta de la cancion correcta",
          CO.clave(real["artist"]) in CO.clave(str(ruta_nueva)),
          str(ruta_nueva.relative_to(MUSICA)))

    # Comparar el fichero nuevo con el preview: tiene que cuadrar
    cliente = dz.DeezerClient()
    cand = (a.detalle.get("deezer") or {}).get("candidato") or {}
    preview = cand.get("preview") or (a.detalle.get("deezer") or {}).get("guardado", {}).get("preview")
    if preview:
        comp = CO.comparar_audio(t2, preview)
        print(f"      verificacion del nuevo: croma={comp.get('croma')} mfcc={comp.get('mfcc')}")
        check("el fichero nuevo SI cuadra con la cancion",
              bool(comp.get("ok")) and comp["croma"] >= CO.UMBRAL_CROMA_MISMA
              and comp["mfcc"] >= CO.UMBRAL_MFCC_MISMA,
              f"croma={comp.get('croma')} mfcc={comp.get('mfcc')}")

    # El viejo, apartado
    descartes = MUSICA / "_descartes"
    apartados = list(descartes.rglob("*.mp3")) if descartes.exists() else []
    check("el fichero viejo se aparto en _descartes (no se borro)", len(apartados) == 1,
          str(apartados[0].relative_to(MUSICA)) if apartados else "no hay ninguno")
    if apartados:
        # OJO: hay que comparar con el tamano capturado ANTES del reemplazo. Despues, la
        # ruta original vuelve a existir (la ocupa el fichero nuevo), asi que mirarla
        # despues compara dos cosas distintas y da un falso fallo.
        check("lo apartado es el fichero viejo de verdad (mismo tamano)",
              apartados[0].stat().st_size == tamano_malo,
              f"{apartados[0].stat().st_size/1e6:.1f} MB frente a {tamano_malo/1e6:.1f} MB")

    print("\n  El arbol de la musica de prueba queda asi:")
    for p in sorted(MUSICA.rglob("*")):
        if p.is_file():
            print(f"      {p.relative_to(MUSICA)}  ({p.stat().st_size/1e6:.1f} MB)")

    shutil.rmtree(BASE_TMP, ignore_errors=True)
    print(f"\n  (entorno temporal borrado)")
    print("=" * 76)
    if fallos:
        print(f"  {fallos} comprobacion(es) fallidas")
        return 1
    print("  TODAS LAS COMPROBACIONES OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
