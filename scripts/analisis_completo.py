"""T-24: UNA sola pasada de análisis sobre radiov.db.

Por cada MP3: calcula `rms` (muestra de 30 s decodificada con ffmpeg + numpy, RÁPIDO) y `gain_db`
(ffmpeg loudnorm a -14 LUFS) en la MISMA iteración. Al terminar, re-normaliza `energy` por percentil.
Corre con el recolector PAUSADO (si no, nunca converge).

Uso:  .venv\\Scripts\\python.exe scripts\\analisis_completo.py
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from radiov.config import DATA_DIR, resolve_music

import radiov.catalog as C

TARGET_LUFS = -14.0
DB = DATA_DIR / "radiov.db"
SAMPLE_SECONDS = 30


def rms_rapido(p: Path) -> float | None:
    """RMS de una muestra de SAMPLE_SECONDS (decodificación ffmpeg mono 22k). Rápido."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav = Path(f.name)
    try:
        r = subprocess.run(
            ["ffmpeg", "-t", str(SAMPLE_SECONDS), "-i", str(p), "-ac", "1", "-ar", "22050",
             "-f", "wav", "-y", str(wav)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        if r.returncode != 0 or not wav.exists() or wav.stat().st_size == 0:
            return None
        import numpy as np
        import soundfile as sf
        y, _ = sf.read(str(wav), dtype="float32")
        if y.size == 0:
            return None
        return float(np.sqrt(np.mean(y ** 2)))
    except Exception:  # noqa: BLE001
        return None
    finally:
        try:
            wav.unlink()
        except OSError:
            pass


def lufs(p: Path) -> float | None:
    try:
        r = subprocess.run(
            ["ffmpeg", "-i", str(p), "-af", "loudnorm=I=-14:print_format=json", "-f", "null", "-"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=150)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    try:
        js = json.loads(r.stderr[r.stderr.rfind("{"): r.stderr.rfind("}") + 1])
        return float(js.get("input_i"))
    except (ValueError, AttributeError, KeyError):
        return None


def main() -> int:
    import sys as _s
    limit = None
    if "--limit" in _s.argv:
        i = _s.argv.index("--limit")
        if i + 1 < len(_s.argv):
            limit = int(_s.argv[i + 1])
    conn = sqlite3.connect(str(DB), timeout=300)
    conn.row_factory = sqlite3.Row
    # OJO con el `status`: aquí ponía solo `status='descargada'`, y las canciones que NECESITAN el
    # gain_db son justo las `incompleta` (con `metadata_strict`, una descarga nueva se marca
    # 'incompleta' precisamente PORQUE le falta gain_db). Es decir: esta pasada no las miraba
    # nunca y no había forma de que salieran de ahí. Un bloqueo mutuo de manual: 279 canciones ya
    # descargadas, con su fichero en el disco, invisibles en la aplicación para siempre.
    rows = conn.execute("SELECT id, file_path, rms, gain_db FROM tracks "
                        "WHERE status IN ('descargada', 'incompleta') AND file_path IS NOT NULL "
                        "AND file_path != '' AND (rms IS NULL OR gain_db IS NULL)").fetchall()
    total = len(rows)
    if limit:
        rows = rows[:limit]
    print(f"[INFO] {len(rows)} canción(es) por analizar (rms/gain_db).")
    done = 0
    for r in rows:
        t = dict(r)
        p = C.resolve_music(t["file_path"])
        if not p.exists():
            continue
        if t["rms"] is None:
            t["rms"] = rms_rapido(p)
        if t["gain_db"] is None:
            i = lufs(p)
            t["gain_db"] = round(TARGET_LUFS - i, 2) if i is not None else None
        upd = {}
        if t["rms"] is not None:
            upd["rms"] = round(t["rms"], 6)
        if t["gain_db"] is not None:
            upd["gain_db"] = t["gain_db"]
        if upd:
            sets = ", ".join(f"{k}=?" for k in upd)
            conn.execute(f"UPDATE tracks SET {sets} WHERE id=?", list(upd.values()) + [t["id"]])
            done += 1
        # CONFIRMAR EN CADA CANCIÓN, no cada 25. Antes se hacía cada 25 filas, y como cada
        # canción tarda unos 12 s (ffmpeg `loudnorm` lee el fichero entero), la transacción de
        # escritura se quedaba ABIERTA 5 minutos. Con SQLite eso deja la base bloqueada para
        # escribir: el recolector, que escribe mientras descarga, se comía «database is locked»
        # y su hilo moría (ver `log_event`). El recolector y este análisis tienen que poder
        # convivir: no tiene sentido parar las descargas 2 horas cada 4.
        conn.commit()
        if done and done % 25 == 0:
            print(f"  procesadas {done}/{total}")
    conn.commit()
    print(f"[OK] rms/gain_db calculados para {done} canción(es).")

    filas = conn.execute("SELECT id, rms FROM tracks WHERE rms IS NOT NULL ORDER BY rms").fetchall()
    n = len(filas)
    for pos, (tid, _) in enumerate(filas):
        energy = round((pos + 0.5) / n, 3)
        conn.execute("UPDATE tracks SET energy=? WHERE id=?", (energy, tid))
    conn.commit()
    print(f"[OK] energy re-normalizada por percentil en {n} filas.")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
