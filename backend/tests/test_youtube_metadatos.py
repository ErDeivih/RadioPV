"""El año y la carátula de una canción de YouTube salen del propio vídeo.

FALLO REAL (19/09/2026)
-----------------------
La puerta de metadatos exige año, género, idioma, BPM, energía, ganancia, duración y carátula para
publicar una canción. Para el contenido que **sólo existe en YouTube** —mashups, remixes caseros,
sesiones de DJ, justo lo que el usuario pidió ampliar— no había de dónde sacar el año ni la
carátula: Deezer no tiene ficha de esas canciones. Resultado medido en el PC:

    aviso: 15 descargadas aún sin completar; se mandarán cuando lo estén

Y ahí se quedaban: bajaban, se analizaban… y no llegaban NUNCA a la aplicación. Entre ellas, la
sesión de DJ de 36 minutos que el usuario había pedido a mano desde la página de pedir canciones.

Ahora `youtube._download_by_id` devuelve el **año de subida** del vídeo y su **miniatura**, y el
pipeline los guarda. Son datos reales de la fuente, no inventados.
"""
import pytest

from radiov import youtube


@pytest.mark.parametrize("info,esperado", [
    ({"upload_date": "20250714"}, 2025),
    ({"upload_date": "19991231"}, 1999),
    ({"upload_date": "2025"}, 2025),                 # sólo el año
    ({"release_date": "20240102"}, 2024),            # sin upload_date
    ({"modified_date": "20220304"}, 2022),
    ({}, None),                                       # no se inventa nada
    ({"upload_date": "no-es-una-fecha"}, None),
])
def test_el_ano_sale_de_la_fecha_del_video(info, esperado):
    assert youtube._ano_de_upload(info) == esperado


def test_la_caratula_es_la_miniatura_mas_grande():
    info = {"thumbnails": [
        {"url": "https://x/pequena.jpg", "width": 120, "height": 90},
        {"url": "https://x/grande.jpg", "width": 1280, "height": 720},
        {"url": "https://x/mediana.jpg", "width": 480, "height": 360},
    ]}
    assert youtube._mejor_miniatura(info) == "https://x/grande.jpg"


def test_se_descartan_las_miniaturas_webp():
    """Las webp no las lee el servidor de carátulas: se coge la siguiente."""
    info = {"thumbnails": [
        {"url": "https://x/grande.webp", "width": 1280, "height": 720},
        {"url": "https://x/buena.jpg", "width": 480, "height": 360},
    ]}
    assert youtube._mejor_miniatura(info) == "https://x/buena.jpg"


def test_sin_lista_de_miniaturas_se_usa_la_principal():
    assert youtube._mejor_miniatura({"thumbnail": "https://x/u.jpg"}) == "https://x/u.jpg"


def test_en_ultimo_termino_se_deduce_la_url_de_la_miniatura():
    """YouTube sirve la miniatura en una URL predecible a partir del id: no hace falta preguntar."""
    assert youtube._mejor_miniatura({"id": "ABC123"}) == "https://i.ytimg.com/vi/ABC123/hqdefault.jpg"
    assert youtube._mejor_miniatura({}) is None


def test_el_ano_no_puede_bloquear_para_siempre_a_lo_que_solo_existe_en_youtube():
    """Una canción bajada de YouTube sin año tiene que poder publicarse igual.

    Deezer no tiene ficha de un mashup casero ni de una sesión de DJ: no hay año que poner. Con la
    regla estricta se quedaban en «incompleta» de por vida y no llegaban NUNCA a la aplicación.

    Se comprueba el COMPORTAMIENTO (la regla de qué es obligatorio), no el texto del código: antes
    esta prueba buscaba `'k != "year"'` dentro de `_persist_yt` con `inspect.getsource`, así que
    reescribir la misma regla en otro sitio la hacía fallar sin que nada estuviera roto… y al revés:
    podía pasar con el código cambiado de forma que la regla ya no se aplicara.
    """
    from radiov.catalog import campos_que_faltan

    # De un vídeo: el año no bloquea (la carátula sí se espera: el vídeo la trae).
    faltan = campos_que_faltan({"youtube_id": "VIDEO123", "cover_url": "https://i.ytimg.com/x.jpg"})
    assert "year" not in faltan
    # Y la regla se aplica de verdad en la puerta de entrada y en el republicador.
    import inspect

    from radiov import pipeline
    from radiov import catalog as C

    assert "campos_que_faltan" in inspect.getsource(pipeline._persist_yt)
    assert "campos_que_faltan" in inspect.getsource(C.republicar_completas)
