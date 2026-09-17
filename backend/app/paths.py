"""Traduce lo que hay guardado en la BD a una ruta real, sea absoluta (heredada) o relativa (nueva)."""
from pathlib import Path, PureWindowsPath
from .config import MUSIC_ROOT, MEDIA_ROOT

_ANCLAS_MUSICA = ("catalogada", "descargas", "auriculares")


def _relativa(guardado: str, anclas: tuple[str, ...]) -> Path:
    p = PureWindowsPath(guardado)
    partes = list(p.parts)
    if p.drive or guardado.startswith(("/", "\\")):       # heredada: recortar por el ancla
        for a in anclas:
            if a in partes:
                return Path(*partes[partes.index(a):])
        # sin ancla conocida: conservar la estructura (sin la raíz) para que _dentro_de la valide
        return Path(*partes[1:])
    return Path(*partes)                                   # ya era relativa


def _dentro_de(raiz: Path, destino: Path) -> Path:
    """Evita path traversal: el resultado tiene que colgar de la raíz."""
    raiz_r, destino_r = raiz.resolve(), destino.resolve()
    if raiz_r != destino_r and raiz_r not in destino_r.parents:
        raise PermissionError(f"Ruta fuera de {raiz_r}: {destino_r}")
    return destino_r


def resolve_music(guardado: str | None) -> Path:
    if not guardado:
        raise FileNotFoundError("La canción no tiene file_path")
    return _dentro_de(MUSIC_ROOT, MUSIC_ROOT / _relativa(guardado, _ANCLAS_MUSICA))


def media_filename(guardado: str | None) -> str | None:
    """Devuelve solo el nombre del fichero de una carátula/foto ('693008911.jpg')."""
    return PureWindowsPath(guardado).name if guardado else None


def resolve_media(sub: str, guardado: str | None) -> Path:
    """sub = 'covers' | 'artists'"""
    nombre = media_filename(guardado)
    if not nombre:
        raise FileNotFoundError("Sin imagen")
    return _dentro_de(MEDIA_ROOT / sub, MEDIA_ROOT / sub / nombre)
