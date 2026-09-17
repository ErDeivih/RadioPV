"""Diagnostica si una copia de YouTube va a distinta VELOCIDAD que el preview de Deezer.

Es un problema conocido: algunas subidas a YouTube estan aceleradas o frenadas un 1-2%
(por el PAL/NTSC, o porque quien la subio la ajusto). Con esa diferencia, las tramas de
croma no se alinean y la similitud se desploma aunque la grabacion sea la misma.

Aqui se prueba la comparacion aplicando varios factores de velocidad al fichero y se ve
cual da la mejor puntuacion. Si al corregir un 1% el croma sube de 0.88 a 0.99, la causa
es esa y el corrector tiene que compensarla.

    python scripts/diagnosticar_velocidad.py 4
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from radiov import corrector as CO, db, deezer as dz  # noqa: E402


def main() -> int:
    db.init_db()
    tid = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    conn = db.get_conn()
    try:
        fila = conn.execute("SELECT * FROM tracks WHERE id=?", (tid,)).fetchone()
    finally:
        conn.close()
    if not fila:
        print("  no existe esa pista")
        return 1
    t = dict(fila)
    print(f"  {t['artist']} - {t['title']}  ({t.get('duration')}s)")

    cliente = dz.DeezerClient()
    det = cliente.track_detail(str(t["deezer_id"]))
    preview = det.get("preview")
    if not preview:
        print("  sin preview")
        return 1
    print(f"  deezer dice: {det.get('duration')}s")

    # --- preparar las senales una sola vez ---
    import tempfile
    import requests
    import numpy as np
    import librosa

    r = requests.get(preview, timeout=25)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(r.content)
        tmp = f.name
    with CO._sin_ruido_de_audio():
        y_prev, sr = librosa.load(tmp, sr=22050, mono=True)
        y_fich, _ = librosa.load(str(CO.resolve_music(t["file_path"])), sr=22050, mono=True)
    Path(tmp).unlink(missing_ok=True)

    croma_p, mfcc_p = CO._huellas(y_prev, sr)

    print(f"\n  {'factor':>8}  {'croma':>7}  {'mfcc':>7}   {'offset':>7}   duracion resultante")
    print("  " + "-" * 62)

    mejor = (0.0, 1.0)
    for factor in (0.96, 0.97, 0.98, 0.99, 0.995, 1.0, 1.005, 1.01, 1.02, 1.03, 1.04):
        if abs(factor - 1.0) < 1e-9:
            y = y_fich
        else:
            # Resamplear cambia la velocidad Y el tono: es justo lo que hace un vídeo
            # subido a otra velocidad, así que es la transformación correcta aquí.
            n = int(len(y_fich) / factor)
            idx = np.linspace(0, len(y_fich) - 1, n)
            y = np.interp(idx, np.arange(len(y_fich)), y_fich).astype(np.float32)
        croma_f, mfcc_f = CO._huellas(y, sr)
        c, off = CO._mejor_alineamiento(croma_f, croma_p)
        m, _ = CO._mejor_alineamiento(mfcc_f, mfcc_p)
        marca = ""
        if c > mejor[0]:
            mejor = (c, factor)
            marca = "  <- mejor"
        print(f"  {factor:>8.3f}  {c:>7.4f}  {m:>7.4f}   {off*2048/22050:>6.1f}s   "
              f"{len(y)/sr:>7.1f}s{marca}")

    print(f"\n  mejor croma {mejor[0]:.4f} con factor {mejor[1]}")
    if mejor[1] != 1.0 and mejor[0] - 0.8769 > 0.05:
        print("  -> SI hay diferencia de velocidad: hay que compensarla en el corrector")
    else:
        print("  -> la velocidad no explica el desajuste")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
