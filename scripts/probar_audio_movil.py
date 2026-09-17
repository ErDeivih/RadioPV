"""Comprueba que se puede REPRODUCIR audio desde la LAN y desde Tailscale.

El navegador no puede enviar cabeceras en un <audio>, asi que el token va en la URL. Aqui
se replica exactamente lo que hara el movil: pedir token y luego el audio, pidiendo un
rango (que es lo que hace el navegador para poder mover la barra de reproduccion).

    python3 /tmp/probar-audio.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request

DB = "/opt/stacks/radiopv/data/backend.db"
MUSICA = "/srv/data/media/music"
EMAIL = "audio-e2e@radiopv-test.com"
CLAVE = "clave-de-pruebas-larga-123"
IPS = ["192.168.1.139", "100.117.58.93"]


def pedir(metodo, url, datos=None, token=None, form=False, crudo=False, cabeceras=None):
    h = dict(cabeceras or {})
    cuerpo = None
    if datos is not None:
        if form:
            cuerpo = urllib.parse.urlencode(datos).encode()
            h["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            cuerpo = json.dumps(datos).encode()
            h["Content-Type"] = "application/json"
    if token:
        h["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=cuerpo, headers=h, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            c = r.read()
            return r.status, (c if crudo else c.decode("utf-8", "replace")), dict(r.headers)
    except urllib.error.HTTPError as e:
        c = e.read()
        return e.code, (c if crudo else c.decode("utf-8", "replace")), dict(e.headers)
    except Exception as e:  # noqa: BLE001
        return 0, f"ERROR: {e}", {}


def main() -> int:
    fallos = 0

    # --- pista cuyo fichero YA este copiado ---
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    filas = conn.execute(
        "SELECT id, title, artist, file_path FROM tracks "
        "WHERE file_path IS NOT NULL AND status='descargada' LIMIT 4000").fetchall()
    conn.close()
    import os
    elegida = None
    for f in filas:
        if os.path.isfile(os.path.join(MUSICA, f["file_path"])):
            elegida = f
            break
    if not elegida:
        print("  [X] no hay ninguna pista copiada todavia; la copia sigue en marcha")
        return 1
    print(f"  pista de prueba: {elegida['artist']} - {elegida['title']}  (id={elegida['id']})")
    print()

    base = f"http://{IPS[0]}:8090/api"
    st, cuerpo, _ = pedir("POST", f"{base}/auth/register",
                          {"email": EMAIL, "password": CLAVE, "display_name": "Audio"})
    if st != 200:
        pedir("POST", f"{base}/auth/login", {"username": EMAIL, "password": CLAVE}, form=True)
    st, cuerpo, _ = pedir("POST", f"{base}/auth/login",
                          {"username": EMAIL, "password": CLAVE}, form=True)
    if st != 200:
        print(f"  [X] no se pudo iniciar sesion: HTTP {st} {cuerpo[:120]}")
        return 1
    token = json.loads(cuerpo)["access_token"]

    st, cuerpo, _ = pedir("POST", f"{base}/auth/stream-token", token=token)
    if st != 200:
        print(f"  [X] no se pudo obtener el token de reproduccion: HTTP {st}")
        return 1
    stok = json.loads(cuerpo).get("token")

    for ip in IPS:
        etiqueta = "LAN" if ip.startswith("192.") else "Tailscale"
        url = f"http://{ip}:8090/api/stream/{elegida['id']}?t={stok}"

        st, contenido, cab = pedir("GET", url, crudo=True)
        bien = st in (200, 206)
        print(f"  {etiqueta:<10} {ip:<16} reproduccion completa: HTTP {st} · "
              f"{len(contenido) if isinstance(contenido, bytes) else 0} bytes · "
              f"{cab.get('Content-Type','?')}")
        if not bien:
            fallos += 1

        # El navegador pide rangos: es lo que permite mover la barra de reproduccion.
        st2, contenido2, cab2 = pedir("GET", url, crudo=True,
                                      cabeceras={"Range": "bytes=0-1023"})
        ok_rango = st2 == 206 and isinstance(contenido2, bytes) and len(contenido2) == 1024
        print(f"  {'':<10} {'':<16} peticion por rangos    : HTTP {st2} · "
              f"{len(contenido2) if isinstance(contenido2, bytes) else 0} bytes · "
              f"{cab2.get('Content-Range','(sin Content-Range)')}")
        if not ok_rango:
            fallos += 1

    # --- limpieza ---
    conn = sqlite3.connect(DB)
    try:
        fila = conn.execute("SELECT id FROM users WHERE email=?", (EMAIL,)).fetchone()
        if fila:
            for t, c in (("reactions", "user_id"), ("playlists", "user_id"),
                         ("mixes", "user_id"), ("plays", "user_id"),
                         ("taste_profile", "user_id")):
                try:
                    conn.execute(f"DELETE FROM {t} WHERE {c}=?", (fila[0],))
                except sqlite3.OperationalError:
                    pass
            conn.execute("DELETE FROM users WHERE id=?", (fila[0],))
            conn.commit()
        print(f"\n  usuarios restantes: {conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]}")
    finally:
        conn.close()

    print()
    if fallos:
        print(f"  [X] {fallos} comprobaciones fallidas")
        return 1
    print("  [OK] el audio se reproduce por LAN y por Tailscale, con soporte de rangos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
