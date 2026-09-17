"""Ejecutor en segundo plano (sin interfaz web).

Útil si quieres que el agente crezca la biblioteca sin tener la web abierta.

Uso:
    python run_agent.py          # enciende el agente y lo deja trabajando
    python run_agent.py --once   # hace una pasada por todas las semillas y termina
"""
from __future__ import annotations

import argparse
import sys
import time

from radiov import db
from radiov.agent import get_manager
from radiov.deezer import DeezerClient
from radiov import pipeline


def once() -> int:
    """Recorre todas las semillas una sola vez. Devuelve el nº de canciones añadidas."""
    from radiov.config import load_settings
    manager = get_manager()
    client = DeezerClient()
    total = 0
    for i, seed in enumerate(load_settings()["agent_seeds"], 1):
        print(f"[{i}/{len(load_settings()['agent_seeds'])}] semilla: {seed.get('query', seed.get('genre'))}", flush=True)
        total += pipeline.process_seed(seed, client=client, progress=manager.progress)
        time.sleep(load_settings().get("agent_sleep_seconds", 1.0))
    print(f"Total añadidas: {total}", flush=True)
    return total


def daemon() -> None:
    manager = get_manager()
    manager.set_agent(True)
    print("Agente activado. Pulsa Ctrl+C para parar.", flush=True)
    try:
        while True:
            snap = manager.snapshot()
            time.sleep(10)
    except KeyboardInterrupt:
        manager.set_agent(False)
        print("\nDetenido.", flush=True)


def main() -> None:
    db.init_db()
    p = argparse.ArgumentParser(description="RadioPV agent runner")
    p.add_argument("--once", action="store_true", help="hacer una pasada sobre las semillas y terminar")
    args = p.parse_args()
    if args.once:
        sys.exit(0 if once() >= 0 else 1)
    daemon()


if __name__ == "__main__":
    main()
