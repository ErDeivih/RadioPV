"""Calibra los umbrales del corrector con controles positivos y negativos.

Positivo: la cancion contra SU PROPIO preview (deberia dar alto y alto).
Negativo: la cancion contra el preview de OTRA cancion (deberia dar croma bajo).
Asi se ve la separacion real entre «es la misma» y «es otra», que es lo que decide los
umbrales. Sin esto, los numeros son inventados: la primera version del corrector uso 0.78
y 0.80 «a ojo», y con esos valores una cancion completamente distinta (croma 0.931) pasaba
por buena mientras que una grabacion correcta (mfcc 0.588) se marcaba como cover.

    python scripts/calibrar_corrector.py            # 4 canciones
    python scripts/calibrar_corrector.py 8          # 8 canciones
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from radiov import corrector as CO, db, deezer as dz  # noqa: E402


def main() -> int:
    db.init_db()
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    conn = db.get_conn()
    try:
        # Se eligen canciones de artistas DISTINTOS para que los negativos sean claros.
        filas = conn.execute(
            "SELECT * FROM tracks WHERE file_path IS NOT NULL AND file_path!='' "
            "AND deezer_id IS NOT NULL GROUP BY artist LIMIT ?", (n,)).fetchall()
    finally:
        conn.close()
    tracks = [dict(f) for f in filas]
    if len(tracks) < 2:
        print("  hacen falta al menos 2 canciones")
        return 1

    cliente = dz.DeezerClient()
    previews: dict[int, str] = {}
    for t in tracks:
        try:
            det = cliente.track_detail(str(t["deezer_id"]))
            p = det.get("preview")
            if p:
                previews[t["id"]] = p
        except Exception as e:  # noqa: BLE001
            print(f"  [X] sin preview para {t['artist']} - {t['title']}: {e}")

    print(f"\n  {len(previews)} previews disponibles de {len(tracks)} canciones")
    print(f"  umbrales actuales: croma>={CO.UMBRAL_CROMA_MISMA} mfcc>={CO.UMBRAL_MFCC_MISMA} "
          f"dudoso<{CO.UMBRAL_CROMA_DUDOSA}\n")

    positivos: list[tuple[float, float, str]] = []
    negativos: list[tuple[float, float, str]] = []

    for t in tracks:
        if t["id"] not in previews:
            continue
        etiqueta = f"{t['artist']} - {t['title']}"
        print(f"  === {etiqueta}")

        # --- positivo: contra su propio preview ---
        r = CO.comparar_audio(t, previews[t["id"]])
        if r.get("ok"):
            positivos.append((r["croma"], r["mfcc"], etiqueta))
            print(f"      PROPIO   croma={r['croma']:.3f}  mfcc={r['mfcc']:.3f}   "
                  f"offset={r['segundo_fichero_croma']}s")
        else:
            print(f"      PROPIO   fallo: {r.get('problemas')}")

        # --- negativos: contra el preview de cada una de las OTRAS ---
        for otro in tracks:
            if otro["id"] == t["id"] or otro["id"] not in previews:
                continue
            if CO.clave(otro["artist"]) == CO.clave(t["artist"]):
                continue          # mismo artista: podria ser parecido de verdad
            r = CO.comparar_audio(t, previews[otro["id"]])
            if r.get("ok"):
                negativos.append((r["croma"], r["mfcc"], f"{etiqueta} vs {otro['artist']}"))
                print(f"      AJENA    croma={r['croma']:.3f}  mfcc={r['mfcc']:.3f}   "
                      f"(vs {otro['artist']} - {otro['title'][:28]})")

    def resumen(nombre: str, datos: list[tuple[float, float, str]]) -> None:
        if not datos:
            print(f"\n  {nombre}: sin datos")
            return
        cromas = sorted(d[0] for d in datos)
        mfccs = sorted(d[1] for d in datos)
        print(f"\n  {nombre}  (n={len(datos)})")
        print(f"    croma: min={cromas[0]:.3f}  medio={sum(cromas)/len(cromas):.3f}  "
              f"max={cromas[-1]:.3f}")
        print(f"    mfcc : min={mfccs[0]:.3f}  medio={sum(mfccs)/len(mfccs):.3f}  "
              f"max={mfccs[-1]:.3f}")

    print("\n" + "=" * 70)
    resumen("POSITIVOS (la cancion contra si misma)", positivos)
    resumen("NEGATIVOS (la cancion contra otra distinta)", negativos)

    if positivos and negativos:
        c_min_pos = min(p[0] for p in positivos)
        c_max_neg = max(n[0] for n in negativos)
        print(f"\n  SEPARACION DE CROMA")
        print(f"    el positivo mas bajo : {c_min_pos:.3f}")
        print(f"    el negativo mas alto : {c_max_neg:.3f}")
        if c_min_pos > c_max_neg:
            medio = (c_min_pos + c_max_neg) / 2
            print(f"    -> hay separacion limpia. Umbral razonable: {medio:.2f}")
        else:
            print("    -> SE SOLAPAN: el croma solo no basta para decidir")

        m_min_pos = min(p[1] for p in positivos)
        m_max_neg = max(n[1] for n in negativos)
        print(f"\n  SEPARACION DE MFCC")
        print(f"    el positivo mas bajo : {m_min_pos:.3f}")
        print(f"    el negativo mas alto : {m_max_neg:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
