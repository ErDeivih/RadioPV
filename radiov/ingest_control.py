"""Control de la ingesta del recolector (encendido / apagado).

El agente recolector (`radiov/agent.py`) corre como proceso aparte. Este módulo es el
punto único desde el que se consulta y se cambia su estado, para que la web de RadioPV
pueda activarlo y desactivarlo sin tocar la interfaz Streamlit antigua.

El estado se guarda en la tabla `agent_state` de `radiov.db` (clave `ingest_enabled`),
así que sobrevive a reinicios y lo ven todos los procesos: la API, el agente y el worker.

Uso desde la API:
    from radiov import ingest_control as ic
    ic.set_enabled(False)
    ic.status()   # -> {"enabled": False, "updated_at": "...", "updated_by": "david"}

Uso desde el agente (una comprobación por vuelta del bucle):
    if not ingest_control.is_enabled():
        time.sleep(ingest_control.POLL_SECONDS)
        continue
"""
from __future__ import annotations

import datetime
from typing import Optional

from . import db

KEY_ENABLED = "ingest_enabled"
KEY_UPDATED_AT = "ingest_updated_at"
KEY_UPDATED_BY = "ingest_updated_by"

# Cuánto debe dormir el agente cuando la ingesta está apagada antes de volver a mirar.
POLL_SECONDS = 30


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def is_enabled() -> bool:
    """¿Está permitida la ingesta? Por defecto SÍ (si nunca se ha tocado el interruptor)."""
    raw = db.get_state(KEY_ENABLED, "1")
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def set_enabled(enabled: bool, by: Optional[str] = None) -> bool:
    """Enciende o apaga la ingesta y deja constancia de quién y cuándo."""
    db.set_state(KEY_ENABLED, "1" if enabled else "0")
    db.set_state(KEY_UPDATED_AT, _now())
    if by:
        db.set_state(KEY_UPDATED_BY, by)
    db.log_event(f"🎛️ Ingesta {'ACTIVADA' if enabled else 'DESACTIVADA'}"
                 + (f" por {by}" if by else ""), "info")
    return enabled


def status() -> dict:
    return {
        "enabled": is_enabled(),
        "updated_at": db.get_state(KEY_UPDATED_AT),
        "updated_by": db.get_state(KEY_UPDATED_BY),
    }
