"""Limpieza de la base: listas con nombre técnico y usuarios de prueba.

1) Listas «Top <id>» / «Subiendo <id>»: las generaba `rebuild_home_tops` con el id del usuario
   dentro del nombre y sin dueño, así que salían en las listas destacadas de todo el mundo.
2) Usuarios de prueba (`*@radiopv-test.com`): los crean las pruebas automáticas contra el
   servidor. Además de sobrar, dejaban REPRODUCCIONES en la base real, y esas reproducciones
   entran en la popularidad, en las tendencias y en los mixes: estaban ensuciando lo que ve el
   usuario de verdad.

Se borran las filas dependientes buscando por introspección todas las tablas que tengan columna
`user_id`, para no dejar huérfanas.

OJO CON EL ORDEN (esto fue un fallo de verdad): `playlists` TAMBIÉN tiene `user_id`, así que el
borrado genérico por `user_id` se llevaba por delante las listas ANTES de borrar sus filas de
`playlist_tracks`. Y como los ids de las listas se reutilizan, la siguiente lista que creaba
cualquier usuario nacía con las canciones de las listas borradas. Por eso las listas se borran
PRIMERO, con sus canciones, y `playlists` queda fuera del barrido genérico.

Uso (dentro del contenedor del API):
    docker exec radiopv-api python3 /tmp/limpiar.py            # sólo informa
    docker exec radiopv-api python3 /tmp/limpiar.py --apply
"""
import re
import sqlite3
import sys

DB = "/app/data/backend.db"
VIEJO = re.compile(r"^(Top|Subiendo) \d+$")
EMAIL_PRUEBA = "%@radiopv-test.com"

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
apply = "--apply" in sys.argv

print("=== listas con nombre técnico ===")
viejas = [dict(r) for r in con.execute(
    "SELECT id, name, user_id FROM playlists WHERE type='system'")]
viejas = [p for p in viejas if VIEJO.match(p["name"] or "")]
print(f"   {len(viejas)} encontradas")

print("\n=== usuarios de prueba ===")
usuarios = [dict(r) for r in con.execute(
    "SELECT id, email FROM users WHERE email LIKE ?", (EMAIL_PRUEBA,))]
print(f"   {len(usuarios)} encontrados")
for u in usuarios[:8]:
    print(f"     {u['id']:4d}  {u['email']}")

total = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
print(f"   usuarios en total: {total} (quedarían {total - len(usuarios)})")

# Tablas con columna user_id (introspección): así no se queda ninguna fila huérfana.
con_user = []
for (tabla,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
    cols = [c[1] for c in con.execute(f"PRAGMA table_info({tabla})")]
    if "user_id" in cols:
        con_user.append(tabla)
print(f"\n   tablas con user_id: {', '.join(sorted(con_user))}")

ids = [u["id"] for u in usuarios]
if apply:
    q = ",".join("?" * len(ids)) if ids else "NULL"
    # 1º las listas: sus canciones y luego la lista. Si se hace después, las listas ya no están y
    # el borrado de sus canciones no encuentra nada (queda basura con un id que se reutilizará).
    listas_usuarios = []
    if ids:
        listas_usuarios = [r["id"] for r in con.execute(
            f"SELECT id FROM playlists WHERE user_id IN ({q})", ids)]
    listas_usuarios += [p["id"] for p in viejas]
    for pid in listas_usuarios:
        con.execute("DELETE FROM playlist_tracks WHERE playlist_id=?", (pid,))
    for pid in listas_usuarios:
        con.execute("DELETE FROM playlists WHERE id=?", (pid,))
    print(f"[OK] listas borradas con sus canciones: {len(listas_usuarios)}")

    # 2º el resto de tablas con user_id. `playlists` se salta: ya está hecho arriba y hacerlo aquí
    # es justo lo que dejaba las canciones huérfanas.
    borradas = 0
    for tabla in con_user:
        if tabla == "playlists":
            continue
        if ids:
            cur = con.execute(f"DELETE FROM {tabla} WHERE user_id IN ({q})", ids)
            borradas += cur.rowcount
    if ids:
        con.execute(f"DELETE FROM users WHERE id IN ({q})", ids)
    con.commit()

    # 3º barrido final: cualquier fila de lista que apunte a una lista que ya no existe. Es la
    # misma red de seguridad que corre al arrancar la API (`database.limpiar_listas_huerfanas`).
    huerfanas = con.execute(
        "DELETE FROM playlist_tracks WHERE playlist_id NOT IN (SELECT id FROM playlists)").rowcount
    con.commit()

    print(f"\n[OK] filas dependientes borradas: {borradas}")
    print(f"[OK] listas técnicas borradas: {len(viejas)}")
    print(f"[OK] usuarios de prueba borrados: {len(ids)}")
    print(f"[OK] filas de lista huérfanas borradas: {huerfanas}")
    print(f"[i] usuarios restantes: {con.execute('SELECT COUNT(*) FROM users').fetchone()[0]}")
else:
    print("\n[..] sólo información: añade --apply para limpiar")

con.close()
