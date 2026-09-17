"""Pruebas de punta a punta contra RadioPV A TRAVES DE NGINX (puerto 8090).

Es lo mismo que hace el navegador: mismo origen, rutas /api/*. Usa solo la libreria
estandar, asi que se ejecuta directamente en el servidor sin instalar nada.

    python3 /tmp/probar-radiopv.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8090"
API = f"{BASE}/api"
DB = "/opt/stacks/radiopv/data/backend.db"
EMAIL = "pruebas-e2e@radiopv-test.com"
CLAVE = "clave-de-pruebas-larga-123"

resultados: list[tuple[str, bool, str]] = []


def check(nombre: str, ok: bool, detalle: str = "") -> bool:
    resultados.append((nombre, ok, detalle))
    print(f"  [{'OK ' if ok else 'FALLO'}] {nombre}" + (f"  ·  {detalle}" if detalle else ""))
    return ok


def peticion(metodo: str, url: str, datos=None, token: str | None = None,
             form: bool = False, crudo: bool = False):
    cabeceras = {}
    cuerpo = None
    if datos is not None:
        if form:
            cuerpo = urllib.parse.urlencode(datos).encode()
            cabeceras["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            cuerpo = json.dumps(datos).encode()
            cabeceras["Content-Type"] = "application/json"
    if token:
        cabeceras["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=cuerpo, headers=cabeceras, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            contenido = r.read()
            return r.status, (contenido if crudo else contenido.decode("utf-8", "replace")), dict(r.headers)
    except urllib.error.HTTPError as e:
        contenido = e.read()
        return e.code, (contenido if crudo else contenido.decode("utf-8", "replace")), dict(e.headers)
    except Exception as e:  # noqa: BLE001
        return 0, f"ERROR: {e}", {}


def limpiar() -> int:
    """Borra el usuario de pruebas y sus datos. Devuelve cuantos usuarios quedan."""
    conn = sqlite3.connect(DB)
    try:
        fila = conn.execute("SELECT id FROM users WHERE email=?", (EMAIL,)).fetchone()
        if fila:
            uid = fila[0]
            for tabla, col in (("reactions", "user_id"), ("playlists", "user_id"),
                               ("mixes", "user_id"), ("plays", "user_id"),
                               ("taste_profile", "user_id")):
                try:
                    conn.execute(f"DELETE FROM {tabla} WHERE {col}=?", (uid,))
                except sqlite3.OperationalError:
                    pass
            conn.execute("DELETE FROM users WHERE id=?", (uid,))
            conn.commit()
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        conn.close()


def main() -> int:
    print("=== 1. LA WEB SE SIRVE ===")
    st, cuerpo, _ = peticion("GET", f"{BASE}/")
    check("GET / responde 200", st == 200, f"HTTP {st}")
    check("el HTML es la app de React", "root" in cuerpo and "<script" in cuerpo,
          f"{len(cuerpo)} bytes")
    st, _, _ = peticion("GET", f"{BASE}/admin")
    check("GET /admin responde 200 (SPA)", st == 200, f"HTTP {st}")

    print()
    print("=== 2. LA API SE ALCANZA POR EL MISMO ORIGEN (/api) ===")
    st, cuerpo, _ = peticion("GET", f"{API}/health")
    ok = st == 200
    check("GET /api/health", ok, f"HTTP {st} {cuerpo[:90]}")
    if ok:
        d = json.loads(cuerpo)
        check("la API ve el catalogo",
              d.get("tracks", 0) > 5000 and d.get("artists", 0) > 3000,
              f"tracks={d.get('tracks')} artists={d.get('artists')}")

    print()
    print("=== 3. SIN SESION, LO PRIVADO SE RECHAZA ===")
    st, _, _ = peticion("GET", f"{API}/admin/status")
    check("sin token, /api/admin/status da 401", st == 401, f"HTTP {st}")
    st, _, _ = peticion("GET", f"{API}/auth/me")
    check("sin token, /api/auth/me da 401", st == 401, f"HTTP {st}")

    limpiar()  # por si quedo algo de una ejecucion anterior

    print()
    print("=== 4. REGISTRO (el primero es admin) ===")
    st, cuerpo, _ = peticion("POST", f"{API}/auth/register",
                             {"email": EMAIL, "password": CLAVE, "display_name": "Pruebas"})
    if not check("POST /api/auth/register", st == 200, f"HTTP {st} {cuerpo[:140]}"):
        return 1
    d = json.loads(cuerpo)
    token_reg = d["access_token"]
    check("el primer usuario es administrador", bool(d["user"].get("is_admin")),
          f"is_admin={d['user'].get('is_admin')}")

    print()
    print("=== 5. INICIO DE SESION ===")
    st, cuerpo, _ = peticion("POST", f"{API}/auth/login",
                             {"username": EMAIL, "password": CLAVE}, form=True)
    if not check("POST /api/auth/login (formulario)", st == 200, f"HTTP {st} {cuerpo[:140]}"):
        return 1
    token = json.loads(cuerpo)["access_token"]

    st, cuerpo, _ = peticion("GET", f"{API}/auth/me", token=token)
    ok = st == 200
    check("GET /api/auth/me con token", ok, f"HTTP {st}")
    if ok:
        check("devuelve el usuario correcto", json.loads(cuerpo).get("email") == EMAIL,
              json.loads(cuerpo).get("email"))

    print()
    print("=== 6. CONTRASEÑA INCORRECTA ===")
    st, _, _ = peticion("POST", f"{API}/auth/login",
                        {"username": EMAIL, "password": "mal-mal-mal"}, form=True)
    check("con clave mala da 401", st == 401, f"HTTP {st}")

    print()
    print("=== 7. CATALOGO (con sesion) ===")
    st, cuerpo, _ = peticion("GET", f"{API}/tracks?limit=3", token=token)
    ok = st == 200
    check("GET /api/tracks?limit=3", ok, f"HTTP {st}")
    pistas = []
    if ok:
        d = json.loads(cuerpo)
        # /tracks devuelve la lista directamente; /admin/tracks devuelve {items: [...], total: n}
        if isinstance(d, list):
            pistas = d
        else:
            pistas = d.get("items", [])
        check("devuelve 3 pistas", len(pistas) == 3, f"{len(pistas)} pistas")
        if pistas:
            p = pistas[0]
            print(f"        ejemplo: {p.get('artist')} - {p.get('title')}")

    print()
    print("=== 8. ADMIN: FILTRAR Y AGRUPAR ===")
    for nombre, url in (
        ("GET /api/admin/status", f"{API}/admin/status"),
        ("GET /api/admin/facets", f"{API}/admin/facets"),
        ("GET /api/admin/tracks?limit=3", f"{API}/admin/tracks?limit=3"),
        ("GET /api/admin/group?by=language", f"{API}/admin/group?by=language"),
        ("GET /api/admin/ingest", f"{API}/admin/ingest"),
        ("GET /api/admin/events?limit=3", f"{API}/admin/events?limit=3"),
        ("GET /api/admin/blacklist", f"{API}/admin/blacklist"),
    ):
        st, cuerpo, _ = peticion("GET", url, token=token)
        check(nombre, st == 200, f"HTTP {st}")

    st, cuerpo, _ = peticion("POST", f"{API}/admin/tracks/bulk", token=token,
                             datos={"filters": {"language": "en"}, "action": "delete",
                                    "veto": True, "dry_run": True})
    ok = st == 200
    check("borrado en masa con vista previa (dry_run)", ok, f"HTTP {st}")
    if ok:
        d = json.loads(cuerpo)
        check("la vista previa NO borra nada", d.get("borradas") == 0 and d.get("vetadas") == 0,
              str(d))

    st, _, _ = peticion("POST", f"{API}/admin/tracks/bulk", token=token,
                        datos={"filters": {}, "action": "delete", "dry_run": True})
    check("borrado en masa SIN filtros se rechaza", st in (400, 422), f"HTTP {st}")

    print()
    print("=== 9. IMAGENES Y AUDIO ===")
    if pistas:
        p = pistas[0]
        # La API devuelve rutas propias tipo /media/covers/123.jpg que sirve ella misma.
        portada = p.get("cover")
        if portada:
            st, contenido, cab = peticion("GET", f"{BASE}/api{portada}", crudo=True)
            bytes_ = len(contenido) if isinstance(contenido, bytes) else 0
            check("la caratula se descarga por el mismo origen",
                  st == 200 and bytes_ > 500,
                  f"HTTP {st} · {bytes_} bytes · {cab.get('Content-Type', '?')}")
        else:
            check("la pista trae portada", False, f"cover={portada!r}")

        st, cuerpo, _ = peticion("GET", f"{API}/artists?limit=1")
        if st == 200:
            artistas = json.loads(cuerpo)
            if isinstance(artistas, dict):
                artistas = artistas.get("items", [])
            if artistas:
                imagen = artistas[0].get("image")
                st2, contenido, cab = peticion("GET", f"{BASE}/api{imagen}", crudo=True)
                bytes_ = len(contenido) if isinstance(contenido, bytes) else 0
                check("la foto de artista se descarga",
                      st2 == 200 and bytes_ > 500,
                      f"HTTP {st2} · {bytes_} bytes · {cab.get('Content-Type', '?')}")

        tid = p.get("id")
        st, cuerpo, _ = peticion("POST", f"{API}/auth/stream-token", token=token)
        check("se obtiene token de reproduccion", st == 200, f"HTTP {st}")
        if st == 200:
            d = json.loads(cuerpo)
            stok = d.get("stream_token") or d.get("token") or d.get("access_token")
            check("el token viene en la respuesta", bool(stok), f"claves={sorted(d)}")
            if stok:
                # OJO: el parametro de la query se llama `t`, no `token` (ver
                # backend/app/routers/stream.py). Con otro nombre la API da 422.
                st, contenido, cab = peticion(
                    "GET", f"{BASE}/api/stream/{tid}?t={stok}", crudo=True)
                # 410 con el catalogo recien instalado es CORRECTO: la musica aun se esta
                # copiando. Lo que se comprueba es que el endpoint responde y no revienta.
                check("el endpoint de audio responde sin romperse",
                      st in (200, 206, 410),
                      f"HTTP {st} · {cab.get('Content-Type', '?')} "
                      f"({'fichero aun no copiado' if st == 410 else 'audio servido'})")

    print()
    print("=== 10. LIMPIEZA ===")
    quedan = limpiar()
    check("usuario de pruebas borrado; la BD queda lista para ti",
          quedan == 0, f"usuarios restantes={quedan}")

    fallos = [n for n, ok, _ in resultados if not ok]
    print()
    print(f"  ===== {len(resultados) - len(fallos)}/{len(resultados)} comprobaciones OK =====")
    if fallos:
        print("  fallos:")
        for f in fallos:
            print(f"    - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
