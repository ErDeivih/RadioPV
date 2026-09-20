"""La ruta que se manda al servidor tiene que ser RELATIVA a la raíz de música.

EL FALLO QUE FIJA ESTA PRUEBA (20/09/2026)
------------------------------------------
En el PC la ficha guarda la ruta absoluta (`E:\MusicaRadioPV\catalogada\…`) hasta que el organizador
la pasa a relativa, en la fase de mantenimiento de la vuelta. Tres canciones de tech house se
publicaron antes de esa fase y el servidor recibió la ruta absoluta: en la aplicación aparecían y **no
sonaban** (`/music/E:/…` no existe), y su audio se subió con ese nombre, cayendo en
`/music/MusicaRadioPV/…` en vez de en `/music/catalogada/…`.

La regla es UNA (`radiov.config.a_ruta_relativa_musica`) y la usan las dos máquinas: el PC antes de
mandar y el servidor al recibir. Dos copias de la misma regla ya se separaron en este proyecto y el
resultado fue que el panel decía una cosa y la aplicación otra.
"""
from pathlib import Path

from radiov.config import a_ruta_relativa_musica as limpiar


def test_quita_el_prefijo_de_la_raiz():
    raiz = "E:/MusicaRadioPV"
    for entrada in ("E:/MusicaRadioPV/catalogada/DJ/tema.mp3",
                    "E:\\MusicaRadioPV\\catalogada\\DJ\\tema.mp3",
                    "e:/musicaradiopv/catalogada/DJ/tema.mp3"):
        assert limpiar(entrada, raiz) == "catalogada/DJ/tema.mp3", entrada


def test_quita_la_unidad_y_la_carpeta_repetida():
    """Las formas que llegaron de verdad al servidor y rompieron la reproducción."""
    raiz = Path("E:/MusicaRadioPV")
    assert limpiar("MusicaRadioPV/catalogada/DJ/tema.mp3", raiz) == "catalogada/DJ/tema.mp3"
    assert limpiar("/music/catalogada/DJ/tema.mp3", raiz) == "catalogada/DJ/tema.mp3"
    # Sin raíz de la que tirar (el servidor no conoce la letra E: del PC), la parte útil empieza en la
    # carpeta de música conocida.
    assert limpiar("E:/MusicaRadioPV/catalogada/DJ/tema.mp3") == "catalogada/DJ/tema.mp3"
    assert limpiar("MusicaRadioPV/descargas/tema.mp3") == "descargas/tema.mp3"


def test_lo_que_ya_estaba_bien_no_se_toca():
    raiz = Path("E:/MusicaRadioPV")
    assert limpiar("catalogada/DJ/tema.mp3", raiz) == "catalogada/DJ/tema.mp3"
    assert limpiar("descargas/tema.mp3", raiz) == "descargas/tema.mp3"
    assert limpiar("", raiz) == ""
    assert limpiar(None, raiz) == ""
