from __future__ import annotations

from typing import Optional

from .config import load_settings
from . import models as M


def activities() -> dict:
    return load_settings().get("activities", {})


def activity_keys() -> list[str]:
    return list(activities().keys())


def activity_label(key: str) -> str:
    a = activities().get(key, {})
    return a.get("label", key)


def activity_desc(key: str) -> str:
    return activities().get(key, {}).get("desc", "")


def activity_bpm_range(key: str) -> tuple[Optional[float], Optional[float]]:
    a = activities().get(key, {})
    bpm = a.get("bpm") or [None, None]
    lo = bpm[0] if len(bpm) > 0 else None
    hi = bpm[1] if len(bpm) > 1 else None
    return lo, hi


def activity_genres(key: str) -> list[str]:
    return activities().get(key, {}).get("preferred_genres", [])


def in_bpm_range(bpm: Optional[float], key: str) -> bool:
    if bpm is None:
        return False
    lo, hi = activity_bpm_range(key)
    if lo is not None and bpm < lo:
        return False
    if hi is not None and bpm > hi:
        return False
    return True


def matches_activity(track: dict, key: str) -> bool:
    """Un tema encaja en la actividad si su BPM entra en el rango,
    o (sin BPM) si su género está entre los preferidos."""
    if in_bpm_range(track.get("bpm"), key):
        return True
    if track.get("bpm") is None:
        return track.get("genre") in activity_genres(key)
    return False
