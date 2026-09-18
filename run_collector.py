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


def debe_reiniciarse(activo: bool, hilo_vivo: bool) -> bool:
    """¿Hay que reiniciar el contenedor? Sí cuando TOCA descargar y el hilo está muerto.

    Se comprueba sólo con la ingesta activada: con el interruptor apagado no se pierde nada, y
    así una parada deliberada no provoca un bucle de reinicios.
    """
    return bool(activo and not hilo_vivo)


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

        # Si TOCA descargar y el hilo de trabajo está muerto, se sale del proceso A PROPÓSITO: el
        # contenedor tiene `restart: unless-stopped`, así que Docker lo levanta otra vez y el hilo
        # vuelve. Sin esto, una excepción suelta dejaba el recolector muerto por dentro y «arriba»
        # por fuera indefinidamente: ni descargaba ni avisaba. (Pasó: su hilo murió al fallar el
        # registro de un evento con la base cogida, y estuvo días sin bajar nada mientras el
        # contenedor parecía estar perfectamente.)
        if debe_reiniciarse(activo, manager.sigue_vivo()):
            print("[collector] la ingesta está activada y el hilo de trabajo ha muerto: "
                  "se reinicia el contenedor", flush=True)
            raise SystemExit(1)

        time.sleep(ic.POLL_SECONDS)


if __name__ == "__main__":
    main()
