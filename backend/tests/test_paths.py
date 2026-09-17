import unicodedata

import pytest
from app.paths import resolve_music, resolve_media, media_filename

import app.paths as P


def test_absoluta_y_relativa_iguales():
    a = resolve_music(r"E:\Musica\catalogada\A\B\x.mp3")
    b = resolve_music(r"catalogada\A\B\x.mp3")
    assert a == b


def test_traversal_lanza_permission():
    # con el anclaje a MUSIC_ROOT, se necesitan varios '..' para intentar salir de E:\Musica
    with pytest.raises(PermissionError):
        resolve_music(r"E:\..\..\..\..\Windows\x.mp3")


def test_media_filename_solo_nombre():
    assert media_filename(r"F:\...\data\covers\693008911.jpg") == "693008911.jpg"
    assert media_filename(None) is None


def test_resolve_media_dentro_de_raiz():
    p = resolve_media("covers", r"covers\693008911.jpg")
    assert str(p).endswith("693008911.jpg")


# --- Normalización Unicode (NFC / NFD) ---------------------------------------------------------
#
# Los nombres llegan de sitios distintos: de un PC con Windows (NFC) y de Deezer o YouTube (a
# veces NFD: la «n» más una tilde combinante). Se ven idénticos, pero en Linux son cadenas
# distintas, así que el fichero «no existía»: el reproductor devolvía 410 y `verificar_ficheros`
# mandaba la canción a la cola de re-descarga... que volvía a dejar el mismo nombre. Había 17
# canciones así en el catálogo.


@pytest.fixture
def musica(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "MUSIC_ROOT", tmp_path)
    return tmp_path


def test_encuentra_el_fichero_guardado_en_NFC_y_presente_en_NFD(musica):
    carpeta = musica / "catalogada" / "Wisin"
    carpeta.mkdir(parents=True)
    real = carpeta / unicodedata.normalize("NFD", "Mi Niña.mp3")
    real.write_bytes(b"x")

    guardado = "catalogada/Wisin/" + unicodedata.normalize("NFC", "Mi Niña.mp3")
    assert resolve_music(guardado) == real
    assert resolve_music(guardado).exists()


def test_encuentra_el_fichero_guardado_en_NFD_y_presente_en_NFC(musica):
    carpeta = musica / "catalogada" / "Wisin"
    carpeta.mkdir(parents=True)
    real = carpeta / unicodedata.normalize("NFC", "Mi Niña.mp3")
    real.write_bytes(b"x")

    guardado = "catalogada/Wisin/" + unicodedata.normalize("NFD", "Mi Niña.mp3")
    assert resolve_music(guardado) == real


def test_carpeta_en_NFD_y_fichero_en_NFC(musica):
    # Caso mixto: la carpeta la creó el colector en el servidor y el título viene de otra fuente.
    carpeta = musica / "catalogada" / unicodedata.normalize("NFC", "ADÉLA")
    carpeta.mkdir(parents=True)
    real = carpeta / "cancion.mp3"
    real.write_bytes(b"x")

    guardado = "catalogada/" + unicodedata.normalize("NFD", "ADÉLA") + "/cancion.mp3"
    assert resolve_music(guardado) == real


def test_la_ruta_exacta_sigue_ganando(musica):
    carpeta = musica / "catalogada" / "A"
    carpeta.mkdir(parents=True)
    (carpeta / "x.mp3").write_bytes(b"x")
    assert resolve_music("catalogada/A/x.mp3") == (carpeta / "x.mp3").resolve()


def test_si_no_existe_devuelve_la_ruta_canonica(musica):
    # No se inventa nada: se devuelve la ruta de la base, que es la que debe salir en el aviso
    # y la que se marcará como 'perdida'.
    (musica / "catalogada").mkdir(parents=True)
    ruta = resolve_music("catalogada/no/existe.mp3")
    assert not ruta.exists()
    assert ruta.name == "existe.mp3"


def test_normalizar_no_permite_salir_de_la_raiz(musica):
    (musica / "catalogada").mkdir(parents=True)
    for mala in ("../fuera.mp3", "..\\..\\fuera.mp3", "catalogada/../../fuera.mp3"):
        with pytest.raises(PermissionError):
            resolve_music(mala)

