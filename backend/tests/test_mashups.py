"""Los mashups y remixes se marcan como tales al catalogar.

Pedido: "a mi me gustan mucho los mashups remixes entre dos o tres canciones que hace la gente en
YouTube, puede anadir ese tipo de canciones al worker". Las semillas de descarga ya estan (se
buscan por texto), pero ademas hay que MARCARLAS al catalogar: si no, se pierden mezcladas entre
las canciones normales y no se pueden buscar ni sacar aparte. El campo es `is_remix`, que la
interfaz ya usa como filtro.
"""
import pytest


@pytest.fixture(autouse=True)
def _radiov_en_el_path():
    import os
    import sys

    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if raiz not in sys.path:
        sys.path.insert(0, raiz)


@pytest.mark.parametrize("titulo,artista", [
    ("Titanium x Without You", "David Guetta"),
    ("Mashup 2 songs", "Varios"),
    ("Best Mash Up 2024", ""),
    ("Megamix de los 90", ""),
    ("Shape of You vs Cheap Thrills", ""),
    ("Blend of classics", ""),
    ("Numb (Remix)", ""),
    ("Extended Mix", ""),
    ("Cualquier cosa", "DJ Paco"),
])
def test_se_marcan_como_remix(titulo, artista):
    from radiov.catalog import is_remix

    assert is_remix(titulo, artista) is True, f"no se marco: {titulo} / {artista}"


@pytest.mark.parametrize("titulo,artista", [
    ("Si Antes Te Hubiera Conocido", "KAROL G"),
    ("NUEVAYoL", "Bad Bunny"),
    ("Bohemian Rhapsody", "Queen"),
])
def test_no_se_marcan_las_canciones_normales(titulo, artista):
    from radiov.catalog import is_remix

    assert is_remix(titulo, artista) is False, f"se marco sin serlo: {titulo}"
