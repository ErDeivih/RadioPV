"""Ejecutor del recolector controlado por el interruptor de ingesta.

A diferencia de `run_agent.py` (que activa el agente y ya no lo suelta), este ejecutor
**obedece al interruptor** que se guarda en la base de datos (`agent_state.ingest_enabled`).
Así la web de RadioPV puede encender y apagar la ingesta desde el panel de administración,
sin tocar la interfaz Streamlit antigua.

Uso (contenedor `collector` del docker-compose):
    python run_collector.py
"""
from __future__ import annotations

import time

from radiov import db
from radiov import ingest_control as ic
from radiov.agent import get_manager


def main() -> None:
    db.init_db()
    manager = get_manager()

    aplicado: bool | None = None
    print("[collector] arrancado; vigilando el interruptor de ingesta", flush=True)

    while True:
        activo = ic.is_enabled()

        if activo != aplicado:
            manager.set_agent(activo)
            aplicado = activo
            print(f"[collector] ingesta {'ACTIVADA' if activo else 'DESACTIVADA'}", flush=True)

        time.sleep(ic.POLL_SECONDS)


if __name__ == "__main__":
    main()
