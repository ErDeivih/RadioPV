"""Valida la decision del corrector con casos simulados (prueba de regresion).

No basta con mirar los numeros del croma y el mfcc: hay que comprobar que la LOGICA que
los interpreta acierta. Aqui se construyen los dos casos que importan:

  · FICHA CORRECTA: el fichero de A, presentado como A, con el preview de A.
        -> debe salir 'correcta' (o 'metadatos', si ademas hay algo que corregir)

  · FICHA CRUZADA: el fichero de A, presentado como si fuera B (el caso real de «alguien
    etiqueto mal este mp3»), comparado con el preview de B.
        -> debe salir 'otra_cancion'

Se llama a `decidir` directamente, con las comprobaciones que no son de audio ya resueltas,
para aislar lo que se esta probando y no depender de la red mas de lo necesario.

    python scripts/validar_corrector.py            # 4 canciones
    python scripts/validar_corrector.py 6
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from radiov import corrector as CO, db, deezer as dz  # noqa: E402


def fichero_ok_sintetico(track: dict) -> dict:
    """Dar por bueno el fichero: lo que se prueba aqui es la decision sobre el audio."""
    return {"ok": True, "problemas": [], "duration": track.get("duration"),
            "estado": "ok", "rms": 0.2}


def main() -> int:
    db.init_db()
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    conn = db.get_conn()
    try:
        filas = conn.execute(
            "SELECT * FROM tracks WHERE file_path IS NOT NULL AND file_path!='' "
            "AND deezer_id IS NOT NULL GROUP BY artist LIMIT ?", (n,)).fetchall()
    finally:
        conn.close()
    tracks = [dict(f) for f in filas]

    cliente = dz.DeezerClient()
    previews: dict[int, str] = {}
    for t in tracks:
        try:
            p = cliente.track_detail(str(t["deezer_id"])).get("preview")
            if p:
                previews[t["id"]] = p
        except Exception:  # noqa: BLE001
            pass

    print(f"\n  {len(previews)} canciones con preview")
    print(f"  umbrales: croma>={CO.UMBRAL_CROMA_MISMA} dudoso<{CO.UMBRAL_CROMA_DUDOSA} "
          f"mfcc>={CO.UMBRAL_MFCC_MISMA}\n")

    aciertos = fallos = 0

    for t in tracks:
        if t["id"] not in previews:
            continue
        etiqueta = f"{t['artist']} - {t['title']}"

        # ---------- caso 1: ficha correcta ----------
        audio = CO.comparar_audio(t, previews[t["id"]])
        v, probs, corr = CO.decidir(
            t, fichero_ok_sintetico(t), {}, {"ok": None},
            {"ok": True, "candidato": {}, "guardado": {}}, audio, {"ok": False})
        ok = v in (CO.CORRECTA, CO.METADATOS)
        aciertos += 1 if ok else 0
        fallos += 0 if ok else 1
        print(f"  {'OK ' if ok else 'FALLO'} ficha correcta · {etiqueta[:44]:<44} "
              f"-> {v}  (croma={audio.get('croma')}, mfcc={audio.get('mfcc')})")

        # ---------- caso 2: ficha cruzada ----------
        for otro in tracks:
            if otro["id"] == t["id"] or otro["id"] not in previews:
                continue
            if CO.clave(otro["artist"]) == CO.clave(t["artist"]):
                continue
            # El fichero de `t`, pero la ficha dice que es `otro`.
            falsa = dict(t)
            falsa["title"] = otro["title"]
            falsa["artist"] = otro["artist"]
            falsa["album"] = otro.get("album")
            falsa["deezer_id"] = otro.get("deezer_id")
            audio2 = CO.comparar_audio(falsa, previews[otro["id"]])
            v2, probs2, _ = CO.decidir(
                falsa, fichero_ok_sintetico(falsa), {}, {"ok": None},
                {"ok": True, "candidato": {}, "guardado": {}}, audio2, {"ok": False})
            # Se acepta otra_cancion u otra_version: lo que importa es que quede marcado como
            # «hay que reemplazar el fichero». Distinguir un cover de una cancion distinta
            # con estas medidas no siempre es posible, y el corrector no lo finge.
            ok2 = v2 in CO.NECESITAN_DESCARGA
            aciertos += 1 if ok2 else 0
            fallos += 0 if ok2 else 1
            cola = f"  <- {probs2[-1][:60]}" if probs2 else ""
            print(f"  {'OK ' if ok2 else 'FALLO'} ficha cruzada  · "
                  f"fichero de «{t['artist']}» como si fuera «{otro['artist']}» "
                  f"-> {v2}  (croma={audio2.get('croma')}, mfcc={audio2.get('mfcc')}){cola}")

    print("\n" + "=" * 74)
    print(f"  {aciertos} aciertos, {fallos} fallos de {aciertos + fallos}")
    if fallos:
        print("  -> hay que ajustar la logica o los umbrales")
        return 1
    print("  -> la decision acierta en todos los casos probados")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
