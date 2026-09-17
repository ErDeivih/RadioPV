"""Mide donde se va el tiempo al analizar una cancion .

    python3 scripts/medir_tiempos_analisis.py
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, "str(Path(__file__).resolve().parent.parent)")

from radiov import corrector as CO, db, deezer as dz  # noqa: E402


def crono(nombre, fn):
    t = time.time()
    r = fn()
    print(f"    {nombre:<40} {time.time()-t:>7.2f} s")
    return r


db.init_db()
conn = db.get_conn()
fila = conn.execute("SELECT * FROM tracks WHERE id=4").fetchone()
conn.close()
t = dict(fila)
print(f"  {t['artist']} - {t['title']}  ({t.get('duration')}s de musica)")

cliente = dz.DeezerClient()
det = crono("Deezer track_detail", lambda: cliente.track_detail(str(t["deezer_id"])))
preview = det.get("preview")

import numpy as np
import librosa
import requests

ruta = str(CO.resolve_music(t["file_path"]))
print(f"    fichero: {Path(ruta).stat().st_size/1e6:.1f} MB")

r = crono("descargar el preview", lambda: requests.get(preview, timeout=25).content)
with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
    f.write(r)
    tmp = f.name

print()
print("  --- fases del analisis de audio ---")
y_p = crono("leer el preview (30 s)", lambda: librosa.load(tmp, sr=22050, mono=True)[0])
y_f = crono(f"leer el fichero entero ({t.get('duration'):.0f} s)",
            lambda: librosa.load(ruta, sr=22050, mono=True)[0])
print(f"    muestras del fichero: {y_f.size} ({y_f.size/22050:.0f} s)")

croma_p, mfcc_p = crono("croma+mfcc del preview", lambda: CO._huellas(y_p, 22050))
croma_f, mfcc_f = crono("croma+mfcc del fichero",
                        lambda: CO._huellas(y_f, 22050))
print(f"    croma del fichero: {croma_f.shape}")

crono("un alineamiento", lambda: CO._mejor_alineamiento(croma_f, croma_p))
crono("11 alineamientos (busqueda de velocidad)",
      lambda: [CO._mejor_alineamiento(CO._reescalar_tiempo(croma_f, f), croma_p)
               for f in CO.FACTORES_VELOCIDAD])
crono("reescalar 11 veces", lambda: [CO._reescalar_tiempo(croma_f, f)
                                     for f in CO.FACTORES_VELOCIDAD])
Path(tmp).unlink(missing_ok=True)

print()
print("  --- alternativas mas rapidas ---")
for sr in (22050, 11025):
    yy = librosa.load(ruta, sr=sr, mono=True)[0]
    tp = time.time()
    librosa.feature.chroma_cqt(y=yy, sr=sr, hop_length=2048)
    print(f"    chroma_cqt a {sr} Hz: {time.time()-tp:.2f} s  ({yy.size} muestras)")
yy = librosa.load(ruta, sr=22050, mono=True)[0]
tp = time.time()
librosa.feature.chroma_stft(y=yy, sr=22050, hop_length=2048)
print(f"    chroma_stft a 22050 Hz: {time.time()-tp:.2f} s  (alternativa a cqt)")

tp = time.time()
librosa.load(ruta, sr=22050, mono=True, duration=90)
print(f"    leer solo 90 s: {time.time()-tp:.2f} s")
