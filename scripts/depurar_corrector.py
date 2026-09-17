"""Depura la comparacion de audio del corrector sobre una cancion concreta (temporal).

    python scripts/_depurar_audio.py             # la primera del catalogo
    python scripts/_depurar_audio.py 12          # la de ese id
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from radiov import corrector as CO, db  # noqa: E402


def main() -> int:
    db.init_db()
    tid = int(sys.argv[1]) if len(sys.argv) > 1 else None
    conn = db.get_conn()
    try:
        if tid:
            fila = conn.execute("SELECT * FROM tracks WHERE id=?", (tid,)).fetchone()
        else:
            fila = conn.execute(
                "SELECT * FROM tracks WHERE file_path IS NOT NULL AND file_path!='' LIMIT 1"
            ).fetchone()
    finally:
        conn.close()
    if not fila:
        print("  no hay ninguna pista")
        return 1
    t = dict(fila)
    print(f"  pista: {t['artist']} - {t['title']}  (id={t['id']})")
    print(f"  fichero: {t.get('file_path')}")
    print(f"  duracion guardada: {t.get('duration')}")

    print("\n  --- 1. el fichero ---")
    fichero = CO.revisar_fichero(t)
    print("   ", json.dumps(fichero, ensure_ascii=False, indent=2)[:600])

    print("\n  --- 2. etiquetas ID3 ---")
    tags = CO.leer_tags(t["file_path"])
    print("   ", json.dumps(tags, ensure_ascii=False)[:400])

    print("\n  --- 3. Deezer ---")
    dz = CO.revisar_deezer(t)
    cand = dz.get("candidato") or {}
    guard = dz.get("guardado") or {}
    print(f"    id guardado valido: {dz.get('id_guardado_valido')}")
    print(f"    preview (guardado): {guard.get('preview')}")
    print(f"    preview (candidato): {cand.get('preview')}")
    print(f"    candidato: {cand.get('artist')} - {cand.get('title')} ({cand.get('duration')}s)")
    print(f"    problemas: {dz.get('problemas')}")

    print("\n  --- 4. audio ---")
    preview = guard.get("preview") or cand.get("preview")
    print(f"    preview usado: {preview}")
    audio = CO.comparar_audio(t, preview)
    print("   ", json.dumps(audio, ensure_ascii=False, indent=2))

    print("\n  --- extra: modulos de audio ---")
    for mod in ("librosa", "soundfile", "numpy", "requests"):
        try:
            m = __import__(mod)
            print(f"    {mod}: {getattr(m, '__version__', '?')}")
        except Exception as e:  # noqa: BLE001
            print(f"    {mod}: FALLA -> {type(e).__name__}: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
