"""Override curado de géneros: arregla los artistas que Deezer etiqueta mal, sin tocar los reales."""
import sys, os
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "scripts"))
from sobreescribir_generos import SOBRESCRIBIR  # noqa: E402


def test_sobrescribir_curado():
    # los obvios mal etiquetados por Deezer -> corregidos
    assert SOBRESCRIBIR["Metallica"] == "rock"
    assert SOBRESCRIBIR["El Fary"] == "flamenco"
    assert SOBRESCRIBIR["Estopa"] == "flamenco"
    assert SOBRESCRIBIR["Loquillo"] == "rock"
    assert SOBRESCRIBIR["Camela"] == "flamenco"
    assert SOBRESCRIBIR["Los Chichos"] == "flamenco"
    # los que SÍ son pop no se tocan (no deben estar en el override)
    for pop_artist in ("Beyoncé", "David Bisbal", "Beret", "El Sueño de Morfeo"):
        assert pop_artist not in SOBRESCRIBIR, f"{pop_artist} no debe sobreescribirse"
