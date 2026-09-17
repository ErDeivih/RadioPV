"""Traduce lo que hay guardado en la BD a una ruta real, sea absoluta (heredada) o relativa (nueva)."""
import unicodedata
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


def _normalizar(partes: tuple[str, ...], forma: str) -> Path:
    return Path(*(unicodedata.normalize(forma, p) for p in partes))


def _candidatos(ruta: Path) -> list[Path]:
    """Rutas alternativas que podrían ser el mismo fichero por normalización Unicode.

    POR QUÉ HACE FALTA
    ------------------
    Los nombres llegan de sitios distintos: de un PC con Windows (que usa NFC) y de Deezer o
    YouTube (que a veces devuelven NFD: la «n» seguida de una tilde combinante, que se ve igual
    pero son bytes distintos). En Linux dos cadenas que se ven idénticas pero están normalizadas
    de otra forma son **ficheros diferentes**, así que una canción podía quedar «perdida» para
    siempre por un detalle invisible: no se encontraba el fichero, el reproductor devolvía 410,
    y `verificar_ficheros` la mandaba a la cola de re-descarga… que volvería a dejar el mismo
    nombre mal normalizado.

    Se prueban unas pocas combinaciones razonables (todo NFC, todo NFD, y sólo el nombre o sólo
    las carpetas), que cubren los casos reales sin recorrer el árbol entero. Sólo se usa cuando
    la ruta exacta no existe, así que en el caso normal no cuesta nada.
    """
    partes = ruta.parts
    vistas = {ruta}
    candidatos: list[Path] = []
    for alt in (
        _normalizar(partes, "NFC"),
        _normalizar(partes, "NFD"),
        _normalizar(partes[:-1], "NFC") / partes[-1] if len(partes) > 1 else ruta,
        _normalizar(partes[:-1], "NFD") / partes[-1] if len(partes) > 1 else ruta,
        Path(*partes[:-1]) / unicodedata.normalize("NFC", partes[-1]) if len(partes) > 1 else ruta,
        Path(*partes[:-1]) / unicodedata.normalize("NFD", partes[-1]) if len(partes) > 1 else ruta,
    ):
        if alt not in vistas:
            vistas.add(alt)
            candidatos.append(alt)
    return candidatos


def resolve_music(guardado: str | None) -> Path:
    if not guardado:
        raise FileNotFoundError("La canción no tiene file_path")
    ruta = _dentro_de(MUSIC_ROOT, MUSIC_ROOT / _relativa(guardado, _ANCLAS_MUSICA))
    if ruta.exists():
        return ruta
    # La ruta guardada no está: puede ser el mismo fichero con el nombre normalizado de otra
    # forma. Si ninguna variante existe, se devuelve la canónica (el mensaje de error y la
    # marca 'perdida' deben hablar de la ruta que hay en la base).
    for alt in _candidatos(ruta):
        if alt.exists():
            return alt
    return ruta


def media_filename(guardado: str | None) -> str | None:
    """Devuelve solo el nombre del fichero de una carátula/foto ('693008911.jpg')."""
    return PureWindowsPath(guardado).name if guardado else None


def resolve_media(sub: str, guardado: str | None) -> Path:
    """sub = 'covers' | 'artists'"""
    nombre = media_filename(guardado)
    if not nombre:
        raise FileNotFoundError("Sin imagen")
    return _dentro_de(MEDIA_ROOT / sub, MEDIA_ROOT / sub / nombre)
