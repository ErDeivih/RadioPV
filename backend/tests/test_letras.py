"""Letras de las canciones (`/tracks/{id}/lyrics`).

El botón de «Letra» de la barra de reproducción abría el **selector de idioma**: prometía una cosa
y hacía otra. Estas pruebas sujetan las dos mitades del arreglo: que el título se limpia antes de
buscar (los títulos del catálogo vienen de YouTube y traen coletillas) y que la respuesta nunca es
un error cuando no hay letra.
"""
import pytest

from app.routers import lyrics as L


@pytest.fixture
def sin_red(monkeypatch):
    """Sustituye la llamada externa y apunta cuántas veces se ha llamado y con qué."""
    llamadas = []

    def falso(artista, titulo, timeout=12):
        llamadas.append((artista, titulo))
        if titulo == "Yellow":
            return "Look at the stars\nlook how they shine for you"
        return None

    monkeypatch.setattr(L, "_pedir_letra", falso)
    L._cache.clear()
    return llamadas


# --- 1 · limpieza de lo que se busca ------------------------------------------------------------

@pytest.mark.parametrize("sucio,limpio", [
    ("Yellow (Official Video)", "Yellow"),
    ("Levitating [HD]", "Levitating"),
    ("DESPECHÁ - Remastered 2021", "DESPECHÁ"),
    ("Song (Audio)", "Song"),
    ("Song (Lyric Video)", "Song"),
    ("Blinding Lights (Official Music Video)", "Blinding Lights"),
    # Un paréntesis que SÍ es parte del nombre no se debe perder del todo: por eso hay un segundo
    # intento sin limpiar (ver `test_segundo_intento_sin_limpiar`).
    ("Yellow", "Yellow"),
])
def test_el_titulo_se_limpia_antes_de_buscar(sucio, limpio):
    assert L.limpiar_titulo(sucio) == limpio


@pytest.mark.parametrize("sucio,limpio", [
    ("Coldplay - Topic", "Coldplay"),
    ("Rosalía feat. Rauw Alejandro", "Rosalía"),
    ("AlguienVEVO", "Alguien"),
])
def test_el_artista_tambien_se_limpia(sucio, limpio):
    assert L.limpiar_artista(sucio) == limpio


# --- 2 · la respuesta ---------------------------------------------------------------------------

def test_devuelve_la_letra(client, sin_red):
    # Una canción cualquiera del catálogo de pruebas, con título sucio como los de verdad.
    from app.database import SessionLocal
    from app import models

    db = SessionLocal()
    t = models.Track(title="Yellow (Official Video)", artist="Coldplay", status="descargada",
                     source="test", file_path="x.mp3", rank=1)
    db.add(t)
    db.commit()
    tid = t.id
    db.close()

    r = client.get(f"/tracks/{tid}/lyrics")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["encontrada"] is True
    assert "shine for you" in cuerpo["letra"]
    assert cuerpo["titulo_buscado"] == "Yellow"
    assert cuerpo["artista_buscado"] == "Coldplay"
    # Y lo que se pidió fuera fue el título limpio, no el de YouTube.
    assert sin_red[0] == ("Coldplay", "Yellow")


def test_sin_letra_no_es_un_error(client, sin_red):
    """La mitad del catálogo no tiene letra en ninguna base: eso se dice, no se falla."""
    from app.database import SessionLocal
    from app import models

    db = SessionLocal()
    t = models.Track(title="Cancion Rarisima De Un Grupo Que No Existe", artist="Nadie",
                     status="descargada", source="test", file_path="y.mp3", rank=1)
    db.add(t)
    db.commit()
    tid = t.id
    db.close()

    r = client.get(f"/tracks/{tid}/lyrics")
    assert r.status_code == 200
    assert r.json()["encontrada"] is False
    assert r.json()["letra"] is None


def test_se_guarda_en_cache(client, sin_red):
    """Las letras no cambian: la segunda visita no puede volver a molestar al servicio externo."""
    from app.database import SessionLocal
    from app import models

    db = SessionLocal()
    t = models.Track(title="Yellow (Official Video)", artist="Coldplay", status="descargada",
                     source="test", file_path="z.mp3", rank=1)
    db.add(t)
    db.commit()
    tid = t.id
    db.close()

    client.get(f"/tracks/{tid}/lyrics")
    llamadas_primera = len(sin_red)
    client.get(f"/tracks/{tid}/lyrics")
    assert len(sin_red) == llamadas_primera, "la segunda vez debería salir de la caché"


def test_una_cancion_que_no_existe_da_404(client):
    assert client.get("/tracks/99999999/lyrics").status_code == 404
