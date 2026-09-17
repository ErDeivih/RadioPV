"""guess_genre/genero_de_album: usa el género del álbum de Deezer (genres.data), fallback 'other',
respeta el override manual. El cliente es falso (sin red)."""
import sys, os
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
from radiov.catalog import guess_genre, genero_de_album  # noqa: E402


class FakeClient:
    def __init__(self, albums):
        self.albums = albums
    def album_detail(self, aid):
        return self.albums.get(str(aid), {})


def test_guess_genre_por_album():
    # álbum cuyo género Deezer es "Metal" -> "rock"
    cli = FakeClient({"1": {"genres": {"data": [{"name": "Metal"}]}}})
    assert genero_de_album("1", cli) == "rock"
    # álbum sin géneros -> 'other' (no inventar, nunca 'pop')
    cli2 = FakeClient({"2": {"genres": {"data": []}}})
    assert genero_de_album("2", cli2) == "other"
    # género desconocido -> 'other'
    cli3 = FakeClient({"3": {"genres": {"data": [{"name": "Symphonic"}]}}})
    assert genero_de_album("3", cli3) == "other"
    # override manual va por encima: "Metallica" -> "rock" aunque el álbum dijera "Pop"
    cli4 = FakeClient({"4": {"genres": {"data": [{"name": "Pop"}]}}})
    assert guess_genre("Some", "Metallica", "4", cli4) == "rock"
    # sin álbum ni override -> 'other'
    assert guess_genre("Cualquiera", "Desconocido") == "other"
