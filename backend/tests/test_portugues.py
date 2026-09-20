"""Portugués: fuera del catálogo, y sin llevarse por delante canciones en español.

La norma es español (España y Latinoamérica), inglés y, de siempre, italiano y francés. El portugués
entraba por YouTube (las búsquedas de sesiones de DJ devuelven funk brasileño) y encima quedaba
etiquetado como español, porque el idioma lo ponía la semilla.

Estas pruebas fijan las dos mitades, porque la mitad importante es la SEGUNDA: un detector que
rechace de más estropea el catálogo tanto como uno que no detecte. Los casos en español de abajo
están sacados del catálogo real.
"""
import pytest

from radiov.quality import parece_portugues, revisar


@pytest.mark.parametrize("titulo,artista", [
    ("Última Saudade (Ao Vivo)", "Henrique & Juliano"),
    ("Ela Vem (SET DJ NENE)", "Mc GP"),
    ("Eu Vou Machucar Só um Pouquinho X Catucando Gostosinho", "JC no beat"),
    ("Ai Que Saudade D'ocê", "Dominguinhos"),
    ("Não Vou Te Deixar", "Sertanejo Top"),
    ("Coração de Pedra", "Pagode do Bom"),
    ("Muito Obrigado, Meu Bem", "Roberto Carlos"),
    # Funk brasileño que se estaba colando en las listas del usuario (medido el 20/09/2026: salían en
    # «Sesiones de DJ» y «Mashups y remixes»). Comprobado contra internet: «SET DJ YURI PEDRADA -
    # TRAVA CHIP» es funk con MC Meno K y MC Ryan SP; Yuri Pedrada es DJ de funk.
    ("SET DJ YURI PEDRADA - TRAVA CHIP", "dj yuri pedrada"),
    ("MOTINHA MIX (Beele, Bing Bong, EoO, Latina Foreva, Baile Inolvidable)", "DJ Renato B"),
    ("Adivinha o quê", "Lulu Santos"),
    ("Recife Minha Cidade", "Reginaldo Rossi"),
    ("Fazendinha Sessions #1", "Fazendinha Sessions"),
])
def test_detecta_portugues(titulo, artista):
    assert parece_portugues(titulo, artista), f"no se detectó portugués en {artista} - {titulo}"


@pytest.mark.parametrize("titulo,artista", [
    # Español de España y de Latinoamérica: nada de esto puede caer.
    ("La Última Vez", "Bad Bunny"),
    ("Yo x Ti, Tu x Mi", "ROSALÍA"),
    ("Cántame una Canción", "Rocío Jurado"),
    ("El Corazón de la Ciudad", "Maná"),
    ("Despacito (Remix)", "Luis Fonsi"),
    ("Himno de la Alegría", "Miguel Ríos"),
    ("Ojos Verdes", "Miguel de Molina"),
    ("Sabor a Mí", "Los Panchos"),
    # Francés e inglés que YA cayeron de verdad en una primera versión del detector (19/09/2026) y
    # que no pueden volver a caer: son las tres trampas que se encontraron contra el catálogo real.
    ("Tout en Gucci", "Ninho"),                       # «Ninho» termina en -inho, pero es un nombre
    ("Lettre à une femme", "Ninho"),
    ("Balek (feat. Aya Nakamura, MC YOSHI, Mauvais Djo)", "TRIANGLE DES BERMUDES"),  # «MC YOSHI»
    ("Here I Am / Small Axe (Come And Take Me)", "UB40"),   # «axe» sin tilde no es el género axé
    ("Tá Bueno", "Un Español Cualquiera"),            # «tá» se escribe igual en español coloquial
    # Las trampas de las marcas nuevas («trava» y el diminutivo femenino «-inha»), medidas contra el
    # catálogo antes de añadirlas: en español «trava» se escribe «traba», y estos títulos son
    # españoles o latinos aunque se parezcan.
    ("El Baile De Los Que Sobran", "Los Prisioneros"),
    ("Amor De Madre", "Denise Rosenthal"),
    ("Amor De Traficantes", "Adriel Favela"),         # «Favela» es su apellido, no una favela
    ("Hoy Daria Yo la Vida", "Martinha"),             # el -inha va en el ARTISTA: no cuenta
])
def test_no_confunde_el_espanol(titulo, artista):
    assert not parece_portugues(titulo, artista), f"se rechazó algo que no es portugués: {artista} - {titulo}"


def test_la_puerta_rechaza_portugues():
    ok, motivo = revisar({"title": "Última Saudade (Ao Vivo)", "artist": "Henrique & Juliano",
                          "duration": 240})
    assert not ok
    assert "portugu" in motivo.lower()


def test_la_puerta_sigue_aceptando_espanol_e_ingles():
    for rec in (
        {"title": "La Última Vez", "artist": "Bad Bunny", "duration": 240},
        {"title": "Shape of You", "artist": "Ed Sheeran", "duration": 233},
        {"title": "Ti Amo", "artist": "Umberto Tozzi", "duration": 250},
        {"title": "La Vie en Rose", "artist": "Édith Piaf", "duration": 200},
    ):
        ok, motivo = revisar(rec)
        assert ok, f"se rechazó {rec['artist']} - {rec['title']}: {motivo}"


def test_las_sesiones_y_mashups_siguen_entrando():
    """El filtro de portugués no puede comerse justo lo que el usuario más escucha.

    OJO: aquí estaba «SET DJ YURI PEDRADA - TRAVA CHIP» como ejemplo de sesión que debía ENTRAR, y
    era un error de la prueba: esa pista es funk brasileño de verdad (con MC Meno K, MC Ryan SP…).
    Ahora está en la lista de las que se detectan. Los ejemplos de abajo son sesiones y mashups que
    sí son español o inglés.
    """
    for rec in (
        {"title": "ENGANCHADO DE REGGAETON VIEJO (MIX - TOMI DJ)", "artist": "TOMI DJ", "duration": 1500},
        {"title": "Stayin Alive x In Da Club (Mashup)", "artist": "Antifarox", "duration": 180},
        {"title": "Party Mix Session 3.2", "artist": "AV8", "duration": 190},
        {"title": "Yo x Ti, Tu x Mi (Remix)", "artist": "ROSALÍA", "duration": 200},
        {"title": "MIX POP EN ESPAÑOL 90's 2000's", "artist": "DJ PIWI / DISCOLOCA", "duration": 2300},
    ):
        ok, motivo = revisar(rec)
        assert ok, f"se rechazó {rec['artist']} - {rec['title']}: {motivo}"
