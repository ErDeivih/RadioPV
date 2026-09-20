"""Override curado de géneros: arregla los artistas que Deezer etiqueta mal, sin tocar los reales."""
import sys, os
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "scripts"))
sys.path.insert(0, _ROOT)
from sobreescribir_generos import SOBRESCRIBIR as DEL_SCRIPT  # noqa: E402
from radiov.catalog import SOBRESCRIBIR as DEL_CATALOGO        # noqa: E402


def test_sobrescribir_curado():
    # los obvios mal etiquetados por Deezer -> corregidos
    assert DEL_CATALOGO["metallica"] == "rock"
    assert DEL_CATALOGO["el fary"] == "flamenco"
    assert DEL_CATALOGO["estopa"] == "flamenco"
    assert DEL_CATALOGO["loquillo"] == "rock"
    assert DEL_CATALOGO["camela"] == "flamenco"
    assert DEL_CATALOGO["los chichos"] == "flamenco"
    # los que SÍ son pop no se tocan (no deben estar en el override)
    for pop_artist in ("beyoncé", "david bisbal", "beret", "el sueño de morfeo"):
        assert pop_artist not in DEL_CATALOGO, f"{pop_artist} no debe sobreescribirse"


def test_tech_house_en_el_override():
    """Tech house / techengue / guaracha: el usuario pidió esta música por su nombre."""
    from radiov.catalog import guess_genre

    for artista in ("Pomata", "Mau P", "Andruss", "CASSIMM", "San Pacho", "Mochakk",
                    "HUGEL", "Dennis Cruz", "Cloonee", "Beltran", "Jude Frank", "Tomi DJ"):
        assert DEL_CATALOGO[artista.lower()] == "techhouse", artista
        # y de verdad se aplica al clasificar, no sólo está en la tabla
        assert guess_genre("Drugs From Amsterdam (Extended Mix)", artista) == "techhouse", artista
        # con mayúsculas raras y tildes tampoco puede fallar (la base no escribe siempre igual)
        assert guess_genre("Drugs From Amsterdam", artista.upper()) == "techhouse", artista


def test_el_script_y_el_clasificador_usan_la_misma_tabla():
    """El script de arreglo y el clasificador NO pueden tener tablas distintas.

    Ya pasó: el script tenía su propia copia y se separó de la del clasificador (le faltaban 17
    artistas: Drake, Eminem, Hans Zimmer, Celia Cruz…), así que `--apply` no arreglaba en
    `artists.genre` lo mismo que la aplicación usaba al clasificar y el panel podía mostrar un género
    y la app otro. Ahora el script importa la tabla del clasificador: es el mismo objeto, y eso se
    comprueba aquí para que nadie vuelva a duplicarla.
    """
    assert DEL_SCRIPT is DEL_CATALOGO
