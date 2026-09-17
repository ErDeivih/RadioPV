"""Verificacion de la API de RadioPV en el servidor. Se ejecuta DENTRO del contenedor api.

    docker exec -i radiopv-api python - < /tmp/verificar-api.py

Crea un usuario temporal (que sera admin por el bootstrap), prueba los endpoints de
administracion, comprueba que el borrado en masa con dry_run NO borra nada y que sin
filtros se rechaza, y finalmente borra el usuario temporal para dejar la BD como estaba.
"""

from __future__ import annotations

import sqlite3
import sys

import requests

BASE = "http://127.0.0.1:8000"
DB = "/app/data/backend.db"
EMAIL = "verificacion@radiopv-test.com"
PASS = "verificacion-clave-larga-123"

resultados: list[tuple[str, bool, str]] = []


def check(nombre: str, ok: bool, detalle: str = "") -> None:
    resultados.append((nombre, ok, detalle))
    print(f"  [{'OK ' if ok else 'FALLO'}] {nombre}" + (f"  ·  {detalle}" if detalle else ""))


def main() -> int:
    s = requests.Session()

    # ---------- 1. registro y bootstrap de admin ----------
    r = s.post(f"{BASE}/auth/register",
               json={"email": EMAIL, "password": PASS, "display_name": "Verificacion"})
    if r.status_code != 200:
        print(f"  [X] no se pudo registrar el usuario temporal: {r.status_code} {r.text[:200]}")
        return 1
    datos = r.json()
    token = datos["access_token"]
    check("registro de usuario temporal", True)
    check("el primer usuario es admin (bootstrap)", bool(datos["user"].get("is_admin")),
          f"is_admin={datos['user'].get('is_admin')}")

    h = {"Authorization": f"Bearer {token}"}

    # ---------- 2. sin token debe dar 401 ----------
    r = requests.get(f"{BASE}/admin/status")
    check("sin token, /admin/status da 401", r.status_code == 401, f"HTTP {r.status_code}")

    # ---------- 3. status ----------
    r = s.get(f"{BASE}/admin/status", headers=h)
    ok = r.status_code == 200
    check("GET /admin/status", ok, f"HTTP {r.status_code}")
    if ok:
        d = r.json()
        print(f"        claves: {sorted(d)[:12]}")

    # ---------- 4. facets ----------
    r = s.get(f"{BASE}/admin/facets", headers=h)
    ok = r.status_code == 200
    check("GET /admin/facets", ok, f"HTTP {r.status_code}")
    if ok:
        d = r.json()
        idiomas = d.get("languages") or d.get("idiomas") or []
        print(f"        idiomas: {len(idiomas)} · claves: {sorted(d)}")

    # ---------- 5. listado de pistas ----------
    r = s.get(f"{BASE}/admin/tracks", params={"limit": 3}, headers=h)
    ok = r.status_code == 200 and len(r.json().get("items", [])) == 3
    check("GET /admin/tracks?limit=3 devuelve 3", ok,
          f"HTTP {r.status_code} items={len(r.json().get('items', [])) if r.status_code == 200 else '-'}")
    if ok:
        it = r.json()["items"][0]
        print(f"        ejemplo: {it.get('artist')} - {it.get('title')} "
              f"[{it.get('language')}/{it.get('genre')}]")

    # ---------- 6. filtro por idioma ----------
    r = s.get(f"{BASE}/admin/tracks", params={"language": "es", "limit": 5}, headers=h)
    ok = r.status_code == 200
    tot_es = r.json().get("total") if ok else None
    check("filtrar por idioma (es)", ok, f"total={tot_es}")

    # ---------- 7. agrupado por idioma ----------
    r = s.get(f"{BASE}/admin/group", params={"by": "language"}, headers=h)
    ok = r.status_code == 200
    check("GET /admin/group?by=language", ok, f"HTTP {r.status_code}")
    if ok:
        grupos = r.json().get("groups", r.json().get("items", []))
        for g in grupos[:6]:
            print(f"        {g}")

    # ---------- 8. agrupado por artista dentro de un idioma ----------
    r = s.get(f"{BASE}/admin/group", params={"by": "artist", "language": "es", "limit": 5},
              headers=h)
    check("agrupar artistas filtrando por idioma es", r.status_code == 200,
          f"HTTP {r.status_code}")

    # ---------- 9. dry_run: no debe borrar nada ----------
    antes = s.get(f"{BASE}/admin/status", headers=h).json()
    r = s.post(f"{BASE}/admin/tracks/bulk", headers=h,
               json={"filters": {"language": "en"}, "action": "delete",
                     "veto": True, "dry_run": True})
    ok = r.status_code == 200
    check("borrado en masa con dry_run responde", ok, f"HTTP {r.status_code}")
    if ok:
        print(f"        prevision: {r.json()}")
    despues = s.get(f"{BASE}/admin/status", headers=h).json()
    check("dry_run NO ha borrado nada",
          antes.get("tracks_total") == despues.get("tracks_total") is not None,
          f"antes={antes.get('tracks_total')} despues={despues.get('tracks_total')}")

    # ---------- 10. sin filtros debe rechazarse ----------
    r = s.post(f"{BASE}/admin/tracks/bulk", headers=h,
               json={"filters": {}, "action": "delete", "veto": True, "dry_run": True})
    check("borrado en masa SIN filtros se rechaza", r.status_code in (400, 422),
          f"HTTP {r.status_code}")

    # ---------- 11. interruptor de ingesta ----------
    r = s.get(f"{BASE}/admin/ingest", headers=h)
    ok = r.status_code == 200
    check("GET /admin/ingest", ok, f"HTTP {r.status_code} {r.text[:80] if ok else ''}")

    # ---------- 12. eventos ----------
    r = s.get(f"{BASE}/admin/events", params={"limit": 3}, headers=h)
    check("GET /admin/events", r.status_code == 200, f"HTTP {r.status_code}")

    # ---------- 13. lista negra ----------
    r = s.get(f"{BASE}/admin/blacklist", headers=h)
    check("GET /admin/blacklist", r.status_code == 200, f"HTTP {r.status_code}")

    # ---------- 14. limpieza: borrar el usuario temporal ----------
    conn = sqlite3.connect(DB)
    try:
        uid = conn.execute("SELECT id FROM users WHERE email=?", (EMAIL,)).fetchone()
        if uid:
            uid = uid[0]
            for tabla, col in (("reactions", "user_id"), ("playlists", "user_id"),
                               ("mixes", "user_id"), ("plays", "user_id"),
                               ("taste_profile", "user_id")):
                try:
                    conn.execute(f"DELETE FROM {tabla} WHERE {col}=?", (uid,))
                except sqlite3.OperationalError:
                    pass
            conn.execute("DELETE FROM users WHERE id=?", (uid,))
            conn.commit()
        quedan = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        admins = conn.execute("SELECT COUNT(*) FROM users WHERE is_admin=1").fetchone()[0]
    finally:
        conn.close()
    check("usuario temporal borrado", quedan == 0, f"users={quedan} admins={admins}")

    # ---------- resumen ----------
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
