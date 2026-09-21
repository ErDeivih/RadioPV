"""La fila de «estados de ánimo» de la aplicación sólo puede enseñar estados de ánimo.

EL FALLO REAL (21/09/2026)
--------------------------
`/facets` sacaba los estados de ánimo de la columna `tags`, que **también** lleva la era («20s»), el
idioma («es»), el género de adorno («house») y avisos («sin bpm», «remix»). Medido en el catálogo de
verdad, la lista que llegaba a la aplicación era:

    energia alta, fiesta, trabajo, …, es, 20s, en, house, pop es, sin bpm

Es decir: la pantalla de explorar enseñaba tarjetas llamadas «es», «20s» o «sin bpm». Y además había
una era con el valor vacío, que pintaba una tarjeta **sin nombre**.

Estas pruebas fijan que:
  · sólo salen ánimos de verdad;
  · los valores vacíos no se enseñan;
  · y la lista de ánimos declarada cubre TODO lo que `radiov.catalog.derive_tags` puede producir, para
    que una etiqueta nueva no se cuele (ni se esconda) sin que nadie se entere.
"""
from app.routers.facets import MOODS_VALIDOS, TAGS_QUE_NO_SON_ANIMO, es_animo


def test_los_animos_de_verdad_pasan_y_lo_demas_no():
    for bueno in ("fiesta", "perreo", "chill", "energia alta", "gimnasio", "romantica"):
        assert es_animo(bueno), bueno
    for malo in ("es", "en", "20s", "90s", "vintage", "house", "urbano", "sin bpm", "remix",
                 "pop es", "instrumental", "", None):
        assert not es_animo(malo), f"«{malo}» no es un estado de ánimo"


def test_la_lista_de_animos_cubre_todo_lo_que_genera_el_clasificador():
    """Si alguien añade una etiqueta a `derive_tags`, esta prueba avisa en vez de enseñarla (o perderla)."""
    from radiov.catalog import derive_tags

    producidas = set()
    for bpm in (60, 80, 100, 120, 140, 160, 180, None):
        for energy in (0.1, 0.4, 0.7, None):
            for genre in ("reggaeton", "pop", "metal", "classical", "house", "lofi", "gospel",
                          "banda", "soul", "rock", "other"):
                for language in ("es", "en", "it", "other"):
                    for year in (1975, 1995, 2005, 2020, None):
                        producidas |= set(derive_tags(bpm=bpm, energy=energy, genre=genre,
                                                      year=year, language=language,
                                                      is_remix_flag=True))
    sin_clasificar = producidas - MOODS_VALIDOS - TAGS_QUE_NO_SON_ANIMO
    assert not sin_clasificar, (f"etiquetas nuevas sin clasificar: {sorted(sin_clasificar)} — "
                                f"decide si son estado de ánimo (MOODS_VALIDOS) o no "
                                f"(TAGS_QUE_NO_SON_ANIMO) en backend/app/routers/facets.py")


def test_la_lista_de_animos_no_tiene_basura():
    """Y al revés: nada declarado como ánimo puede ser en realidad un idioma, era o aviso."""
    assert not (MOODS_VALIDOS & TAGS_QUE_NO_SON_ANIMO), MOODS_VALIDOS & TAGS_QUE_NO_SON_ANIMO
    for tag in MOODS_VALIDOS:
        assert tag == tag.strip().lower(), f"«{tag}» tiene que ir en minúsculas y sin espacios"


def test_las_facetas_no_ensenan_valores_vacios(client):
    """/facets es público y lo pinta la aplicación: un valor vacío es una tarjeta sin nombre."""
    r = client.get("/facets")
    assert r.status_code == 200
    datos = r.json()
    for tipo in ("genres", "eras", "languages", "years", "moods"):
        for fila in datos[tipo]:
            assert fila["value"] not in ("", None), f"{tipo} tiene un valor vacío: {fila}"
    for fila in datos["moods"]:
        assert es_animo(fila["value"]), f"«{fila['value']}» no es un estado de ánimo"
