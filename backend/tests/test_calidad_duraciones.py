"""Qué es cada cosa y qué duración se le permite (radiov/quality.py).

Contexto (18/09/2026): la puerta de calidad tenía UN margen de duración (1:30 – 15:00) con el
comentario «corta mezclas de DJ y ruido». Medido en el servidor: 28 pistas en cuarentena por
duración, y entre ellas una sesión de reggaetón viejo de 22 minutos y varios mashups de 60-90 s
—justo el tipo de música que el usuario escucha—, mientras colaban compilaciones de 5 horas y
tonos de móvil. Miraba CUÁNTO dura en vez de QUÉ es.

Estas pruebas fijan las dos mitades: la clasificación y los márgenes.
"""
import pytest

from radiov.quality import (DUR_MAX, DUR_MIN, clasificar, margenes, revisar,  # noqa: E402
                            ventanas)


# --- 1 · clasificación -------------------------------------------------------------------------

@pytest.mark.parametrize("titulo,artista,duracion,esperado", [
    # Una canción normal no se marca.
    ("Blinding Lights", "The Weeknd", 200, None),
    # Un «feat. DJ …» NO convierte la canción en sesión: era un falso positivo real del catálogo
    # («Basshunter - Now You're Gone (feat. DJ Mental Theo's Bazzheadz)»).
    ("Now You're Gone (feat. DJ Mental Theo's Bazzheadz)", "Basshunter", 130, None),
    # Mashups: la palabra, el cruce «A x B» y el «vs».
    ("Best Mashup Mix", "djpino", 1800, "sesion"),
    ("Shape of You x Despacito", "Mashup Man", 210, "mashup"),
    ("Danza Kuduro vs Danza Kuduro", "Alguien", 180, "mashup"),
    ("Trolls 2 Many Hits Mashup", "Anna Kendrick", 63, "mashup"),
    # Remixes.
    ("Ba Ba Bad Remix", "Kybba", 150, "remix"),
    ("Blinding Lights (Bootleg)", "Alguien", 200, "remix"),
    # Sesiones de DJ: por el título, por el artista o por la duración.
    ("SET DJ YURI PEDRADA - TRAVA CHIP", "dj yuri pedrada", 480, "sesion"),
    ("REGGAETON VIEJO / OLD SCHOOL", "DJ RONALD HESS", 1320, "sesion"),
    ("Party Mix Session 1.5", "AV8", 72, "sesion"),
    ("Mezcla continua de verano", "Alguien", 3000, "sesion"),
    # «Bzrp Music Sessions» son CANCIONES de dos minutos, no sesiones de DJ.
    ("Daddy Yankee: Bzrp Music Sessions, Vol. 0/66", "Bizarrap", 120, None),
])
def test_clasificacion(titulo, artista, duracion, esperado):
    assert clasificar(titulo, artista, duracion) == esperado


# --- 2 · duraciones ----------------------------------------------------------------------------

def test_una_sesion_de_dj_larga_entra():
    """Lo que el usuario escucha: sesiones de 20-60 minutos. Antes no entraban nunca."""
    ok, motivo = revisar({"title": "REGGAETON VIEJO / OLD SCHOOL", "artist": "DJ RONALD HESS",
                          "duration": 1320})
    assert ok, motivo


def test_una_sesion_de_dos_horas_entra():
    ok, _ = revisar({"title": "DJ Set en directo", "artist": "djpino", "duration": 7200})
    assert ok


def test_un_mashup_corto_entra():
    """Un mashup de 63 s no llega al mínimo de canción normal (90 s), pero es un mashup."""
    ok, motivo = revisar({"title": "Trolls 2 Many Hits Mashup", "artist": "Anna Kendrick",
                          "duration": 63})
    assert ok, motivo


def test_una_cancion_corta_sigue_fuera():
    """Sin ser mashup ni mezcla, 40 s es un fragmento."""
    ok, motivo = revisar({"title": "Intro", "artist": "Alguien", "duration": 40})
    assert not ok and "duración" in motivo


@pytest.mark.parametrize("titulo,artista,duracion", [
    ("2024 Top Hits.wav", "2024 Hit Playlist", 17340),          # compilación de 5 horas
    ("EDM Workout Music 2020 Top 100 Hits (2hr DJ Mix)", "Workout Electronica", 6780),
    ("Promiscuous Girl (Remix)", "Ringtone Hits", 63),           # tono de móvil
    ("Teenage Mutant Ninja Turtles Cartoon Opening Theme", "TV Hits", 58),
])
def test_lo_que_no_es_musica_sigue_fuera(titulo, artista, duracion):
    ok, motivo = revisar({"title": titulo, "artist": artista, "duration": duracion})
    assert not ok, f"{titulo} debería quedarse fuera"
    assert "no es música" in motivo or "duración" in motivo


def test_una_compilacion_de_cinco_horas_no_cabe_en_ninguna_ventana():
    ok, _ = revisar({"title": "Grandes éxitos", "artist": "Alguien", "duration": 5 * 3600})
    assert not ok


def test_las_ventanas_son_las_esperadas():
    """Que quede escrito: canción 1:30-15:00 · mezcla 0:45-20:00 · sesión 5:00-3:00:00."""
    assert margenes(None) == (DUR_MIN, DUR_MAX) == (90.0, 900.0)
    assert margenes("sesion") == (300.0, 10800.0)
    assert margenes("remix") == (45.0, 1200.0)
    # Una sesión también tiene que caber como mezcla corta (una mezcla de 72 s es una mezcla).
    assert (45.0, 1200.0) in ventanas("sesion")
    assert (300.0, 10800.0) in ventanas("sesion")
    # Una canción normal sólo tiene su ventana.
    assert ventanas(None) == [(90.0, 900.0)]


def test_el_motivo_dice_de_que_tipo_era():
    """Cuando algo se rechaza, el motivo tiene que decir qué se creía que era: sin eso, no hay
    forma de saber si el fallo fue la duración o la clasificación."""
    ok, motivo = revisar({"title": "Party Mix Session", "artist": "AV8", "duration": 12})
    assert not ok
    assert "[sesion]" in motivo
