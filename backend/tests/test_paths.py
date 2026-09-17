import pytest
from app.paths import resolve_music, resolve_media, media_filename


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
