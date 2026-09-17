"""Limpia la copia de backend.db para el despliegue: borra usuarios de prueba y sus datos.

Solo actua sobre la copia (_deploy/backend.db), nunca sobre la BD local de trabajo.

Uso:
    python scripts/limpiar_copia_despliegue.py --db _deploy/backend.db --emails a@x.com,b@y.com
    python scripts/limpiar_copia_despliegue.py --db _deploy/backend.db --listar
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def tablas(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]


def columnas(conn: sqlite3.Connection, tabla: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({tabla})").fetchall()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="_deploy/backend.db")
    ap.add_argument("--emails", default="", help="emails a borrar, separados por comas")
    ap.add_argument("--listar", action="store_true")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"[X] no existe {db}")
        return 1
    conn = sqlite3.connect(str(db))
    todos = tablas(conn)

    if args.listar or not args.emails:
        print("  users:")
        for r in conn.execute("SELECT id, email, display_name, is_admin FROM users").fetchall():
            print("   ", r)
        print("  tablas con user_id:",
              [t for t in todos if "user_id" in columnas(conn, t)])
        conn.close()
        return 0

    emails = [e.strip().lower() for e in args.emails.split(",") if e.strip()]
    ids = [r[0] for r in conn.execute(
        f"SELECT id FROM users WHERE lower(email) IN ({','.join('?' * len(emails))})",
        emails).fetchall()]
    if not ids:
        print("[i] ningun usuario coincide; nada que borrar")
        conn.close()
        return 0
    print(f"[i] usuarios a borrar: {ids}")

    marcadores = ",".join("?" * len(ids))
    for tabla in todos:
        cols = columnas(conn, tabla)
        for col in ("user_id", "owner_id", "usuario_id"):
            if col in cols:
                n = conn.execute(
                    f"DELETE FROM {tabla} WHERE {col} IN ({marcadores})", ids).rowcount
                if n:
                    print(f"    {tabla}.{col}: {n} filas borradas")
        if "user_a" in cols and "user_b" in cols:
            n = conn.execute(
                f"DELETE FROM {tabla} WHERE user_a IN ({marcadores}) "
                f"OR user_b IN ({marcadores})", ids + ids).rowcount
            if n:
                print(f"    {tabla}: {n} filas borradas")
    n = conn.execute(f"DELETE FROM users WHERE id IN ({marcadores})", ids).rowcount
    print(f"    users: {n} filas borradas")
    conn.commit()

    print("  estado final users:")
    for r in conn.execute("SELECT id, email, display_name, is_admin FROM users").fetchall():
        print("   ", r)
    print("  admins:",
          conn.execute("SELECT COUNT(*) FROM users WHERE is_admin=1").fetchone()[0])
    conn.close()
    print("[OK] copia limpia")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
